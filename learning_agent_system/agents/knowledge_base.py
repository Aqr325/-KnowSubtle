#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库 Agent - KnowledgeBase
构建领域知识图谱，管理知识的存储、检索和关联
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles import Role

from learning_agent_system.actions import BuildKnowledgeGraph, RetrieveKnowledge, StoreKnowledge
from learning_agent_system.schema import KnowledgeStatus
from learning_agent_system.tools.tool_factory import create_tool_map


class KnowledgeBase(Role):
    """
    知识库 Agent。
    构建领域知识图谱，管理知识的存储、检索和关联，为其他Agent提供知识支撑。
    """

    profile: str = "Knowledge Base"
    name: str = "Kai"
    goal: str = "构建领域知识图谱，管理知识的存储、检索和关联，为其他Agent提供知识支撑"
    constraints: str = "确保知识的准确性和结构化，支持语义检索"
    tools: List[str] = ["Editor", "SearchEnhancedQA"]
    todo_action: str = "StoreKnowledge"
    react_mode: str = "react"
    max_react_loop: int = 30
    knowledge_store: Dict[str, Any] = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_actions([StoreKnowledge, RetrieveKnowledge, BuildKnowledgeGraph])
        self._tool_map = create_tool_map()

    def _watch(self, watch=None):
        """订阅消息类型"""
        super()._watch(watch or [UserRequirement])

    def _update_tool_execution(self):
        """注册工具执行映射"""
        if "Editor" in self._tool_map:
            editor_cfg = self._tool_map.get("Editor", {})
            if editor_cfg.get("enabled"):
                self.record_observation("Registered Editor tool for KnowledgeBase")

    async def store(
        self,
        content: str,
        topic: str,
        **kwargs,
    ) -> str:
        """
        存储知识
        """
        result = await StoreKnowledge().llm.aask(
            f"知识点: {topic}, 内容: {content}"
        )
        self.knowledge_store[topic] = {
            "content": content,
            "structured": result,
            "stored_at": kwargs.get("timestamp", ""),
        }
        return f"Knowledge stored for topic: {topic}"

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        检索知识
        """
        # 先在内存中检索
        results = []
        for topic, data in self.knowledge_store.items():
            if query.lower() in topic.lower() or query.lower() in data.get("content", "").lower():
                results.append({
                    "topic": topic,
                    "content": data.get("content", "")[:200],
                    "relevance": 0.8,
                })
        
        # 如果内存结果不足，调用LLM增强
        if len(results) < top_k:
            llm_result = await RetrieveKnowledge().llm.aask(
                f"查询: {query}, 顶部结果数: {top_k}"
            )
            results.append({"topic": "LLM Enhanced", "content": llm_result, "relevance": 0.9})
        
        return results[:top_k]

    async def build_graph(self, topics: List[str]) -> str:
        """
        构建知识图谱
        """
        topics_text = "\n".join(topics)
        result = await BuildKnowledgeGraph().llm.aask(topics_text)
        return result
