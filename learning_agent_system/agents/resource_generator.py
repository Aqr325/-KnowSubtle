#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
资源生成 Agent - ResourceGenerator
根据学习者画像生成个性化的图文、习题、案例、代码演示等学习资源
"""

from __future__ import annotations

from typing import List, Optional

from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles import Role

from learning_agent_system.actions import (
    GenerateCase,
    GenerateCodeExample,
    GenerateExercise,
    GenerateKnowledgePoint,
    GenerateVisualAid,
)
from learning_agent_system.schema import LearnerProfile, KnowledgeResource
from learning_agent_system.tools.tool_factory import create_tool_map


class ResourceGenerator(Role):
    """
    资源生成 Agent。
    根据学习者画像，生成个性化的图文讲解、习题、案例、代码示例和可视化辅助等学习资源。
    """

    profile: str = "Resource Generator"
    name: str = "Rhea"
    goal: str = "根据学习者画像，生成个性化的图文讲解、习题、案例、代码示例和可视化辅助等学习资源"
    constraints: str = "根据学习者的知识水平和学习风格调整内容的难度和呈现方式"
    tools: List[str] = ["Editor", "Browser"]
    todo_action: str = "GenerateKnowledgePoint"
    react_mode: str = "react"
    max_react_loop: int = 50
    learner_profile: Optional[LearnerProfile] = None

    def __init__(self, learner_profile: Optional[LearnerProfile] = None, **kwargs):
        super().__init__(**kwargs)
        self.learner_profile = learner_profile
        self.set_actions([
            GenerateKnowledgePoint,
            GenerateExercise,
            GenerateCase,
            GenerateCodeExample,
            GenerateVisualAid,
        ])
        self._tool_map = create_tool_map()

    def _watch(self, watch=None):
        """订阅消息类型"""
        super()._watch(watch or [UserRequirement])

    def _update_tool_execution(self):
        """注册工具执行映射"""
        if "Editor" in self._tool_map:
            editor_cfg = self._tool_map.get("Editor", {})
            if editor_cfg.get("enabled"):
                self.record_observation("Registered Editor tool for ResourceGenerator")

    async def generate_resource(
        self,
        topic: str,
        resource_type: str = "explanation",
        difficulty: Optional[float] = None,
        **kwargs,
    ) -> KnowledgeResource:
        """
        生成一个学习资源
        """
        level = "beginner"
        style = "visual"
        if self.learner_profile:
            level = self._get_current_level(topic, difficulty)
            style = self.learner_profile.learning_style

        action_map = {
            "explanation": GenerateKnowledgePoint,
            "exercise": GenerateExercise,
            "case": GenerateCase,
            "code_example": GenerateCodeExample,
            "visual_aid": GenerateVisualAid,
        }

        action_cls = action_map.get(resource_type, GenerateKnowledgePoint)
        result = await action_cls().llm.aask(
            f"为学习者生成关于'{topic}'的{resource_type}资源，"
            f"学习者水平:{level}, 风格:{style}"
        )

        return KnowledgeResource(
            id=f"res_{topic.replace(' ', '_')}_{len(kwargs)}",
            title=f"{topic} - {resource_type}",
            content=result,
            resource_type=resource_type,
            difficulty=difficulty or 0.5,
            topics=[topic],
            format="text",
        )

    def _get_current_level(self, topic: str, difficulty: Optional[float] = None) -> str:
        """根据学习者和难度确定当前水平"""
        if difficulty is not None:
            if difficulty < 0.3:
                return "beginner"
            elif difficulty < 0.7:
                return "intermediate"
            return "advanced"
        return "beginner"
