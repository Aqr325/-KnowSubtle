#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
学习路径规划与自适应调整 Action
"""

from __future__ import annotations

from typing import List, Optional

from metagpt.actions import Action


class PlanLearningPath(Action):
    """
    学习路径规划 Action。
    根据目标知识点和学习者画像规划最优学习路径。
    """

    name: str = "PlanLearningPath"
    prompt_template: str = """\
你是一位学习路径规划专家。请根据以下信息设计个性化的学习路径。

学习者画像：
{profile_json}

学习目标：
{goals}

要求：
1. 遵循从基础到进阶的递进逻辑
2. 考虑学习者的薄弱环节，前置相关模块
3. 为每个模块标注知识点、预估时间、前置条件
4. 输出结构化的学习路径

请按以下 JSON 格式输出：
{{
  "path_name": "学习路径名称",
  "modules": [
    {{
      "order": 1,
      "title": "模块标题",
      "topics": ["知识点1", "知识点2"],
      "estimated_hours": 2.0,
      "prerequisites": [],
      "resources_needed": ["讲解文档", "练习题"]
    }}
  ],
  "total_estimated_hours": 10.0,
  "summary": "路径规划说明..."
}}
"""

    async def run(
        self,
        goals: List[str],
        profile_json: str,
        **kwargs,
    ) -> str:
        goals_text = "\n".join(f"- {g}" for g in goals)
        prompt = self.prompt_template.format(
            profile_json=profile_json,
            goals=goals_text,
        )
        result = await self.llm.aask(prompt)
        return result


class AdaptiveAdjust(Action):
    """
    自适应调整 Action。
    根据学习进度和练习结果动态调整学习路径。
    """

    name: str = "AdaptiveAdjust"
    prompt_template: str = """\
你是一个自适应学习系统。请根据以下信息对学习路径进行调整。

当前学习路径：
{current_path}

学习进度与练习结果：
{progress_data}

请分析：
1. 哪些环节遇到了瓶颈？
2. 瓶颈的原因是什么？
3. 应该如何调整路径？

请按以下 JSON 格式输出调整建议：
{{
  "bottleneck_topics": ["遇到的瓶颈知识点"],
  "bottleneck_reason": "原因分析...",
  "adjustments": [
    {{
      "module_id": "模块ID",
      "action": "补基础/加深理解/更换资源/跳过",
      "reason": "调整理由"
    }}
  ],
  "adjusted_path_summary": "调整后的路径概述..."
}}
"""

    async def run(
        self,
        current_path: str,
        progress_data: str,
        **kwargs,
    ) -> str:
        prompt = self.prompt_template.format(
            current_path=current_path,
            progress_data=progress_data,
        )
        result = await self.llm.aask(prompt)
        return result
