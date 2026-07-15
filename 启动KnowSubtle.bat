@echo off
rem ── KnowSubtle 启动器 ──
rem 双击本文件即启动【项目内已修复的】KnowSubtle.exe，避免误用旧安装版/旧快捷方式。
cd /d "%~dp0"
if not exist "Release-Package\Core\KnowSubtle\KnowSubtle.exe" (
    echo 未找到 KnowSubtle.exe，请确认本启动器位于项目根目录。
    pause
    exit /b 1
)
start "" "Release-Package\Core\KnowSubtle\KnowSubtle.exe"
