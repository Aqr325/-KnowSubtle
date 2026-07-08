#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
偏好建模 Action
"""

from __future__ import annotations

from metagpt.actions import Action


class PrefModeling(Action):
    """
    偏好建模 Action。
    分析学习者的交互模式，推断其偏好的学习风格。
    """

    name: str = "PrefModeling"
    prompt_template: str = """\
你是一个学习风格分析专家。请根据学习者的交互记录，分析其偏好的学习风格。

学习风格类别：
- visual (视觉型): 喜欢看图表、流程图、概念图
- auditory (听觉型): 喜欢听讲解、播客、讨论
- read_write (阅读/写作型): 喜欢阅读文本、写笔记
- kinesthetic (实践型): 喜欢动手操作、做实验、写代码

学习者的交互记录：
{learner_interactions}

请按以下 JSON 格式输出偏好模型：
{{
  "preferred_styles": ["visual", "kinesthetic"],
  "confidence": 0.75,
  "recommendations": ["建议使用更多图示和动手练习"],
  "avoid_styles": ["auditory"],
  "summary": "偏好分析摘要..."
}}
"""

    async def run(
        self,
        learner_interactions: str,
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            learner_interactions=learner_interactions,
        )
        result = await self.llm.aask(prompt)
        return result
