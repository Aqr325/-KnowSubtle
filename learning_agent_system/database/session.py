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
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects.sqlite import dialect as _sqlite_dialect
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


def _column_default_literal(col) -> str:
    """为新模型里有、但旧表里没有的列生成安全的 INSERT 默认值字面量。

    否则像 vocab.created_at（NOT NULL 且只有 Python 端 default=datetime.now、无 SQL
    server_default）在重建 INSERT 时会落 NULL → 触发 NOT NULL 约束崩溃，导致 init_db
    抛异常、后端服务起不来、浏览器 ERR_CONNECTION_REFUSED。
    """
    # 优先使用 SQL 层 server_default
    sd = getattr(col, "server_default", None)
    if sd is not None:
        arg = getattr(sd, "arg", None)
        if arg is not None:
            return str(arg)
    # 标量 Python default
    d = getattr(col, "default", None)
    if d is not None and getattr(d, "is_scalar", False):
        return repr(d.arg)
    # 按类型给兜底字面量
    from sqlalchemy import DateTime, String, Text, Integer, Boolean, Float

    t = col.type
    try:
        if isinstance(t, DateTime):
            return "'2026-01-01 00:00:00'"
        if isinstance(t, (String, Text)):
            return "''"
        if isinstance(t, Boolean):
            return "0"
        if isinstance(t, Integer):
            return "0"
        if isinstance(t, Float):
            return "0.0"
    except Exception:
        pass
    return "''"


async def _rebuild_table_with_unique(conn, tname: str) -> None:
    """
    重建含 user_id 的共享表，解决旧库唯一约束由 SQLite 自动索引（sqlite_autoindex_*）
    实现、而自动索引无法通过 DROP INDEX 删除的问题。

    做法：重命名旧表 → 按当前 SQLAlchemy 元数据建新表（不含唯一索引）
    → 拷贝数据 → 删除旧表 → 按模型元数据重建全部索引（含复合唯一索引，使用显式命名）。
    显式 Index(..., unique=True) 在 SQLite 中会保留名称（UNIQUE CONSTRAINT 则不会），
    因此重建后索引名为 uq_*，可被后续迁移安全管理。

    健壮性：
    - 先 DROP TABLE IF EXISTS _{tname}_old，避免上次中断的重建遗留同名表导致 RENAME 失败；
    - 旧表缺少的列（新模型新增、可能 NOT NULL 无 server_default）用 _column_default_literal
      补默认值，避免 NOT NULL 约束崩溃。
    """
    new_table = Base.metadata.tables[tname]
    # 幂等：清理上次可能中断遗留的临时表
    await conn.execute(text(f"DROP TABLE IF EXISTS _{tname}_old"))
    old_cols = [r[1] for r in (await conn.execute(text(f"PRAGMA table_info({tname})"))).fetchall()]
    new_cols = [c.name for c in new_table.columns]
    # 构建 SELECT 表达式：旧表有的列直接拷贝；旧表没有的列给安全默认值
    select_exprs = []
    for c in new_table.columns:
        if c.name in old_cols:
            select_exprs.append(c.name)
        else:
            select_exprs.append(f"{_column_default_literal(c)} AS {c.name}")
    insert_cols = ", ".join(new_cols)
    select_sql = ", ".join(select_exprs)
    ddl = str(CreateTable(new_table).compile(dialect=_sqlite_dialect()))
    await conn.execute(text(f"ALTER TABLE {tname} RENAME TO _{tname}_old"))
    await conn.execute(text(ddl))
    await conn.execute(text(f"INSERT INTO {tname} ({insert_cols}) SELECT {select_sql} FROM _{tname}_old"))
    await conn.execute(text(f"DROP TABLE _{tname}_old"))
    # 重建模型定义的所有索引（唯一 + 非唯一），使用显式命名
    for ix in new_table.indexes:
        await conn.execute(text(str(CreateIndex(ix).compile(dialect=_sqlite_dialect()))))


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

        # ── 用户隔离迁移：为会话表与全局共享表补充 user_id 列，并修正唯一约束 ──
        # 旧库 create_all 不会补列；匿名历史数据 user_id 为 NULL，向后兼容（user_id IS NULL）。
        for _t, _need in (
            ("sessions", ("user_id",)),
            ("vocab", ("user_id",)),
            ("daily_stats", ("user_id",)),
            ("daily_words", ("user_id",)),
            ("daily_accuracy", ("user_id",)),
            ("daily_goals", ("user_id",)),
        ):
            _cols = [r[1] for r in (await conn.execute(text(f"PRAGMA table_info({_t})"))).fetchall()]
            for _c in _need:
                if _c not in _cols:
                    await conn.execute(text(f"ALTER TABLE {_t} ADD COLUMN {_c} INTEGER"))

        # ── 共享表唯一约束迁移（账号隔离）──
        # 旧库用单列唯一（vocab: word+subject；daily_*: date），现改为按用户隔离的复合唯一。
        # 注意：SQLite 对 UNIQUE CONSTRAINT 会生成 sqlite_autoindex_* 且无法通过 DROP INDEX
        # 删除；对显式 CREATE UNIQUE INDEX 才保留名称。因此模型改用 Index(..., unique=True)，
        # 此处策略：若现有唯一索引列与期望不符且无法删除（自动索引）→ 重建表；否则补建显式索引。
        # 期望唯一索引（列 + 显式名称）：
        _unique_specs = {
            "vocab": (("word", "subject", "user_id"), "uq_vocab_word_subject_user"),
            "daily_stats": (("date", "user_id"), "uq_daily_stats_date_user"),
            "daily_words": (("date", "user_id"), "uq_daily_words_date_user"),
            "daily_accuracy": (("date", "user_id"), "uq_daily_accuracy_date_user"),
            "daily_goals": (("date", "user_id"), "uq_daily_goals_date_user"),
        }
        for _t, (_ucols, _uname) in _unique_specs.items():
            _need_rebuild = False
            _idxs = (await conn.execute(text(f"PRAGMA index_list({_t})"))).fetchall()
            for _idx in _idxs:
                _iname, _iunique = _idx[1], _idx[2]
                if not _iunique:
                    continue
                _info = (await conn.execute(text(f"PRAGMA index_info({_iname})"))).fetchall()
                _icols = tuple(c[2] for c in _info)
                if _icols != _ucols:
                    # 旧唯一约束与期望不同，需移除；自动索引无法 DROP → 重建表
                    try:
                        await conn.execute(text(f"DROP INDEX IF EXISTS {_iname}"))
                    except Exception:
                        _need_rebuild = True
            if _need_rebuild:
                try:
                    await _rebuild_table_with_unique(conn, _t)
                except Exception as _re:
                    logger.warning("重建表 %s 失败（跳过，服务仍会启动）: %s: %s", _t, type(_re).__name__, _re)
            else:
                # 期望索引已存在（已是复合唯一）或旧命名索引已成功删除 → 补建显式命名索引
                await conn.execute(text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {_uname} ON {_t}({', '.join(_ucols)})"
                ))

        await conn.execute(text("PRAGMA busy_timeout=5000"))

    logger.info(f"数据库初始化完成: {DB_PATH}")

    # 尝试从 JSON 导入（异常不应阻断服务启动）
    if migrate:
        try:
            await migrate_json_to_db()
            logger.info("JSON 数据迁移检查完成")
        except Exception as _je:
            logger.warning("JSON 数据迁移失败（跳过，服务仍会启动）: %s: %s", type(_je).__name__, _je)


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