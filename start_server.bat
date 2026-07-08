@echo off
cd /d "D:\workbuddy workspace\2026-06-26-10-37-12\learning-agent-system"
set METAGPT_PROJECT_ROOT=D:\workbuddy workspace\2026-06-26-10-37-12\learning-agent-system
set OPENAI_API_KEY=sk-test-dummy
set OPENAI_API_MODEL=gpt-4o-mini
start /B "" "D:\workbuddy workspace\2026-06-26-10-37-12\.venv\Scripts\python" run_backend.py > backend.log 2>&1
echo Server starting...
timeout /t 5 /nobreak >nul
echo Done.
