#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识诊断模块 - 知识诊断 + 能力评估 Action
"""

from __future__ import annotations

from typing import Any, List, Optional

from metagpt.actions import Action
from learning_agent_system.schema import KnowledgeStatus


class KnowledgeDiagnosis(Action):
    """
    知识诊断 Action。
    通过分析学习者的对话历史和输入，诊断其在各知识点上的掌握程度。
    """

    name: str = "KnowledgeDiagnosis"
    prompt_template: str = """\
你是一个专业的知识诊断专家。请根据以下学习者的表现，诊断其在各知识点上的掌握程度。

学习者表现：
{learner_input}

对话历史：
{history}

请按以下 JSON 格式输出诊断结果：
{{
  "knowledge_status": {{
    "知识点1": {{ "mastery_level": 0.8, "confidence": 0.9, "notes": "掌握良好" }},
    "知识点2": {{ "mastery_level": 0.3, "confidence": 0.7, "notes": "需要加强" }}
  }},
  "weak_points": ["知识点2", "知识点3"],
  "strengths": ["知识点1"],
  "overall_summary": "整体表现摘要..."
}}
"""

    async def run(
        self,
        learner_input: str,
        history: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        history_text = "\n".join(history) if history else "无历史记录"
        prompt = self.prompt_template.format(
            learner_input=learner_input,
            history=history_text,
        )
        result = await self.llm.aask(prompt)
        return result


class CapabilityAssessment(Action):
    """
    能力评估 Action。
    基于布鲁姆分类法评估学习者的认知能力维度得分。
    """

    name: str = "CapabilityAssessment"
    prompt_template: str = """\
你是一个教育测量学专家。请根据学习者的表现，评估其在布鲁姆认知能力各维度的得分（0.0-1.0）。

学习者表现：
{learner_input}

对话历史：
{history}

请按以下 JSON 格式输出评估结果：
{{
  "capability_scores": {{
    "记忆": 0.8,
    "理解": 0.6,
    "应用": 0.5,
    "分析": 0.4,
    "评价": 0.3,
    "创造": 0.2
  }},
  "summary": "能力评估摘要..."
}}
"""

    async def run(
        self,
        learner_input: str,
        history: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        history_text = "\n".join(history) if history else "无历史记录"
        prompt = self.prompt_template.format(
            learner_input=learner_input,
            history=history_text,
        )
        result = await self.llm.aask(prompt)
        return result
