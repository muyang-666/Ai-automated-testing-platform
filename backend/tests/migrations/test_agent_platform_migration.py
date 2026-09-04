"""Alembic 增量接管方案的迁移测试。

全部使用临时 SQLite 文件，不操作真实 MySQL、不把 create_all 成功当作 migration 证据。

覆盖：
- 构造 V1-only schema（模拟存量数据库）→ stamp 0001 → upgrade head → 校验 Agent 表；
- downgrade 只删 Agent 表、V1 表保留；
- 再次 upgrade 可成功；
- create_all 先建过 Agent 表的重叠场景：0002 结构校验通过而非静默跳过；
- 结构不一致时必须明确失败；
- 0001 no-op 不创建任何表。
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.database import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT_LOCATION = str(BACKEND_DIR / "alembic")

BASELINE_REVISION = "0001_v1_schema_baseline"
HEAD_REVISION = "0003_conversation_persistence"

AGENT_TABLE_NAMES = {
    "agent_sessions",
    "agent_messages",
    "agent_events",
    "agent_runs",
    "agent_steps",
    "agent_artifacts",
    "agent_approvals",
}

V1_TABLE_NAMES = {
    "api_cases",
    "auth_sessions",
    "test_runs",
    "ai_analyses",
    "reports",
    "scenes",
    "projects",
    "roles",
    "test_modules",
    "requirement_docs",
    "function_cases",
    "scene_runs",
    "scene_step_runs",
    "scene_steps",
    "api_documents",
    "llm_providers",
    "llm_models",
    "llm_scene_configs",
    "users",
    "user_project_permissions",
    "user_roles",
}


def _make_config(db_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _create_v1_schema(engine) -> None:
    """模拟存量数据库：只创建 V1 的 21 张表。"""
    v1_tables = [t for t in Base.metadata.sorted_tables if not t.name.startswith("agent_")]
    Base.metadata.create_all(bind=engine, tables=v1_tables)


def _table_names(engine) -> set:
    return set(inspect(engine).get_table_names())


def _version_num(engine) -> str:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    return rows[0][0]


def _prepare_existing_db(tmp_path) -> str:
    """构造存量数据库（V1-only）并返回其 URL。"""
    db_url = f"sqlite:///{tmp_path / 'existing.db'}"
    engine = create_engine(db_url)
    _create_v1_schema(engine)
    engine.dispose()
    return db_url


# ── 存量数据库：stamp 0001 → upgrade head 创建 Agent 表 ──


def test_stamp_then_upgrade_creates_agent_tables(tmp_path):
    db_url = _prepare_existing_db(tmp_path)
    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    names = _table_names(engine)
    assert AGENT_TABLE_NAMES <= names
    assert V1_TABLE_NAMES <= names  # V1 表仍在
    assert _version_num(engine) == HEAD_REVISION

    inspector = inspect(engine)

    # 关键列抽查
    run_cols = {c["name"] for c in inspector.get_columns("agent_runs")}
    assert {
        "id", "session_id", "project_id", "requester_user_id", "workflow_code",
        "status", "idempotency_key", "heartbeat_at", "error_code",
        "user_message_id", "active_slot",
    } <= run_cols
    session_cols = {c["name"]: c for c in inspector.get_columns("agent_sessions")}
    assert {"mode", "next_message_sequence", "next_event_sequence"} <= set(session_cols)
    assert session_cols["project_id"]["nullable"] is True
    message_cols = {c["name"] for c in inspector.get_columns("agent_messages")}
    assert {"message_id", "schema_version", "timestamp_ms"} <= message_cols

    # 唯一约束（sequence_no 与 idempotency）
    msg_uniques = {(uc["name"], tuple(uc["column_names"])) for uc in inspector.get_unique_constraints("agent_messages")}
    assert ("uq_agent_messages_session_seq", ("session_id", "sequence_no")) in msg_uniques
    event_uniques = {(uc["name"], tuple(uc["column_names"])) for uc in inspector.get_unique_constraints("agent_events")}
    assert ("uq_agent_events_session_seq", ("session_id", "sequence_no")) in event_uniques
    step_uniques = {(uc["name"], tuple(uc["column_names"])) for uc in inspector.get_unique_constraints("agent_steps")}
    assert ("uq_agent_steps_run_seq", ("agent_run_id", "sequence_no")) in step_uniques
    run_uniques = {(uc["name"], tuple(uc["column_names"])) for uc in inspector.get_unique_constraints("agent_runs")}
    assert ("uq_agent_runs_idempotency", ("session_id", "workflow_code", "idempotency_key")) in run_uniques
    assert ("uq_agent_runs_session_active_slot", ("session_id", "active_slot")) in run_uniques

    # 索引
    run_indexes = {ix["name"] for ix in inspector.get_indexes("agent_runs")}
    assert "ix_agent_runs_status" in run_indexes
    assert "ix_agent_runs_heartbeat_at" in run_indexes

    # 外键
    session_fks = {(tuple(sorted(fk["constrained_columns"])), fk["referred_table"]) for fk in inspector.get_foreign_keys("agent_sessions")}
    assert (("project_id",), "projects") in session_fks
    assert (("user_id",), "users") in session_fks

    engine.dispose()


# ── downgrade 删除 Agent 表、保留 V1 表 ──


def test_downgrade_removes_agent_tables_keeps_v1(tmp_path):
    db_url = _prepare_existing_db(tmp_path)
    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, BASELINE_REVISION)

    engine = create_engine(db_url)
    names = _table_names(engine)
    assert not (AGENT_TABLE_NAMES & names)  # Agent 表全部消失
    assert V1_TABLE_NAMES <= names  # V1 表仍在
    engine.dispose()


# ── 重新 upgrade 可成功 ──


def test_reupgrade_after_downgrade(tmp_path):
    db_url = _prepare_existing_db(tmp_path)
    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    names = _table_names(engine)
    assert AGENT_TABLE_NAMES <= names
    assert _version_num(engine) == HEAD_REVISION
    engine.dispose()


# ── 重叠场景：create_all 先建过 Agent 表 → 0002 结构校验通过（非静默跳过） ──


def test_create_all_overlap_upgrade_verifies_structure(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'overlap.db'}"
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)  # 模拟新代码先启动，建了全部表
    engine.dispose()

    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")  # 已存在表 → 校验结构，一致则通过

    engine = create_engine(db_url)
    assert _version_num(engine) == HEAD_REVISION
    engine.dispose()


# ── 结构不一致必须明确失败 ──


def test_structure_mismatch_fails_explicitly(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'mismatch.db'}"
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE agent_sessions (id INTEGER PRIMARY KEY, wrong_col TEXT)"))
    engine.dispose()

    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    with pytest.raises(RuntimeError) as exc:
        command.upgrade(cfg, "head")
    message = str(exc.value)
    assert "agent_sessions" in message
    assert "结构不一致" in message


# ── 0001 no-op 不创建任何表 ──


def test_noop_baseline_creates_nothing(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'empty.db'}"
    engine = create_engine(db_url)
    engine.dispose()

    cfg = _make_config(db_url)
    command.upgrade(cfg, BASELINE_REVISION)

    engine = create_engine(db_url)
    assert _table_names(engine) == {"alembic_version"}
    assert _version_num(engine) == BASELINE_REVISION
    engine.dispose()


def test_0003_backfills_legacy_mode_and_sequence_cursors(tmp_path):
    db_url = _prepare_existing_db(tmp_path)
    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "0002_agent_platform_tables")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO agent_sessions (id, project_id, user_id, title) VALUES (1, 1, 1, 'legacy')"))
        conn.execute(text("INSERT INTO agent_messages (session_id, role, sequence_no) VALUES (1, 'user', 4)"))
        conn.execute(text("INSERT INTO agent_events (session_id, event_type, sequence_no) VALUES (1, 'old', 7)"))
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT mode, project_id, next_message_sequence, next_event_sequence "
            "FROM agent_sessions WHERE id=1"
        )).one()
        assert tuple(row) == ("legacy_workflow", 1, 5, 8)
    command.downgrade(cfg, "0002_agent_platform_tables")
    assert _version_num(engine) == "0002_agent_platform_tables"
    engine.dispose()


def test_0003_downgrade_refuses_to_lose_conversation_data(tmp_path):
    db_url = _prepare_existing_db(tmp_path)
    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO agent_sessions "
            "(id, project_id, user_id, mode, title, next_message_sequence, next_event_sequence) "
            "VALUES (1, NULL, 1, 'conversation', 'chat', 1, 1)"
        ))
    engine.dispose()
    with pytest.raises(RuntimeError) as exc:
        command.downgrade(cfg, "0002_agent_platform_tables")
    assert "会丢失 conversation 数据" in str(exc.value)


def test_0003_partial_columns_fail_explicitly(tmp_path):
    db_url = _prepare_existing_db(tmp_path)
    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "0002_agent_platform_tables")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE agent_sessions ADD COLUMN mode VARCHAR(20)"))
    engine.dispose()
    with pytest.raises(RuntimeError) as exc:
        command.upgrade(cfg, "head")
    assert "不完整" in str(exc.value)
