#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
学习规划 Agent - LearningPlanner
根据学习者画像和目标，设计最优学习路径并持续自适应调整
"""

from __future__ import annotations

from typing import Dict, List, Optional

from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles import Role

from learning_agent_system.actions import AdaptiveAdjust, PlanLearningPath
from learning_agent_system.schema import LearnerProfile, LearningPath
from learning_agent_system.tools.tool_factory import create_tool_map


class LearningPlanner(Role):
    """
    学习规划 Agent。
    根据学习者画像和学习目标，设计最优学习路径并持续自适应调整。
    """

    profile: str = "Learning Planner"
    name: str = "Plato"
    goal: str = "根据学习者画像和学习目标，设计最优学习路径并持续自适应调整"
    constraints: str = "遵循从基础到进阶的递进逻辑，确保路径可行性"
    tools: List[str] = ["Editor"]
    todo_action: str = "PlanLearningPath"
    react_mode: str = "react"
    max_react_loop: int = 30
    learner_profile: Optional[LearnerProfile] = None
    current_path: Optional[LearningPath] = None

    def __init__(self, learner_profile: Optional[LearnerProfile] = None, **kwargs):
        super().__init__(**kwargs)
        self.learner_profile = learner_profile
        self.set_actions([PlanLearningPath, AdaptiveAdjust])
        self._tool_map = create_tool_map()

    def _watch(self, watch=None):
        """订阅消息类型"""
        super()._watch(watch or [UserRequirement])

    def _update_tool_execution(self):
        """注册工具执行映射"""
        if "Editor" in self._tool_map:
            editor_cfg = self._tool_map.get("Editor", {})
            if editor_cfg.get("enabled"):
                self.record_observation("Registered Editor tool for LearningPlanner")

    async def plan_path(
        self,
        goals: List[str],
        **kwargs,
    ) -> LearningPath:
        """
        规划学习路径
        """
        profile_json = self.learner_profile.to_json() if self.learner_profile else "{}"
        result = await PlanLearningPath().llm.aask(
            f"为目标 {goals} 规划学习路径，学习者画像: {profile_json}"
        )
        
        path = LearningPath(goals=goals)
        self.current_path = path
        return path

    async def adjust_path(
        self,
        progress_data: str,
        **kwargs,
    ) -> LearningPath:
        """
        调整学习路径
        """
        if not self.current_path:
            raise ValueError("No current path to adjust")
        
        result = await AdaptiveAdjust().llm.aask(
            f"当前路径: {self.current_path.to_json()}, 进度数据: {progress_data}"
        )
        return self.current_path
