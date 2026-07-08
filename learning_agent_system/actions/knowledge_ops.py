#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识操作 Action - 存储、检索、图谱构建
"""

from __future__ import annotations

from typing import Dict, List, Optional

from metagpt.actions import Action


class StoreKnowledge(Action):
    """
    知识存储 Action。
    将知识点结构化存入知识库。
    """

    name: str = "StoreKnowledge"
    prompt_template: str = """\
请将以下知识点结构化存储到知识库中。

知识点内容：
{knowledge_content}

要求：
1. 提取关键概念
2. 建立与其他知识点的关联
3. 标注难度等级

请按以下 JSON 格式输出存储记录：
{{
  "topic": "知识点标题",
  "summary": "摘要...",
  "keywords": ["关键词1", "关键词2"],
  "related_topics": ["相关知识点"],
  "difficulty": 0.5,
  "content_hash": "存储标识"
}}
"""

    async def run(
        self,
        knowledge_content: str,
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            knowledge_content=knowledge_content,
        )
        result = await self.llm.aask(prompt)
        return result


class RetrieveKnowledge(Action):
    """
    知识检索 Action。
    根据查询检索相关知识。
    """

    name: str = "RetrieveKnowledge"
    prompt_template: str = """\
你是一个知识库检索助手。请根据以下查询检索相关知识。

查询内容：
{query}

返回最多 {top_k} 条最相关的知识条目。

请按以下 JSON 格式输出：
{{
  "results": [
    {{
      "topic": "知识点标题",
      "relevance": 0.95,
      "snippet": "相关内容摘要...",
      "id": "知识条目ID"
    }}
  ],
  "total_found": 3
}}
"""

    async def run(
        self,
        query: str,
        top_k: int = 5,
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            query=query,
            top_k=top_k,
        )
        result = await self.llm.aask(prompt)
        return result


class BuildKnowledgeGraph(Action):
    """
    知识图谱构建 Action。
    从知识点集合构建知识图谱（节点+边）。
    """

    name: str = "BuildKnowledgeGraph"
    prompt_template: str = """\
请根据以下知识点集合构建知识图谱。

知识点列表：
{knowledge_items}

要求：
1. 每个知识点是一个节点
2. 知识点之间有依赖或关联关系则建立边
3. 输出节点和边的结构化描述

请按以下 JSON 格式输出：
{{
  "nodes": [
    {{"id": "n1", "label": "知识点1", "type": "core/related"}},
    {{"id": "n2", "label": "知识点2", "type": "core"}}
  ],
  "edges": [
    {{"from": "n1", "to": "n2", "relation": "prerequisite"}},
    {{"from": "n2", "to": "n3", "relation": "related"}}
  ],
  "clusters": [
    {{"name": "核心概念群", "nodes": ["n1", "n2"]}}
  ]
}}
"""

    async def run(
        self,
        knowledge_items: str,
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            knowledge_items=knowledge_items,
        )
        result = await self.llm.aask(prompt)
        return result
