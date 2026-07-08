"""
AchievementChecker — 成就检测 Action

负责：
1. 检测学习者是否解锁了新成就
2. 根据练习正确率、学习天数、知识掌握速度等触发成就
3. 支持稀有度分级（普通/稀有/史诗/传说）
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from metagpt.schema import Message
from pydantic import BaseModel, Field

from learning_agent_system.schema import Achievement, MistakeRecord, ExerciseResult, StudyStreak

logger = logging.getLogger(__name__)


# ---- 预设成就池 ----
ACHIEVEMENT_POOL: List[Achievement] = [
    # 新手类
    Achievement(id="first_step", title="第一步", description="完成了第一次学习目标设定", icon="🎯", category="milestone", rarity="common", points_awarded=10),
    Achievement(id="first_quiz", title="初试身手", description="完成了第一次练习评测", icon="📝", category="milestone", rarity="common", points_awarded=15),
    Achievement(id="perfect_score", title="满分状元", description="一次性答对所有题目", icon="💯", category="score", rarity="rare", points_awarded=50),
    # 坚持类
    Achievement(id="streak_3", title="三日精进", description="连续学习3天", icon="🔥", category="streak", rarity="common", points_awarded=20),
    Achievement(id="streak_7", title="一周不息", description="连续学习7天", icon="🌟", category="streak", rarity="rare", points_awarded=50),
    Achievement(id="streak_30", title="月入三十", description="连续学习30天", icon="🏆", category="streak", rarity="epic", points_awarded=150),
    # 知识类
    Achievement(id="first_module", title="学海初探", description="完成了第一个学习模块", icon="📚", category="milestone", rarity="common", points_awarded=25),
    Achievement(id="halfway_hero", title="半程英雄", description="完成了50%的学习进度", icon="⚡", category="milestone", rarity="rare", points_awarded=75),
    Achievement(id="full_completion", title="学业有成", description="完成了100%的学习路径", icon="🎓", category="milestone", rarity="epic", points_awarded=200),
    # 纠错类
    Achievement(id="comeback_king", title="触底反弹", description="从低分恢复到高分", icon="🔄", category="score", rarity="rare", points_awarded=40),
    Achievement(id="mistake_master", title="错题大师", description="分析了20道错题", icon="🧩", category="general", rarity="rare", points_awarded=60),
    Achievement(id="error_annihilator", title="错题终结者", description="分析了50道错题", icon="⚔️", category="general", rarity="epic", points_awarded=100),
    # 速度类
    Achievement(id="speed_demon", title="极速达人", description="在极短时间内完成了一个模块", icon="💨", category="milestone", rarity="rare", points_awarded=45),
    Achievement(id="knowledge_ninja", title="知识忍者", description="连续10次答题正确", icon="🥷", category="score", rarity="legendary", points_awarded=200),
]


class AchievementCheckResult(BaseModel):
    """成就检测结果"""

    new_achievements: List[Achievement] = Field(default_factory=list, description="新解锁的成就")
    point_earnings: int = Field(default=0, description="新解锁成就获得的总积分")
    total_points: int = Field(default=0, description="累计总积分")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "AchievementCheckResult":
        return cls.model_validate_json(json_str)


class AchievementChecker:
    """成就检测器"""

    def __init__(self):
        self.earned_ids: List[str] = []
        self.total_points: int = 0
        self.exercises_completed: int = 0
        self.consecutive_correct: int = 0
        self.mistakes_analyzed: int = 0
        self.modules_completed: int = 0

    def check(
        self,
        streak: Optional[StudyStreak] = None,
        results: Optional[List[ExerciseResult]] = None,
        mistakes: Optional[List[MistakeRecord]] = None,
    ) -> AchievementCheckResult:
        """根据当前状态检测是否解锁新成就"""
        new_achievements = []
        points = 0

        # 新手类
        if self.exercises_completed == 1 and "first_step" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[0].model_dump()))
            points += 10
        if self.exercises_completed >= 1 and "first_quiz" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[1].model_dump()))
            points += 15
        if results and len(results) > 0 and all(r.is_correct for r in results) and "perfect_score" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[2].model_dump()))
            points += 50

        # 坚持类
        if streak and streak.current_streak >= 3 and "streak_3" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[3].model_dump()))
            points += 20
        if streak and streak.current_streak >= 7 and "streak_7" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[4].model_dump()))
            points += 50
        if streak and streak.current_streak >= 30 and "streak_30" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[5].model_dump()))
            points += 150

        # 知识类
        if self.modules_completed >= 1 and "first_module" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[6].model_dump()))
            points += 25
        if self.exercises_completed >= 10 and "knowledge_ninja" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[13].model_dump()))
            points += 200

        # 纠错类
        if mistakes and len(mistakes) >= 20 and "mistake_master" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[10].model_dump()))
            points += 60
        if mistakes and len(mistakes) >= 50 and "error_annihilator" not in self.earned_ids:
            new_achievements.append(Achievement(**ACHIEVEMENT_POOL[11].model_dump()))
            points += 100

        # 标记已解锁
        for a in new_achievements:
            self.earned_ids.append(a.id)
            self.total_points += a.points_awarded

        return AchievementCheckResult(
            new_achievements=new_achievements,
            point_earnings=sum(a.points_awarded for a in new_achievements),
            total_points=self.total_points,
        )

    def record_result(self, result: ExerciseResult) -> None:
        """记录每次练习结果"""
        self.exercises_completed += 1
        if result.is_correct:
            self.consecutive_correct += 1
        else:
            self.consecutive_correct = 0

    def record_mistake(self) -> None:
        """记录错题分析"""
        self.mistakes_analyzed += 1

    def record_module_completion(self) -> None:
        """记录模块完成"""
        self.modules_completed += 1


class CheckAchievementsAction:
    """用于 Agent 协作的标准化 Action"""

    name: str = "CheckAchievements"
    description: str = "检测学习者是否满足新成就条件"

    def __init__(self, checker: AchievementChecker = None):
        self.checker = checker or AchievementChecker()

    async def run(self, streak_data: Optional[Dict] = None, results_data: Optional[List[Dict]] = None, mistakes_data: Optional[List[Dict]] = None) -> AchievementCheckResult:
        """运行成就检测"""
        streak = StudyStreak(**streak_data) if streak_data else None
        results = [ExerciseResult(**r) for r in (results_data or [])]
        mistakes = [MistakeRecord(**m) for m in (mistakes_data or [])]
        for r in results:
            self.checker.record_result(r)
        return self.checker.check(streak, results, mistakes)
