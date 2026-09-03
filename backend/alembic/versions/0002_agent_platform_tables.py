"""0002: 创建 Agent 平台七张表

Revision ID: 0002_agent_platform_tables
Revises: 0001_v1_schema_baseline
Create Date: 2026-09-01

- 只创建 agent_sessions / agent_messages / agent_events / agent_runs /
  agent_steps / agent_artifacts / agent_approvals，不触碰任何 V1 表。
- 表已存在时不静默跳过：逐表校验列、主键、唯一约束、索引和外键，
  结构不一致时抛出带差异明细的 RuntimeError，migration 明确失败。
- downgrade 按反向依赖顺序删除本迁移创建的表。
- 所有外键 ondelete=RESTRICT：Agent 数据不随用户/项目/会话删除而级联消失。
- 注意：server_default 仅用于时间戳；status 等默认值是 ORM 层 client default，
  与 create_all 产生的结构保持一致。

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_agent_platform_tables"
down_revision: Union[str, None] = "0001_v1_schema_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def _ts():
    """时间戳列：与模型 server_default=func.now() 渲染一致。"""
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=_NOW)


# ── 七张表的期望结构（create 与 verify 共用，防止两处 DDL 漂移） ──

AGENT_TABLES: dict[str, dict] = {
    "agent_sessions": {
        "columns": [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("current_skill_code", sa.String(100), nullable=True),
            sa.Column("agent_version", sa.String(50), nullable=True),
            sa.Column("context_json", sa.JSON(), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
            _ts(),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=_NOW),
        ],
        "uniques": [],
        "indexes": [
            ("ix_agent_sessions_id", ["id"]),
            ("ix_agent_sessions_project_id", ["project_id"]),
            ("ix_agent_sessions_user_id", ["user_id"]),
        ],
        "fks": [
            (["project_id"], "projects", "RESTRICT"),
            (["user_id"], "users", "RESTRICT"),
        ],
    },
    "agent_messages": {
        "columns": [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=True),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("message_type", sa.String(20), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("content_json", sa.JSON(), nullable=True),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            _ts(),
        ],
        "uniques": [("uq_agent_messages_session_seq", ["session_id", "sequence_no"])],
        "indexes": [
            ("ix_agent_messages_id", ["id"]),
            ("ix_agent_messages_session_id", ["session_id"]),
            ("ix_agent_messages_run_id", ["run_id"]),
        ],
        "fks": [
            (["session_id"], "agent_sessions", "RESTRICT"),
            (["run_id"], "agent_runs", "RESTRICT"),
        ],
    },
    "agent_events": {
        "columns": [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(50), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            _ts(),
        ],
        "uniques": [("uq_agent_events_session_seq", ["session_id", "sequence_no"])],
        "indexes": [
            ("ix_agent_events_id", ["id"]),
            ("ix_agent_events_session_id", ["session_id"]),
            ("ix_agent_events_run_id", ["run_id"]),
        ],
        "fks": [
            (["session_id"], "agent_sessions", "RESTRICT"),
            (["run_id"], "agent_runs", "RESTRICT"),
        ],
    },
    "agent_runs": {
        "columns": [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("requester_user_id", sa.Integer(), nullable=False),
            sa.Column("workflow_code", sa.String(100), nullable=False),
            sa.Column("workflow_version", sa.String(50), nullable=True),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("current_step", sa.String(100), nullable=True),
            sa.Column("input_json", sa.JSON(), nullable=True),
            sa.Column("output_json", sa.JSON(), nullable=True),
            sa.Column("input_hash", sa.String(64), nullable=True),
            sa.Column("idempotency_key", sa.String(128), nullable=True),
            sa.Column("model_snapshot_json", sa.JSON(), nullable=True),
            sa.Column("prompt_version", sa.String(50), nullable=True),
            sa.Column("max_steps", sa.Integer(), nullable=True),
            sa.Column("steps_used", sa.Integer(), nullable=True),
            sa.Column("llm_calls_used", sa.Integer(), nullable=True),
            sa.Column("tool_calls_used", sa.Integer(), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(50), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("worker_id", sa.String(64), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            _ts(),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=_NOW),
        ],
        "uniques": [("uq_agent_runs_idempotency", ["session_id", "workflow_code", "idempotency_key"])],
        "indexes": [
            ("ix_agent_runs_id", ["id"]),
            ("ix_agent_runs_session_id", ["session_id"]),
            ("ix_agent_runs_project_id", ["project_id"]),
            ("ix_agent_runs_requester_user_id", ["requester_user_id"]),
            ("ix_agent_runs_status", ["status"]),
            ("ix_agent_runs_heartbeat_at", ["heartbeat_at"]),
        ],
        "fks": [
            (["session_id"], "agent_sessions", "RESTRICT"),
            (["project_id"], "projects", "RESTRICT"),
            (["requester_user_id"], "users", "RESTRICT"),
        ],
    },
    "agent_steps": {
        "columns": [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("agent_run_id", sa.Integer(), nullable=False),
            sa.Column("sequence_no", sa.Integer(), nullable=False),
            sa.Column("step_kind", sa.String(20), nullable=False),
            sa.Column("step_name", sa.String(100), nullable=False),
            sa.Column("tool_name", sa.String(100), nullable=True),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("input_json", sa.JSON(), nullable=True),
            sa.Column("output_json", sa.JSON(), nullable=True),
            sa.Column("provider_name", sa.String(100), nullable=True),
            sa.Column("model_name", sa.String(100), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_code", sa.String(50), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            _ts(),
        ],
        "uniques": [("uq_agent_steps_run_seq", ["agent_run_id", "sequence_no"])],
        "indexes": [
            ("ix_agent_steps_id", ["id"]),
            ("ix_agent_steps_agent_run_id", ["agent_run_id"]),
            ("ix_agent_steps_status", ["status"]),
        ],
        "fks": [
            (["agent_run_id"], "agent_runs", "RESTRICT"),
        ],
    },
    "agent_artifacts": {
        "columns": [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("agent_run_id", sa.Integer(), nullable=False),
            sa.Column("artifact_type", sa.String(50), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("source_refs_json", sa.JSON(), nullable=True),
            sa.Column("source_hash", sa.String(64), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            _ts(),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=_NOW),
        ],
        "uniques": [],
        "indexes": [
            ("ix_agent_artifacts_id", ["id"]),
            ("ix_agent_artifacts_session_id", ["session_id"]),
            ("ix_agent_artifacts_agent_run_id", ["agent_run_id"]),
            ("ix_agent_artifacts_artifact_type", ["artifact_type"]),
            ("ix_agent_artifacts_status", ["status"]),
        ],
        "fks": [
            (["session_id"], "agent_sessions", "RESTRICT"),
            (["agent_run_id"], "agent_runs", "RESTRICT"),
            (["created_by_user_id"], "users", "RESTRICT"),
        ],
    },
    "agent_approvals": {
        "columns": [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.Integer(), nullable=False),
            sa.Column("agent_run_id", sa.Integer(), nullable=False),
            sa.Column("artifact_id", sa.Integer(), nullable=True),
            sa.Column("action_code", sa.String(100), nullable=False),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("request_json", sa.JSON(), nullable=True),
            sa.Column("resolution_json", sa.JSON(), nullable=True),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
            _ts(),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=_NOW),
        ],
        "uniques": [],
        "indexes": [
            ("ix_agent_approvals_id", ["id"]),
            ("ix_agent_approvals_session_id", ["session_id"]),
            ("ix_agent_approvals_agent_run_id", ["agent_run_id"]),
            ("ix_agent_approvals_artifact_id", ["artifact_id"]),
            ("ix_agent_approvals_status", ["status"]),
            ("ix_agent_approvals_resolved_by_user_id", ["resolved_by_user_id"]),
        ],
        "fks": [
            (["session_id"], "agent_sessions", "RESTRICT"),
            (["agent_run_id"], "agent_runs", "RESTRICT"),
            (["artifact_id"], "agent_artifacts", "RESTRICT"),
            (["resolved_by_user_id"], "users", "RESTRICT"),
        ],
    },
}

_DOWNGRADE_ORDER = [
    "agent_approvals",
    "agent_artifacts",
    "agent_steps",
    "agent_messages",
    "agent_events",
    "agent_runs",
    "agent_sessions",
]


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _verify_table(bind, table_name: str, spec: dict) -> None:
    """校验已存在表的结构；不一致时抛出带差异明细的 RuntimeError。"""
    inspector = sa.inspect(bind)
    errors: list[str] = []

    # 列：集合、nullable、类型
    actual_columns = {c["name"]: c for c in inspector.get_columns(table_name)}
    expected_columns = {c.name: c for c in spec["columns"]}
    if set(actual_columns) != set(expected_columns):
        missing = sorted(set(expected_columns) - set(actual_columns))
        extra = sorted(set(actual_columns) - set(expected_columns))
        errors.append(f"列集合不一致: 缺失={missing}, 多余={extra}")
    else:
        for name, spec_col in expected_columns.items():
            actual = actual_columns[name]
            if bool(actual["nullable"]) != bool(spec_col.nullable):
                errors.append(f"列 {name} nullable 不一致: 期望={spec_col.nullable}, 实际={actual['nullable']}")
            if str(actual["type"]).upper() != str(spec_col.type).upper():
                errors.append(f"列 {name} 类型不一致: 期望={spec_col.type}, 实际={actual['type']}")

    # 主键
    pk = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
    if sorted(pk) != ["id"]:
        errors.append(f"主键不一致: 期望=['id'], 实际={sorted(pk)}")

    # 唯一约束
    actual_uniques = {
        (uc.get("name"), tuple(uc.get("column_names") or []))
        for uc in inspector.get_unique_constraints(table_name)
    }
    expected_uniques = {(name, tuple(cols)) for name, cols in spec["uniques"]}
    if actual_uniques != expected_uniques:
        errors.append(
            f"唯一约束不一致: 期望={sorted(expected_uniques)}, 实际={sorted(actual_uniques)}"
        )

    # 普通索引（排除 SQLite 为 UNIQUE 约束生成的 autoindex）
    all_indexes = inspector.get_indexes(table_name)
    actual_indexes = {
        (ix.get("name"), tuple(ix.get("column_names") or []))
        for ix in all_indexes
        if not (ix.get("name") or "").startswith("sqlite_autoindex")
    }
    expected_indexes = {(name, tuple(cols)) for name, cols in spec["indexes"]}
    if actual_indexes != expected_indexes:
        errors.append(f"索引不一致: 期望={sorted(expected_indexes)}, 实际={sorted(actual_indexes)}")
    for ix in all_indexes:
        if (ix.get("name"), tuple(ix.get("column_names") or [])) in expected_indexes and ix.get("unique"):
            errors.append(f"索引 {ix.get('name')} 不应为唯一索引")

    # 外键（列集合 + 引用表 + ondelete）
    actual_fks = {
        (
            tuple(sorted(fk.get("constrained_columns") or [])),
            fk.get("referred_table"),
            ((fk.get("options") or {}).get("ondelete") or "").upper(),
        )
        for fk in inspector.get_foreign_keys(table_name)
    }
    expected_fks = {
        (tuple(sorted(cols)), referred, ondelete.upper())
        for cols, referred, ondelete in spec["fks"]
    }
    if actual_fks != expected_fks:
        errors.append(f"外键不一致: 期望={sorted(expected_fks)}, 实际={sorted(actual_fks)}")

    if errors:
        raise RuntimeError(
            f"已存在的表 {table_name} 与迁移定义结构不一致，拒绝标记 migration 成功:\n- "
            + "\n- ".join(errors)
        )


def upgrade() -> None:
    bind = op.get_bind()
    for table_name, spec in AGENT_TABLES.items():
        if _table_exists(bind, table_name):
            # 已存在（如新代码 create_all 先建过）→ 校验结构，不一致即失败，绝不静默跳过
            _verify_table(bind, table_name, spec)
            continue
        op.create_table(
            table_name,
            *spec["columns"],
            *[
                sa.ForeignKeyConstraint(cols, [f"{referred}.id"], ondelete=ondelete)
                for cols, referred, ondelete in spec["fks"]
            ],
            *[sa.UniqueConstraint(*cols, name=name) for name, cols in spec["uniques"]],
        )
        for name, cols in spec["indexes"]:
            op.create_index(name, table_name, cols)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in _DOWNGRADE_ORDER:
        if _table_exists(bind, table_name):
            op.drop_table(table_name)
