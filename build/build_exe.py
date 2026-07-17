"""在 Windows 上把项目打包为 Release-Package/Core/KnowSubtle/KnowSubtle.exe（PyInstaller 单文件夹 onedir）。

前置条件（在本机 Windows 执行）：
    pip install pyinstaller
    pip install fastapi uvicorn pydantic pydantic-settings rich "httpx>=0.24,<0.28" openai==1.6.1 pywebview

用法：
    cd learning-agent-system
    python build/build_exe.py

产物：Release-Package/Core/KnowSubtle/KnowSubtle.exe 及其依赖（Core/main/_internal、*.dll）。
随后把 Release-Package 整体交给 NSIS 安装脚本（Release-Package/Install/install.nsi）制成安装包。

注意（已验证可独立运行的关键参数）：
  * --exclude-module metagpt   : 项目用 local_metagpt stub 打桩，不收集真实 metagpt，避免体积膨胀与缺失依赖。
  * --add-data local_metagpt   : stub 包作为数据文件打入 _internal，运行时由 app.py 注入 sys.path。
  * --collect-submodules       : 确保 learning_agent_system 所有子模块都被收集（否则运行时 import 失败）。
  * --noupx                    : 关闭 UPX 压缩，规避部分环境下 UPX 导致的启动崩溃。
  * --clean -y                 : 清理旧产物并覆盖输出目录，避免 COLLECT 阶段 "output directory not empty"。

HTML 资源（dashboard/）不在此处打进 Core，而是由 NSIS 以同级 Release-Package/Resources/html
形式分发；app.py 在打包态用 `_find_up` 从可执行文件目录逐级向上查找 `Resources/html`
（即 Core/KnowSubtle/KnowSubtle.exe → 向上到 Release-Package/Resources/html，布局无关）。
"""
import PyInstaller.__main__
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # learning-agent-system/
DIST = ROOT / "Release-Package" / "Core"
ICO = ROOT / "Release-Package" / "Install" / "程序图标.ico"

args = [
    str(ROOT / "launcher.py"),
    "--name=KnowSubtle",
    "--onedir",
    "--windowed",
    # 图标缺失（例如 CI checkout 未提交 .ico）则跳过，PyInstaller 用默认图标，不影响构建/运行
    *([f"--icon={ICO}"] if ICO.exists() else []),
    f"--distpath={DIST}",
    f"--workpath={ROOT / 'build' / 'work'}",
    f"--specpath={ROOT / 'build'}",
    "--clean",
    "-y",
    # 关键：用 local_metagpt stub 替代真实 metagpt，绝不收集真实 metagpt
    "--exclude-module=metagpt",
    # stub 包作为数据打入 _internal（运行时由 app.py 注入 sys.path）
    f"--add-data={ROOT / 'local_metagpt'};local_metagpt",
    # 确保业务包全部子模块被收集（等价于手动构建命令的 --collect-submodules）
    "--collect-submodules=learning_agent_system",
    # 隐藏导入（PyInstaller 静态分析可能漏掉的运行时导入）
    "--hidden-import=local_metagpt.stub",
    "--hidden-import=learning_agent_system.orchestrator",
    "--hidden-import=learning_agent_system.schema",
    # 数据库层：SQLAlchemy + aiosqlite（dialect 为动态导入，需显式声明）
    "--hidden-import=sqlalchemy",
    "--hidden-import=sqlalchemy.dialects.sqlite.aiosqlite",
    "--hidden-import=aiosqlite",
    # bottle：webview 的可选依赖，作为安全隐藏导入保留（不影响启动）。
    # 注意：刻意【不】收集 pywebview(webview)。其 PyInstaller 运行时 hook(hook-webview.py)
    # 会在解释器启动早期强制 import webview，在无显示/沙箱环境会卡死，导致 exe 启动即挂起、
    # 连日志重定向都来不及执行。本项目桌面窗口以 PyQt6+QWebEngine 为主，浏览器兜底走
    # 系统 webbrowser；webview 仅作次级 fallback，故显式排除，使构建结果在所有环境一致可靠。
    "--hidden-import=bottle",
    "--exclude-module=webview",
    # PyQt6 桌面窗口（自带 Chromium，不依赖系统 WebView2）：承载仪表盘的真正桌面程序
    "--hidden-import=PyQt6",
    "--hidden-import=PyQt6.sip",
    "--hidden-import=PyQt6.QtCore",
    "--hidden-import=PyQt6.QtWidgets",
    "--hidden-import=PyQt6.QtGui",
    "--hidden-import=PyQt6.QtWebEngineWidgets",
    "--hidden-import=PyQt6.QtWebEngineCore",
    "--hidden-import=PyQt6.QtWebChannel",
    "--hidden-import=PyQt6.QtNetwork",
    "--hidden-import=PyQt6.QtPrintSupport",
    # 排除未使用且在本无显示(headless)沙箱中 import 会死锁的 Qt 子模块。
    # 本项目只用 QWebEngineView，不依赖 Qml/Quick/Positioning；hook-PyQt6 会把全部 Qt
    # 子模块自动加为 hiddenimport，其中 PyQt6.QtQml 的 import 在 headless 环境下卡死，
    # 导致 PyInstaller analysis 阶段永久挂起（日志冻结在 hook-PyQt6.QtQml.py）。显式排除即可。
    "--exclude-module=PyQt6.QtQml",
    "--exclude-module=PyQt6.QtQuick",
    "--exclude-module=PyQt6.QtQuickWidgets",
    "--exclude-module=PyQt6.QtPositioning",
    # 注意：不要 --collect-submodules=PyQt6 / --collect-data=PyQt6！
    # PyQt6 自带 PyInstaller hook 已会自动收集 QtWebEngine 二进制与资源
    # (QtWebEngineProcess.exe / icudtl.dat / qtwebengine_resources.pak / locales)，
    # 全量递归收集会导致 analysis 阶段 OOM 被杀。显式 hidden-import 即可。
    # Phase 1 新增依赖：httpx（服务端 Key 代理转发）、yaml（llm_config.yaml 持久化）、rich（日志着色）
    "--hidden-import=httpx",
    "--hidden-import=yaml",
    "--hidden-import=rich",
    # 关闭 UPX，规避启动崩溃
    "--noupx",
]

if __name__ == "__main__":
    PyInstaller.__main__.run(args)
    # 注意：输出只用 ASCII，避免 CI Windows 控制台(cp1252)打印中文时抛 UnicodeEncodeError
    print(f"\n[OK] Build complete. Output dir: {DIST}")
    print(f"[Note] Before running, ensure Release-Package/Resources/html and Resources/Config are in place (distributed via NSIS).")
