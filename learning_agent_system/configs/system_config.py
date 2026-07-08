#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
系统配置模块 - 从环境变量和默认值加载配置
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from pydantic import BaseSettings, Field
except ImportError:
    from pydantic.v1 import BaseSettings, Field  # type: ignore[no-redef, import-not-found, assignment]


class SystemConfig(BaseSettings):
    """系统全局配置"""

    # LLM 配置
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    llm_model: str = Field(default="gpt-4o", description="LLM 模型名称")
    llm_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="LLM API 基础 URL"
    )
    llm_temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=4096)

    # 向量数据库
    vector_db_type: str = Field(default="chroma", description="向量数据库类型: chroma/faiss/qdrant/milvus")
    vector_db_path: str = Field(default="./memory/vector_db")
    knowledge_dir: str = Field(default="./memory/knowledge")
    max_learner_history: int = Field(default=100)

    # MetaGPT context
    max_round: int = Field(default=20, description="最大对话轮次")
    memory_k: int = Field(default=200, description="短期记忆保留条目数")

    class Config:
        env_file = ".env"
        extra = "ignore"

    @classmethod
    def from_env(cls) -> "SystemConfig":
        """从环境变量加载配置"""
        # Support both Pydantic V1 (model_fields) and V2 (__fields__)
        default_key = getattr(cls, "model_fields", None)
        if default_key:
            default_val = default_key.get("openai_api_key", {}).get("default", "")
        else:
            default_val = cls.__fields__["openai_api_key"].default
        os.environ.setdefault("OPENAI_API_KEY", str(default_val or ""))
        return cls()

    @property
    def is_configured(self) -> bool:
        """检查关键配置是否就绪"""
        return bool(self.openai_api_key.strip())
