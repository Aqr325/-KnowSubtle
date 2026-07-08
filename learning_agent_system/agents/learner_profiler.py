#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
学习者画像 Agent - LearnerProfiler
基于RoleZero实现知识诊断、能力评估、偏好建模
"""

from __future__ import annotations

from typing import Dict, List, Optional

from metagpt.actions.add_requirement import UserRequirement
from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles import Role

from learning_agent_system.actions import CapabilityAssessment, KnowledgeDiagnosis, PrefModeling
from learning_agent_system.tools.tool_factory import create_tool_map


class LearnerProfiler(Role):
    """
    学习者画像 Agent。
    诊断学习者的知识水平、能力维度和学习偏好，建立动态画像。
    """

    profile: str = "Learner Profiler"
    name: str = "Alex"
    goal: str = "诊断学习者的知识水平、能力维度和学习偏好，建立动态学习者画像"
    constraints: str = "使用与用户相同的语言交流，输出结构化的学习者画像"
    tools: List[str] = ["Editor"]
    todo_action: str = "KnowledgeDiagnosis"
    react_mode: str = "react"
    max_react_loop: int = 30

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_actions([KnowledgeDiagnosis, CapabilityAssessment, PrefModeling])
        self._tool_map = create_tool_map()

    def _update_tool_execution(self):
        """注册工具执行映射"""
        if "Editor" in self._tool_map:
            editor_cfg = self._tool_map.get("Editor", {})
            if editor_cfg.get("enabled"):
                self.record_observation("Registered Editor tool")

    async def _act(self) -> Message:
        """执行角色行为"""
        for action_cls in self._rc.todo:
            logger.info(f"[{self.name}] Running action: {action_cls.__name__}")
            result = await action_cls().llm.aask("请完成学习者画像诊断")
            logger.info(f"[{self.name}] Result: {result[:100]}...")
            return Message(content=result, role=self.name)
        return Message(content="No action to take", role=self.name)

    def _watch(self, watch=None):
        """订阅消息类型"""
        super()._watch(watch or [UserRequirement])
