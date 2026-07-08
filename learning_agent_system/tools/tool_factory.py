#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
工具工厂 - 为 RoleZero 创建可用的工具映射
"""

from __future__ import annotations

from typing import Dict, Any


def create_tool_map() -> Dict[str, Any]:
    """
    返回可用工具映射字典。
    实际运行时会根据 Agent 需要的工具动态加载 MetaGPT 内置工具。
    """
    return {
        "Editor": {
            "name": "editor",
            "description": "文本文件编辑器，支持读写文件内容",
            "enabled": True,
        },
        "Browser": {
            "name": "browser",
            "description": "浏览器工具，支持网页搜索和抓取",
            "enabled": False,
        },
        "SearchEnhancedQA": {
            "name": "search_enhanced_qa",
            "description": "增强问答搜索工具",
            "enabled": False,
        },
    }


def get_enabled_tools(tools_dict: Dict[str, Any], enabled_only: bool = True) -> list:
    """筛选启用的工具"""
    if enabled_only:
        return [name for name, cfg in tools_dict.items() if cfg.get("enabled", False)]
    return list(tools_dict.keys())
