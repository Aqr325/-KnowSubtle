#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
资源生成模块 - 知识点讲解、智能出题、案例生成、代码示例、可视化辅助
"""

from __future__ import annotations

from typing import List, Optional

from metagpt.actions import Action


class GenerateKnowledgePoint(Action):
    """
    知识点讲解生成 Action。
    根据知识点、学习者水平和风格生成个性化的讲解内容。
    """

    name: str = "GenerateKnowledgePoint"
    prompt_template: str = """\
你是一位优秀的教师。请根据以下信息生成个性化的知识点讲解。

知识点：{topic}
学习者水平：{learner_level}
学习风格：{learning_style}
薄弱点：{weak_points}

要求：
1. 根据学习者的水平调整讲解难度
2. 根据学习风格选择合适的呈现方式（视觉型多用图示类比，实践型多用例子）
3. 覆盖薄弱知识点
4. 输出通俗易懂的讲解内容

请输出知识点讲解内容：
"""

    async def run(
        self,
        topic: str,
        learner_level: str = "beginner",
        learning_style: str = "visual",
        weak_points: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        weak_points_text = ", ".join(weak_points) if weak_points else "无明显薄弱点"
        prompt = self.prompt_template.format(
            topic=topic,
            learner_level=learner_level,
            learning_style=learning_style,
            weak_points=weak_points_text,
        )
        result = await self.llm.aask(prompt)
        return result


class GenerateExercise(Action):
    """
    智能出题 Action。
    根据知识点和学习者水平生成练习题。
    """

    name: str = "GenerateExercise"
    prompt_template: str = """\
请根据以下要求生成一道练习题：

知识点：{topic}
难度等级：{difficulty}
题型：{exercise_type}

要求：
1. 题目要有针对性，考察核心概念
2. 如果是选择题，提供 A-D 四个选项
3. 必须提供正确答案和详细解析

请按以下 JSON 格式输出：
{{
  "question": "题目内容...",
  "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
  "answer": "A",
  "explanation": "详细解析...",
  "difficulty": "{difficulty}"
}}
"""

    async def run(
        self,
        topic: str,
        difficulty: str = "medium",
        exercise_type: str = "choice",
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            topic=topic,
            difficulty=difficulty,
            exercise_type=exercise_type,
        )
        result = await self.llm.aask(prompt)
        return result


class GenerateCase(Action):
    """
    案例生成 Action。
    基于真实应用场景生成教学案例。
    """

    name: str = "GenerateCase"
    prompt_template: str = """\
请根据以下信息生成一个教学案例：

知识点：{topic}
行业/领域：{industry}
复杂度：{complexity}

要求：
1. 案例要贴近实际应用场景
2. 有明确的问题背景和解决思路
3. 适合教学目标

请输出完整的案例描述：
"""

    async def run(
        self,
        topic: str,
        industry: str = "general",
        complexity: str = "basic",
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            topic=topic,
            industry=industry,
            complexity=complexity,
        )
        result = await self.llm.aask(prompt)
        return result


class GenerateCodeExample(Action):
    """
    代码示例生成 Action。
    针对编程知识点生成带注释的代码示例。
    """

    name: str = "GenerateCodeExample"
    prompt_template: str = """\
请根据以下信息生成一个编程代码示例：

知识点：{topic}
编程语言：{language}
代码级别：{level}

要求：
1. 代码要简洁清晰
2. 包含必要的注释
3. 展示核心概念的最佳实践

请输出完整的代码示例：
"""

    async def run(
        self,
        topic: str,
        language: str = "python",
        level: str = "beginner",
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            topic=topic,
            language=language,
            level=level,
        )
        result = await self.llm.aask(prompt)
        return result


class GenerateVisualAid(Action):
    """
    可视化辅助生成 Action。
    生成概念图、流程图、思维导图的 Mermaid 格式描述。
    """

    name: str = "GenerateVisualAid"
    prompt_template: str = """\
请为以下知识点生成一个可视化的 Mermaid 流程图或思维导图描述。

知识点：{topic}
可视化类型：{viz_type}

要求：
1. 使用合法的 Mermaid 语法
2. 结构清晰，层次分明
3. 适合教学展示

请输出 Mermaid 代码块：
"""

    async def run(
        self,
        topic: str,
        viz_type: str = "flowchart",
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            topic=topic,
            viz_type=viz_type,
        )
        result = await self.llm.aask(prompt)
        return result
