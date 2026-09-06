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
HEAD_REVISION = "0006_agent_run_artifact_context"
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
