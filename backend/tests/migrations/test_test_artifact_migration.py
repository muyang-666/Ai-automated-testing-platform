"""0005_test_artifact_core 迁移测试（临时 SQLite，不碰真实 MySQL）。

与 agent 迁移测试同法：先构造「V1 存量库（不含 agent_* 与 artifact 表）」→
stamp 0001 → upgrade head（0002 建 agent 表、0005 建 artifact 表 create 分支）。
覆盖：create 分支、downgrade、再 upgrade、overlap verify、结构不一致明确失败。
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
HEAD_REVISION = "0008_agent_run_workspace_context"
ARTIFACT_TABLE_NAMES = {"test_artifact", "artifact_node", "artifact_revision", "artifact_operation"}


def _make_config(db_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", db_url)
    return config


def _create_v1_schema(engine) -> None:
    """构造存量库：V1 表（不含 agent_* 与 artifact 表）。"""
    v1_tables = [
        t for t in Base.metadata.sorted_tables
        if not t.name.startswith("agent_") and t.name not in ARTIFACT_TABLE_NAMES
    ]
    Base.metadata.create_all(bind=engine, tables=v1_tables)


def _prepare_db(tmp_path, name: str) -> str:
    db_url = f"sqlite:///{tmp_path / name}"
    engine = create_engine(db_url)
    _create_v1_schema(engine)
    engine.dispose()
    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    return db_url


def _table_names(engine) -> set:
    return set(inspect(engine).get_table_names())


def _version_num(engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_upgrade_creates_artifact_tables(tmp_path):
    db_url = _prepare_db(tmp_path, "ta_upgrade.db")
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    assert ARTIFACT_TABLE_NAMES <= _table_names(engine)
    assert _version_num(engine) == HEAD_REVISION

    inspector = inspect(engine)
    revision_cols = {c["name"] for c in inspector.get_columns("artifact_revision")}
    assert {"artifact_id", "revision_no", "base_revision", "actor_type",
            "conversation_id", "run_id", "summary"} <= revision_cols
    revision_uniques = {(uc["name"], tuple(uc["column_names"]))
                        for uc in inspector.get_unique_constraints("artifact_revision")}
    assert ("uq_artifact_revision_no", ("artifact_id", "revision_no")) in revision_uniques
    node_cols = {c["name"] for c in inspector.get_columns("artifact_node")}
    assert {"artifact_id", "parent_id", "node_type", "order_key", "title",
            "content_json", "created_revision", "deleted_revision"} <= node_cols
    op_uniques = {(uc["name"], tuple(uc["column_names"]))
                  for uc in inspector.get_unique_constraints("artifact_operation")}
    assert ("uq_artifact_operation_idx", ("revision_id", "op_index")) in op_uniques
    engine.dispose()


def test_downgrade_drops_artifact_tables(tmp_path):
    db_url = _prepare_db(tmp_path, "ta_downgrade.db")
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    assert ARTIFACT_TABLE_NAMES <= _table_names(engine)
    engine.dispose()

    command.downgrade(cfg, "0004_agent_run_execution_token")
    engine = create_engine(db_url)
    assert not (ARTIFACT_TABLE_NAMES & _table_names(engine))
    assert _version_num(engine) == "0004_agent_run_execution_token"
    engine.dispose()


def test_reupgrade_after_downgrade(tmp_path):
    db_url = _prepare_db(tmp_path, "ta_reup.db")
    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0005_test_artifact_core")
    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    assert ARTIFACT_TABLE_NAMES <= _table_names(engine)
    assert _version_num(engine) == HEAD_REVISION
    engine.dispose()


def test_overlap_create_all_verify_structure(tmp_path):
    """create_all 先建全部表 → stamp 0001 → upgrade head：走 verify 分支通过。"""
    db_url = f"sqlite:///{tmp_path / 'ta_overlap.db'}"
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    assert _version_num(engine) == HEAD_REVISION
    engine.dispose()


def test_mismatch_fails_explicitly(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ta_mismatch.db'}"
    engine = create_engine(db_url)
    _create_v1_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE artifact_node (id INTEGER PRIMARY KEY, wrong_col TEXT)"))
    engine.dispose()

    cfg = _make_config(db_url)
    command.stamp(cfg, BASELINE_REVISION)
    with pytest.raises(RuntimeError) as exc:
        command.upgrade(cfg, "head")
    assert "artifact_node" in str(exc.value)
    assert "结构不一致" in str(exc.value)


# ── 0007：node_type 收敛 + 项目主 Artifact 唯一约束 ──


def _insert_artifact_and_nodes(engine):
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO test_artifact (id, owner_user_id, project_id, title, artifact_type, "
            "status, current_revision, schema_version) "
            "VALUES (1, 1, NULL, '资产', 'test_design', 'active', 1, 1)"))
        for node_id, node_type, title in [(1, "root", "root"), (2, "group", "G1"),
                                          (3, "test_point", "P1"), (4, "test_case", "TC1")]:
            conn.execute(text(
                "INSERT INTO artifact_node (id, artifact_id, parent_id, node_type, order_key, "
                "title, created_revision) VALUES (:id, 1, :parent, :nt, 1, :t, 1)"),
                {"id": node_id, "parent": None if node_type == "root" else (1 if node_type != "test_case" else 2),
                 "nt": node_type, "t": title})


def test_module_convergence_converts_legacy_node_types(tmp_path):
    db_url = _prepare_db(tmp_path, "ta_conv.db")
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0006_agent_run_artifact_context")
    engine = create_engine(db_url)
    _insert_artifact_and_nodes(engine)
    engine.dispose()
    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, node_type FROM artifact_node ORDER BY id")).fetchall()
        assert dict(rows) == {1: "root", 2: "module", 3: "module", 4: "test_case"}
    uniques = {(uc["name"], tuple(uc["column_names"]))
               for uc in inspect(engine).get_unique_constraints("test_artifact")}
    assert ("uq_test_artifact_project_type", ("project_id", "artifact_type")) in uniques
    engine.dispose()
    command.downgrade(cfg, "0006_agent_run_artifact_context")
    engine = create_engine(db_url)
    uniques = {(uc["name"], tuple(uc["column_names"]))
               for uc in inspect(engine).get_unique_constraints("test_artifact")}
    assert "uq_test_artifact_project_type" not in {name for name, _ in uniques}
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, node_type FROM artifact_node WHERE id IN (2,3) ORDER BY id")).fetchall()
        assert dict(rows) == {2: "group", 3: "group"}  # 损失性回退（module→group）
    engine.dispose()

def test_workspace_context_column_upgrade_and_downgrade(tmp_path):
    db_url = _prepare_db(tmp_path, "workspace_context.db")
    cfg = _make_config(db_url)
    command.upgrade(cfg, "0007_artifact_module_convergence")
    engine = create_engine(db_url)
    assert "workspace_context_json" not in {
        column["name"] for column in inspect(engine).get_columns("agent_runs")}
    engine.dispose()

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    columns = {column["name"]: column for column in inspect(engine).get_columns("agent_runs")}
    assert columns["workspace_context_json"]["nullable"] is True
    engine.dispose()

    command.downgrade(cfg, "0007_artifact_module_convergence")
    engine = create_engine(db_url)
    assert "workspace_context_json" not in {
        column["name"] for column in inspect(engine).get_columns("agent_runs")}
    assert "artifact_context_json" in {
        column["name"] for column in inspect(engine).get_columns("agent_runs")}
    engine.dispose()
