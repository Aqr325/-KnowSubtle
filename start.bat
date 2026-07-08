@echo off
REM ============================================================================
REM start.bat — FastAPI 项目「一键启动 + 进程守护」脚本 (Windows cmd 版)
REM
REM 用途:
REM   自动探测可用的 python 解释器, 运行 app.py; 若进程以非零码退出则记录并在
REM   3 秒后自动重启 (崩溃自愈), 若以 0 码干净退出则停止。
REM
REM 用法:
REM   双击 start.bat   或   在 cmd 中运行 start.bat
REM   (仅依赖 cmd, 无需 powershell)
REM
REM 退出行为:
REM   - app.py 以 0 码退出  -> 打印干净退出信息并停止守护 (goto :end)
REM   - app.py 以非 0 码退出 -> 记录退出码, 延迟 3 秒后自动重启
REM
REM 说明:
REM   解释器优先级: 本地 .\.venv\Scripts\python.exe  ->  回退 PATH 上的 python
REM ============================================================================

setlocal

REM --- 1. 探测 python 解释器 ---------------------------------------------------
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

echo [start] using python: %PY%
echo [start] launching app.py ... (Ctrl+C 可中断)

REM --- 2. 守护循环 -------------------------------------------------------------
:loop
%PY% app.py
if "%errorlevel%"=="0" (
  echo [start] app.py exited cleanly (code 0). Guardian stopped.
  goto :end
)
echo [guardian] app.py exited with code %errorlevel% at %date% %time%
echo [guardian] restarting in 3 seconds ...
timeout /t 3 >nul
goto :loop

:end
endlocal
