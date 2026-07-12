"""
KnowSubtle Database Session — 异步引擎与会话管理

SQLite + asyncpg 不兼容，使用 aiosqlite 作为异步驱动。
支持桌面应用打包后从 AppData 读取数据库路径。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session as SyncSession
from sqlalchemy import text
from contextlib import asynccontextmanager

from .models import Base

logger = logging.getLogger("db.session")

# ── 全局单例 ──
_async_engine = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_sync_engine = None
_sync_session_factory = None


def _old_db_path() -> Optional[Path]:
    """旧版本（WordCosmos）数据库路径，用于升级迁移。"""
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / "WordCosmos" / "Data" / "wordcosmos.db"
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / ".learning_memory" / "wordcosmos.db"


def _maybe_migrate_old_db(new_path: Path) -> None:
    """升级兼容：若新库不存在但旧 WordCosmos 库存在，复制旧库到新位置（保留旧库）。"""
    if new_path.exists():
        return
    old = _old_db_path()
    if old and old.exists():
        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(old, new_path)
            logger.info("已从旧数据库迁移: %s -> %s", old, new_path)
        except Exception as e:
            logger.warning("旧数据库迁移失败（将新建空库）: %s", e)


def _resolve_db_path() -> Path:
    """解析数据库文件路径，兼容开发模式与打包模式，并迁移旧版数据。"""
    env = os.environ.get("LAS_DB_PATH")
    if env:
        d = Path(env)
        d.parent.mkdir(parents=True, exist_ok=True)
        p = d
        _maybe_migrate_old_db(p)
        return p

    # 打包后：AppData/KnowSubtle/Data/knowsubtle.db
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = Path(base) / "KnowSubtle" / "Data"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "knowsubtle.db"
        _maybe_migrate_old_db(p)
        return p

    # 开发模式：.learning_memory/knowsubtle.db
    project_root = Path(__file__).resolve().parent.parent.parent
    data_dir = project_root / ".learning_memory"
    data_dir.mkdir(parents=True, exist_ok=True)
    p = data_dir / "knowsubtle.db"
    _maybe_migrate_old_db(p)
    return p


DB_PATH: Path = _resolve_db_path()
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"


from sqlalchemy import event as _sa_event


def _on_connect_fk(dbapi_conn, conn_record):
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA foreign_keys=ON")
        # 双引擎（async 用于 FastAPI，sync 用于 orchestrator）同开一个 SQLite 文件；
        # 设置 busy_timeout 让并发写入自动重试，避免 "database is locked"。
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
    finally:
        cur.close()


def _enable_foreign_keys(engine):
    try:
        sync_engine = engine.sync_engine if hasattr(engine, "sync_engine") else engine
        _sa_event.listen(sync_engine, "connect", _on_connect_fk)
    except Exception:
        pass


async def get_engine():
    """获取或创建异步引擎（单例）"""
    global _async_engine, _async_session_factory
    if _async_engine is None:
        _async_engine = create_async_engine(
            DB_URL,
            echo=False,
            future=True,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        _enable_foreign_keys(_async_engine)
        _async_session_factory = async_sessionmaker(
            _async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_engine


def get_sync_engine():
    """获取同步引擎（用于 Alembic 迁移或一次性操作）"""
    global _sync_engine, _sync_session_factory
    if _sync_engine is None:
        from sqlalchemy import create_engine as _create_sync
        from sqlalchemy.orm import sessionmaker as _sync_sessionmaker
        _sync_engine = _create_sync(f"sqlite:///{DB_PATH}", echo=False, future=True)
        _enable_foreign_keys(_sync_engine)
        _sync_session_factory = _sync_sessionmaker(_sync_engine, expire_on_commit=False)
    return _sync_engine


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步会话（异步上下文管理器，用于 FastAPI 端点与迁移）"""
    if _async_session_factory is None:
        await get_engine()
    async with _async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db(migrate: bool = True):
    """
    初始化数据库：创建所有表（如果不存在）。
    migrate=True 时同时尝试从 JSON 文件导入数据。
    """
    from .repo import migrate_json_to_db

    engine = await get_engine()

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 验证 SQLite WAL 模式（提升并发性能）
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        # 为所有含 session_id 的表补充索引（避免按 session_id 查询/级联删除全表扫描）
        for tname, table in Base.metadata.tables.items():
            if "session_id" in table.columns:
                idx = f"ix_{tname}_session_id"
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx} ON {tname}(session_id)"))
        # 词库大小写不敏感去重索引 + word_lower 列迁移
        # 注意：必须先确保 word_lower 列存在（已有库 create_all 不会补列），再回填，最后建索引
        _cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(vocab)"))).fetchall()]
        if "word_lower" not in _cols:
            await conn.execute(text("ALTER TABLE vocab ADD COLUMN word_lower VARCHAR"))
        await conn.execute(text("UPDATE vocab SET word_lower = lower(word) WHERE word_lower IS NULL"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vocab_word_lower ON vocab(word_lower, subject)"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))

    logger.info(f"数据库初始化完成: {DB_PATH}")

    # 尝试从 JSON 导入
    if migrate:
        await migrate_json_to_db()
        logger.info("JSON 数据迁移检查完成")


async def close_db():
    """关闭数据库引擎"""
    global _async_engine, _async_session_factory, _sync_engine, _sync_session_factory
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
    if _sync_engine:
        _sync_engine.dispose()
        _sync_engine = None
        _sync_session_factory = None