#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Actions 包初始化 - 延迟导入避免循环依赖
"""

from __future__ import annotations


def _get_KnowledgeDiagnosis():
    from learning_agent_system.actions.knowledge_diagnosis import KnowledgeDiagnosis
    return KnowledgeDiagnosis


def _get_CapabilityAssessment():
    from learning_agent_system.actions.knowledge_diagnosis import CapabilityAssessment
    return CapabilityAssessment


def _get_PrefModeling():
    from learning_agent_system.actions.pref_modeling import PrefModeling
    return PrefModeling


def _get_GenerateKnowledgePoint():
    from learning_agent_system.actions.resource_generation import GenerateKnowledgePoint
    return GenerateKnowledgePoint


def _get_GenerateExercise():
    from learning_agent_system.actions.resource_generation import GenerateExercise
    return GenerateExercise


def _get_GenerateCase():
    from learning_agent_system.actions.resource_generation import GenerateCase
    return GenerateCase


def _get_GenerateCodeExample():
    from learning_agent_system.actions.resource_generation import GenerateCodeExample
    return GenerateCodeExample


def _get_GenerateVisualAid():
    from learning_agent_system.actions.resource_generation import GenerateVisualAid
    return GenerateVisualAid


def _get_PlanLearningPath():
    from learning_agent_system.actions.learning_path import PlanLearningPath
    return PlanLearningPath


def _get_AdaptiveAdjust():
    from learning_agent_system.actions.learning_path import AdaptiveAdjust
    return AdaptiveAdjust


def _get_EvaluateExercise():
    from learning_agent_system.actions.exercise_evaluation import EvaluateExercise
    return EvaluateExercise


def _get_AnalyzeMistakes():
    from learning_agent_system.actions.exercise_evaluation import AnalyzeMistakes
    return AnalyzeMistakes


def _get_AnswerQuestion():
    from learning_agent_system.actions.tutor_actions import AnswerQuestion
    return AnswerQuestion


def _get_ExplainConcept():
    from learning_agent_system.actions.tutor_actions import ExplainConcept
    return ExplainConcept


def _get_GuideDiscussion():
    from learning_agent_system.actions.tutor_actions import GuideDiscussion
    return GuideDiscussion


def _get_StoreKnowledge():
    from learning_agent_system.actions.knowledge_ops import StoreKnowledge
    return StoreKnowledge


def _get_RetrieveKnowledge():
    from learning_agent_system.actions.knowledge_ops import RetrieveKnowledge
    return RetrieveKnowledge


def _get_BuildKnowledgeGraph():
    from learning_agent_system.actions.knowledge_ops import BuildKnowledgeGraph
    return BuildKnowledgeGraph


# 所有 Action 类导出（占位，实际类会在导入时延迟解析）
KnowledgeDiagnosis = _get_KnowledgeDiagnosis()
CapabilityAssessment = _get_CapabilityAssessment()
PrefModeling = _get_PrefModeling()
GenerateKnowledgePoint = _get_GenerateKnowledgePoint()
GenerateExercise = _get_GenerateExercise()
GenerateCase = _get_GenerateCase()
GenerateCodeExample = _get_GenerateCodeExample()
GenerateVisualAid = _get_GenerateVisualAid()
PlanLearningPath = _get_PlanLearningPath()
AdaptiveAdjust = _get_AdaptiveAdjust()
EvaluateExercise = _get_EvaluateExercise()
AnalyzeMistakes = _get_AnalyzeMistakes()
AnswerQuestion = _get_AnswerQuestion()
ExplainConcept = _get_ExplainConcept()
GuideDiscussion = _get_GuideDiscussion()
StoreKnowledge = _get_StoreKnowledge()
RetrieveKnowledge = _get_RetrieveKnowledge()
BuildKnowledgeGraph = _get_BuildKnowledgeGraph()

__all__ = [
    "KnowledgeDiagnosis",
    "CapabilityAssessment",
    "PrefModeling",
    "GenerateKnowledgePoint",
    "GenerateExercise",
    "GenerateCase",
    "GenerateCodeExample",
    "GenerateVisualAid",
    "PlanLearningPath",
    "AdaptiveAdjust",
    "EvaluateExercise",
    "AnalyzeMistakes",
    "AnswerQuestion",
    "ExplainConcept",
    "GuideDiscussion",
    "StoreKnowledge",
    "RetrieveKnowledge",
    "BuildKnowledgeGraph",
]
