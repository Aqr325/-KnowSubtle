"""
TeamOrchestrator — 多智能体团队编排器

负责：
1. 接收用户学习目标
2. 依次调度 6 个 Agent 协同工作
3. 管理阶段状态流转（画像 → 诊断 → 资源 → 规划 → 辅导 → 评测）
4. 维护跨 Agent 的上下文共享
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from metagpt.roles import Role
from metagpt.schema import Message

from learning_agent_system.agents.learner_profiler import LearnerProfiler
from learning_agent_system.agents.resource_generator import ResourceGenerator
from learning_agent_system.agents.learning_planner import LearningPlanner
from learning_agent_system.agents.exercise_evaluator import ExerciseEvaluator
from learning_agent_system.agents.learning_tutor import LearningTutor
from learning_agent_system.agents.knowledge_base import KnowledgeBase
from learning_agent_system.schema import (
    LearningGoal,
    LearnerProfile,
    KnowledgeDiagnosis,
    ResourcePlan,
    LearningPath,
    LearningModule,
    TutorSession,
    ExerciseResult,
    Achievement,
    MistakeRecord,
    KnowledgeDecay,
    StudyStreak,
    ReportCard,
    MultiGoalProgress,
)
from learning_agent_system.actions.mistake_analyzer import MistakeAnalyzer, MistakeAnalysis
from learning_agent_system.actions.achievement_checker import AchievementChecker, AchievementCheckResult
from learning_agent_system.actions.knowledge_graph_generator import KnowledgeGraphGenerator, GraphExportFormat
from learning_agent_system.memory.longterm_memory import LongTermMemory
from learning_agent_system.memory.role_zero_memory import RoleZeroMemory
from learning_agent_system.configs.system_config import SystemConfig

logger = logging.getLogger(__name__)

# 演示模式：local_metagpt stub 在启动时设置该环境变量（无真实大模型时）。
# 此模式下流水线/辅导/评测直接构造合法占位对象，保证离线桌面版核心流程可用且不崩溃。
DEMO_MODE = os.environ.get("METAGPT_STUBBED") == "1"


def _safe_from_dict(cls, data):
    """安全反序列化单对象：优先 Pydantic model_validate，失败返回 None。"""
    if not data:
        return None
    try:
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        if hasattr(cls, "from_dict"):
            return cls.from_dict(data)
        return cls(**data)
    except Exception as e:
        logger.warning(f"反序列化 {getattr(cls, '__name__', cls)} 失败，使用默认: {e}")
        return None


def _safe_list_from_dict(cls, items):
    """安全反序列化对象列表（坏条目跳过）。"""
    out = []
    for it in (items or []):
        obj = _safe_from_dict(cls, it)
        if obj is not None:
            out.append(obj)
    return out


class Phase(Enum):
    """系统工作阶段"""
    PROFILING = "profiling"           # 画像师 — 学习者建模
    DIAGNOSIS = "diagnosis"           # 知识官 — 知识诊断
    RESOURCE = "resource"             # 资源师 — 资源生成
    PLANNING = "planning"             # 规划师 — 路径规划
    TUTORING = "tutoring"             # 导师 — 辅导对话
    EVALUATION = "evaluation"
    COMPLETED = "completed"         # 流水线完成（终态，供前端判定就绪）         # 评测师 — 练习评测


@dataclass
class SessionContext:
    """一次完整学习会话的上下文"""

    session_id: str = field(default_factory=lambda: f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    learning_goal: Optional[LearningGoal] = None
    learner_profile: Optional[LearnerProfile] = None
    diagnosis: Optional[KnowledgeDiagnosis] = None
    resource_plan: Optional[ResourcePlan] = None
    learning_path: Optional[LearningPath] = None
    tutor_sessions: List[TutorSession] = field(default_factory=list)
    exercise_results: List[ExerciseResult] = field(default_factory=list)
    current_phase: Phase = Phase.PROFILING
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 新增功能数据
    achievements: List[Achievement] = field(default_factory=list)
    mistake_records: List[MistakeRecord] = field(default_factory=list)
    knowledge_decay: List[KnowledgeDecay] = field(default_factory=list)
    study_streak: StudyStreak = field(default_factory=StudyStreak)
    multi_goals: List[MultiGoalProgress] = field(default_factory=list)
    graph_data: Optional[GraphExportFormat] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_phase": self.current_phase.value,
            "learning_goal": self.learning_goal.model_dump() if self.learning_goal else None,
            "learner_profile": self.learner_profile.model_dump() if self.learner_profile else None,
            "diagnosis": self.diagnosis.model_dump() if self.diagnosis else None,
            "resource_plan": self.resource_plan.model_dump() if self.resource_plan else None,
            "learning_path": self.learning_path.model_dump() if self.learning_path else None,
            # 完善：此前仅存 len 计数，tutor_sessions / exercise_results 内容从未持久化，现已补齐
            "tutor_sessions": [t.model_dump() for t in self.tutor_sessions],
            "exercise_results": [e.model_dump() for e in self.exercise_results],
            "metadata": self.metadata,
            # 完善：此前遗漏持久化的字段（成就/错题/衰减/连续天数/多目标/图谱）
            "achievements": [a.model_dump() for a in self.achievements],
            "mistake_records": [m.model_dump() for m in self.mistake_records],
            "knowledge_decay": [k.model_dump() for k in self.knowledge_decay],
            "study_streak": self.study_streak.model_dump() if self.study_streak else None,
            "multi_goals": [g.model_dump() for g in self.multi_goals],
            "graph_data": self.graph_data.model_dump() if self.graph_data else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        data = data or {}
        try:
            current_phase = Phase(data.get("current_phase", "profiling"))
        except Exception:
            current_phase = Phase.PROFILING
        ctx = cls(session_id=data.get("session_id", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"))
        ctx.current_phase = current_phase
        ctx.learning_goal = _safe_from_dict(LearningGoal, data.get("learning_goal"))
        ctx.learner_profile = _safe_from_dict(LearnerProfile, data.get("learner_profile"))
        ctx.diagnosis = _safe_from_dict(KnowledgeDiagnosis, data.get("diagnosis"))
        ctx.resource_plan = _safe_from_dict(ResourcePlan, data.get("resource_plan"))
        ctx.learning_path = _safe_from_dict(LearningPath, data.get("learning_path"))
        ctx.tutor_sessions = _safe_list_from_dict(TutorSession, data.get("tutor_sessions", []))
        ctx.exercise_results = _safe_list_from_dict(ExerciseResult, data.get("exercise_results", []))
        ctx.metadata = data.get("metadata", {})
        # 完善：恢复此前遗漏的字段
        ctx.achievements = _safe_list_from_dict(Achievement, data.get("achievements", []))
        ctx.mistake_records = _safe_list_from_dict(MistakeRecord, data.get("mistake_records", []))
        ctx.knowledge_decay = _safe_list_from_dict(KnowledgeDecay, data.get("knowledge_decay", []))
        ctx.study_streak = _safe_from_dict(StudyStreak, data.get("study_streak"))
        ctx.multi_goals = _safe_list_from_dict(MultiGoalProgress, data.get("multi_goals", []))
        ctx.graph_data = _safe_from_dict(GraphExportFormat, data.get("graph_data"))
        return ctx


class TeamOrchestrator:
    """
    多智能体团队编排器

    工作流程（流水线）：
    user_input
      → [Profiler] learner_profile
      → [KnowledgeBase] knowledge_diagnosis
      → [ResourceGenerator] resource_plan
      → [LearningPlanner] learning_path
      → [LearningTutor] tutor_sessions (循环)
      → [ExerciseEvaluator] exercise_results
    """

    def __init__(
        self,
        storage_dir: str = ".learning_memory",
        llm_config: Optional[Dict[str, Any]] = None,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 长期记忆（文件持久化）— 使用与 storage_dir 一致的用户可写目录，
        # 避免装在 Program Files 等只读位置时 os.makedirs 报 PermissionError
        config = SystemConfig.from_env()
        self.long_term_memory = LongTermMemory(config=config, dir_override=str(self.storage_dir / "longterm"))

        # 配置
        self.llm_config = llm_config or {}

        # 当前会话上下文
        self.context: Optional[SessionContext] = None

        # Agent 实例（懒加载）
        self._agents: Dict[str, Role] = {}
        
        # 新增功能组件
        self._mistake_analyzer = MistakeAnalyzer()
        self._achievement_checker = AchievementChecker()
        self._graph_generator = KnowledgeGraphGenerator()

        logger.info(f"TeamOrchestrator initialized, storage: {self.storage_dir}")

    def _get_agent(self, name: str) -> Role:
        """获取或创建 Agent 实例（懒加载 + 缓存）"""
        if name not in self._agents:
            agent_map = {
                "profiler": LearnerProfiler,
                "knowledge_base": KnowledgeBase,
                "resource_generator": ResourceGenerator,
                "learning_planner": LearningPlanner,
                "tutor": LearningTutor,
                "evaluator": ExerciseEvaluator,
            }
            if name not in agent_map:
                raise ValueError(f"Unknown agent: {name}")
            cls = agent_map[name]
            self._agents[name] = cls()
        return self._agents[name]

    async def run_full_pipeline(self, learning_goal: str) -> SessionContext:
        """
        执行完整学习流水线（全阶段）

        Args:
            learning_goal: 用户的学习目标/需求描述

        Returns:
            完整的 SessionContext
        """
        self.context = SessionContext()
        self.context.learning_goal = LearningGoal(description=learning_goal)

        logger.info(f"=== Starting full pipeline for goal: {learning_goal[:50]}... ===")

        # 演示模式（离线桌面版）：不调用真实大模型，直接构造合法占位上下文，
        # 使「创建学习目标 → 仪表盘可见 → 辅导/评测可走通」在无需 API Key 时也能用。
        if DEMO_MODE:
            logger.info("DEMO_MODE: 构建演示会话（不调用大模型）")
            self.context = self._build_demo_context(learning_goal)
            self.context.current_phase = Phase.COMPLETED
            self._save_checkpoint()
            return self.context

        # Phase 1: 画像 — 学习者建模
        self.context.current_phase = Phase.PROFILING
        self.context.learner_profile = await self._run_profiler()
        self._save_checkpoint()

        # Phase 2: 诊断 — 知识诊断
        self.context.current_phase = Phase.DIAGNOSIS
        self.context.diagnosis = await self._run_diagnosis()
        self._save_checkpoint()

        # Phase 3: 资源 — 个性化资源生成
        self.context.current_phase = Phase.RESOURCE
        self.context.resource_plan = await self._run_resource_generation()
        self._save_checkpoint()

        # Phase 4: 规划 — 学习路径规划
        self.context.current_phase = Phase.PLANNING
        self.context.learning_path = await self._run_planning()
        self.context.current_phase = Phase.COMPLETED
        self._save_checkpoint()

        logger.info(f"=== Full pipeline completed for session: {self.context.session_id} ===")
        return self.context

    def _build_demo_context(self, learning_goal: str) -> SessionContext:
        """演示模式：直接构造合法占位上下文，使离线桌面版核心流程可用。"""
        ctx = SessionContext()
        ctx.learning_goal = LearningGoal(description=learning_goal)
        ctx.learner_profile = LearnerProfile(name="演示学习者", learning_style="visual")
        ctx.diagnosis = KnowledgeDiagnosis(
            summary="演示模式：未连接大模型，已生成占位诊断。配置 LLM API Key 后可获得真实诊断。",
            weak_points=["示例薄弱点"],
            strengths=["示例优势点"],
        )
        ctx.resource_plan = ResourcePlan(
            topics_covered=["演示资源主题"],
            resource_counts={"article": 1, "exercise": 1},
        )
        ctx.learning_path = LearningPath(
            goals=[learning_goal],
            modules=[
                LearningModule(id="m1", title="核心词汇与词根词缀", topics=["词根词缀"], estimated_hours=2.0),
                LearningModule(id="m2", title="高频搭配与短语", topics=["搭配"], estimated_hours=1.5),
                LearningModule(id="m3", title="阅读强化与真题演练", topics=["阅读"], estimated_hours=2.5),
            ],
            progress=0.0,
        )
        ctx.current_phase = Phase.PLANNING
        return ctx

    async def run_tutor_loop(self, rounds: int = 1) -> List[TutorSession]:
        """
        执行辅导循环

        Args:
            rounds: 辅导轮次

        Returns:
            辅导会话列表
        """
        if not self.context or not self.context.learning_path:
            raise ValueError("Must complete full pipeline before tutor loop")

        self.context.current_phase = Phase.TUTORING
        sessions = []
        for i in range(rounds):
            session = await self._run_tutor_round(i + 1)
            sessions.append(session)
            self.context.tutor_sessions.append(session)
            self._save_checkpoint()
        return sessions

    async def run_evaluation(self, student_answer: str) -> ExerciseResult:
        """
        运行练习评测

        Args:
            student_answer: 学生提交的答案

        Returns:
            评测结果
        """
        if not self.context:
            raise ValueError("Must complete full pipeline before evaluation")

        # 学习路径未生成时（画像已建但路径未生成的半完成态）拒绝评测，
        # 避免非 demo 模式下 _run_evaluation 访问 None.to_dict() 导致 500。
        if not self.context.learning_path:
            raise ValueError("Learning path not generated yet, cannot evaluate")

        # 演示模式：构造合法占位评测结果（ExerciseResult 含必填字段）
        if DEMO_MODE:
            result = ExerciseResult(
                exercise_id=f"demo_{len(self.context.exercise_results) + 1}",
                learner_answer=student_answer,
                correct_answer="演示答案（需配置 API Key 获得真实评测）",
                is_correct=False,
                score=0.0,
            )
            self.context.exercise_results.append(result)
            self._save_checkpoint()
            return result

        self.context.current_phase = Phase.EVALUATION
        result = await self._run_evaluation(student_answer)
        self.context.exercise_results.append(result)
        self._save_checkpoint()
        
        # 增强：自动记录练习结果到成就系统
        self._achievement_checker.record_result(result)
        
        # 增强：如果错误，触发错题分析
        if not result.is_correct:
            mistake_analysis = await self._mistake_analyzer.analyze(result, self.context.diagnosis.weak_points if self.context.diagnosis else [])
            if mistake_analysis.mistake.error_type != "correct":
                self.context.mistake_records.append(mistake_analysis.mistake)
                self._achievement_checker.record_mistake()
            
        self._save_checkpoint()
        return result

    async def run_multi_goal_progress(self, goals: List[LearningGoal]) -> Dict[str, Any]:
        """
        多目标并行学习进度管理
        
        Args:
            goals: 多个学习目标列表
            
        Returns:
            多目标进度字典
        """
        progress_map = {}
        for goal in goals:
            progress = MultiGoalProgress(
                goal_id=goal.description[:20],
                description=goal.description,
                priority=goal.priority,
            )
            progress_map[progress.goal_id] = progress
            if self.context:
                self.context.multi_goals.append(progress)
        return {gid: gp.to_dict() for gid, gp in progress_map.items()}

    async def generate_report_card(self) -> ReportCard:
        """
        生成学习报告卡
        
        Returns:
            ReportCard 对象
        """
        if not self.context:
            raise ValueError("No active session")
            
        # 检查成就解锁
        check_result = self._achievement_checker.check(streak=self.context.study_streak)
        self.context.achievements.extend(check_result.new_achievements)
        
        # 计算统计数据
        correct_count = sum(1 for r in self.context.exercise_results if r.is_correct)
        total_count = len(self.context.exercise_results)
        avg_score = sum(r.score for r in self.context.exercise_results) / total_count if total_count > 0 else 0.0
        
        # 生成知识图谱
        if self.context.diagnosis:
            status_list = []
            for topic, level in self.context.diagnosis.diagnosed_topics.items():
                status_list.append(KnowledgeStatus(topic=topic, mastery_level=level))
            graph = self._graph_generator.generate(status_list, None)
            self.context.graph_data = graph
            
        return ReportCard(
            session_id=self.context.session_id,
            learner_name=self.context.learner_profile.name if self.context.learner_profile else "Unknown",
            date_range={"start": self.context.learning_goal.created_at if self.context.learning_goal else ""},
            total_hours=sum(m.estimated_hours for m in (self.context.learning_path.modules or [])) if self.context.learning_path else 0,
            topics_covered=list(self.context.diagnosis.diagnosed_topics.keys()) if self.context.diagnosis else [],
            exercises_completed=total_count,
            exercises_correct=correct_count,
            average_score=avg_score,
            weak_points=self.context.diagnosis.weak_points if self.context.diagnosis else [],
            achievements_unlocked=check_result.new_achievements,
            mistakes_reviewed=self.context.mistake_records,
            streak_info=self.context.study_streak,
        )

    # ---- 各阶段内部实现 ----

    async def _run_profiler(self) -> LearnerProfile:
        """Phase 1: 画像师 — 学习者建模"""
        agent = self._get_agent("profiler")
        goal_json = json.dumps(self.context.learning_goal.to_dict(), ensure_ascii=False)
        msg = Message(content=goal_json, role="user")
        rsp = await agent.run(msg)
        return LearnerProfile.from_json(rsp.content)

    async def _run_diagnosis(self) -> KnowledgeDiagnosis:
        """Phase 2: 知识官 — 知识诊断"""
        agent = self._get_agent("knowledge_base")
        context = {
            "learner_profile": self.context.learner_profile.to_dict(),
            "learning_goal": self.context.learning_goal.to_dict(),
        }
        msg = Message(content=json.dumps(context, ensure_ascii=False), role="user")
        rsp = await agent.run(msg)
        return KnowledgeDiagnosis.from_json(rsp.content)

    async def _run_resource_generation(self) -> ResourcePlan:
        """Phase 3: 资源师 — 个性化资源生成"""
        agent = self._get_agent("resource_generator")
        context = {
            "learner_profile": self.context.learner_profile.to_dict(),
            "diagnosis": self.context.diagnosis.to_dict(),
        }
        msg = Message(content=json.dumps(context, ensure_ascii=False), role="user")
        rsp = await agent.run(msg)
        return ResourcePlan.from_json(rsp.content)

    async def _run_planning(self) -> LearningPath:
        """Phase 4: 规划师 — 学习路径规划"""
        agent = self._get_agent("learning_planner")
        context = {
            "learner_profile": self.context.learner_profile.to_dict(),
            "diagnosis": self.context.diagnosis.to_dict(),
            "resource_plan": self.context.resource_plan.to_dict(),
        }
        msg = Message(content=json.dumps(context, ensure_ascii=False), role="user")
        rsp = await agent.run(msg)
        return LearningPath.from_json(rsp.content)

    async def _run_tutor_round(self, round_num: int, history: list = None) -> TutorSession:
        """辅导循环 — 单轮"""
        # 演示模式：返回占位辅导内容（前端聊天接口会用到本方法）
        if DEMO_MODE:
            return TutorSession(
                round_number=round_num,
                topic="演示辅导",
                explanation="演示模式：未连接大模型，无法提供真实苏格拉底辅导。请在 Config 中配置 LLM API Key 后重试。",
                next_steps=["配置 LLM API Key", "体验仪表盘与目标追踪", "使用词库与番茄钟"],
            )
        agent = self._get_agent("tutor")
        context = {
            "learning_path": self.context.learning_path.to_dict(),
            "round": round_num,
            "previous_sessions": [s.to_dict() for s in self.context.tutor_sessions],
        }
        msg = Message(content=json.dumps(context, ensure_ascii=False), role="user")
        rsp = await agent.run(msg)
        return TutorSession.from_json(rsp.content)

    async def _run_evaluation(self, student_answer: str) -> ExerciseResult:
        """评测 — 单次"""
        agent = self._get_agent("evaluator")
        context = {
            "learning_path": self.context.learning_path.to_dict(),
            "student_answer": student_answer,
        }
        msg = Message(content=json.dumps(context, ensure_ascii=False), role="user")
        rsp = await agent.run(msg)
        return ExerciseResult.from_json(rsp.content)

    # ---- 持久化支持（SQLite 数据库，替代散落的 JSON 文件） ----

    def _db_session_factory(self):
        """获取同步 Session 工厂（在 async 事件循环内安全使用，不冲突 async 引擎）"""
        from sqlalchemy.orm import sessionmaker
        from learning_agent_system.database.session import get_sync_engine
        return sessionmaker(get_sync_engine(), expire_on_commit=False)

    def _save_checkpoint(self) -> None:
        """保存当前阶段检查点到数据库（Session.metadata_json 存完整 SessionContext）。"""
        if not self.context:
            return
        from sqlalchemy import select
        from learning_agent_system.database.models import Session as SessionModel

        data = json.dumps(self.context.to_dict(), ensure_ascii=False)
        phase = self.context.current_phase.value if hasattr(self.context.current_phase, "value") else str(self.context.current_phase)
        sid = self.context.session_id

        try:
            factory = self._db_session_factory()
            with factory() as s:
                existing = s.execute(
                    select(SessionModel).where(SessionModel.session_id == sid)
                ).scalar_one_or_none()
                now = datetime.now()
                if existing:
                    existing.metadata_json = data
                    existing.current_phase = phase
                    existing.updated_at = now
                else:
                    s.add(SessionModel(
                        session_id=sid,
                        current_phase=phase,
                        metadata_json=data,
                        created_at=now,
                        updated_at=now,
                    ))
                s.commit()
        except Exception as e:
            logger.error(f"Checkpoint save to DB failed: {e}")

    def _validate_session_id(self, session_id: str) -> bool:
        """白名单校验 session_id，仅允许字母、数字、下划线、中划线、点号。防止路径穿越。"""
        import re
        return bool(re.match(r'^[a-zA-Z0-9_\-\.]+$', session_id))

    def load_session(self, session_id: str) -> Optional[SessionContext]:
        """从数据库加载指定会话（损坏时安全降级）"""
        if not self._validate_session_id(session_id):
            logger.warning(f"Invalid session_id (path traversal attempt): {session_id}")
            return None
        from sqlalchemy import select
        from learning_agent_system.database.models import Session as SessionModel

        try:
            factory = self._db_session_factory()
            with factory() as s:
                rec = s.execute(
                    select(SessionModel).where(SessionModel.session_id == session_id)
                ).scalar_one_or_none()
            if not rec or not rec.metadata_json:
                logger.warning(f"Session not found in DB: {session_id}")
                return None
            data = json.loads(rec.metadata_json)
            self.context = SessionContext.from_dict(data)
            return self.context
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    def list_sessions(self) -> List[str]:
        """列出所有历史会话（从数据库）"""
        from sqlalchemy import select
        from learning_agent_system.database.models import Session as SessionModel
        try:
            factory = self._db_session_factory()
            with factory() as s:
                rows = s.execute(select(SessionModel.session_id)).scalars().all()
            return list(rows)
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []

    def get_summary(self) -> Dict[str, Any]:
        """获取当前会话摘要"""
        if not self.context:
            return {"status": "no_active_session"}
        
        summary = {
            "session_id": self.context.session_id,
            "current_phase": self.context.current_phase.value,
            "goal": self.context.learning_goal.description if self.context.learning_goal else None,
            "has_profile": self.context.learner_profile is not None,
            "has_diagnosis": self.context.diagnosis is not None,
            "has_resource_plan": self.context.resource_plan is not None,
            "has_learning_path": self.context.learning_path is not None,
            "tutor_rounds": len(self.context.tutor_sessions),
            "exercise_count": len(self.context.exercise_results),
            "achievement_count": len(self.context.achievements),
            "mistake_count": len(self.context.mistake_records),
            "streak_days": self.context.study_streak.current_streak if self.context.study_streak else 0,
            "has_graph_data": self.context.graph_data is not None,
        }
        
        # 添加多目标进度
        if self.context.multi_goals:
            summary["multi_goals"] = [g.to_dict() for g in self.context.multi_goals]
            
        return summary

    def record_study_activity(self) -> None:
        """记录学习活动（用于连续天数追踪）"""
        if self.context:
            self.context.study_streak.record_today()
            self._save_checkpoint()