"""
个性化资源生成与学习多智能体系统
基于 MetaGPT 框架的 6-Agent 协作学习引擎
"""

__version__ = "0.1.0"
__author__ = "Learning Agent System Team"

__all__ = []

# --- Early MetaGPT config bootstrap ---
import os

# Ensure LLM config env vars exist BEFORE importing any metagpt module
os.environ.setdefault("LLM_API_KEY", "sk-test-1234567890abcdef")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-1234567890abcdef")

# Patch metagpt.config2 to skip the module-level Config.default() call
# This prevents the ValidationError caused by missing 'llm' field during merge
_original_config2 = None
try:
    import metagpt.config2 as _orig_mod
    _original_config2 = _orig_mod
    # Replace the module-level `config` singleton with a default instance
    from metagpt.configs.llm_config import LLMConfig, LLMType

    _llm_cfg = LLMConfig(
        api_key=os.environ.get("LLM_API_KEY", "dummy"),
        api_type=LLMType.OPENAI,
        model=os.environ.get("LLM_MODEL", "gpt-4o"),
        base_url=os.environ.get("LLM_BASE_URL", None),
    )
    _patched_config = _orig_mod.Config(llm=_llm_cfg)
    _orig_mod.config = _patched_config
except Exception as _bootstrap_err:
    # Non-fatal: the system will try to reconfigure at runtime
    pass
