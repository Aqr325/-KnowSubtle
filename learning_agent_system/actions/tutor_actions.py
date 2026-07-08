#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
学习互动 Action - 问答、概念讲解、讨论引导
"""

from __future__ import annotations

from typing import Optional

from metagpt.actions import Action


class AnswerQuestion(Action):
    """
    问答解答 Action。
    使用苏格拉底式引导方式回答问题。
    """

    name: str = "AnswerQuestion"
    prompt_template: str = """\
你是一位优秀的导师，使用苏格拉底式对话方法。

学习者的问题：
{question}

相关上下文：
{context}

请按照以下原则回答：
1. 先引导学习者思考，不要直接给答案
2. 通过提问启发学习者自己找到答案
3. 如果学习者坚持要答案，再简明扼要地给出
4. 语气友好、鼓励性强

请输出一段引导式的回答：
"""

    async def run(
        self,
        question: str,
        context: str = "",
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            question=question,
            context=context,
        )
        result = await self.llm.aask(prompt)
        return result


class ExplainConcept(Action):
    """
    概念讲解 Action。
    使用类比、举例、对比等多种方式深入讲解概念。
    """

    name: str = "ExplainConcept"
    prompt_template: str = """\
你是一位善于讲课的老师。请深入浅出地讲解以下概念。

概念名称：{concept}
讲解深度：{level}
类比偏好：{analogy_preference}

要求：
1. 先用通俗的语言概括
2. 使用类比或生活中的例子帮助理解
3. 给出正式的定义
4. 列举常见误区

请输出详细的概念讲解：
"""

    async def run(
        self,
        concept: str,
        level: str = "beginner",
        analogy_preference: str = "daily_life",
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            concept=concept,
            level=level,
            analogy_preference=analogy_preference,
        )
        result = await self.llm.aask(prompt)
        return result


class GuideDiscussion(Action):
    """
    讨论引导 Action。
    引导学习者进行深度思考和讨论。
    """

    name: str = "GuideDiscussion"
    prompt_template: str = """\
你是一位讨论引导者。请根据以下话题和历史，提出启发性问题引导深入讨论。

讨论主题：
{topic}

讨论历史：
{discussion_history}

要求：
1. 每次提出一个有深度的问题
2. 问题要与主题密切相关
3. 鼓励学习者表达个人观点
4. 逐步引导向更深层次的理解

请输出一段引导语和接下来的讨论问题：
"""

    async def run(
        self,
        topic: str,
        discussion_history: str = "",
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            topic=topic,
            discussion_history=discussion_history,
        )
        result = await self.llm.aask(prompt)
        return result
