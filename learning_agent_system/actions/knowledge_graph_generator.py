"""
KnowledgeGraphGenerator — 知识图谱生成 Action

负责：
1. 根据学习者的知识状态生成可视化知识图谱
2. 自动标注薄弱点和已掌握知识点
3. 支持 D3.js / ECharts 格式的图谱输出
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from metagpt.schema import Message
from pydantic import BaseModel, Field

from learning_agent_system.schema import KnowledgeGraph, KnowledgeStatus

logger = logging.getLogger(__name__)


class GraphExportFormat(BaseModel):
    """图谱导出格式"""

    format: str = "echarts"  # echarts / d3 / mermaid
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "GraphExportFormat":
        return cls.model_validate_json(json_str)


class KnowledgeGraphGenerator:
    """知识图谱生成器"""

    def __init__(self):
        self.format: str = "echarts"

    def generate(
        self,
        statuses: List[KnowledgeStatus],
        dependencies: Optional[List[Dict[str, str]]] = None,
    ) -> GraphExportFormat:
        """根据知识状态生成图谱"""
        nodes = []
        edges = []

        for i, status in enumerate(statuses):
            # 根据掌握程度着色
            if status.mastery_level >= 0.8:
                color = "#00cc88"  # 绿色 - 已掌握
                symbol_size = 50
            elif status.mastery_level >= 0.5:
                color = "#ffaa00"  # 橙色 - 进行中
                symbol_size = 40
            else:
                color = "#ff4444"  # 红色 - 薄弱
                symbol_size = 35

            nodes.append({
                "id": str(i),
                "name": status.topic,
                "category": "knowledge_point",
                "value": int(status.mastery_level * 100),
                "symbolSize": symbol_size,
                "itemStyle": {"color": color},
                "label": {"show": True, "position": "inside", "color": "#fff", "fontSize": 10},
                "mastery": status.mastery_level,
                "confidence": status.confidence,
                "reviewCount": status.review_count,
            })

        # 添加依赖边
        if dependencies:
            for dep in dependencies:
                source = dep.get("source", "0")
                target = dep.get("target", "1")
                strength = dep.get("strength", 1.0)
                edges.append({
                    "source": source,
                    "target": target,
                    "value": strength,
                    "lineStyle": {"width": int(strength * 3), "curveness": 0.2},
                })
        elif len(statuses) > 1:
            # 如果没有显式依赖，按顺序连接
            for i in range(len(statuses) - 1):
                edges.append({
                    "source": str(i),
                    "target": str(i + 1),
                    "value": 0.5,
                    "lineStyle": {"width": 1, "curveness": 0.2},
                })

        return GraphExportFormat(
            format=self.format,
            nodes=nodes,
            edges=edges,
            metadata={
                "topic_count": len(statuses),
                "strongest_topic": max(statuses, key=lambda s: s.mastery_level).topic if statuses else "",
                "weakest_topic": min(statuses, key=lambda s: s.mastery_level).topic if statuses else "",
                "average_mastery": sum(s.mastery_level for s in statuses) / len(statuses) if statuses else 0,
            },
        )

    def to_mermaid(self, export: GraphExportFormat) -> str:
        """转换为 Mermaid 格式"""
        lines = ["graph TD"]
        for node in export.nodes:
            lines.append(f"    {node['id']}[{node['name']}:{node['value']}%]")
        for edge in export.edges:
            lines.append(f"    {edge['source']} -->|{edge['value']:.1f}| {edge['target']}")
        return "\n".join(lines)


class GenerateKnowledgeGraphAction:
    """用于 Agent 协作的标准化 Action"""

    name: str = "GenerateKnowledgeGraph"
    description: str = "根据知识状态生成可视化知识图谱"

    def __init__(self, generator: KnowledgeGraphGenerator = None):
        self.generator = generator or KnowledgeGraphGenerator()

    async def run(self, statuses: List[Dict[str, Any]], dependencies: Optional[List[Dict]] = None) -> GraphExportFormat:
        """运行图谱生成"""
        knowledge_statuses = [KnowledgeStatus(**s) for s in statuses]
        return self.generator.generate(knowledge_statuses, dependencies)
