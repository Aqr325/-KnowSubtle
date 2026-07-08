#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agents 包初始化 - 延迟导入避免循环依赖
"""

from __future__ import annotations


def _get_LearnerProfiler():
    from learning_agent_system.agents.learner_profiler import LearnerProfiler
    return LearnerProfiler


def _get_ResourceGenerator():
    from learning_agent_system.agents.resource_generator import ResourceGenerator
    return ResourceGenerator


def _get_LearningPlanner():
    from learning_agent_system.agents.learning_planner import LearningPlanner
    return LearningPlanner


def _get_ExerciseEvaluator():
    from learning_agent_system.agents.exercise_evaluator import ExerciseEvaluator
    return ExerciseEvaluator


def _get_LearningTutor():
    from learning_agent_system.agents.learning_tutor import LearningTutor
    return LearningTutor


def _get_KnowledgeBase():
    from learning_agent_system.agents.knowledge_base import KnowledgeBase
    return KnowledgeBase


# 所有 Agent 类导出
LearnerProfiler = _get_LearnerProfiler()
ResourceGenerator = _get_ResourceGenerator()
LearningPlanner = _get_LearningPlanner()
ExerciseEvaluator = _get_ExerciseEvaluator()
LearningTutor = _get_LearningTutor()
KnowledgeBase = _get_KnowledgeBase()

__all__ = [
    "LearnerProfiler",
    "ResourceGenerator",
    "LearningPlanner",
    "ExerciseEvaluator",
    "LearningTutor",
    "KnowledgeBase",
]
