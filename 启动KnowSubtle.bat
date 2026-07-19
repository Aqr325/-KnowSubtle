@echo off
cd /d "%~dp0"
if not exist "Release-Package\Core\KnowSubtle\KnowSubtle.exe" (
    echo KnowSubtle.exe not found. Make sure this launcher is in the project root directory.
    pause
    exit /b 1
)
start "" "Release-Package\Core\KnowSubtle\KnowSubtle.exe"
