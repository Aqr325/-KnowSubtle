"""KnowSubtle Learning Universe - Windows 启动器（PyInstaller 入口 → KnowSubtle.exe）

职责：
1. 设置 metagpt / LLM 运行环境变量（兼容 local_metagpt stub 打桩）
2. 启动 FastAPI 本地服务（uvicorn），并做端口冲突 / 单实例 / 就绪检测
3. 用系统原生 WebView 打开仪表盘（真正的桌面窗口，无浏览器地址栏/标签页）；
   若环境不支持（缺 WebView2 / 无显示等）则回退到默认浏览器，保证仍可用

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


def _log(msg: str):
    try:
        print(f"[launcher] {msg}", flush=True)
    except Exception:
        pass


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


def _is_server_up(url: str, timeout: float = 20.0) -> bool:
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
    """基于 PID 锁文件的单实例判定。

    返回 (acquired, existing_url)：
    - 若已有【存活】实例持有锁 → 返回 (False, 它的 url)，调用方应直接打开该 url 并退出；
    - 否则写入自己的锁，返回 (True, None)。
    """
    try:
        lock_dir = Path(os.environ.get("APPDATA", str(ROOT))) / "KnowSubtle"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock = lock_dir / "run.lock"
        if lock.exists():
            try:
                data = json.loads(lock.read_text(encoding="utf-8"))
                if _pid_alive(int(data.get("pid", 0))):
                    return False, str(data.get("url", ""))
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
    """在独立线程中运行 uvicorn；stop_event 置位时优雅退出。"""
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _watch_stop():
        while not stop_event.is_set():
            time.sleep(0.5)
        server.should_exit = True

    threading.Thread(target=_watch_stop, daemon=True).start()
    server.run()


def _open_native_window(port: int) -> str:
    """打开仪表盘窗口。

    返回值（供 main 决定如何保活进程）：
      - "webview"        : WebView2 窗口正常打开并由用户关闭（主线程无需保活，直接退出）
      - "black-fallback" : 黑屏看门狗已打开浏览器并销毁黑窗（需控制窗口保活）
      - "browser"        : 无 WebView2 / 强制浏览器，已打开默认浏览器（需控制窗口保活）
      - "failed"         : 服务启动超时，未能打开任何界面（直接退出）
    """
    url = f"http://127.0.0.1:{port}/"
    if not _is_server_up(url):
        _log("服务启动超时，未能打开界面。")
        return "failed"

    # WebView2 不可用 或 用户显式强制浏览器模式 → 直接开浏览器，绝不创建黑窗
    if (not _webview2_available()) or os.environ.get("KS_FORCE_BROWSER"):
        _log("WebView2 不可用 / 强制浏览器模式：改用默认浏览器打开仪表盘。")
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

    tk.Button(root, text="退出应用", command=_quit, width=14, height=1).pack(pady=6)
    root.protocol("WM_DELETE_WINDOW", _quit)
    root.mainloop()


def main():
    from app import app, load_app_config

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
    if os.environ.get("WC_HEADLESS"):
        _log("WC_HEADLESS=1：仅启动本地服务，不创建窗口。")
        try:
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        _shutdown(server_thread)
        return

    mode = _open_native_window(port)
    if mode in ("browser", "black-fallback"):
        # 回退路径：用控制窗口保活，确保浏览器里的服务不会因窗口销毁而消失
        _run_control_window(url)
    # 其余（webview 正常关闭 / failed）直接收尾
    _shutdown(server_thread)


def _shutdown(server_thread: threading.Thread):
    stop_event.set()
    try:
        server_thread.join(timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    main()
