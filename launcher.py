"""KnowSubtle Learning Universe - Windows 启动器（PyInstaller 入口 → KnowSubtle.exe）

职责：
1. 设置 metagpt / LLM 运行环境变量（兼容 local_metagpt stub 打桩）
2. 启动 FastAPI 本地服务（uvicorn），并做端口冲突 / 单实例 / 就绪检测
3. 默认用【PyQt6 原生桌面窗口】（内嵌自带的 Chromium/QWebEngine）承载仪表盘，
   这是一个真正的桌面程序（系统标题栏、任务栏、可最小化/最大化/关闭），不再打开浏览器；
   PyQt6 自带内核、不依赖系统 WebView2，规避此前 WebView2 黑屏问题。
   仅当 PyQt6 不可用、或设置 KS_FORCE_BROWSER=1 时回退到浏览器 / opt-in 原生 WebView。

关键设计（2026-07-15 修复黑屏后 "无法访问"）：
- 服务运行在【独立受控线程】，进程生消亡不再绑定 WebView 窗口。
  旧实现把服务放在 daemon 线程、主线程被 webview.start() 阻塞，一旦窗口关闭
  （或黑屏看门狗销毁黑窗）主线程返回 → 进程退出 → 守护线程里的服务被一并杀死，
  浏览器回退标签页随即 "无法访问"。新实现用 stop_event 显式控制服务生命周期。
- 回退路径（无 WebView2 / 黑屏看退浏览器）改用一个常驻的轻量控制窗口（tkinter）
  保活：进程持续运行、服务可用，用户点 "退出应用" 才干净收尾。
- 单实例由 PID 锁文件判定，不再用 "端口返回 200 就当已有实例" 的激进探测
  （那会在 8753 被任意程序占用时误杀启动）。
打包后路径由 app.py 内部的 _resolve_* 系列函数自动适配。
"""
import os
import sys
import json
import subprocess
import time
import socket
import threading
import atexit
import webbrowser
import urllib.request
from pathlib import Path

ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

# 在导入 metagpt / app 之前设置运行环境变量（local_metagpt stub 依赖）
os.environ.setdefault("METAGPT_PROJECT_ROOT", str(ROOT))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")
os.environ.setdefault("OPENAI_API_MODEL", "gpt-4o-mini")
os.environ.setdefault("DISABLE_LLM_PROVIDER_CHECK", "true")

# 打包模式（--windowed）下 stdout/stderr 无处可去，重定向到用户目录日志
if getattr(sys, "frozen", False):
    try:
        _log_dir = Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle" / "Logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
        sys.stdout = open(_log_dir / "stdout.log", "a", buffering=1, errors="replace")
        sys.stderr = open(_log_dir / "stderr.log", "a", buffering=1, errors="replace")
    except Exception:
        # AppData 不可写等情况：日志重定向失败不应阻断程序（windowed 下 stdout 本就无去处）
        pass


# 服务生命周期由该事件控制：置位 → uvicorn 退出 → 进程退出
stop_event = threading.Event()

# 记录服务线程中的致命异常（供 main 在 failed 路径展示给用户）
_server_error = None


def _log(msg: str):
    try:
        print(f"[launcher] {msg}", flush=True)
    except Exception:
        pass


# 当前生效的渲染模式（含 Chromium flags），供 _write_diagnose 与启动日志使用；
# 在 _open_pyqt_window 选定渲染模式后赋值，早期错误时为空属正常。
_RENDER_MODE_INFO = ""
# 请求重启标志：托盘菜单切换渲染模式并选择「立即重启」后置 True，
# _open_pyqt_window 在 app.exec() 返回后据此返回 "restart"，由 main 重启进程。
_PENDING_RESTART = False

# 渲染模式持久化偏好：托盘菜单切换后写入，下次启动读取并应用
_RENDER_PREFS = {"balance": "平衡模式", "gpu": "全GPU合成", "software": "全软件渲染"}


def _render_pref_path() -> Path:
    return Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle" / "render_mode.txt"


def _load_render_mode_pref():
    """读取已保存的渲染模式偏好，返回 'balance'/'gpu'/'software' 或 None。"""
    try:
        p = _render_pref_path()
        if p.exists():
            v = p.read_text(encoding="utf-8").strip().lower()
            if v in _RENDER_PREFS:
                return v
    except Exception:
        pass
    return None


def _save_render_mode_pref(mode: str):
    """持久化渲染模式偏好到 render_mode.txt（下次启动生效）。"""
    try:
        p = _render_pref_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(mode, encoding="utf-8")
    except Exception as e:
        _log(f"保存渲染模式偏好失败: {type(e).__name__}: {e}")


def _find_free_port(preferred: int, host: str = "127.0.0.1", span: int = 100) -> int:
    """从 preferred 起向上探测第一个可绑定的端口，避免端口被占用直接崩溃。"""
    for p in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return preferred  # 都满了，交回给 uvicorn 报错


def _is_server_up(url: str, timeout: float = 60.0) -> bool:
    """轮询直到服务返回 200，替代盲目的固定 sleep。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _probe_url(url: str, timeout: float = 1.0) -> bool:
    """一次性的快速探测，用于判断「旧实例」是否真在服务（区分存活实例与僵尸进程）。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    """跨平台判断进程是否存活（Windows 下 os.kill(pid,0) 用于探活）。"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except Exception:
        return True
    return True


def _acquire_instance_lock(port: int):
    """基于 PID 锁文件的单实例判定（带僵尸实例识别）。

    返回 (acquired, existing_url)：
    - 若已有【存活且真正在服务】的实例 → 返回 (False, 它的 url)，调用方打开并退出；
    - 若旧实例进程在、但端口无响应（僵尸）→ 杀掉它、清锁，返回 (True, None) 让自己启动；
    - 其余（无锁 / 锁损坏 / 不可写）→ 写入自己的锁，返回 (True, None)。
    """
    try:
        lock_dir = Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock = lock_dir / "run.lock"
        if lock.exists():
            try:
                data = json.loads(lock.read_text(encoding="utf-8"))
                old_pid = int(data.get("pid", 0))
                old_port = int(data.get("port", port))
                old_url = str(data.get("url", f"http://127.0.0.1:{old_port}/"))
                if _pid_alive(old_pid):
                    # 区分「真在服务的实例」与「僵尸进程」：探测端口是否响应
                    if _probe_url(old_url):
                        return False, old_url
                    # 僵尸：进程在但服务无响应，强制结束并接管
                    _log(f"检测到僵尸旧实例 (pid={old_pid})：进程存活但端口无响应，尝试结束以接管。")
                    try:
                        os.kill(old_pid, 9)
                    except Exception:
                        pass
                    try:
                        lock.unlink()
                    except Exception:
                        pass
            except Exception:
                pass
        lock.write_text(
            json.dumps({"pid": os.getpid(), "port": port, "url": f"http://127.0.0.1:{port}/"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return True, None
    except Exception:
        # 锁文件不可写不应阻断启动
        return True, None


def _release_instance_lock():
    try:
        lock = Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle" / "run.lock"
        if lock.exists():
            lock.unlink()
    except Exception:
        pass


def _record_url(url: str):
    """把本次实际服务的 URL 记到文件，方便排查（用户也可直接打开）。"""
    try:
        p = Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle" / "last_url.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(url, encoding="utf-8")
    except Exception:
        pass


def _write_diagnose(title: str, detail: str):
    """把启动诊断落地成文件，便于用户零成本回传（无需打字描述）。

    同时写到 %APPDATA%/KnowSubtle/diagnose.txt 与桌面 diagnose.txt，
    并在错误框中提示路径，用户把文件发回即可精准定位。
    """
    try:
        appdata = Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle"
        desktop = Path.home() / "Desktop"
        last_url = ""
        try:
            last_url = (appdata / "last_url.txt").read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            pass
        db_path = os.environ.get("LAS_DB_PATH") or str(appdata / "Data" / "knowsubtle.db")
        lines = [
            "=== KnowSubtle 启动诊断 (diagnose) ===",
            f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"exe 路径: {sys.executable}",
            f"标题: {title}",
            f"详情: {detail}",
            f"服务线程错误(_server_error): {_server_error}",
            f"本应监听 URL (last_url.txt): {last_url}",
            f"推断数据库路径: {db_path}",
            f"渲染模式: {_RENDER_MODE_INFO}",
            f"APPDATA: {os.environ.get('APPDATA')}",
        ]
        text = "\n".join(lines)
        for d in (appdata, desktop):
            try:
                d.mkdir(parents=True, exist_ok=True)
                (d / "diagnose.txt").write_text(text, encoding="utf-8")
            except Exception:
                pass
    except Exception:
        pass


def _webview2_available() -> bool:
    """检测系统是否安装 Microsoft Edge WebView2 Runtime。
    未安装时 pywebview 会创建出黑窗或抛错，这里提前识别并改用浏览器，避免沉默黑屏。"""
    try:
        import winreg  # type: ignore
    except Exception:
        return True  # 非 Windows 或无法检测：交给 pywebview 自行处理
    _guid = "{F3017226-FE2A-4295-8BDF-00C3A9A08C11}"  # EdgeWebView 客户端 GUID
    for root, sub in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\\" + _guid),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\\" + _guid),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\\" + _guid),
    ):
        try:
            with winreg.OpenKey(root, sub) as k:  # noqa: F841
                return True
        except OSError:
            continue
    return False


def _start_server(app, host: str, port: int):
    """在独立线程中运行 uvicorn；stop_event 置位时优雅退出。

    增强健壮性：若 uvicorn 因异常退出（而非用户主动停止 stop_event 置位），
    则等待 3 秒后自动重建并重启，避免单次崩溃导致整个应用不可用。
    用户通过托盘退出时 stop_event 置位，循环正常 break，不重启。
    """
    import uvicorn
    import traceback

    global _server_error
    _consecutive_failures = 0

    while not stop_event.is_set():
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)

        def _watch_stop(srv):
            while not stop_event.is_set():
                time.sleep(0.5)
            srv.should_exit = True

        threading.Thread(target=_watch_stop, args=(server,), daemon=True).start()
        try:
            server.run()
        except Exception as e:  # 服务线程异常：记录并暴露给 main，避免静默死亡导致连接被拒
            _server_error = f"{type(e).__name__}: {e}"
            _log(f"服务线程异常: {_server_error}")
            traceback.print_exc()
            _write_diagnose("服务线程异常", _server_error)
        # server.run() 返回
        if stop_event.is_set():
            break
        # 非主动停止 → 视为崩溃，自动重启
        _consecutive_failures += 1
        _log(f"检测到服务异常退出（第 {_consecutive_failures} 次），3 秒后自动重启…")
        _write_diagnose(
            "服务异常退出自动重启",
            f"uvicorn 退出但未收到停止指令（连续第 {_consecutive_failures} 次），将自动重启。",
        )
        try:
            time.sleep(3)
        except Exception:
            pass


def _resolve_app_icon():
    """从可执行文件目录向上查找程序图标（与 app.py 的 _find_up 思路一致）。"""
    try:
        base = Path(sys.executable).parent
        for _ in range(6):
            cand = base / "程序图标.ico"
            if cand.exists():
                return cand
            for sub in ("Resources", "Resources/html", "Install"):
                c2 = base / sub / "程序图标.ico"
                if c2.exists():
                    return c2
            parent = base.parent
            if parent == base:
                break
            base = parent
    except Exception:
        pass
    return None


def _detect_gpu_tier() -> str:
    """粗略探测显卡档位，用于首启引导「推荐」默认（非精确指纹，仅供参考）。

    返回：
      - 'intel'    ：Intel 集成显卡（历史上易与 DWM 冲突闪屏，推荐平衡模式）
      - 'discrete' ：独显（NVIDIA/AMD/Intel Arc 等，倾向推荐全 GPU 合成）
      - 'unknown'  ：探测失败 / 非 Windows / 无明确特征
    失败一律返回 'unknown'，不影响引导正常弹出。
    """
    try:
        if sys.platform.startswith("win"):
            _out = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            if "intel" in _out:
                # Intel Arc 是独显（命名含 'arc'），其余 Intel 多为集成显卡
                return "discrete" if "arc" in _out else "intel"
            if any(_k in _out for _k in ("nvidia", "geforce", "rtx", "radeon", "amd", "arc")):
                return "discrete"
    except Exception:
        pass
    return "unknown"


def _first_launch_render_guide(app) -> str:
    """首次启动引导：让用户选择渲染模式，降低发现成本（而非藏在托盘右键）。

    返回用户选择的模式键 ('balance'/'gpu'/'software')；点击「稍后再说」、取消或关闭时返回
    'skip'（调用方不写入偏好，下次启动仍引导）。纯 Qt 控件、无需 QWebEngine，可在平衡模式下安全弹出。
    """
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QButtonGroup, QRadioButton,
        QDialogButtonBox, QFrame,
    )
    from PyQt6.QtCore import Qt

    dlg = QDialog()
    dlg.setWindowTitle("欢迎使用 KnowSubtle")
    dlg.setMinimumWidth(480)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(12)

    title = QLabel("选择渲染模式")
    title.setStyleSheet("font:700 17px 'Microsoft YaHei'; color:#E6E6F0;")
    layout.addWidget(title)

    sub = QLabel(
        "为获得最佳体验，请选择适合你电脑显卡的渲染模式。\n"
        "选择后可在系统托盘右键「渲染模式」随时切换；也可选「稍后再说」，下次启动再引导。"
    )
    sub.setStyleSheet("color:#9AA0B5; font:12px 'Microsoft YaHei';")
    sub.setWordWrap(True)
    layout.addWidget(sub)

    # 按机器显卡「指纹」推荐默认档位：独显倾向全 GPU 合成，Intel 集成/未知默认平衡
    _gpu_tier = _detect_gpu_tier()
    _recommend_key = "gpu" if _gpu_tier in ("discrete", "unknown") else "balance"
    _tier_hint = {
        "intel": "检测到 Intel 集成显卡，已默认「平衡模式」（不闪兜底）；如你的机器不闪屏，可在托盘切换到「全 GPU 合成」获得最丝滑滚动。",
        "discrete": "检测到独立显卡，已默认推荐「全 GPU 合成」获得最丝滑滚动。",
        "unknown": "未能识别显卡型号，已默认推荐「全 GPU 合成」（现代合成器已修复闪屏）；如首次出现闪屏请在托盘切回「平衡模式」。",
    }.get(_gpu_tier, "")

    opts = [
        ("balance", "平衡模式（不闪兜底）",
         "GPU 光栅 + CPU 合成，绝对不闪，滚动流畅，适合易闪屏的集成显卡。"),
        ("gpu", "全 GPU 合成（最丝滑 · 推荐）",
         "GPU 光栅 + GPU 合成，滚动最丝滑；现代合成器已修复闪屏，绝大多数机器可用。"),
        ("software", "全软件渲染（最稳 · 最卡）",
         "完全不依赖显卡，最稳定但最卡，仅作极端兜底。"),
    ]
    group = QButtonGroup(dlg)
    for i, (key, t, d) in enumerate(opts):
        _title = (f"{t}  ★推荐" if key == _recommend_key else t)
        rb = QRadioButton()
        rb.setText(f"<b>{_title}</b><br><span style='color:#8A90A6;'>{d}</span>")
        rb.setStyleSheet("font:12px 'Microsoft YaHei'; padding:5px;")
        group.addButton(rb, i)
        if key == _recommend_key:
            rb.setChecked(True)
        layout.addWidget(rb)

    if _tier_hint:
        _hint = QLabel(_tier_hint)
        _hint.setStyleSheet("color:#7FB0FF; font:11px 'Microsoft YaHei';")
        _hint.setWordWrap(True)
        layout.addWidget(_hint)

    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color:#2A2636;")
    layout.addWidget(line)

    bbox = QDialogButtonBox()
    btn_later = bbox.addButton("稍后再说", QDialogButtonBox.ButtonRole.RejectRole)
    btn_ok = bbox.addButton("开始使用", QDialogButtonBox.ButtonRole.AcceptRole)
    btn_ok.clicked.connect(dlg.accept)
    btn_later.clicked.connect(dlg.reject)
    layout.addWidget(bbox)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        idx = group.checkedId()
        if 0 <= idx < len(opts):
            return opts[idx][0]
    # 稍后再说 / 取消 / 关闭：不写入偏好，下次启动仍弹出引导
    return "skip"


def _open_diagnose_dialog(app, port: int) -> None:
    """一键诊断面板：列出当前渲染 flags、Web 缓存、后端健康与运行时信息。

    纯 Qt 控件，随时可点；信息为点击时实时探测，便于排查卡顿/白屏/闪屏。
    """
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QTextEdit, QDialogButtonBox, QMessageBox,
    )
    from PyQt6.QtCore import Qt
    from datetime import datetime

    dlg = QDialog()
    dlg.setWindowTitle("KnowSubtle 诊断信息")
    dlg.setMinimumWidth(580)
    dlg.setMinimumHeight(380)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(18, 16, 18, 14)
    layout.setSpacing(10)

    edit = QTextEdit()
    edit.setReadOnly(True)
    edit.setStyleSheet(
        "font:12px 'Consolas','Microsoft YaHei'; background:#15131F; color:#C8CFE0; border:none;"
    )
    layout.addWidget(edit)

    status = QLabel("")
    status.setStyleSheet("color:#7FB0FF; font:11px 'Microsoft YaHei';")
    layout.addWidget(status)

    bbox = QDialogButtonBox()
    btn_copy = bbox.addButton("复制全部", QDialogButtonBox.ButtonRole.ActionRole)
    btn_close = bbox.addButton("关闭", QDialogButtonBox.ButtonRole.AcceptRole)
    btn_close.clicked.connect(dlg.accept)
    layout.addWidget(bbox)

    # ---- 渲染 ----
    _info = _RENDER_MODE_INFO or ""
    _mode_name = _info.split(" | ", 1)[0] if _info else "未知（极早期/无头？）"
    _flags = _info.split("flags=", 1)[1] if "flags=" in _info else "(无)"
    _lines = ["【渲染模式】", f"  当前档位 : {_mode_name}", f"  Chromium flags : {_flags}",
              f"  持久化偏好 : {_render_pref_path()}"]

    # ---- Web 缓存 ----
    _lines += ["", "【Web 缓存】"]
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        _p = QWebEngineProfile.defaultProfile()
        _ct = {0: "无缓存", 1: "内存缓存", 2: "磁盘缓存"}.get(
            int(_p.httpCacheType()), str(_p.httpCacheType()))
        _lines.append(f"  缓存类型 : {_ct}")
        _lines.append(f"  容量上限 : {_p.httpCacheMaximumSize() // (1024 * 1024)} MB")
        _lines.append(f"  缓存路径 : {_p.cachePath() or '(默认)'}")
    except Exception as e:
        _lines.append(f"  缓存信息获取失败: {type(e).__name__}: {e}")

    # ---- 后端健康 ----
    _lines += ["", "【本地后端】"]
    _health_url = f"http://127.0.0.1:{port}/api/health"
    _up = _probe_url(_health_url, timeout=1.0)
    _lines.append(f"  健康检查 {_health_url} : {'正常 ✅' if _up else '异常 ❌'}")
    _lines.append(f"  服务端口 : {port}")

    # ---- 运行时 ----
    _lines += ["", "【运行时】"]
    _lines.append(f"  Headless : {bool(os.environ.get('WC_HEADLESS'))}")
    _lines.append(f"  Python   : {sys.executable}")
    _lines.append(f"  PID      : {os.getpid()}")

    _text = "\n".join(_lines)

    # 自动落盘到 %APPDATA%/KnowSubtle/diagnose.txt，便于直接发送排查
    try:
        _dp = Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle" / "diagnose.txt"
        _dp.parent.mkdir(parents=True, exist_ok=True)
        _dp.write_text(
            "KnowSubtle 诊断信息（生成于 "
            + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "）\n\n" + _text,
            encoding="utf-8",
        )
        status.setText(f"已自动保存到：{_dp}")
    except Exception as e:
        status.setText(f"保存失败：{type(e).__name__}: {e}")

    edit.setPlainText(_text)

    def _copy_all():
        try:
            app.clipboard().setText(_text)
            QMessageBox.information(dlg, "已复制", "诊断信息已复制到剪贴板。")
        except Exception as e:
            QMessageBox.warning(dlg, "复制失败", f"{type(e).__name__}: {e}")

    btn_copy.clicked.connect(lambda checked=False: _copy_all())

    dlg.exec()


def _open_pyqt_window(port: int) -> str:
    """用 PyQt6 原生桌面窗口（内嵌 Chromium/QWebEngine）承载仪表盘。

    真正的桌面程序（系统任务栏、可最小化/最大化/关闭），不再打开浏览器。
    内置增强：
      - 自定义深色标题栏（可拖拽 / 双击最大化 / 最小化·最大化·关闭按钮），与仪表盘主题统一；
        说明：刻意不用真·毛玻璃（WA_TranslucentBackground + DWM blur），因其可能复现 Intel 集显闪屏，
        防闪优先，故标题栏用纯深色填充。
      - 系统托盘常驻：关闭/最小化默认缩到托盘防误关，双击托盘图标恢复；
        托盘不可用时回退为正常任务栏最小化 + 关闭退出（KS_QUIT_ON_CLOSE=1 强制真正退出）。
      - 启动 splash + 加载进度：页面加载期间覆盖层显示百分比，避免深色背景被误认为卡死。
      - 窗口位置/大小记忆：QSettings 持久化，下次启动自动还原。
    """
    url = f"http://127.0.0.1:{port}/"
    if not _is_server_up(url):
        _log("服务启动超时，未能打开界面。")
        _write_diagnose("服务启动超时", f"url={url}, error={_server_error}")
        return "failed"

    try:
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QLabel, QHBoxLayout,
            QVBoxLayout, QPushButton, QSystemTrayIcon, QMenu, QMessageBox,
        )
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import QUrl, Qt, QSettings, QEvent, QTimer, QPoint
        from PyQt6.QtGui import QIcon, QColor, QAction
    except Exception as e:
        _log(f"PyQt6 不可用，回退到浏览器: {type(e).__name__}: {e}")
        return "pyqt-unavailable"

    # 关闭 QtWebEngine 子进程沙箱：规避部分受限/权限环境下的启动失败
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

    # ===== 防闪屏加固（同上轮，未动）=====
    try:
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    # 渲染模式（稳定优先；流畅/兜底）：
    #  - 默认「平衡模式」：GPU 光栅 + CPU 合成（关闭 GPU 合成层）。Intel 集显上 GPU 合成层
    #    会与 Windows DWM 双缓冲冲突导致闪烁/不稳定，关闭 GPU 合成即可根除闪屏；
    #    同时保留 GPU 光栅化保住大部分滚动流畅度（配合前端合成层提升进一步抗卡顿）。
    #  - KS_GPU_COMPOSITING=1 ：全 GPU 合成（光栅+合成均走 GPU，滚动最丝滑），
    #    仅在你的机器不闪时启用；集显上仍可能闪烁。
    #  - KS_SOFTWARE_RENDER=1 ：全软件渲染，最稳但最卡，最后兜底。
    #  - KS_BALANCE=1 ：显式平衡模式（与默认一致，保留以兼容旧开关）。
    # 持久化渲染偏好：命令行环境变量优先；未显式指定时应用托盘菜单已保存的选择
    _pref = _load_render_mode_pref()
    if _pref == "gpu" and not os.environ.get("KS_GPU_COMPOSITING"):
        os.environ["KS_GPU_COMPOSITING"] = "1"
    elif _pref == "software" and not os.environ.get("KS_SOFTWARE_RENDER"):
        os.environ["KS_SOFTWARE_RENDER"] = "1"
    # _pref == "balance" 或 None → 走默认平衡模式（不设变量，与程序默认一致）
    if os.environ.get("KS_SOFTWARE_RENDER"):
        _mode_name = "全软件渲染(SOFTWARE_RENDER)"
        _chromium_flags = (
            "--disable-gpu --disable-gpu-compositing --enable-software-compositing"
        )
    elif os.environ.get("KS_GPU_COMPOSITING"):
        # 显式全 GPU 合成：最丝滑滚动。现代 Viz 合成器（不再禁用 VizDisplayCompositor）
        # 与 Windows DWM 正常同步，已根除旧版集显闪屏；仅极个别老旧驱动仍可能闪。
        _mode_name = "全GPU合成(GPU_COMPOSITING)"
        _chromium_flags = (
            "--enable-gpu-rasterization --enable-gpu-compositing"
        )
    elif os.environ.get("KS_BALANCE"):
        # 显式平衡模式（与默认一致，保留以兼容旧开关）
        _mode_name = "平衡模式(BALANCE)"
        _chromium_flags = (
            "--enable-gpu-rasterization --disable-gpu-compositing"
        )
    else:
        # 默认：平衡模式（GPU 光栅 + CPU 合成），规避集显 GPU 合成闪屏
        _mode_name = "平衡模式(默认)"
        _chromium_flags = (
            "--enable-gpu-rasterization --disable-gpu-compositing"
        )
    # 通用增强 flags（各模式共用，不重新引入闪屏）：
    #  - 平滑滚动、关闭后台计时器/渲染进程/Occluded 窗口节流 → 滚动跟手、遮挡恢复不卡顿；
    #  - 关闭 IPC 洪泛保护 → 长文本/大列表渲染更跟手。
    # 注：各模式均已改用现代 VizDisplayCompositor（不再 --disable-features=VizDisplayCompositor），
    #     这是默认 Chrome 的合成器；GPU 合成下既丝滑又不会与 Windows DWM 冲突闪屏。
    _COMMON_FLAGS = (
        " --enable-smooth-scrolling"
        " --disable-background-timer-throttling"
        " --disable-renderer-backgrounding"
        " --disable-backgrounding-occluded-windows"
        " --disable-ipc-flooding-protection"
    )
    _chromium_flags = (_chromium_flags + _COMMON_FLAGS).strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _chromium_flags
    global _RENDER_MODE_INFO
    _RENDER_MODE_INFO = f"{_mode_name} | flags={_chromium_flags}"
    _log(f"渲染模式: {_RENDER_MODE_INFO}")

    _UI_BG = "#120F17"
    _UI_BAR = "#1A1722"
    _settings = QSettings("KnowSubtle", "Launcher")

    class _TitleBar(QWidget):
        def __init__(self, window):
            super().__init__(window)
            self._window = window
            self._drag_pos = None
            self.setFixedHeight(38)
            self.setStyleSheet(f"background:{_UI_BAR};")
            layout = QHBoxLayout(self)
            layout.setContentsMargins(12, 0, 8, 0)
            layout.setSpacing(4)
            title = QLabel("KnowSubtle 学习宇宙")
            title.setStyleSheet("color:#E6E6F0; font:600 13px 'Microsoft YaHei';")
            layout.addWidget(title)
            layout.addStretch(1)
            self._min = QPushButton("—")
            self._max = QPushButton("▢")
            self._close = QPushButton("✕")
            self._min.setFixedSize(34, 26)
            self._max.setFixedSize(34, 26)
            self._close.setFixedSize(34, 26)
            btn_style = (
                f"QPushButton{{background:{_UI_BAR};color:#C8C8D4;border:none;font-size:14px;}}"
                f"QPushButton:hover{{background:#2A2636;}}"
            )
            for b in (self._min, self._max, self._close):
                b.setStyleSheet(btn_style)
            self._min.clicked.connect(self._on_min)
            self._max.clicked.connect(self._on_max)
            self._close.clicked.connect(self._window.close)
            layout.addWidget(self._min)
            layout.addWidget(self._max)
            layout.addWidget(self._close)

        def _on_min(self):
            if self._window._tray_ok:
                self._window.hide()
            else:
                self._window.showMinimized()

        def _on_max(self):
            if self._window.isMaximized():
                self._window.showNormal()
            else:
                self._window.showMaximized()

        def mousePressEvent(self, ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = ev.globalPosition().toPoint()
            super().mousePressEvent(ev)

        def mouseMoveEvent(self, ev):
            if self._drag_pos is not None and (ev.buttons() & Qt.MouseButton.LeftButton):
                delta = ev.globalPosition().toPoint() - self._drag_pos
                self._window.move(self._window.pos() + delta)
                self._drag_pos = ev.globalPosition().toPoint()
            super().mouseMoveEvent(ev)

        def mouseReleaseEvent(self, ev):
            self._drag_pos = None
            super().mouseReleaseEvent(ev)

        def mouseDoubleClickEvent(self, ev):
            self._on_max()

    class _DesktopWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self._tray_ok = False
            self._tray = None
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
            self.setWindowTitle("KnowSubtle 学习宇宙")
            geo = _settings.value("geometry")
            if geo is not None:
                try:
                    self.restoreGeometry(geo)
                except Exception:
                    self.resize(1280, 800)
            else:
                self.resize(1280, 800)
            self.setMinimumSize(1024, 680)

            container = QWidget()
            container.setStyleSheet(f"background:{_UI_BG};")
            root = QVBoxLayout(container)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            self._title_bar = _TitleBar(self)
            root.addWidget(self._title_bar)

            self._view = QWebEngineView()
            try:
                self._view.page().setBackgroundColor(QColor(0x12, 0x0F, 0x17))
            except Exception:
                pass
            # 硬件加速 & 平滑滚动：最大化 GPU 合成收益，根除 CPU 合成滚动卡顿
            try:
                from PyQt6.QtWebEngineCore import QWebEngineSettings
                _s = QWebEngineSettings.defaultSettings()
                for _attr in ("Accelerated2dCanvasEnabled", "WebGLEnabled", "ScrollAnimatorEnabled"):
                    try:
                        _s.setAttribute(getattr(QWebEngineSettings.WebAttribute, _attr), True)
                    except Exception:
                        pass
                try:
                    _s.setAttribute(QWebEngineSettings.WebAttribute.HardwareAccelerationPolicy,
                                    QWebEngineSettings.HardwareAccelerationPolicy.Always)
                except Exception:
                    pass
            except Exception:
                pass
            # 磁盘 HTTP 缓存：本地仪表盘资源（JS/CSS/字体）缓存到磁盘，
            # 重载/二次打开瞬时完成，减少白屏等待、提升流畅度
            try:
                from PyQt6.QtWebEngineCore import QWebEngineProfile
                _prof = QWebEngineProfile.defaultProfile()
                _prof.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
                _prof.setHttpCacheMaximumSize(200 * 1024 * 1024)  # 200MB
            except Exception:
                pass
            self._view.setStyleSheet(f"background-color:{_UI_BG};")
            self._view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self._view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            root.addWidget(self._view, 1)
            self.setCentralWidget(container)

            # 启动 splash / 加载进度（覆盖整窗，加载完成后淡出）
            self._splash = QLabel(self)
            self._splash.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._splash.setStyleSheet(
                f"background:{_UI_BG}; color:#9AA0B5; font:14px 'Microsoft YaHei';"
            )
            self._splash.setText("正在加载仪表盘 … 0%")
            self._splash.resize(self.size())
            self._splash.show()
            self._view.loadProgress.connect(self._on_progress)
            self._view.loadFinished.connect(self._on_loaded)
            self._url = url
            self._load_retries = 0
            self._server_was_down = False
            # 渲染进程崩溃自愈：Chromium 渲染子进程意外终止时自动重载，避免白屏/卡死
            try:
                from PyQt6.QtWebEngineCore import QWebEnginePage
                self._view.page().renderProcessTerminated.connect(self._on_render_terminated)
            except Exception:
                pass
            # 后端自愈重载：后端崩溃重启期间页面会报错，恢复后自动重载，避免停留在错误态
            # 间隔可经 KS_BE_WATCHDOG_MS 覆盖（毫秒，默认 4000）
            self._be_watchdog = QTimer(self)
            self._be_watchdog.setInterval(
                max(500, int(os.environ.get("KS_BE_WATCHDOG_MS", "4000")))
            )
            self._be_watchdog.timeout.connect(self._backend_watchdog)
            self._be_watchdog.start()

            _ico = _resolve_app_icon()
            if _ico:
                try:
                    self.setWindowIcon(QIcon(str(_ico)))
                except Exception:
                    pass
            self._view.load(QUrl(url))

        def _on_progress(self, p):
            try:
                self._splash.setText(f"正在加载仪表盘 … {p}%")
            except Exception:
                pass

        def _safe_reload(self):
            try:
                self._view.reload()
            except Exception:
                pass

        def _on_render_terminated(self, status, exit_code):
            _log(f"Web 渲染进程异常终止(status={status}, code={exit_code})，自动重载页面。")
            self._load_retries = 0
            QTimer.singleShot(500, self._safe_reload)

        def _backend_watchdog(self):
            _up = _probe_url(self._url, timeout=1.0)
            if _up:
                if self._server_was_down:
                    self._server_was_down = False
                    _log("本地服务已恢复，自动重载页面。")
                    self._safe_reload()
            else:
                self._server_was_down = True

        def _on_loaded(self, ok):
            try:
                if ok:
                    self._load_retries = 0
                    QTimer.singleShot(300, self._splash.hide)
                else:
                    self._load_retries += 1
                    if self._load_retries <= 3:
                        self._splash.setText(f"加载未成功，正在重试 ({self._load_retries}/3) …")
                        QTimer.singleShot(800 * self._load_retries, self._safe_reload)
                    else:
                        self._splash.setText("加载失败，请检查本地服务是否运行。")
            except Exception:
                pass

        def resizeEvent(self, ev):
            try:
                self._splash.resize(self.size())
            except Exception:
                pass
            super().resizeEvent(ev)

        def changeEvent(self, ev):
            # 系统最小化（如 Win+M）→ 有托盘时缩到托盘
            if ev.type() == QEvent.Type.WindowStateChange and self.isMinimized():
                if self._tray_ok:
                    self.hide()
            super().changeEvent(ev)

        def closeEvent(self, event):
            # 保存窗口状态
            try:
                _settings.setValue("geometry", self.saveGeometry())
            except Exception:
                pass
            # 默认：关闭=缩到托盘防误关；KS_QUIT_ON_CLOSE=1 或托盘不可用时真正退出
            _force_quit = os.environ.get("KS_QUIT_ON_CLOSE", "").strip().lower() in ("1", "true", "yes")
            if _force_quit or not self._tray_ok:
                stop_event.set()
                event.accept()
            else:
                event.ignore()
                self.hide()
                try:
                    if self._tray is not None:
                        self._tray.showMessage(
                            "KnowSubtle", "已最小化到系统托盘，点击托盘图标可恢复。",
                            QSystemTrayIcon.MessageIcon.Information, 2000,
                        )
                except Exception:
                    pass

    try:
        _log("正在打开原生桌面窗口 (PyQt6 + QWebEngine) ...")
        _write_diagnose("启动成功(桌面窗口)", f"url={url}")
        app = QApplication(sys.argv)
    except Exception as e:
        _log(f"QApplication 初始化失败，回退到浏览器: {type(e).__name__}: {e}")
        return "pyqt-unavailable"

    # 首次启动引导：用户尚未表达任何渲染偏好时，弹窗引导选择（降低发现成本）。
    # 无显示/测试环境 (WC_HEADLESS) 或已设 KS_* 显式开关则跳过。
    if (
        not os.environ.get("WC_HEADLESS")
        and _load_render_mode_pref() is None
        and not os.environ.get("KS_GPU_COMPOSITING")
        and not os.environ.get("KS_SOFTWARE_RENDER")
        and not os.environ.get("KS_BALANCE")
    ):
        _chosen = _first_launch_render_guide(app)
        if _chosen == "skip":
            # 用户选择「稍后再说」：不写入偏好，下次启动仍引导；本次以默认平衡模式直接开窗口。
            _log("首启引导：用户选择稍后再说，不写入偏好，下次启动仍引导。")
        else:
            _save_render_mode_pref(_chosen)
            if _chosen != "balance":
                # 非默认模式需重启以重新应用 Chromium flags（须在 QWebEngine 初始化前生效）
                _log(f"首次引导选择渲染模式：{_chosen}，重启以应用。")
                return "restart"
            _log("首次引导选择渲染模式：平衡模式（默认，无需重启）。")

    win = _DesktopWindow()

    # 系统托盘
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = QSystemTrayIcon(app)
            _ico = _resolve_app_icon()
            if _ico:
                try:
                    tray.setIcon(QIcon(str(_ico)))
                except Exception:
                    tray.setIcon(app.windowIcon())
            else:
                tray.setIcon(app.windowIcon())
            tray.setToolTip("KnowSubtle 学习宇宙")
            menu = QMenu()
            # 当前渲染模式（可点击：展开子菜单直接切换；切换后持久化并需重启生效）
            act_mode = QAction("渲染模式：未知", app)
            act_mode.setIconVisibleInMenu(False)

            # 子菜单：三种渲染档位，当前生效项打勾
            _mode_submenu = QMenu("切换渲染模式", menu)
            _mode_labels = {
                "balance": "平衡模式（默认·不闪）",
                "gpu": "全GPU合成（最丝滑·集显可能闪）",
                "software": "全软件渲染（最稳·最卡）",
            }

            def _current_pref_key():
                _info = _RENDER_MODE_INFO or ""
                if "GPU_COMPOSITING" in _info:
                    return "gpu"
                if "SOFTWARE_RENDER" in _info:
                    return "software"
                return "balance"

            _mode_actions = {}

            def _apply_render_mode(mode: str):
                _save_render_mode_pref(mode)
                _cur = _current_pref_key()
                _msg = (
                    f"已选择渲染模式：{_mode_labels.get(mode, mode)}\n"
                    f"（之前为：{_mode_labels.get(_cur, _cur)}）\n\n"
                    f"渲染模式需在桌面程序重启后生效。是否立即重启？"
                )
                _reply = QMessageBox.question(
                    win, "切换渲染模式", _msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if _reply == QMessageBox.StandardButton.Yes:
                    global _PENDING_RESTART
                    _PENDING_RESTART = True
                    app.exit()

            for _m, _lab in _mode_labels.items():
                _a = QAction(_lab, app)
                _a.setCheckable(True)
                _a.setData(_m)
                _a.triggered.connect(
                    lambda checked=False, mm=_m: _apply_render_mode(mm)
                )
                _mode_submenu.addAction(_a)
                _mode_actions[_m] = _a
            act_mode.setMenu(_mode_submenu)

            _SHORT_LABEL = {
                "balance": "平衡模式",
                "gpu": "全GPU合成",
                "software": "全软件渲染",
            }

            def _refresh_mode_label():
                _info = _RENDER_MODE_INFO or ""
                _flags = _info.split("flags=", 1)[1] if "flags=" in _info else ""
                _cur = _current_pref_key()
                _cur_label = _SHORT_LABEL.get(_cur, "未知")
                act_mode.setText(f"当前已选：{_cur_label}  \u25b6")
                _tip = f"当前已选：{_cur_label}"
                if _flags:
                    _tip += f"\nChromium flags: {_flags}"
                _tip += "\n点击展开可切换渲染模式；或「重置渲染偏好」重新引导"
                act_mode.setToolTip(_tip)
                for _m, _a in _mode_actions.items():
                    _a.setChecked(_m == _cur)

            menu.aboutToShow.connect(_refresh_mode_label)
            menu.addAction(act_mode)

            # 重置渲染偏好：清除已保存选择并重新打开首启引导，便于真机反复试不同档位
            act_reset = QAction("重置渲染偏好（重新引导）", app)
            act_reset.setIconVisibleInMenu(False)

            def _reset_render_pref():
                _reply = QMessageBox.question(
                    win, "重置渲染偏好",
                    "将清除已保存的渲染模式偏好，并重新打开首启引导让你重新选择。\n\n"
                    "是否立即重置并重启？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if _reply == QMessageBox.StandardButton.Yes:
                    try:
                        _p = _render_pref_path()
                        if _p.exists():
                            _p.unlink()
                        _log("已重置渲染偏好，重启以重新引导。")
                    except Exception as e:
                        _log(f"重置渲染偏好失败: {type(e).__name__}: {e}")
                    global _PENDING_RESTART
                    _PENDING_RESTART = True
                    app.exit()

            act_reset.triggered.connect(lambda checked=False: _reset_render_pref())
            menu.addAction(act_reset)

            # 一键诊断面板：实时列出渲染 flags / 缓存 / 后端健康 / 运行时信息
            act_diag = QAction("诊断信息", app)
            act_diag.setIconVisibleInMenu(False)
            act_diag.triggered.connect(
                lambda checked=False, p=port: _open_diagnose_dialog(app, p)
            )
            menu.addAction(act_diag)

            menu.addSeparator()
            act_show = QAction("显示窗口", app)
            act_quit = QAction("退出应用", app)
            menu.addAction(act_show)
            menu.addAction(act_quit)
            tray.setContextMenu(menu)

            def _restore():
                win.showNormal()
                win.activateWindow()

            def _quit():
                stop_event.set()
                app.quit()

            act_show.triggered.connect(_restore)
            act_quit.triggered.connect(_quit)
            tray.activated.connect(
                lambda reason: _restore()
                if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                              QSystemTrayIcon.ActivationReason.Trigger)
                else None
            )
            tray.show()
            win._tray = tray
            win._tray_ok = True
    except Exception as e:
        _log(f"系统托盘初始化失败（不影响主窗口）: {type(e).__name__}: {e}")
        win._tray_ok = False

    win.show()
    app.exec()
    if _PENDING_RESTART:
        return "restart"
    return "pyqt"


def _open_fallback_window(port: int) -> str:
    """回退路径：默认浏览器 / opt-in 原生 WebView（KS_FORCE_WEBVIEW=1）。

    仅当 PyQt6 不可用、或用户强制 KS_FORCE_BROWSER=1 时走这里。
    """
    url = f"http://127.0.0.1:{port}/"
    if not _is_server_up(url):
        _write_diagnose("服务启动超时", f"url={url}, error={_server_error}")
        return "failed"

    # 默认浏览器模式：PyQt 不可用时的兜底入口
    if not os.environ.get("KS_FORCE_WEBVIEW"):
        _log("回退：使用默认浏览器打开仪表盘（PyQt 不可用或被 KS_FORCE_BROWSER 强制）。")
        _write_diagnose("启动成功(浏览器回退)", f"url={url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return "browser"

    # 以下为 opt-in 的原生 WebView 路径（KS_FORCE_WEBVIEW=1 时）：
    if not _webview2_available():
        _log("WebView2 不可用，改用默认浏览器打开仪表盘。")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return "browser"

    try:
        import webview

        _log("正在打开原生桌面窗口 ...")
        _w = webview.create_window(
            "KnowSubtle 学习宇宙",
            url,
            width=1280,
            height=800,
            min_size=(1024, 680),
            resizable=True,
            text_select=True,
            confirm_close=False,
        )

        # 防黑屏看门狗：若 6 秒后页面 body 仍无内容（疑似黑屏/渲染失败），
        # 自动在浏览器中打开，并销毁黑窗（由 main 用控制窗口保活，服务不会随之死亡）。
        state = {"black": False}

        def _watchdog() -> None:
            time.sleep(6)
            try:
                _len = _w.evaluate_js(
                    "document && document.body ? document.body.innerHTML.length : -1"
                )
            except Exception:
                _len = -1
            if _len == 0:
                _log("页面 6 秒内未渲染（疑似黑屏），回退到浏览器。")
                state["black"] = True
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                try:
                    _w.destroy()
                except Exception:
                    pass

        threading.Thread(target=_watchdog, daemon=True).start()
        webview.start()
        return "black-fallback" if state["black"] else "webview"
    except Exception as e:
        _log(f"原生窗口不可用 ({type(e).__name__}: {e})，回退到浏览器。")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return "browser"


def _open_native_window(port: int) -> str:
    """总入口：优先 PyQt6 桌面窗口；不可用时回退浏览器 / 原生 WebView。

    返回值（供 main 决定如何保活进程）：
      - "pyqt"             : PyQt 窗口正常打开并由用户关闭（直接退出）
      - "browser"          : 回退浏览器（需控制窗口保活）
      - "black-fallback"   : WebView 黑屏看门狗已回退浏览器（需控制窗口保活）
      - "failed"           : 服务启动超时，未能打开任何界面（直接退出并报错）
    """
    if os.environ.get("KS_FORCE_BROWSER"):
        return _open_fallback_window(port)
    r = _open_pyqt_window(port)
    if r == "pyqt":
        return "pyqt"
    if r == "restart":
        return "restart"
    if r == "failed":
        return "failed"
    # pyqt-unavailable → 回退
    return _open_fallback_window(port)


def _run_control_window(url: str):
    """回退路径下的常驻控制窗口：保证进程存活、服务可用，并提供干净退出。

    若 tkinter 不可用，则退化为阻塞等待 stop_event（用户需从任务管理器结束）。
    """
    try:
        import tkinter as tk
    except Exception:
        _log("无控制窗口可用（tkinter 缺失），服务将持续运行直到进程被结束。")
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    root = tk.Tk()
    root.title("KnowSubtle 运行中")
    root.geometry("460x190")
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    msg = (
        "KnowSubtle 已在浏览器打开：\n"
        + url
        + "\n\n关闭此窗口将退出应用并停止本地服务。\n"
        + "（若浏览器未自动弹出，请手动复制上面的地址打开）"
    )
    tk.Label(root, text=msg, wraplength=420, justify="left", anchor="w").pack(
        padx=16, pady=14, anchor="w"
    )

    def _quit():
        stop_event.set()
        try:
            root.destroy()
        except Exception:
            pass

    tk.Button(root, text="打开仪表盘", command=lambda: webbrowser.open(url), width=14, height=1).pack(pady=4)
    tk.Button(root, text="退出应用", command=_quit, width=14, height=1).pack(pady=6)
    root.protocol("WM_DELETE_WINDOW", _quit)
    root.mainloop()


def main():
    try:
        from app import app, load_app_config
    except Exception as e:
        import traceback as _tb

        err = f"{type(e).__name__}: {e}"
        _log(f"导入后端模块失败: {err}")
        _tb.print_exc()
        _write_diagnose("导入后端模块失败", err)
        _show_error_box(
            "KnowSubtle 启动失败",
            f"加载后端模块 (app) 时失败，服务无法启动。\n\n"
            f"错误：{err}\n\n"
            f"诊断文件已生成，请直接发我：\n"
            f"%APPDATA%\\KnowSubtle\\diagnose.txt\n（也已复制到桌面 diagnose.txt）\n\n"
            f"或查看日志：%APPDATA%\\KnowSubtle\\Logs\\stderr.log",
        )
        return

    cfg = load_app_config()
    preferred = int(cfg.get("port", 8753))
    host = cfg.get("host", "127.0.0.1")

    port = _find_free_port(preferred, host)
    if port != preferred:
        _log(f"端口 {preferred} 不可用，自动改用 {port}。")

    # 单实例判定（基于 PID 锁，不会误杀）：已有存活实例则打开它的地址并退出
    acquired, existing_url = _acquire_instance_lock(port)
    if not acquired and existing_url:
        _log(f"检测到已在运行的实例（{existing_url}），直接打开并退出。")
        try:
            webbrowser.open(existing_url)
        except Exception:
            pass
        return

    url = f"http://{host}:{port}/"
    _record_url(url)
    atexit.register(_release_instance_lock)

    # 启动服务（【非守护】线程，生命周期由 stop_event 控制，独立于窗口）
    server_thread = threading.Thread(target=_start_server, args=(app, host, port), daemon=False)
    server_thread.start()

    # 无显示 / 测试环境：仅起服务便于验证（不创建窗口）
    # 注意：显式判断 "1/true/yes"，避免 "WC_HEADLESS=0" 被当成真值（非空字符串皆真）
    if os.environ.get("WC_HEADLESS", "").strip().lower() in ("1", "true", "yes"):
        _log("WC_HEADLESS=1：仅启动本地服务，不创建窗口。")
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        _shutdown(server_thread)
        return

    mode = _open_native_window(port)
    if mode == "restart":
        # 托盘菜单切换渲染模式后请求重启：先释放单实例锁，再启动全新进程，
        # 最后退出旧进程（新 PID 不与基于 PID 的锁冲突）。
        _log("渲染模式切换：重启桌面程序以应用新设置。")
        _shutdown(server_thread)
        _release_instance_lock()
        try:
            subprocess.Popen([sys.executable])
        except Exception as e:
            _log(f"重启失败（请手动重启 KnowSubtle）: {type(e).__name__}: {e}")
        sys.exit(0)
    if mode in ("browser", "black-fallback"):
        # 回退路径：用控制窗口保活，确保浏览器里的服务不会因窗口销毁而消失
        _run_control_window(url)
    elif mode == "failed":
        # 服务启动失败：给出可见错误，避免静默退出让用户毫无头绪
        _show_error_box(
            "KnowSubtle 启动失败",
            f"本地服务在超时内未能启动。\n\n"
            f"本应监听的地址：{url}\n\n"
            f"错误详情：{_server_error or '（未见异常，可能是首次启动较慢或端口被占用）'}\n\n"
            f"诊断文件已生成，请直接发我：\n"
            f"%APPDATA%\\KnowSubtle\\diagnose.txt\n（也已复制到桌面 diagnose.txt）\n\n"
            f"或查看日志：%APPDATA%\\KnowSubtle\\Logs\\stderr.log",
        )
    # 其余（webview 正常关闭）直接收尾
    _shutdown(server_thread)


def _shutdown(server_thread: threading.Thread):
    stop_event.set()
    try:
        server_thread.join(timeout=10)
    except Exception:
        pass


def _show_error_box(title: str, message: str):
    """失败时给出可见的提示（而非静默退出）。tkinter 不可用时退化为阻塞等待。"""
    try:
        import tkinter as tk
    except Exception:
        _log(f"[{title}] {message}")
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return
    try:
        root = tk.Tk()
        root.title(title)
        root.geometry("540x250")
        tk.Label(root, text=message, wraplength=500, justify="left", anchor="w").pack(
            padx=16, pady=16, anchor="w"
        )
        tk.Button(
            root, text="退出", width=12,
            command=lambda: (stop_event.set(), root.destroy()),
        ).pack(pady=8)
        root.protocol("WM_DELETE_WINDOW", lambda: (stop_event.set(), root.destroy()))
        root.mainloop()
    except Exception:
        _log(f"[{title}] {message}")


if __name__ == "__main__":
    main()
