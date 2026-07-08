"""MetaGPT stub module for demo mode."""


class Role:
    """Dummy Role class for demo."""

    def __init__(self, **kwargs):
        self.name = kwargs.get("name", "Role")
        self.role_name = kwargs.get("role_name", "")
        self.goals = kwargs.get("goals", [])
        self.constraints = kwargs.get("constraints", "")
        self.desc = kwargs.get("desc", "")
        self.states = kwargs.get("states", [])
        self.project = kwargs.get("project", None)
        self.env = kwargs.get("env", None)
        self.codes = kwargs.get("codes", [])

    def set_actions(self, actions):
        self.actions = actions or []

    def add_prompts(self, prompts):
        self.prompts = prompts

    def get_prompts(self):
        return self.prompts

    def observe(self, message):
        pass

    def reset(self):
        pass

    async def _a_star(self):
        return None

    async def _react(self):
        content = ""
        for action in self.actions:
            try:
                result = await action._run(self)
                if result:
                    content += result
            except Exception:
                continue
        return content

    async def _run(self):
        return None

    def __repr__(self):
        return f"<Role name={self.name}>"


class RoleZero(Role):
    """Dummy RoleZero class (not used in our agents)."""
    pass
