"""
WordCosmos 数据库后端回归测试

验证 SQLite 升级后的数据层：
  - 数据库初始化 / 表自动创建
  - 词库 CRUD + 按学科去重 + 学科过滤
  - 统计聚合（daily stats / dashboard summary）
  - 每日目标 设定 / 今日进度
  - TeamOrchestrator checkpoint 存/取（同步引擎，含路径穿越防护）

运行方式：
  python tests/test_db_backend.py
（建议使用项目根目录的绝对路径，且不在打包环境运行）
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# 让脚本在仓库根目录直接运行也能找到包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# metagpt 打桩（离线 demo 模式，避免真实 import metagpt）
sys.path.insert(0, str(ROOT / "local_metagpt"))
try:
    import local_metagpt.stub  # noqa: F401
except Exception:
    pass

import pytest


def _isolate():
    """创建隔离的临时数据目录并注入环境变量"""
    td = tempfile.mkdtemp(prefix="wc_db_test_")
    os.environ["LAS_DATA_DIR"] = td
    os.environ["LAS_DB_PATH"] = os.path.join(td, "wordcosmos.db")
    os.environ["METAGPT_STUBBED"] = "1"
    return td


@pytest.fixture(scope="module", autouse=True)
def setup():
    _isolate()
    from learning_agent_system.database.session import init_db, close_db

    async def boot():
        await init_db()

    asyncio.run(boot())
    yield
    async def shut():
        await close_db()
    asyncio.run(shut())


def test_init_creates_db_file():
    from learning_agent_system.database.session import DB_PATH
    assert os.path.exists(DB_PATH), "数据库文件应在初始化后存在"


def test_vocab_crud_and_subject_dedup():
    from learning_agent_system.database.session import get_async_session
    from learning_agent_system.database.repo import VocabRepository

    async def run():
        async with get_async_session() as s:
            repo = VocabRepository(s)
            _, c1 = await repo.add(word="Algorithm", meaning="算法", subject="english")
            assert c1 is True, "首建应成功"
            _, c2 = await repo.add(word="algorithm", meaning="算法", subject="english")
            assert c2 is False, "同词同学科应去重（大小写不敏感）"
            _, c3 = await repo.add(word="algorithm", meaning="算法", subject="programming")
            assert c3 is True, "同词跨学科应允许"
            eng = await repo.get_by_subject("english")
            assert len(eng) == 1
            allw = await repo.get_by_subject(None)
            assert len(allw) == 2
            # 复习计数
            await repo.record_review(eng[0].id)
            v = await repo.get_by_id(eng[0].id)
            assert v.review_count == 1
            # 删除
            assert await repo.delete(eng[0].id) is True

    asyncio.run(run())


def test_stats_aggregation():
    from learning_agent_system.database.session import get_async_session
    from learning_agent_system.database.repo import StatsRepository

    async def run():
        async with get_async_session() as s:
            repo = StatsRepository(s)
            await repo.upsert_daily_stats("2026-07-09", 42.5)
            await repo.upsert_daily_accuracy("2026-07-09", 88.0)
            await repo.upsert_daily_words("2026-07-09", 10, 120)
            summ = await repo.get_dashboard_summary()
            assert summ["summary"]["totalMinutes"] == 42.5
            assert summ["summary"]["totalWords"] == 120

    asyncio.run(run())


def test_daily_goals():
    from learning_agent_system.database.session import get_async_session
    from learning_agent_system.database.repo import DailyGoalRepository

    async def run():
        async with get_async_session() as s:
            repo = DailyGoalRepository(s)
            await repo.update_target(6, 30, 90)
            t = await repo.get_target()
            assert t["daily_pomodoros"] == 6
            await repo.update_today_progress(words=5, minutes=15)
            p = await repo.get_today_progress()
            assert p["progress"]["words_learned"] == 5
            assert p["progress"]["minutes_studied"] == 15

    asyncio.run(run())


def test_orchestrator_checkpoint_roundtrip():
    from learning_agent_system.orchestrator import (
        TeamOrchestrator,
        SessionContext,
        LearningGoal,
        Phase,
    )

    td = tempfile.mkdtemp(prefix="wc_orch_")
    orch = TeamOrchestrator(storage_dir=td)
    ctx = SessionContext()
    ctx.learning_goal = LearningGoal(description="learn Python asyncio")
    ctx.current_phase = Phase.PLANNING
    orch.context = ctx
    orch._save_checkpoint()

    loaded = orch.load_session(ctx.session_id)
    assert loaded is not None
    assert loaded.learning_goal.description == "learn Python asyncio"
    assert loaded.current_phase == Phase.PLANNING

    sessions = orch.list_sessions()
    assert ctx.session_id in sessions


def test_orchestrator_path_traversal_blocked():
    from learning_agent_system.orchestrator import TeamOrchestrator

    orch = TeamOrchestrator(storage_dir=tempfile.mkdtemp())
    assert orch.load_session("../../etc/passwd") is None
    assert orch.load_session("..\\..\\windows\\system32") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
