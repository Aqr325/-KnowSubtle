"""MetaGPT stubs for demo mode — replaces real metagpt package imports.

Usage: run this file BEFORE importing anything from the learning_agent_system package.
"""

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Inject stub package ────────────────────────────────────────────────
import types

_meta_stub = types.ModuleType("metagpt")
_meta_stub.__path__ = [str(Path(__file__).resolve().parent)]
_meta_stub.__file__ = str(__file__)
sys.modules["metagpt"] = _meta_stub

# 标记演示模式：orchestrator 据此跳过真实大模型调用，改走离线占位逻辑
os.environ["METAGPT_STUBBED"] = "1"

# 1) metagpt.roles
_roles_mod = types.ModuleType("metagpt.roles")
_roles_mod.__file__ = str(Path(__file__).parent / "metagpt" / "roles.py")

class _Role:
    """Minimal Role base — our agents inherit from this in demo mode."""
    def __init__(self, **kwargs):
        self.name: str = kwargs.get("name", "Agent")
        self.role_name: str = kwargs.get("role_name", "")
        self.goals: list = kwargs.get("goals", [])
        self.constraints: str = kwargs.get("constraints", "")
        self.desc: str = kwargs.get("desc", "")
        self.project = kwargs.get("project", None)
        self.env = kwargs.get("env", None)
        self.codes: list = kwargs.get("codes", [])
        self._actions: list = []
        self.states: list = kwargs.get("states", [])
        self.prompts: list = kwargs.get("prompts", [])

    def set_actions(self, actions):
        self._actions = list(actions)

    def add_prompts(self, prompts):
        self.prompts = list(prompts)

    def get_prompts(self):
        return self.prompts

    def observe(self, message):
        pass

    def reset(self):
        self._memory = []

    async def _react(self):
        content_parts = []
        for action in self._actions:
            try:
                result = await action._run(self)
                if result:
                    content_parts.append(str(result))
            except Exception:
                continue
        return "".join(content_parts)

    async def _run(self):
        return None

    def __repr__(self):
        return f"<Role name={self.name!r}>"


class RoleZero(_Role):
    """RoleZero not used in our agents, alias for compatibility."""
    pass


_roles_mod.Role = _Role
_roles_mod.RoleZero = RoleZero
sys.modules["metagpt.roles"] = _roles_mod
_meta_stub.roles = _roles_mod

# 2) metagpt.schema
_schema_mod = types.ModuleType("metagpt.schema")
_schema_mod.__file__ = str(Path(__file__).parent / "metagpt" / "schema.py")

class _Message:
    """Minimal Message stub."""
    def __init__(self, content="", role="user", id=None, cause_by="", meta=None, instruct_content=None):
        self.content = content
        self.role = role
        self.id = id
        self.cause_by = cause_by
        self.meta = meta or {}
        self.instruct_content = instruct_content

    def __repr__(self):
        return f"<Message role={self.role} content={self.content!r}>"

    def __str__(self):
        return self.content


_schema_mod.Message = _Message
sys.modules["metagpt.schema"] = _schema_mod
_meta_stub.schema = _schema_mod

# 3) metagpt.actions
_actions_mod = types.ModuleType("metagpt.actions")
_actions_mod.__file__ = str(Path(__file__).parent / "metagpt" / "actions.py")

class _Action:
    """Minimal Action stub."""
    def __init__(self, name="", context=None, *args, **kwargs):
        self.name = name or self.__class__.__name__
        self.context = context
        self.desc = kwargs.get("desc", self.name)

    async def _run(self, *args, **kwargs):
        return "Demo mode — no real AI generation."

    def __repr__(self):
        return f"<Action name={self.name!r}>"


_actions_mod.Action = _Action

_add_req = types.ModuleType("metagpt.actions.add_requirement")
_add_req.UserRequirement = _Action(name="UserRequirement")
sys.modules["metagpt.actions.add_requirement"] = _add_req
_actions_mod.add_requirement = _add_req

sys.modules["metagpt.actions"] = _actions_mod
_meta_stub.actions = _actions_mod

# 4) metagpt.logs
_logs_mod = types.ModuleType("metagpt.logs")
_logs_mod.__file__ = str(Path(__file__).parent / "metagpt" / "logs.py")

class _Logger:
    """No-op logger."""
    @staticmethod
    def info(msg, *args, **kwargs): pass
    @staticmethod
    def warning(msg, *args, **kwargs): pass
    @staticmethod
    def error(msg, *args, **kwargs): pass
    @staticmethod
    def debug(msg, *args, **kwargs): pass
    @staticmethod
    def success(msg, *args, **kwargs): pass

logger = _Logger()
_logs_mod.logger = logger
sys.modules["metagpt.logs"] = _logs_mod
_meta_stub.logs = _logs_mod

print("[local_metagpt.stub] OK metagpt package stubbed for demo mode.")
