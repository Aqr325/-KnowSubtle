#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
学习互动 Agent - LearningTutor
通过苏格拉底式对话引导学习者深入理解知识
"""

from __future__ import annotations

from typing import List, Optional

from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles import Role

from learning_agent_system.actions import AnswerQuestion, ExplainConcept, GuideDiscussion
from learning_agent_system.tools.tool_factory import create_tool_map


class LearningTutor(Role):
    """
    学习互动 Agent。
    通过苏格拉底式对话引导学习者深入理解知识，而非直接给出答案。
    """

    profile: str = "Learning Tutor"
    name: str = "Socrates"
    goal: str = "通过苏格拉底式对话引导学习者深入理解知识，而非直接给出答案"
    constraints: str = "始终使用引导式提问，启发学习者自主思考"
    tools: List[str] = ["Editor", "Browser", "SearchEnhancedQA"]
    todo_action: str = "AnswerQuestion"
    react_mode: str = "react"
    max_react_loop: int = 30
    language: str = "zh-cn"
    conversation_history: Optional[List[str]] = None

    def __init__(self, conversation_history: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.conversation_history = conversation_history or []
        self.set_actions([AnswerQuestion, ExplainConcept, GuideDiscussion])
        self._tool_map = create_tool_map()

    def _watch(self, watch=None):
        """订阅消息类型"""
        super()._watch(watch or [UserRequirement])

    def _update_tool_execution(self):
        """注册工具执行映射"""
        if "Editor" in self._tool_map:
            editor_cfg = self._tool_map.get("Editor", {})
            if editor_cfg.get("enabled"):
                self.record_observation("Registered Editor tool for LearningTutor")

    async def answer(
        self,
        question: str,
        context: str = "",
        **kwargs,
    ) -> str:
        """
        回答学习者问题（苏格拉底式引导）
        """
        result = await AnswerQuestion().llm.aask(
            f"问题: {question}, 上下文: {context}"
        )
        self.conversation_history.append(f"Q: {question}\nA: {result}")
        return result

    async def explain(
        self,
        concept: str,
        level: str = "beginner",
        **kwargs,
    ) -> str:
        """
        讲解概念
        """
        result = await ExplainConcept().llm.aask(
            f"概念: {concept}, 深度: {level}"
        )
        self.conversation_history.append(f"Explain {concept}: {result}")
        return result

    async def guide(
        self,
        topic: str,
        **kwargs,
    ) -> str:
        """
        引导讨论
        """
        history_text = "\n".join(self.conversation_history[-10:])
        result = await GuideDiscussion().llm.aask(
            f"主题: {topic}, 历史: {history_text}"
        )
        self.conversation_history.append(f"Guide {topic}: {result}")
        return result
