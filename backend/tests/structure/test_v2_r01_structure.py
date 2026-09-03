"""V2-R01 目录整理的结构性回归测试。

- 只验证“移动后结构与行为不变”：
  1) 新规范路径可导入、schemas/agent 包级重导出指向同一实现；
  2) 模型类身份一致、Base.metadata 表集合/结构未变（无重复 ORM 注册）；
  3) 路由集合无重复注册、关键端点仍各只有一个；
  4) case_generation 的 Prompt 资源仍可加载；
  5) monkeypatch 的 llm_client_service 就是业务实际使用的模块对象。

不发起业务请求、不写文件产物、不初始化真实客户端；DB 仅 conftest 临时 SQLite。
"""

import pytest
from sqlalchemy.orm import Session

from app.core.database import Base


def _import_all_new_paths():
    # models/agent
    from app.models.agent import agent_session  # noqa: F401
    from app.models.agent import agent_message  # noqa: F401
    from app.models.agent import agent_run  # noqa: F401
    from app.models.agent import agent_step  # noqa: F401
    from app.models.agent import agent_event  # noqa: F401
    from app.models.agent import agent_artifact  # noqa: F401
    from app.models.agent import agent_approval  # noqa: F401
    # models/llm
    from app.models.llm import llm_provider  # noqa: F401
    from app.models.llm import llm_model  # noqa: F401
    from app.models.llm import llm_scene_config  # noqa: F401
    # services/agent + llm
    from app.services.agent import agent_session_service  # noqa: F401
    from app.services.agent import agent_run_service  # noqa: F401
    from app.services.agent import agent_artifact_service  # noqa: F401
    from app.services.agent import agent_approval_service  # noqa: F401
    from app.services.llm import llm_config_service  # noqa: F401
    from app.services.llm import llm_client_service  # noqa: F401
    from app.services.llm import llm_gateway  # noqa: F401
    # schemas/llm
    from app.schemas.llm import llm_config  # noqa: F401
    from app.schemas.llm import llm_gateway  # noqa: F401
    # schemas/agent (package api + platform)
    from app.schemas.agent import platform  # noqa: F401
    # routers
    from app.routers.agent import agent_router  # noqa: F401
    from app.routers.llm import llm_config_router  # noqa: F401


def test_new_paths_importable():
    _import_all_new_paths()


def test_schemas_agent_package_reexport_single_implementation():
    from app.schemas.agent import AgentSessionCreate as PkgSessionCreate
    from app.schemas.agent.api import AgentSessionCreate as ApiSessionCreate
    from app.schemas.agent.platform import SESSION_STATUSES, RUN_STATUSES

    assert PkgSessionCreate is ApiSessionCreate  # 同一定义，非复制
    assert SESSION_STATUSES == ("active", "closed", "archived")
    assert "queued" in RUN_STATUSES


def test_model_identity_and_metadata_registration(db_session: Session):
    from app.models import AgentRun as RootAgentRun
    from app.models import LLMProvider as RootProvider
    from app.models.agent.agent_run import AgentRun as PkgAgentRun
    from app.models.llm.llm_provider import LLMProvider as PkgProvider

    # 同一模型类（app.models 原公开名仍可用）
    assert RootAgentRun is PkgAgentRun
    assert RootProvider is PkgProvider

    moved_tables = {
        "agent_sessions", "agent_messages", "agent_runs", "agent_steps",
        "agent_events", "agent_artifacts", "agent_approvals",
        "llm_providers", "llm_models", "llm_scene_configs",
    }
    tables = set(Base.metadata.tables)
    assert moved_tables <= tables
    # 注册到同一份 metadata，无重复表定义
    assert PkgAgentRun.__table__ is Base.metadata.tables["agent_runs"]
    assert PkgProvider.__table__ is Base.metadata.tables["llm_providers"]
    # 结构关键列未变
    cols = {c.name for c in Base.metadata.tables["agent_sessions"].columns}
    assert {"id", "project_id", "user_id", "title", "status", "context_json"} <= cols


def test_route_registration_no_duplicates_and_key_endpoints_present():
    from app.main import app

    seen: dict[tuple[str, str], int] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in methods:
            key = (method.upper(), path)
            seen[key] = seen.get(key, 0) + 1

    assert all(count == 1 for count in seen.values()), [
        key for key, count in seen.items() if count > 1
    ]
    assert ("POST", "/agent/sessions") in seen
    assert ("GET", "/llm-config/providers") in seen
    assert ("POST", "/agent/runs/case-generation") in seen


def test_case_generation_prompt_still_loadable():
    from app.agents.skills.case_generation.prompt_loader import load_instructions, load_prompt

    plan = load_prompt("analyze_and_plan_v1")
    instructions = load_instructions()
    assert isinstance(plan, str) and "source_context" in plan
    assert isinstance(instructions, str) and instructions.strip()


def test_llm_client_service_patch_target_is_actual_module(monkeypatch):
    # monkeypatch 必须作用于业务实际使用的模块对象（不是假转发副本）
    import app.services.llm.llm_client_service as via_import
    from app.services.llm import llm_client_service as via_package

    assert via_import is via_package

    sentinel = object()
    monkeypatch.setattr(via_import, "_gateway", sentinel)
    assert via_package._gateway is sentinel
