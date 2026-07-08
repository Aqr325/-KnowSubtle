#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RoleZero 专用记忆模块
扩展 MetaGPT 的 Memory 支持经验检索
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class RoleZeroMemory:
    """
    为 RoleZero 提供的记忆支持。
    包含短期经验、长期记忆、失败回溯等功能。
    """

    def __init__(self, max_entries: int = 200):
        self.max_entries = max_entries
        self.experience_buffer: List[Dict[str, Any]] = []
        self.short_term_memory: List[str] = []

    def add_experience(self, experience: Dict[str, Any]):
        """添加一条经验到缓冲区"""
        self.experience_buffer.append(experience)
        if len(self.experience_buffer) > self.max_entries:
            self.experience_buffer.pop(0)

    def retrieve_recent(self, k: int = 10) -> List[Dict[str, Any]]:
        """检索最近 k 条经验"""
        return self.experience_buffer[-k:]

    def clear(self):
        """清空记忆"""
        self.experience_buffer.clear()
        self.short_term_memory.clear()
