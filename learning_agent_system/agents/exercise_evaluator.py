#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
练习评测 Agent - ExerciseEvaluator
对学习者的练习作答进行深度分析、智能批改并生成针对性反馈
"""

from __future__ import annotations

from typing import List, Optional

from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.roles import Role

from learning_agent_system.actions import AnalyzeMistakes, EvaluateExercise
from learning_agent_system.schema import Exercise, ExerciseResult, LearnerProfile
from learning_agent_system.tools.tool_factory import create_tool_map


class ExerciseEvaluator(Role):
    """
    练习评测 Agent。
    对学习者答案进行深度分析、智能批改并生成针对性反馈。
    """

    profile: str = "Exercise Evaluator"
    name: str = "Eva"
    goal: str = "对学习者的练习作答进行深度分析、智能批改并生成针对性反馈"
    constraints: str = "提供建设性反馈而非简单判断对错，分析错误根源"
    tools: List[str] = ["Editor"]
    todo_action: str = "EvaluateExercise"
    react_mode: str = "react"
    max_react_loop: int = 30
    learner_profile: Optional[LearnerProfile] = None
    mistake_log: List[ExerciseResult] = []

    def __init__(self, learner_profile: Optional[LearnerProfile] = None, **kwargs):
        super().__init__(**kwargs)
        self.learner_profile = learner_profile
        self.mistake_log = []
        self.set_actions([EvaluateExercise, AnalyzeMistakes])
        self._tool_map = create_tool_map()

    def _watch(self, watch=None):
        """订阅消息类型"""
        super()._watch(watch or [UserRequirement])

    def _update_tool_execution(self):
        """注册工具执行映射"""
        if "Editor" in self._tool_map:
            editor_cfg = self._tool_map.get("Editor", {})
            if editor_cfg.get("enabled"):
                self.record_observation("Registered Editor tool for ExerciseEvaluator")

    async def evaluate(
        self,
        exercise: Exercise,
        learner_answer: str,
        **kwargs,
    ) -> ExerciseResult:
        """
        评测练习作答
        """
        result_str = await EvaluateExercise().llm.aask(
            f"题目: {exercise.question}, 正确答案: {exercise.answer}, 学习者答案: {learner_answer}"
        )
        
        is_correct = exercise.answer.lower() in learner_answer.lower() or learner_answer.lower() in exercise.answer.lower()
        
        result = ExerciseResult(
            exercise_id=exercise.id,
            learner_answer=learner_answer,
            correct_answer=exercise.answer,
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            error_analysis=result_str,
        )
        
        if not is_correct:
            self.mistake_log.append(result)
            
        return result

    async def analyze_mistakes(self) -> str:
        """
        分析错题模式
        """
        if not self.mistake_log:
            return "暂无错题记录"
        
        mistakes_text = "\n".join(r.to_json() for r in self.mistake_log)
        result = await AnalyzeMistakes().llm.aask(mistakes_text)
        return result
