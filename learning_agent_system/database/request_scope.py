"""
请求作用域：跨 sync/async 会话传递当前登录用户身份。

本项目存在两套数据库会话：
  - FastAPI 端点使用 async 引擎（aiosqlite）
  - TeamOrchestrator 内部使用 sync 引擎（sqlite3）

contextvars 能在同一请求/任务的 async 与 sync 调用之间安全传递用户身份，
因此用它在请求生命周期内持有 `current_user_id`，供 Repository 与 Orchestrator
做数据隔离过滤。匿名访问时值为 None（对应各表 `user_id IS NULL`）。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# 当前登录用户的 id；未登录（匿名）为 None。
current_user_id: ContextVar[Optional[int]] = ContextVar("current_user_id", default=None)
