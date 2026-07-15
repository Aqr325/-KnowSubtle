"""KnowSubtle Learning Universe - Windows 启动器（PyInstaller 入口 → KnowSubtle.exe）

职责：
1. 设置 metagpt / LLM 运行环境变量（兼容 local_metagpt stub 打桩）
2. 启动 FastAPI 本地服务（uvicorn），并做端口冲突 / 单实例 / 就绪检测
3. 用系统原生 WebView 打开仪表盘（真正的桌面窗口，无浏览器地址栏/标签页）；
   若环境不支持（缺 WebView2 / 无显示等）则回退到默认浏览器，保证仍可用
打包后路径由 app.py 内部的 _resolve_* 系列函数自动适配。
"""
import os
import sys
import socket
import threading
import webbrowser
import time
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


def _another_instance_running(url: str) -> bool:
    """若目标端口已有服务在响应，视为已存在实例（单实例守护）。"""
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


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


def _open_native_window(port: int) -> bool:
    """用系统原生 WebView 打开仪表盘（真正的桌面窗口，无浏览器地址栏/标签页）。
    若环境不支持（缺 WebView2 / 无显示 / 页面渲染失败），回退到浏览器，保证仍可用。

    关键加固：WebView2 缺失或页面长时间不渲染（黑屏）时，自动回退到默认浏览器，
    杜绝「双击后只剩一个黑窗、用户不知如何是好」的静默失败。
    """
    import webview

    url = f"http://127.0.0.1:{port}/"
    if not _is_server_up(url):
        _log("服务启动超时，未能打开界面。")
        return False

    # WebView2 不可用 或 用户显式强制浏览器模式 → 直接开浏览器，绝不创建黑窗
    if (not _webview2_available()) or os.environ.get("KS_FORCE_BROWSER"):
        _log("WebView2 不可用 / 强制浏览器模式：改用默认浏览器打开仪表盘。")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return True

    try:
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
        # 自动销毁黑窗并在浏览器中打开，保证用户一定能看到界面。
        def _watchdog() -> None:
            import time as _t
            _t.sleep(6)
            try:
                _len = _w.evaluate_js(
                    "document && document.body ? document.body.innerHTML.length : -1"
                )
            except Exception:
                _len = -1
            if _len == 0:
                _log("页面 6 秒内未渲染（疑似黑屏），回退到浏览器。")
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
        return True
    except Exception as e:
        _log(f"原生窗口不可用 ({type(e).__name__}: {e})，回退到浏览器。")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return False


def _start_server(app, host: str, port: int):
    import uvicorn

    uvicorn.run(app, host=host, port=port)


def main():
    from app import app, load_app_config

    cfg = load_app_config()
    preferred = int(cfg.get("port", 8000))
    host = cfg.get("host", "127.0.0.1")

    # 单实例：若目标端口已有实例在跑（说明窗口已打开），直接退出避免重复
    probe = f"http://{host}:{preferred}/"
    if _another_instance_running(probe):
        _log("检测到已在运行的实例，退出（请勿重复启动）。")
        return

    port = _find_free_port(preferred, host)
    if port != preferred:
        _log(f"端口 {preferred} 不可用，自动改用 {port}。")
        cfg["port"] = port

    # 无显示 / 测试环境：仅起服务便于验证（不创建窗口）
    if os.environ.get("WC_HEADLESS"):
        _log("WC_HEADLESS=1：仅启动本地服务，不创建窗口。")
        _start_server(app, host, port)
        return

    # 后台线程运行 FastAPI；主线程交给 pywebview 事件循环（其 start() 会阻塞到窗口关闭）
    threading.Thread(target=_start_server, args=(app, host, port), daemon=True).start()
    _open_native_window(port)


if __name__ == "__main__":
    main()
