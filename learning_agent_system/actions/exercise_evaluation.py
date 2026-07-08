#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
练习评测与错题分析 Action
"""

from __future__ import annotations

from typing import Optional

from metagpt.actions import Action


class EvaluateExercise(Action):
    """
    练习评测 Action。
    对学习者答案进行智能批改，不仅判断对错，还分析错误原因。
    """

    name: str = "EvaluateExercise"
    prompt_template: str = """\
你是一位经验丰富的教师。请对学习者的答案进行智能批改和深度分析。

题目：
{question}

正确答案：
{correct_answer}

学习者答案：
{learner_answer}

请进行以下分析：
1. 是否正确
2. 如果错误，错误类型（概念混淆/粗心/方法错误/完全不会）
3. 具体分析
4. 建议

请按以下 JSON 格式输出：
{{
  "is_correct": false,
  "score": 0.3,
  "error_type": "概念混淆",
  "error_analysis": "学习者混淆了...的概念",
  "feedback": "建议你重新复习...部分",
  "tips": ["复习相关知识点", "多做类似练习"]
}}
"""

    async def run(
        self,
        question: str,
        correct_answer: str,
        learner_answer: str,
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            question=question,
            correct_answer=correct_answer,
            learner_answer=learner_answer,
        )
        result = await self.llm.aask(prompt)
        return result


class AnalyzeMistakes(Action):
    """
    错题分析 Action。
    分析错题集，找出模式和薄弱环节。
    """

    name: str = "AnalyzeMistakes"
    prompt_template: str = """\
你是一个学习数据分析专家。请分析学习者的错题记录，找出模式并提供补救建议。

错题历史记录：
{mistakes_history}

请分析：
1. 哪些知识点错误率最高？
2. 错误类型有没有共同特征？
3. 应该优先复习哪些内容？

请按以下 JSON 格式输出：
{{
  "most_errors_topic": "最高错误率的知识点",
  "error_patterns": ["模式1", "模式2"],
  "priority_topics": ["优先复习知识点1", "优先复习知识点2"],
  "remediation_plan": "补救学习计划...",
  "confidence_score": 0.8
}}
"""

    async def run(
        self,
        mistakes_history: str,
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            mistakes_history=mistakes_history,
        )
        result = await self.llm.aask(prompt)
        return result
