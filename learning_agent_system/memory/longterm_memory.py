#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
长期记忆模块 - 支持知识持久化和语义检索
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from learning_agent_system.configs.system_config import SystemConfig


class LongTermMemory:
    """
    长期记忆管理。
    支持将学习者画像、知识状态、练习结果持久化到磁盘。
    """

    def __init__(self, config: Optional[SystemConfig] = None, dir_override: Optional[str] = None):
        """
        config: SystemConfig（提供 knowledge_dir 等）
        dir_override: 直接指定持久化目录，优先级高于 config.knowledge_dir。
                      打包部署时传入 STORAGE_DIR 以避免在只读 Program Files 下创建目录。
        """
        self.config = config or SystemConfig.from_env()
        self.dir = dir_override or self.config.knowledge_dir
        try:
            os.makedirs(self.dir, exist_ok=True)
        except (PermissionError, OSError) as e:
            # 无法写入（如装到 Program Files）：回退到用户 AppData，保证不启动即崩
            import sys as _sys
            fallback = None
            if getattr(_sys, "frozen", False):
                base = os.environ.get("APPDATA") or os.path.expanduser("~")
                fallback = os.path.join(base, "WordCosmos", "Data", "longterm")
            if fallback:
                try:
                    os.makedirs(fallback, exist_ok=True)
                    self.dir = fallback
                    print(f"[LongTermMemory] 回退持久化目录 -> {fallback}  (原 {self.dir} 不可写: {e})")
                except Exception:
                    self.dir = os.path.join(os.path.expanduser("~"), ".wordcosmos", "longterm")
                    os.makedirs(self.dir, exist_ok=True)
            else:
                raise RuntimeError(f"LongTermMemory 无法创建目录 {self.dir}: {e}") from e

    def save(self, key: str, data: Dict[str, Any], filename: Optional[str] = None):
        """将数据保存到文件"""
        fname = filename or f"{key}_{datetime.now().strftime('%Y%m%d')}.json"
        filepath = os.path.join(self.dir, fname)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载指定 key 的最新数据"""
        dir_path = self.dir
        if not os.path.isdir(dir_path):
            return None
        files = [f for f in os.listdir(dir_path) if f.startswith(key) and f.endswith(".json")]
        if not files:
            return None
        latest = sorted(files)[-1]
        filepath = os.path.join(dir_path, latest)
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def delete(self, key: str):
        """删除指定 key 的所有相关文件"""
        files = glob.glob(os.path.join(self.dir, f"{key}_*.json"))
        for f in files:
            os.remove(f)
