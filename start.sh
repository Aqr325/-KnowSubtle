#!/usr/bin/env bash
# ============================================================================
# start.sh — FastAPI 项目「一键启动 + 进程守护」脚本 (bash 版)
#
# 用途:
#   自动探测可用的 python 解释器，运行 app.py；若进程以非零码退出则记录并在
#   3 秒后自动重启 (崩溃自愈)，若以 0 码干净退出则停止。
#
# 用法:
#   ./start.sh            # 直接运行 (需先 chmod +x start.sh)
#   bash start.sh         # 未授权限时也可运行
#
# 退出行为:
#   - app.py 以 0 码退出  -> 打印干净退出信息并停止守护 (break)
#   - app.py 以非 0 码退出 -> 记录退出码, sleep 3 后自动重启
#
# 说明:
#   解释器优先级: 本地 ./.venv/bin/python  ->  回退 PATH 上的 python3
# ============================================================================

set -u

# --- 1. 探测 python 解释器 ----------------------------------------------------
if [ -x "./.venv/bin/python" ]; then
  PY="./.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "[start] ERROR: 找不到可用的 python 解释器 (.venv/bin/python 或 python3)" >&2
  exit 1
fi

echo "[start] using python: $PY"
echo "[start] launching app.py ... (Ctrl+C 可中断)"

# --- 2. 守护循环 --------------------------------------------------------------
while true; do
  "$PY" app.py
  CODE=$?

  if [ "$CODE" -eq 0 ]; then
    echo "[start] app.py exited cleanly (code 0). Guardian stopped."
    break
  fi

  echo "[guardian] app.py exited with code $CODE at $(date)"
  echo "[guardian] restarting in 3 seconds ..."
  sleep 3
done
