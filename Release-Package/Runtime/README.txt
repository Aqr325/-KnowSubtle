Runtime / vc_redist.exe
======================

本目录用于放置 Visual C++ 可再发行组件（Microsoft Visual C++ 2019/2022 x64 Redistributable）。
主程序（Core/main/main.exe，onedir 单文件夹）由 PyInstaller 打包，运行依赖本机已安装该组件。

此外，桌面窗口由系统原生 WebView2 渲染（pywebview 调用，无浏览器地址栏/标签页）。Windows 10/11 通常已内置 WebView2 运行时；若缺失，主程序会自动回退打开默认浏览器访问 `http://127.0.0.1:8000/`，功能不受影响。

获取方式（任选其一）：
1. 微软官方下载（推荐）：
   https://learn.microsoft.com/zh-CN/cpp/windows/latest-supported-vc-redist
   下载 "vc_redist.x64.exe"，重命名为 vc_redist.exe 放入本目录。
2. 或直接使用本机已安装的 Visual C++ 运行库（多数开发机已具备）。

安装脚本（Release-Package/Install/install.nsi）会在安装阶段检测并静默执行：
   vc_redist.exe /install /quiet /norestart

注意：出于安全与体积考虑，发行包不内置该二进制，请自行从官方渠道获取后纳入打包。
