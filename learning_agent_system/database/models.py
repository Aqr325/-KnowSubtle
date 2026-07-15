"""
KnowSubtle Database Models — SQLAlchemy ORM

SQLite 数据库，异步引擎，支持桌面应用打包。
所有 Model 对应原有的 JSON 实体。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """ORM 基类"""
    __allow_unmapped__ = True  # 允许非 Mapped[] 风格的类型标注


# ════════════════════════════════════════════
# Session 相关表
# ════════════════════════════════════════════

class Session(Base):
    """学习会话表"""
    __tablename__ = "sessions"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: str = Column(String(64), unique=True, nullable=False, index=True)
    current_phase: str = Column(String(32), default="profiling")
    created_at: datetime = Column(DateTime, default=datetime.now, nullable=False)
    updated_at: datetime = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    user_id: int = Column(Integer, nullable=True, index=True)  # 账号隔离：NULL = 匿名共享

    # 一对一关系
    learning_goal: "LearningGoal" = relationship("LearningGoal", back_populates="session", uselist=False, cascade="all, delete-orphan")
    learner_profile: "LearnerProfile" = relationship("LearnerProfile", back_populates="session", uselist=False, cascade="all, delete-orphan")
    diagnosis: "KnowledgeDiagnosis" = relationship("KnowledgeDiagnosis", back_populates="session", uselist=False, cascade="all, delete-orphan")
    resource_plan: "ResourcePlan" = relationship("ResourcePlan", back_populates="session", uselist=False, cascade="all, delete-orphan")
    learning_path: "LearningPath" = relationship("LearningPath", back_populates="session", uselist=False, cascade="all, delete-orphan")
    study_streak: "StudyStreak" = relationship("StudyStreak", back_populates="session", uselist=False, cascade="all, delete-orphan")

    # 一对多关系
    tutor_sessions: List["TutorSession"] = relationship("TutorSession", back_populates="session", cascade="all, delete-orphan")
    exercise_results: List["ExerciseResult"] = relationship("ExerciseResult", back_populates="session", cascade="all, delete-orphan")
    achievements: List["Achievement"] = relationship("Achievement", back_populates="session", cascade="all, delete-orphan")
    mistake_records: List["MistakeRecord"] = relationship("MistakeRecord", back_populates="session", cascade="all, delete-orphan")
    knowledge_decay: List["KnowledgeDecay"] = relationship("KnowledgeDecay", back_populates="session", cascade="all, delete-orphan")
    multi_goals: List["MultiGoalProgress"] = relationship("MultiGoalProgress", back_populates="session", cascade="all, delete-orphan")

    metadata_json: str = Column(Text, default="{}")

    def get_metadata(self) -> Dict[str, Any]:
        import json
        try:
            return json.loads(self.metadata_json or "{}")
        except Exception:
            return {}

    def set_metadata(self, d: Dict[str, Any]):
        import json
        self.metadata_json = json.dumps(d, ensure_ascii=False)


class LearningGoal(Base):
    __tablename__ = "learning_goals"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    description: str = Column(Text, nullable=False)
    domain: str = Column(String(64), default="")
    target_topics: str = Column(Text, default="[]")
    estimated_time: float = Column(Float, default=10.0)
    priority: str = Column(String(16), default="normal")
    session: Session = relationship("Session", back_populates="learning_goal")

    def get_target_topics(self) -> List[str]:
        import json
        try:
            return json.loads(self.target_topics or "[]")
        except Exception:
            return []


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    name: str = Column(String(128), default="Unknown Learner")
    knowledge_levels: str = Column(Text, default="{}")
    capability_scores: str = Column(Text, default="{}")
    learning_style: str = Column(String(32), default="visual")
    weaknesses: str = Column(Text, default="[]")
    strengths: str = Column(Text, default="[]")
    history: str = Column(Text, default="[]")
    created_at: datetime = Column(DateTime, default=datetime.now, nullable=False)
    updated_at: datetime = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    session: Session = relationship("Session", back_populates="learner_profile")


class KnowledgeDiagnosis(Base):
    __tablename__ = "knowledge_diagnoses"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    diagnosed_topics: str = Column(Text, default="{}")
    weak_points: str = Column(Text, default="[]")
    strengths: str = Column(Text, default="[]")
    summary: str = Column(Text, default="")
    session: Session = relationship("Session", back_populates="diagnosis")


class ResourcePlan(Base):
    __tablename__ = "resource_plans"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    resources: str = Column(Text, default="[]")
    resource_counts: str = Column(Text, default="{}")
    topics_covered: str = Column(Text, default="[]")
    session: Session = relationship("Session", back_populates="resource_plan")


class LearningPath(Base):
    __tablename__ = "learning_paths"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    goals: str = Column(Text, default="[]")
    progress: float = Column(Float, default=0.0)
    learner_name: str = Column(String(128), default=None)
    created_at: datetime = Column(DateTime, default=datetime.now, nullable=False)
    session: Session = relationship("Session", back_populates="learning_path")
    modules: List["LearningModule"] = relationship("LearningModule", back_populates="path", cascade="all, delete-orphan")


class LearningModule(Base):
    __tablename__ = "learning_modules"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    path_id: int = Column(Integer, ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=False)
    module_id: str = Column(String(64), default="")
    title: str = Column(String(256), default="")
    topics: str = Column(Text, default="[]")
    resources: str = Column(Text, default="[]")
    exercises: str = Column(Text, default="[]")
    status: str = Column(String(32), default="待学习")
    estimated_hours: float = Column(Float, default=1.0)
    prerequisites: str = Column(Text, default="[]")
    path: LearningPath = relationship("LearningPath", back_populates="modules")


class TutorSession(Base):
    __tablename__ = "tutor_sessions"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    round_number: int = Column(Integer, default=1)
    topic: str = Column(String(256), default="")
    explanation: str = Column(Text, default="")
    questions_asked: str = Column(Text, default="[]")
    student_responses: str = Column(Text, default="[]")
    next_steps: str = Column(Text, default="[]")
    session: Session = relationship("Session", back_populates="tutor_sessions")


class ExerciseResult(Base):
    __tablename__ = "exercise_results"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    exercise_id: str = Column(String(64), default="")
    learner_answer: str = Column(Text, default="")
    correct_answer: str = Column(Text, default="")
    is_correct: bool = Column(Boolean, default=False)
    score: float = Column(Float, default=0.0)
    error_analysis: str = Column(Text, default="")
    timestamp: str = Column(String(32), default="")
    session: Session = relationship("Session", back_populates="exercise_results")

    __table_args__ = (
        Index("ix_exercise_results_session_id", "session_id"),
        Index("ix_exercise_results_timestamp", "timestamp"),
    )


class Achievement(Base):
    __tablename__ = "achievements"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    achievement_id: str = Column(String(64), nullable=False)
    title: str = Column(String(128), default="")
    description: str = Column(Text, default="")
    icon: str = Column(String(32), default="badge")
    unlocked_at: str = Column(String(32), default="")
    category: str = Column(String(32), default="general")
    rarity: str = Column(String(32), default="common")
    points_awarded: int = Column(Integer, default=0)
    session: Session = relationship("Session", back_populates="achievements")

    __table_args__ = (
        Index("ix_achievements_session_id", "session_id"),
    )


class MistakeRecord(Base):
    __tablename__ = "mistake_records"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    exercise_id: str = Column(String(64), default="")
    topic: str = Column(String(128), default="")
    question: str = Column(Text, default="")
    learner_answer: str = Column(Text, default="")
    correct_answer: str = Column(Text, default="")
    error_type: str = Column(String(64), default="concept_error")
    severity: float = Column(Float, default=0.5)
    reviewed_count: int = Column(Integer, default=0)
    last_reviewed: str = Column(String(32), default="")
    timestamp: str = Column(String(32), default="")
    session: Session = relationship("Session", back_populates="mistake_records")


class KnowledgeDecay(Base):
    __tablename__ = "knowledge_decay"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    topic: str = Column(String(128), default="")
    initial_mastery: float = Column(Float, default=0.0)
    current_mastery: float = Column(Float, default=0.0)
    half_life_hours: float = Column(Float, default=24.0)
    last_revised: str = Column(String(32), default="")
    revision_count: int = Column(Integer, default=0)
    decay_rate: float = Column(Float, default=0.0)
    session: Session = relationship("Session", back_populates="knowledge_decay")


class StudyStreak(Base):
    __tablename__ = "study_streaks"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    current_streak: int = Column(Integer, default=0)
    longest_streak: int = Column(Integer, default=0)
    last_study_date: str = Column(String(32), default="")
    total_study_days: int = Column(Integer, default=0)
    weekly_goal: int = Column(Integer, default=5)
    weekly_progress: int = Column(Integer, default=0)
    session: Session = relationship("Session", back_populates="study_streak")


class MultiGoalProgress(Base):
    __tablename__ = "multi_goal_progress"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: int = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    goal_id: str = Column(String(64), default="")
    description: str = Column(Text, default="")
    priority: str = Column(String(16), default="normal")
    progress: float = Column(Float, default=0.0)
    status: str = Column(String(32), default="active")
    modules_completed: int = Column(Integer, default=0)
    modules_total: int = Column(Integer, default=0)
    started_at: str = Column(String(32), default="")
    completed_at: str = Column(String(32), default="")
    session: Session = relationship("Session", back_populates="multi_goals")


# ════════════════════════════════════════════
# 全局共享表（不依赖 session）
# ════════════════════════════════════════════

class Vocab(Base):
    """词库表"""
    __tablename__ = "vocab"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    word: str = Column(String(128), nullable=False)
    meaning: str = Column(Text, default="")
    notes: str = Column(Text, default="")
    example: str = Column(Text, default="")
    source: str = Column(String(32), default="manual")
    subject: str = Column(String(32), default="main")
    mastered: bool = Column(Boolean, default=False)
    review_count: int = Column(Integer, default=0)
    last_reviewed: str = Column(String(32), default="")
    word_lower: str = Column(String(128), default=None, nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.now, nullable=False)
    user_id: int = Column(Integer, nullable=True, index=True)  # 账号隔离：NULL = 匿名共享

    __table_args__ = (
        # 显式命名唯一索引（SQLite 对 UniqueConstraint 会忽略名称生成 sqlite_autoindex_*，
        # 仅对 CREATE UNIQUE INDEX 保留显式名称，便于旧库迁移时删除/重建）
        Index("uq_vocab_word_subject_user", "word", "subject", "user_id", unique=True),
        Index("ix_vocab_subject_word", "subject", "word"),
    )


class DailyStats(Base):
    """每日学习时长"""
    __tablename__ = "daily_stats"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    date: str = Column(String(32), nullable=False, index=True)
    minutes: float = Column(Float, default=0.0)
    user_id: int = Column(Integer, nullable=True, index=True)  # 账号隔离：NULL = 匿名共享

    __table_args__ = (
        Index("uq_daily_stats_date_user", "date", "user_id", unique=True),
    )


class DailyWords(Base):
    """每日词汇量"""
    __tablename__ = "daily_words"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    date: str = Column(String(32), nullable=False, index=True)
    new_words: int = Column(Integer, default=0)
    total_words: int = Column(Integer, default=0)
    user_id: int = Column(Integer, nullable=True, index=True)  # 账号隔离：NULL = 匿名共享

    __table_args__ = (
        Index("uq_daily_words_date_user", "date", "user_id", unique=True),
    )


class DailyAccuracy(Base):
    """每日准确率"""
    __tablename__ = "daily_accuracy"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    date: str = Column(String(32), nullable=False, index=True)
    accuracy: float = Column(Float, default=0.0)
    user_id: int = Column(Integer, nullable=True, index=True)  # 账号隔离：NULL = 匿名共享

    __table_args__ = (
        Index("uq_daily_accuracy_date_user", "date", "user_id", unique=True),
    )


# ════════════════════════════════════════════
# 用户认证相关表
# ════════════════════════════════════════════

class User(Base):
    """用户账号表"""
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    username: str = Column(String(64), unique=True, nullable=False, index=True)
    email: str = Column(String(128), unique=True, nullable=False)
    password_hash: str = Column(String(256), nullable=False)
    password_salt: str = Column(String(32), nullable=False)
    display_name: str = Column(String(64), default="")
    avatar: str = Column(String(32), default="👤")
    created_at: datetime = Column(DateTime, default=datetime.now, nullable=False)
    last_login: datetime = Column(DateTime, default=None, nullable=True)
    is_active: bool = Column(Boolean, default=True)


class AuthToken(Base):
    """登录令牌表"""
    __tablename__ = "auth_tokens"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: str = Column(String(128), unique=True, nullable=False, index=True)
    created_at: datetime = Column(DateTime, default=datetime.now, nullable=False)
    expires_at: datetime = Column(DateTime, nullable=False)
    is_revoked: bool = Column(Boolean, default=False)

    # 关系
    user: User = relationship("User")


class DailyGoal(Base):
    """每日目标"""
    __tablename__ = "daily_goals"
    id: int = Column(Integer, primary_key=True, autoincrement=True)
    date: str = Column(String(32), nullable=False, index=True)
    pomodoros_target: int = Column(Integer, default=4)
    words_target: int = Column(Integer, default=20)
    minutes_target: int = Column(Integer, default=60)
    pomodoros_done: int = Column(Integer, default=0)
    words_done: int = Column(Integer, default=0)
    minutes_done: int = Column(Integer, default=0)
    user_id: int = Column(Integer, nullable=True, index=True)  # 账号隔离：NULL = 匿名共享

    __table_args__ = (
        Index("uq_daily_goals_date_user", "date", "user_id", unique=True),
    )