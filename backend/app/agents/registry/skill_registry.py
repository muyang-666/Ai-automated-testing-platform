"""SkillRegistry：测试 Skill 的内存注册表。

- skill code 唯一（首期单版本，版本记录在 SkillDefinition.version）；
- 未知 Skill / 重复注册报明确错误；
- 不动态 import 任意路径、不扫描未知来源 SKILL.md；
- 本任务只注册测试 Fake Skill，不添加生产业务 Skill。
"""

from dataclasses import dataclass, field
from typing import Callable

from app.agents.runtime.errors import DuplicateSkillError, UnknownSkillError


@dataclass(frozen=True)
class SkillDefinition:
    """代码中的不可变 Skill 配置（首期不建数据库表）。"""

    code: str
    name: str
    version: str = "1"
    description: str = ""
    workflow: object | None = None  # AgentWorkflow 实例
    workflow_factory: Callable[[], object] | None = None  # 或按需创建的工厂
    required_context: tuple[str, ...] = field(default_factory=tuple)  # 如 ("requirement_id",)
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)  # 允许的工具名
    default_max_steps: int = 20


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        if skill.code in self._skills:
            raise DuplicateSkillError(
                f"Skill '{skill.code}' 已注册（版本 {self._skills[skill.code].version}），不允许重复注册。"
            )
        self._skills[skill.code] = skill

    def get(self, code: str) -> SkillDefinition:
        skill = self._skills.get(code)
        if skill is None:
            raise UnknownSkillError(f"未知 Skill: '{code}'。已注册: {sorted(self._skills.keys())}")
        return skill

    def list(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda s: s.code)
