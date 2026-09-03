"""SkillRegistry 测试：注册/查询/唯一性/未知错误。"""

import pytest

from app.agents.registry import SkillDefinition, SkillRegistry
from app.agents.runtime.errors import DuplicateSkillError, UnknownSkillError


def _skill(code="fake_skill"):
    return SkillDefinition(code=code, name=f"技能 {code}", version="1", description="测试技能")


def test_register_and_get():
    registry = SkillRegistry()
    skill = _skill("fake_a")
    registry.register(skill)
    registry.register(_skill("fake_b"))

    assert registry.get("fake_a") is skill
    assert [s.code for s in registry.list()] == ["fake_a", "fake_b"]


def test_duplicate_code_rejected():
    registry = SkillRegistry()
    registry.register(_skill("fake_dup"))

    with pytest.raises(DuplicateSkillError) as exc:
        registry.register(_skill("fake_dup"))
    assert "fake_dup" in str(exc.value)
    assert exc.value.error_code == "agent_duplicate_skill"


def test_unknown_skill_error():
    registry = SkillRegistry()

    with pytest.raises(UnknownSkillError) as exc:
        registry.get("no_such_skill")
    assert "no_such_skill" in str(exc.value)
    assert exc.value.error_code == "agent_unknown_skill"


def test_skill_definition_defaults():
    skill = _skill("fake_defaults")

    assert skill.version == "1"
    assert skill.description == "测试技能"
    assert skill.workflow is None
    assert skill.workflow_factory is None
    assert skill.required_context == ()
    assert skill.allowed_tools == ()
    assert skill.default_max_steps == 20
