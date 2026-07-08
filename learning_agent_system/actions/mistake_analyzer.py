"""
MistakeAnalyzer — 错题分析 Action

负责：
1. 对学习者在练习中出现的错误进行分类和深度分析
2. 识别错误类型（概念错误 / 粗心 / 知识盲区 / 理解偏差）
3. 生成针对性纠正方案
4. 自动加入错题本
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from metagpt.schema import Message
from pydantic import BaseModel, Field

from learning_agent_system.schema import ExerciseResult, MistakeRecord, ExerciseType

logger = logging.getLogger(__name__)


class MistakeAnalysis(BaseModel):
    """错题分析结果"""

    mistake: MistakeRecord
    root_cause: str = ""
    correction_plan: List[str] = Field(default_factory=list)
    similar_topics: List[str] = Field(default_factory=list)
    difficulty_adjustment: str = "maintain"  # easier / maintain / harder
    priority: str = "normal"  # high / medium / low

    def to_dict(self) -> Dict[str, Any]:
        return self.dict() if hasattr(self, "dict") else self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json() if hasattr(self, "model_dump_json") else self.json()

    @classmethod
    def from_json(cls, json_str: str) -> "MistakeAnalysis":
        return cls.parse_raw(json_str) if hasattr(cls, "parse_raw") else cls.model_validate_json(json_str)


class MistakeAnalyzer:
    """错题分析器"""

    def __init__(self):
        self.llm_config: Dict[str, Any] = {}

    async def analyze(self, result: ExerciseResult, topics: List[str] = None) -> MistakeAnalysis:
        """对一次练习结果进行错题分析"""
        if result.is_correct:
            return MistakeAnalysis(
                mistake=MistakeRecord(
                    exercise_id=result.exercise_id,
                    topic=topics[0] if topics else "unknown",
                    question="",
                    learner_answer=result.learner_answer,
                    correct_answer=result.correct_answer,
                    error_type="correct",
                    severity=0.0,
                    timestamp=datetime.now().isoformat(),
                ),
                root_cause="Answer is correct, no error to analyze",
                correction_plan=["Continue current learning path"],
                difficulty_adjustment="maintain",
                priority="low",
            )

        topics = topics or []
        system_prompt = f"""你是一个专业的错题分析AI。请分析以下学习者的错误并给出针对性建议。

当前学习者的薄弱知识点：{', '.join(topics) if topics else '未知'}
"""
        user_prompt = f"""## 错误分析任务

**题目ID:** {result.exercise_id}
**正确答案:** {result.correct_answer}
**学习者答案:** {result.learner_answer}
**错误描述:** {result.error_analysis}

请分析并返回 JSON 格式：
{{
    "error_type": "concept_error|careless|knowledge_gap|misunderstanding",
    "severity": 0.0-1.0,
    "root_cause": "错误的根本原因",
    "correction_plan": ["针对性的纠正措施1", "纠正措施2"],
    "similar_topics": ["相关薄弱知识点"],
    "difficulty_adjustment": "easier|maintain|harder",
    "priority": "high|medium|low"
}}

仅输出 JSON，不要输出其他内容。
"""
        prompt = f"{system_prompt}\n\n{user_prompt}"
        msg = Message(content=prompt, role="user")

        try:
            rsp = await self._llm_call(msg)
            analysis_data = json.loads(rsp)
            mistake = MistakeRecord(
                exercise_id=result.exercise_id,
                topic=topics[0] if topics else "unknown",
                question=f"Exercise: {result.exercise_id}",
                learner_answer=result.learner_answer,
                correct_answer=result.correct_answer,
                error_type=analysis_data.get("error_type", "knowledge_gap"),
                severity=analysis_data.get("severity", 0.5),
                timestamp=datetime.now().isoformat(),
            )
            return MistakeAnalysis(
                mistake=mistake,
                root_cause=analysis_data.get("root_cause", ""),
                correction_plan=analysis_data.get("correction_plan", []),
                similar_topics=analysis_data.get("similar_topics", []),
                difficulty_adjustment=analysis_data.get("difficulty_adjustment", "maintain"),
                priority=analysis_data.get("priority", "medium"),
            )
        except Exception as e:
            logger.error(f"MistakeAnalysis failed: {e}")
            return MistakeAnalysis(
                mistake=MistakeRecord(
                    exercise_id=result.exercise_id,
                    topic=topics[0] if topics else "unknown",
                    question="",
                    learner_answer=result.learner_answer,
                    correct_answer=result.correct_answer,
                    error_type="unknown",
                    severity=0.7,
                ),
                root_cause="Analysis failed due to error",
                correction_plan=["Please review the basics of this topic"],
            )

    async def batch_analyze(self, results: List[ExerciseResult], topics: List[str] = None) -> List[MistakeAnalysis]:
        """批量分析多个练习结果"""
        analyses = []
        for result in results:
            if not result.is_correct:
                analysis = await self.analyze(result, topics)
                analyses.append(analysis)
        return analyses

    async def _llm_call(self, msg: Message) -> Dict[str, Any]:
        """调用 LLM 进行分析"""
        try:
            from metagpt.const import METAGPT_PROJECT_KW
            from metagpt.config2 import Config
            cfg = Config.from_dict({METAGPT_PROJECT_KW: []})
            self.llm_config = cfg.to_llm_config()
        except Exception:
            pass
        try:
            from metagpt.provider.base_llm import BaseLLM
            llm = BaseLLM()
            rsp = await llm.aask(msg.content)
            return json.loads(rsp)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                "error_type": "knowledge_gap",
                "severity": 0.7,
                "root_cause": "LLM analysis unavailable, using heuristic default",
                "correction_plan": ["Review foundational concepts", "Practice similar problems"],
                "difficulty_adjustment": "easier",
            }


class AnalyzeMistakesAction:
    """用于 Agent 协作的标准化 Action"""

    name: str = "AnalyzeMistakes"
    description: str = "分析学习者的练习题错误，生成纠正方案"

    def __init__(self, mistake_analyzer: MistakeAnalyzer = None):
        self.mistake_analyzer = mistake_analyzer or MistakeAnalyzer()

    async def run(self, results: List[Dict[str, Any]], topics: List[str] = None) -> List[MistakeAnalysis]:
        """运行错题分析"""
        exercise_results = []
        for r in results:
            exercise_results.append(ExerciseResult(**r))
        return await self.mistake_analyzer.batch_analyze(exercise_results, topics)
