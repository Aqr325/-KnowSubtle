"""
KnowSubtle Database Repository — 数据访问层

为每个核心实体提供 Repository 类，封装 CRUD 操作。
统一使用 async/await，支持批量查询和聚合统计。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import (
    Session, LearningGoal, LearnerProfile, KnowledgeDiagnosis,
    ResourcePlan, LearningPath, LearningModule, TutorSession,
    ExerciseResult, Achievement, MistakeRecord, KnowledgeDecay,
    StudyStreak, MultiGoalProgress, Vocab, DailyStats, DailyWords,
    DailyAccuracy, DailyGoal, User, AuthToken,
)

logger = logging.getLogger("db.repo")


# ════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════

def _json_load(text: str, default=None):
    """安全反序列化 JSON 字符串"""
    if not text:
        return default if default is not None else {}
    try:
        return json.loads(text)
    except Exception:
        return default if default is not None else {}


def _json_dump(obj: Any) -> str:
    """安全序列化 JSON 字符串"""
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _now() -> str:
    return datetime.now().isoformat()


# ════════════════════════════════════════════
# 账号隔离：请求作用域 user_id（匿名为 None）
# ══════════════════════════════════════════

from .request_scope import current_user_id

_UNSET = object()


def _resolve_user_id(user_id):
    """user_id 未显式传入时回退到请求作用域 contextvar（由 app 中间件在每次请求注入）。"""
    if user_id is _UNSET:
        return current_user_id.get()
    return user_id


# ════════════════════════════════════════════
# SessionRepository — 会话管理
# ════════════════════════════════════════════

class SessionRepository:
    """Session 相关 CRUD"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_session_ids(self) -> List[str]:
        """列出所有 session_id"""
        result = await self._session.execute(
            select(Session.session_id).order_by(Session.id)
        )
        return [r[0] for r in result.all()]

    async def get_session_by_id(self, session_id: str) -> Optional[Session]:
        """按 session_id 获取 Session"""
        stmt = select(Session).where(Session.session_id == session_id).options(
            selectinload(Session.learning_goal),
            selectinload(Session.learner_profile),
            selectinload(Session.diagnosis),
            selectinload(Session.resource_plan),
            selectinload(Session.learning_path),
            selectinload(Session.learning_path).selectinload(LearningPath.modules),
            selectinload(Session.tutor_sessions),
            selectinload(Session.exercise_results),
            selectinload(Session.achievements),
            selectinload(Session.mistake_records),
            selectinload(Session.knowledge_decay),
            selectinload(Session.study_streak),
            selectinload(Session.multi_goals),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_session(self, session_id: str, phase: str = "profiling") -> Session:
        """创建新 Session"""
        s = Session(
            session_id=session_id,
            current_phase=phase,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._session.add(s)
        await self._session.commit()
        await self._session.refresh(s)
        return s

    async def _get_session_light(self, session_id: str):
        result = await self._session.execute(
            select(Session).where(Session.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def update_phase(self, session_id: str, phase: str):
        """更新会话阶段（轻量，不加载整图）"""
        s = await self._get_session_light(session_id)
        if s:
            s.current_phase = phase
            s.updated_at = datetime.now()
            await self._session.commit()

    async def save_study_streak(self, session_id: str, streak_data: Dict[str, Any]):
        """保存/更新 StudyStreak（轻量）"""
        s = await self._get_session_light(session_id)
        if not s:
            return
        if s.study_streak is None:
            streak = StudyStreak(session_id=s.id, **streak_data)
            s.study_streak = streak
            self._session.add(streak)
        else:
            for k, v in streak_data.items():
                setattr(s.study_streak, k, v)
        await self._session.commit()

    async def get_study_streak(self, session_id: str) -> Optional[StudyStreak]:
        """获取 StudyStreak（轻量）"""
        s = await self._get_session_light(session_id)
        if not s:
            return None
        await self._session.refresh(s, ["study_streak"])
        return s.study_streak

    async def add_achievement(self, session_id: str, ach: Achievement) -> Achievement:
        """添加成就"""
        self._session.add(ach)
        await self._session.commit()
        await self._session.refresh(ach)
        return ach

    async def get_achievements(self, session_id: str) -> List[Achievement]:
        """获取所有成就"""
        result = await self._session.execute(
            select(Achievement).where(Achievement.session_id == session_id)
        )
        return result.scalars().all()

    async def add_mistake(self, session_id: str, mistake: MistakeRecord) -> MistakeRecord:
        """添加错题"""
        self._session.add(mistake)
        await self._session.commit()
        await self._session.refresh(mistake)
        return mistake

    async def get_mistakes(self, session_id: str) -> List[MistakeRecord]:
        """获取所有错题"""
        result = await self._session.execute(
            select(MistakeRecord).where(MistakeRecord.session_id == session_id)
        )
        return result.scalars().all()

    async def add_exercise_result(self, session_id: str, result: ExerciseResult) -> ExerciseResult:
        """添加练习结果"""
        self._session.add(result)
        await self._session.commit()
        await self._session.refresh(result)
        return result

    async def get_exercise_results(self, session_id: str) -> List[ExerciseResult]:
        """获取所有练习结果"""
        result = await self._session.execute(
            select(ExerciseResult)
            .where(ExerciseResult.session_id == session_id)
            .order_by(ExerciseResult.timestamp.desc())
        )
        return result.scalars().all()

    async def get_exercise_stats(self, session_id: str) -> Dict[str, Any]:
        """获取练习统计"""
        total = await self._session.scalar(
            select(func.count()).select_from(ExerciseResult).where(ExerciseResult.session_id == session_id)
        ) or 0
        correct = await self._session.scalar(
            select(func.count()).select_from(ExerciseResult)
            .where(ExerciseResult.session_id == session_id, ExerciseResult.is_correct == True)
        ) or 0
        avg_score = await self._session.scalar(
            select(func.avg(ExerciseResult.score)).where(ExerciseResult.session_id == session_id)
        ) or 0.0
        return {
            "total": total,
            "correct": correct,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
            "avg_score": round(float(avg_score), 2),
        }

    async def add_tutor_session(self, session_id: str, ts: TutorSession) -> TutorSession:
        """添加辅导会话"""
        self._session.add(ts)
        await self._session.commit()
        await self._session.refresh(ts)
        return ts

    async def get_tutor_sessions(self, session_id: str) -> List[TutorSession]:
        """获取所有辅导会话"""
        result = await self._session.execute(
            select(TutorSession)
            .where(TutorSession.session_id == session_id)
            .order_by(TutorSession.round_number)
        )
        return result.scalars().all()


# ════════════════════════════════════════════
# VocabRepository — 词库管理
# ════════════════════════════════════════════

class VocabRepository:
    """Vocab CRUD + 按学科/用户过滤"""

    def __init__(self, session: AsyncSession, user_id=_UNSET):
        self._session = session
        self._user_id = _resolve_user_id(user_id)

    def _user_filter(self):
        if self._user_id is None:
            return [Vocab.user_id.is_(None)]
        return [Vocab.user_id == self._user_id]

    async def get_by_subject(self, subject: Optional[str] = None) -> List[Vocab]:
        """获取词库，可选按学科/用户过滤"""
        conds = self._user_filter()
        if subject:
            conds.append(Vocab.subject == subject)
        result = await self._session.execute(
            select(Vocab).where(*conds).order_by(Vocab.id)
        )
        return result.scalars().all()

    async def get_by_id(self, word_id: int) -> Optional[Vocab]:
        conds = self._user_filter()
        conds.append(Vocab.id == word_id)
        return await self._session.scalar(select(Vocab).where(*conds))

    async def add(
        self, word: str, meaning: str = "", notes: str = "", example: str = "",
        source: str = "manual", subject: str = "main", mastered: bool = False,
    ) -> tuple[Optional[Vocab], bool]:
        """
        添加单词。
        返回 (vocab, created)：created=True 表示新建，False 表示已存在（去重）。
        """
        existing = await self._session.scalar(
            select(Vocab).where(
                and_(*self._user_filter(), Vocab.word_lower == word.lower(), Vocab.subject == subject)
            )
        )
        if existing:
            return existing, False

        v = Vocab(
            word=word, word_lower=word.lower(), meaning=meaning, notes=notes, example=example,
            source=source, subject=subject, mastered=mastered,
            user_id=self._user_id,
            created_at=datetime.now(),
        )
        self._session.add(v)
        await self._session.commit()
        await self._session.refresh(v)
        return v, True

    async def update(self, word_id: int, **kwargs) -> bool:
        """更新单词"""
        v = await self.get_by_id(word_id)
        if not v:
            return False
        for k, val in kwargs.items():
            if hasattr(v, k):
                setattr(v, k, val)
        await self._session.commit()
        return True

    async def delete(self, word_id: int) -> bool:
        """删除单词"""
        v = await self.get_by_id(word_id)
        if not v:
            return False
        await self._session.delete(v)
        await self._session.commit()
        return True

    async def record_review(self, word_id: int):
        """记录一次复习（原子自增），返回更新后的 Vocab 或 None"""
        from sqlalchemy import update as _sa_update
        await self._session.execute(
            _sa_update(Vocab).where(Vocab.id == word_id).values(
                review_count=Vocab.review_count + 1,
                last_reviewed=_now(),
            )
        )
        await self._session.commit()
        return await self.get_by_id(word_id)

    async def get_stats(self) -> Dict[str, int]:
        """词库统计（按当前用户隔离）"""
        total = await self._session.scalar(
            select(func.count()).select_from(Vocab).where(*self._user_filter())
        ) or 0
        mastered = await self._session.scalar(
            select(func.count()).select_from(Vocab).where(*self._user_filter(), Vocab.mastered == True)
        ) or 0
        need_review = await self._session.scalar(
            select(func.count()).select_from(Vocab).where(
                *self._user_filter(), Vocab.mastered == False, Vocab.review_count == 0
            )
        ) or 0
        return {"total": total, "mastered": mastered, "needReview": need_review}

    async def get_due_review(self) -> Dict[str, Any]:
        """艾宾浩斯复习推荐"""
        import math
        ebbinghaus_intervals = [1, 2, 4, 7, 15, 30]
        now = datetime.now()

        # 已掌握
        mastered_count = await self._session.scalar(
            select(func.count()).select_from(Vocab).where(*self._user_filter(), Vocab.mastered == True)
        ) or 0

        # 需要复习的（未掌握且 review_count == 0 或超过间隔）
        due_words = []
        # 获取未掌握的词
        result = await self._session.execute(
            select(Vocab).where(*self._user_filter(), Vocab.mastered == False).limit(500)
        )
        unmastered = result.scalars().all()

        for v in unmastered:
            if v.review_count == 0:
                due_words.append({
                    "id": v.id, "word": v.word, "meaning": v.meaning,
                    "urgency": "high", "reason": "从未复习",
                    "next_interval_days": 1, "retention_estimate": 30.0,
                })
                continue

            last = v.last_reviewed or v.created_at.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                ref_date = datetime.fromisoformat(last)
            except Exception:
                ref_date = now

            days_since = (now - ref_date).days
            next_interval = ebbinghaus_intervals[min(v.review_count - 1, len(ebbinghaus_intervals) - 1)]
            retention = round(max(5, 100 * math.exp(-days_since / 5)), 1)

            if days_since >= next_interval:
                due_words.append({
                    "id": v.id, "word": v.word, "meaning": v.meaning,
                    "urgency": "high" if days_since >= next_interval * 2 else "medium",
                    "reason": f"距上次复习 {days_since} 天，已超间隔 {next_interval} 天",
                    "next_interval_days": ebbinghaus_intervals[min(v.review_count, len(ebbinghaus_intervals) - 1)],
                    "retention_estimate": retention,
                })

        urgency_order = {"high": 0, "medium": 1}
        due_words.sort(key=lambda w: urgency_order.get(w["urgency"], 2))

        return {
            "due_today": len(due_words),
            "mastered": mastered_count,
            "total": await self._session.scalar(
                select(func.count()).select_from(Vocab).where(*self._user_filter())
            ) or 0,
            "words": due_words,
            "intervals": ebbinghaus_intervals,
        }


# ════════════════════════════════════════════
# StatsRepository — 统计聚合
# ════════════════════════════════════════════

class StatsRepository:
    """DailyStats / DailyWords / DailyAccuracy CRUD（按用户隔离）"""

    def __init__(self, session: AsyncSession, user_id=_UNSET):
        self._session = session
        self._user_id = _resolve_user_id(user_id)

    def _user_filter(self):
        if self._user_id is None:
            return [DailyStats.user_id.is_(None)]
        return [DailyStats.user_id == self._user_id]

    async def get_daily_stats(self) -> List[Dict[str, Any]]:
        """获取过去 14 天每日时长（按当前用户隔离）"""
        result = await self._session.execute(
            select(DailyStats).where(*self._user_filter()).order_by(DailyStats.date.desc()).limit(14)
        )
        rows = result.scalars().all()
        return [{"date": r.date, "minutes": float(r.minutes)} for r in reversed(rows)]

    async def upsert_daily_stats(self, date: str, minutes: float):
        """插入或更新每日时长"""
        existing = await self._session.execute(
            select(DailyStats).where(*self._user_filter(), DailyStats.date == date)
        )
        ds = existing.scalar_one_or_none()
        if ds:
            ds.minutes = minutes
        else:
            ds = DailyStats(date=date, minutes=minutes, user_id=self._user_id)
            self._session.add(ds)
        await self._session.commit()

    async def get_daily_words(self) -> List[Dict[str, Any]]:
        """获取过去 14 天每日词汇量（按当前用户隔离）"""
        result = await self._session.execute(
            select(DailyWords).where(*self._user_filter()).order_by(DailyWords.date.desc()).limit(14)
        )
        rows = result.scalars().all()
        return [{"date": r.date, "new": r.new_words, "total": r.total_words} for r in reversed(rows)]

    async def upsert_daily_words(self, date: str, new_words: int, total_words: int):
        """插入或更新每日词汇量"""
        existing = await self._session.execute(
            select(DailyWords).where(*self._user_filter(), DailyWords.date == date)
        )
        dw = existing.scalar_one_or_none()
        if dw:
            dw.new_words = new_words
            dw.total_words = total_words
        else:
            dw = DailyWords(date=date, new_words=new_words, total_words=total_words, user_id=self._user_id)
            self._session.add(dw)
        await self._session.commit()

    async def get_daily_accuracy(self) -> List[Dict[str, Any]]:
        """获取过去 14 天每日准确率（按当前用户隔离）"""
        result = await self._session.execute(
            select(DailyAccuracy).where(*self._user_filter()).order_by(DailyAccuracy.date.desc()).limit(14)
        )
        rows = result.scalars().all()
        return [{"date": r.date, "accuracy": float(r.accuracy)} for r in reversed(rows)]

    async def upsert_daily_accuracy(self, date: str, accuracy: float):
        """插入或更新每日准确率"""
        existing = await self._session.execute(
            select(DailyAccuracy).where(*self._user_filter(), DailyAccuracy.date == date)
        )
        da = existing.scalar_one_or_none()
        if da:
            da.accuracy = accuracy
        else:
            da = DailyAccuracy(date=date, accuracy=accuracy, user_id=self._user_id)
            self._session.add(da)
        await self._session.commit()

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """仪表盘汇总"""
        today = datetime.now()
        daily_minutes = await self.get_daily_stats()
        daily_words = await self.get_daily_words()
        daily_accuracy = await self.get_daily_accuracy()

        total_minutes = sum(m["minutes"] for m in daily_minutes)
        total_words = daily_words[-1]["total"] if daily_words else 0
        avg_accuracy = round(sum(a["accuracy"] for a in daily_accuracy) / len(daily_accuracy), 1) if daily_accuracy else 0

        return {
            "dailyMinutes": daily_minutes,
            "dailyWords": daily_words,
            "dailyAccuracy": daily_accuracy,
            "summary": {
                "totalMinutes": total_minutes,
                "totalWords": total_words,
                "avgAccuracy": avg_accuracy,
            },
        }


# ════════════════════════════════════════════
# ExerciseRepository — 练习记录
# ════════════════════════════════════════════

class ExerciseRepository:
    """练习记录 CRUD"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_by_session(self, session_id: str) -> List[ExerciseResult]:
        result = await self._session.execute(
            select(ExerciseResult).where(ExerciseResult.session_id == session_id)
            .order_by(ExerciseResult.timestamp.desc())
        )
        return result.scalars().all()


# ════════════════════════════════════════════
# DailyGoalRepository — 每日目标
# ════════════════════════════════════════════

class DailyGoalRepository:
    """每日目标 CRUD（按用户隔离）"""

    # 目标设定使用固定哨兵日期，与每日进度（真实日期）明确区分
    TARGET_DATE = "0000-00-00"

    def __init__(self, session: AsyncSession, user_id=_UNSET):
        self._session = session
        self._user_id = _resolve_user_id(user_id)

    def _user_filter(self):
        if self._user_id is None:
            return [DailyGoal.user_id.is_(None)]
        return [DailyGoal.user_id == self._user_id]

    async def get_target(self) -> Dict[str, int]:
        """获取目标设定（专用哨兵行，按当前用户隔离）"""
        result = await self._session.execute(
            select(DailyGoal).where(*self._user_filter(), DailyGoal.date == self.TARGET_DATE)
        )
        dg = result.scalar_one_or_none()
        if dg:
            return {
                "daily_pomodoros": dg.pomodoros_target,
                "daily_words": dg.words_target,
                "daily_minutes": dg.minutes_target,
            }
        return {"daily_pomodoros": 4, "daily_words": 20, "daily_minutes": 60}

    async def update_target(self, pomodoros: int, words: int, minutes: int):
        """更新目标设定（upsert 哨兵行，按当前用户隔离）"""
        result = await self._session.execute(
            select(DailyGoal).where(*self._user_filter(), DailyGoal.date == self.TARGET_DATE)
        )
        dg = result.scalar_one_or_none()
        if dg:
            dg.pomodoros_target = pomodoros
            dg.words_target = words
            dg.minutes_target = minutes
        else:
            dg = DailyGoal(
                date=self.TARGET_DATE,
                pomodoros_target=pomodoros, words_target=words, minutes_target=minutes,
                user_id=self._user_id,
            )
            self._session.add(dg)
        await self._session.commit()

    async def get_today_progress(self) -> Dict[str, Any]:
        """获取今日进度（按当前用户隔离）"""
        today = datetime.now().strftime("%Y-%m-%d")
        result = await self._session.execute(
            select(DailyGoal).where(*self._user_filter(), DailyGoal.date == today)
        )
        dg = result.scalar_one_or_none()
        if not dg:
            # 创建今日记录
            dg = DailyGoal(
                date=today, pomodoros_done=0, words_done=0, minutes_done=0,
                user_id=self._user_id,
            )
            self._session.add(dg)
            await self._session.commit()

        target = await self.get_target()
        return {
            "target": {
                "pomodoros": target["daily_pomodoros"],
                "words": target["daily_words"],
                "minutes": target["daily_minutes"],
            },
            "progress": {
                "pomodoros_done": dg.pomodoros_done or 0,
                "words_learned": dg.words_done or 0,
                "minutes_studied": dg.minutes_done or 0,
            },
            "date": today,
        }

    async def update_today_progress(self, pomodoros: int = 0, words: int = 0, minutes: int = 0):
        """更新今日进度（原子增量，避免并发读-改-写覆盖）"""
        from sqlalchemy import update as _sa_update, func as _sa_func
        today = datetime.now().strftime("%Y-%m-%d")
        vals = {}
        if pomodoros:
            vals["pomodoros_done"] = _sa_func.coalesce(DailyGoal.pomodoros_done, 0) + pomodoros
        if words:
            vals["words_done"] = _sa_func.coalesce(DailyGoal.words_done, 0) + words
        if minutes:
            vals["minutes_done"] = _sa_func.coalesce(DailyGoal.minutes_done, 0) + minutes
        if not vals:
            return
        stmt = _sa_update(DailyGoal).where(*self._user_filter(), DailyGoal.date == today).values(**vals)
        res = await self._session.execute(stmt)
        if res.rowcount == 0:
            self._session.add(DailyGoal(
                date=today,
                pomodoros_done=pomodoros, words_done=words, minutes_done=minutes,
                user_id=self._user_id,
            ))
        await self._session.commit()


# ════════════════════════════════════════════
# JSON → DB 迁移
# ════════════════════════════════════════════

async def migrate_json_to_db(storage_dir: Optional[str] = None):
    """
    从现有 JSON 文件自动导入数据到 SQLite。
    仅在首次启动时有效（已有数据则跳过）。
    """
    import importlib
    from .session import get_async_session, get_engine

    await get_engine()

    # 确定 storage_dir
    if not storage_dir:
        env = os.environ.get("LAS_DATA_DIR")
        if env:
            storage_dir = env
        elif getattr(sys, "frozen", False):
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            storage_dir = str(Path(base) / "KnowSubtle" / "Data")
        else:
            storage_dir = str(Path(__file__).resolve().parent.parent.parent / ".learning_memory")

    storage_path = Path(storage_dir)
    if not storage_path.exists():
        logger.debug("Storage directory does not exist, skipping migration")
        return

    migrated = False

    async with get_async_session() as s:
        # ── 迁移 vocabulary.json ──
        vocab_file = storage_path / "vocabulary.json"
        if vocab_file.exists() and not (await s.execute(select(func.count()).select_from(Vocab))).scalar_one_or_none():
            try:
                data = json.loads(vocab_file.read_text(encoding="utf-8-sig"))
                for item in data:
                    if isinstance(item, dict):
                        v = Vocab(
                            word=item.get("word", ""),
                            meaning=item.get("meaning", ""),
                            notes=item.get("notes", ""),
                            example=item.get("example", ""),
                            source=item.get("source", "manual"),
                            subject=item.get("subject", "main"),
                            mastered=bool(item.get("mastered", False)),
                            review_count=item.get("review_count", 0),
                            last_reviewed=item.get("last_reviewed", ""),
                            created_at=datetime.now(),
                        )
                        s.add(v)
                await s.commit()
                migrated = True
                logger.info(f"迁移词库: {len(data)} 条")
            except Exception as e:
                logger.error(f"迁移 vocabulary.json 失败: {e}")

        # ── 迁移 daily_goals.json ──
        goals_file = storage_path / "daily_goals.json"
        if goals_file.exists() and not (await s.execute(select(func.count()).select_from(DailyGoal))).scalar_one_or_none():
            try:
                data = json.loads(goals_file.read_text(encoding="utf-8-sig"))
                # 目标设定
                dg = DailyGoal(
                    date="0000-00-00",
                    pomodoros_target=data.get("daily_pomodoros", 4),
                    words_target=data.get("daily_words", 20),
                    minutes_target=data.get("daily_minutes", 60),
                )
                s.add(dg)

                # 历史进度
                for date_str, progress in data.get("history", {}).items():
                    day = DailyGoal(
                        date=date_str,
                        pomodoros_target=data.get("daily_pomodoros", 4),
                        words_target=data.get("daily_words", 20),
                        minutes_target=data.get("daily_minutes", 60),
                        pomodoros_done=progress.get("pomodoros_done", 0),
                        words_done=progress.get("words_learned", 0),
                        minutes_done=progress.get("minutes_studied", 0),
                    )
                    s.add(day)

                await s.commit()
                migrated = True
                logger.info("迁移每日目标")
            except Exception as e:
                logger.error(f"迁移 daily_goals.json 失败: {e}")

        # ── 迁移 stats_history.json ──
        stats_file = storage_path / "stats_history.json"
        if stats_file.exists() and not (await s.execute(select(func.count()).select_from(DailyStats))).scalar_one_or_none():
            try:
                data = json.loads(stats_file.read_text(encoding="utf-8-sig"))
                for item in data.get("daily_minutes", []):
                    ds = DailyStats(date=item.get("date", ""), minutes=item.get("minutes", 0))
                    s.add(ds)
                for item in data.get("daily_words", []):
                    dw = DailyWords(date=item.get("date", ""), new_words=item.get("new", 0), total_words=item.get("total", 0))
                    s.add(dw)
                for item in data.get("daily_accuracy", []):
                    da = DailyAccuracy(date=item.get("date", ""), accuracy=item.get("accuracy", 0))
                    s.add(da)
                await s.commit()
                migrated = True
                logger.info("迁移统计数据")
            except Exception as e:
                logger.error(f"迁移 stats_history.json 失败: {e}")

        # ── 迁移 checkpoint_*.json（会话上下文） ──
        checkpoint_files = sorted(storage_path.glob("checkpoint_*.json"))
        if checkpoint_files:
            session_count = await s.execute(
                select(func.count()).select_from(Session)
            )
            if not session_count.scalar_one_or_none():
                for cp in checkpoint_files:
                    try:
                        raw = cp.read_text(encoding="utf-8-sig")
                        data = json.loads(raw)
                        sid = data.get("session_id") or cp.stem.replace("checkpoint_", "")
                        phase = data.get("current_phase", "profiling")
                        s.add(Session(
                            session_id=sid,
                            current_phase=phase,
                            metadata_json=raw,
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                        ))
                        migrated = True
                        logger.info(f"迁移会话检查点: {sid}")
                    except Exception as e:
                        logger.error(f"迁移 {cp.name} 失败: {e}")
                await s.commit()

    if migrated:
        logger.info("JSON 数据迁移完成")
    else:
        logger.info("无需迁移（数据库已有数据或无 JSON 文件）")


# ════════════════════════════════════════════
# User Authentication Repository
# ════════════════════════════════════════════

import hashlib as _hashlib
import secrets as _secrets
from datetime import timedelta as _timedelta

from .models import User, AuthToken


class UserRepository:
    """用户认证 Repository"""

    def __init__(self, session: AsyncSession):
        self.s = session

    # ── 密码工具 ──

    @staticmethod
    def _hash_password(password: str) -> tuple[str, str]:
        """返回 (hash, salt)，使用 SHA-256 + 16 字节随机盐。"""
        salt = _secrets.token_hex(16)
        h = _hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return h, salt

    @staticmethod
    def _verify_password(password: str, stored_hash: str, salt: str) -> bool:
        h = _hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return h == stored_hash

    # ── 注册 ──

    async def register(self, username: str, email: str, password: str, display_name: str = "") -> User:
        """注册新用户，返回 User 对象。用户名/邮箱重复时返回 None（由调用方处理错误消息）。"""
        pw_hash, pw_salt = self._hash_password(password)
        user = User(
            username=username,
            email=email,
            password_hash=pw_hash,
            password_salt=pw_salt,
            display_name=display_name or username,
            avatar="👤",
            created_at=datetime.now(),
            is_active=True,
        )
        self.s.add(user)
        await self.s.commit()
        await self.s.refresh(user)
        return user

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.s.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.s.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.s.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    # ── 登录 / Token ──

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        """验证用户名+密码，成功返回 User，失败返回 None。"""
        user = await self.get_by_username(username)
        if not user:
            return None
        if not self._verify_password(password, user.password_hash, user.password_salt):
            return None
        return user

    async def create_token(self, user_id: int, ttl_hours: int = 24 * 30) -> AuthToken:
        """创建长效 token（默认 30 天），并吊销该用户其他活跃 token（单设备登录策略）。"""
        token_str = _secrets.token_hex(32)
        expires = datetime.now() + _timedelta(hours=ttl_hours)
        token = AuthToken(
            user_id=user_id,
            token=token_str,
            created_at=datetime.now(),
            expires_at=expires,
            is_revoked=False,
        )
        self.s.add(token)
        await self.s.commit()  # 先落库，确保 keep_token 存在
        # 吊销除当前新 token 外的所有活跃 token（单设备登录）
        await self.revoke_other_tokens(user_id, token_str)
        await self.s.refresh(token)
        return token

    async def get_user_by_token(self, token_str: str) -> Optional[User]:
        """按 token 查用户，跳过过期/已吊销的。"""
        result = await self.s.execute(
            select(AuthToken).where(
                AuthToken.token == token_str,
                AuthToken.is_revoked == False,  # noqa: E712
                AuthToken.expires_at > datetime.now(),
            )
        )
        token = result.scalar_one_or_none()
        if not token:
            return None
        # 顺便查用户
        user_result = await self.s.execute(select(User).where(User.id == token.user_id))
        return user_result.scalar_one_or_none()

    async def revoke_token(self, token_str: str) -> bool:
        """吊销指定 token。"""
        result = await self.s.execute(select(AuthToken).where(AuthToken.token == token_str))
        token = result.scalar_one_or_none()
        if not token:
            return False
        token.is_revoked = True
        await self.s.commit()
        return True

    async def revoke_all_user_tokens(self, user_id: int) -> int:
        """吊销用户所有 token，返回影响行数。"""
        result = await self.s.execute(
            select(AuthToken).where(
                AuthToken.user_id == user_id,
                AuthToken.is_revoked == False,  # noqa: E712
            )
        )
        tokens = result.scalars().all()
        count = 0
        for t in tokens:
            t.is_revoked = True
            count += 1
        await self.s.commit()
        return count

    # ── 单设备登录（吊销其他活跃 token）──

    async def revoke_other_tokens(self, user_id: int, keep_token: str) -> int:
        """吊销该用户除 keep_token 之外的所有活跃 token，返回影响行数。"""
        result = await self.s.execute(
            select(AuthToken).where(
                AuthToken.user_id == user_id,
                AuthToken.is_revoked == False,  # noqa: E712
                AuthToken.token != keep_token,
            )
        )
        tokens = result.scalars().all()
        count = 0
        for t in tokens:
            t.is_revoked = True
            count += 1
        await self.s.commit()
        return count

    # ── 资料更新 ──

    async def update_last_login(self, user_id: int) -> None:
        """登录成功时刷新 last_login。"""
        user = await self.get_by_id(user_id)
        if user:
            user.last_login = datetime.now()
            await self.s.commit()

    async def update_profile(self, user_id: int, display_name: Optional[str] = None,
                             avatar: Optional[str] = None) -> Optional[User]:
        """更新显示名称 / 头像，返回更新后的 User。"""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if display_name is not None:
            user.display_name = display_name[:64]
        if avatar is not None:
            user.avatar = avatar[:8]
        await self.s.commit()
        await self.s.refresh(user)
        return user

    async def change_password(self, user_id: int, old_password: str,
                              new_password: str) -> bool:
        """校验原密码后更新密码；原密码错误返回 False。"""
        user = await self.get_by_id(user_id)
        if not user:
            return False
        if not self._verify_password(old_password, user.password_hash, user.password_salt):
            return False
        pw_hash, pw_salt = self._hash_password(new_password)
        user.password_hash = pw_hash
        user.password_salt = pw_salt
        await self.s.commit()
        return True