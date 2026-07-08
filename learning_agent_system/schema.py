#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
个性化资源生成与学习多智能体系统 - 数据模型定义
基于MetaGPT的多Agent学习系统Schema
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    from pydantic.v1 import BaseModel, Field  # type: ignore[no-redef, import-not-found, assignment]


# ───────────────────────────── Enums ─────────────────────────────

class ResourceType(str, Enum):
    EXPLANATION = "讲解"
    EXERCISE = "练习"
    CASE = "案例"
    CODE_EXAMPLE = "代码示例"
    VISUAL_AID = "可视化"
    VIDEO = "视频"


class ExerciseType(str, Enum):
    CHOICE = "choice"
    FILL_BLANK = "fill_blank"
    PROGRAMMING = "programming"
    OPEN_ENDED = "open_ended"


class ModuleStatus(str, Enum):
    PENDING = "待学习"
    IN_PROGRESS = "学习中"
    COMPLETED = "已完成"


# ───────────────────────────── Learner Profile ─────────────────────────────

class LearnerProfile(BaseModel):
    """学习者画像模型"""

    name: str = "Unknown Learner"
    knowledge_levels: Dict[str, float] = Field(default_factory=dict, description="知识点掌握程度 (0.0-1.0)")
    capability_scores: Dict[str, float] = Field(default_factory=dict, description="能力维度得分 (0.0-1.0)")
    learning_style: str = Field(default="visual", description="学习风格: visual/auditory/read_write/kinesthetic")
    weaknesses: List[str] = Field(default_factory=list, description="薄弱知识点")
    strengths: List[str] = Field(default_factory=list, description="优势知识点")
    history: List[Dict[str, Any]] = Field(default_factory=list, description="学习历史记录")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def update_at(self):
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearnerProfile":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "LearnerProfile":
        return cls.model_validate_json(json_str)


# ───────────────────────────── Knowledge Resource ─────────────────────────────

class KnowledgeResource(BaseModel):
    """学习资源模型"""

    id: str
    title: str
    content: str
    resource_type: ResourceType
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0, description="难度 0.0-1.0")
    topics: List[str] = Field(default_factory=list, description="关联知识点")
    target_level: Optional[str] = Field(default=None, description="目标学习者水平")
    format: str = Field(default="text", description="呈现格式: text/markdown/code/mermaid")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "KnowledgeResource":
        return cls.model_validate_json(json_str)


# ───────────────────────────── Exercise ─────────────────────────────

class Exercise(BaseModel):
    """练习题模型"""

    id: str
    question: str
    options: Optional[List[str]] = Field(default=None, description="选择题选项 (A-D)")
    answer: str
    explanation: str = ""
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    topic: str
    exercise_type: ExerciseType = ExerciseType.CHOICE
    points: int = 10

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "Exercise":
        return cls.model_validate_json(json_str)


# ───────────────────────────── Learning Path ─────────────────────────────

class LearningModule(BaseModel):
    """学习模块"""

    id: str
    title: str
    topics: List[str] = Field(default_factory=list)
    resources: List[KnowledgeResource] = Field(default_factory=list)
    exercises: List[Exercise] = Field(default_factory=list)
    status: ModuleStatus = ModuleStatus.PENDING
    estimated_hours: float = 1.0
    prerequisites: List[str] = Field(default_factory=list, description="前置模块ID")


class LearningPath(BaseModel):
    """学习路径模型"""

    goals: List[str] = Field(default_factory=list)
    modules: List[LearningModule] = Field(default_factory=list)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    learner_name: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "LearningPath":
        return cls.model_validate_json(json_str)


# ───────────────────────────── Exercise Result ─────────────────────────────

class ExerciseResult(BaseModel):
    """练习结果模型"""

    exercise_id: str
    learner_answer: str
    correct_answer: str
    is_correct: bool
    score: float
    error_analysis: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "ExerciseResult":
        return cls.model_validate_json(json_str)


# ───────────────────────────── Knowledge Status ─────────────────────────────

class KnowledgeStatus(BaseModel):
    """知识状态模型"""

    topic: str
    mastery_level: float = 0.0
    confidence: float = 0.0
    last_reviewed: str = ""
    review_count: int = 0
    related_topics: List[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json()

# ───────────────────────────── Missing Models for Orchestrator ─────────────────────────────

class LearningGoal(BaseModel):
    """学习目标模型"""

    description: str
    domain: str = ""
    target_topics: List[str] = Field(default_factory=list)
    estimated_time: float = 10.0  # hours
    priority: str = "normal"  # high / normal / low

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LearningGoal":
        return cls(**data)


class KnowledgeDiagnosis(BaseModel):
    """知识诊断结果模型"""

    diagnosed_topics: Dict[str, float] = Field(default_factory=dict, description="知识点 -> 掌握程度")
    weak_points: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeDiagnosis":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "KnowledgeDiagnosis":
        return cls.model_validate_json(json_str)


class ResourcePlan(BaseModel):
    """资源生成计划模型"""

    resources: List[Dict[str, Any]] = Field(default_factory=list)
    resource_counts: Dict[str, int] = Field(default_factory=dict)
    topics_covered: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourcePlan":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "ResourcePlan":
        return cls.model_validate_json(json_str)


class TutorSession(BaseModel):
    """辅导会话模型"""

    round_number: int = 1
    topic: str = ""
    explanation: str = ""
    questions_asked: List[str] = Field(default_factory=list)
    student_responses: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TutorSession":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "TutorSession":
        return cls.model_validate_json(json_str)


class KnowledgeGraph(BaseModel):
    """知识点图谱模型"""

    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    topic_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeGraph":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "KnowledgeGraph":
        return cls.model_validate_json(json_str)


class Achievement(BaseModel):
    """成就徽章模型"""

    id: str
    title: str
    description: str
    icon: str = "badge"
    unlocked_at: str = ""
    category: str = "general"  # general / streak / score / milestone
    rarity: str = "common"  # common / rare / epic / legendary
    points_awarded: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Achievement":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "Achievement":
        return cls.model_validate_json(json_str)


class MistakeRecord(BaseModel):
    """错题记录模型"""

    exercise_id: str
    topic: str
    question: str
    learner_answer: str
    correct_answer: str
    error_type: str  # concept_error / careless / knowledge_gap / misunderstanding
    severity: float = 0.5  # 错误严重程度 0-1
    reviewed_count: int = 0
    last_reviewed: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MistakeRecord":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "MistakeRecord":
        return cls.model_validate_json(json_str)


class KnowledgeDecay(BaseModel):
    """知识衰减追踪模型"""

    topic: str
    initial_mastery: float = 0.0
    current_mastery: float = 0.0
    half_life_hours: float = 24.0  # 知识半衰期（小时）
    last_revised: str = ""
    revision_count: int = 0
    decay_rate: float = 0.0  # 当前衰减率

    def update_decay(self, hours_passed: float = 1.0) -> None:
        if hasattr(self, "model_copy"):
            updated = self.model_copy()
        else:
            updated = self.copy()
        if self.initial_mastery > 0:
            updated.current_mastery = self.initial_mastery * (0.5 ** (hours_passed / self.half_life_hours))
        updated.decay_rate = (self.initial_mastery - updated.current_mastery) / self.initial_mastery if self.initial_mastery > 0 else 0
        updated.last_revised = datetime.now().isoformat()
        updated.revision_count += 1
        self.current_mastery = updated.current_mastery
        self.decay_rate = updated.decay_rate
        self.last_revised = updated.last_revised
        self.revision_count = updated.revision_count

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeDecay":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "KnowledgeDecay":
        return cls.model_validate_json(json_str)


class StudyStreak(BaseModel):
    """学习连续天数追踪"""

    current_streak: int = 0
    longest_streak: int = 0
    last_study_date: str = ""
    total_study_days: int = 0
    weekly_goal: int = 5  # 每周目标学习天数
    weekly_progress: int = 0

    def record_today(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_study_date != today:
            last_date = datetime.fromisoformat(self.last_study_date) if self.last_study_date else None
            if last_date:
                delta = (datetime.now() - last_date).days
                if delta == 1:
                    self.current_streak += 1
                elif delta > 1:
                    self.current_streak = 1
            else:
                self.current_streak = 1
            self.last_study_date = today
            self.total_study_days += 1
            if self.current_streak > self.longest_streak:
                self.longest_streak = self.current_streak
            self.weekly_progress = min(self.weekly_progress + 1, self.weekly_goal)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StudyStreak":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "StudyStreak":
        return cls.model_validate_json(json_str)


class MultiGoalProgress(BaseModel):
    """多目标并行学习进度"""

    goal_id: str
    description: str
    priority: str = "normal"
    progress: float = 0.0
    status: str = "active"  # active / paused / completed / archived
    modules_completed: int = 0
    modules_total: int = 0
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiGoalProgress":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "MultiGoalProgress":
        return cls.model_validate_json(json_str)


class ReportCard(BaseModel):
    """学习报告卡模型"""

    session_id: str
    learner_name: str
    date_range: Dict[str, str] = Field(default_factory=dict)
    total_hours: float = 0.0
    topics_covered: List[str] = Field(default_factory=list)
    exercises_completed: int = 0
    exercises_correct: int = 0
    average_score: float = 0.0
    weak_points: List[str] = Field(default_factory=list)
    achievements_unlocked: List[Achievement] = Field(default_factory=list)
    mistakes_reviewed: List[MistakeRecord] = Field(default_factory=list)
    streak_info: StudyStreak = Field(default_factory=StudyStreak)
    knowledge_decay_alerts: List[KnowledgeDecay] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportCard":
        return cls(**data)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "ReportCard":
        return cls.model_validate_json(json_str)
