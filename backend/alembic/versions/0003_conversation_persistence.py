"""0003: add V2 conversation persistence and concurrency fields.

Revision ID: 0003_conversation_persistence
Revises: 0002_agent_platform_tables

Existing sessions/runs remain ``legacy_workflow`` and keep their project IDs.
Downgrade refuses when conversation data would be lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_conversation_persistence"
down_revision: Union[str, None] = "0002_agent_platform_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _new_columns_state(bind) -> tuple[bool, bool]:
    inspector = sa.inspect(bind)
    expected = {
        "agent_sessions": {"mode", "next_message_sequence", "next_event_sequence"},
        "agent_messages": {"message_id", "schema_version", "timestamp_ms"},
        "agent_runs": {"user_message_id", "active_slot"},
    }
    present = []
    for table, names in expected.items():
        actual = {column["name"] for column in inspector.get_columns(table)}
        present.extend(name in actual for name in names)
    return all(present), any(present)


def _verify_existing_head(bind) -> None:
    inspector = sa.inspect(bind)
    errors: list[str] = []
    sessions = {column["name"]: column for column in inspector.get_columns("agent_sessions")}
    messages = {column["name"]: column for column in inspector.get_columns("agent_messages")}
    runs = {column["name"]: column for column in inspector.get_columns("agent_runs")}
    for name in ("mode", "next_message_sequence", "next_event_sequence"):
        if sessions[name]["nullable"]:
            errors.append(f"agent_sessions.{name} 不应 nullable")
    if not sessions["project_id"]["nullable"] or not runs["project_id"]["nullable"]:
        errors.append("conversation project_id 必须 nullable")
    if messages["schema_version"]["nullable"]:
        errors.append("agent_messages.schema_version 不应 nullable")
    message_uniques = {(item.get("name"), tuple(item.get("column_names") or []))
                       for item in inspector.get_unique_constraints("agent_messages")}
    run_uniques = {(item.get("name"), tuple(item.get("column_names") or []))
                   for item in inspector.get_unique_constraints("agent_runs")}
    run_checks = {item.get("name") for item in inspector.get_check_constraints("agent_runs")}
    if ("uq_agent_messages_session_message_id", ("session_id", "message_id")) not in message_uniques:
        errors.append("缺少消息稳定 ID 唯一约束")
    if ("uq_agent_runs_session_active_slot", ("session_id", "active_slot")) not in run_uniques:
        errors.append("缺少 conversation 活跃槽唯一约束")
    if "ck_agent_runs_active_slot" not in run_checks:
        errors.append("缺少 conversation 活跃槽取值约束")
    session_indexes = {item.get("name") for item in inspector.get_indexes("agent_sessions")}
    run_indexes = {item.get("name") for item in inspector.get_indexes("agent_runs")}
    session_checks = {item.get("name") for item in inspector.get_check_constraints("agent_sessions")}
    if "ix_agent_sessions_mode" not in session_indexes:
        errors.append("缺少 agent_sessions.mode 索引")
    if "ix_agent_runs_user_message_id" not in run_indexes:
        errors.append("缺少 agent_runs.user_message_id 索引")
    if not {"ck_agent_sessions_mode", "ck_agent_sessions_legacy_project"} <= session_checks:
        errors.append("缺少会话模式/旧项目约束")
    if errors:
        raise RuntimeError("已存在的 0003 conversation 结构不一致:\n- " + "\n- ".join(errors))


def upgrade() -> None:
    bind = op.get_bind()
    complete, partial = _new_columns_state(bind)
    if complete:
        # New-code create_all may have created the head schema before Alembic is stamped.
        _verify_existing_head(bind)
        return
    if partial:
        raise RuntimeError("检测到不完整的 0003 conversation 列集合，拒绝静默升级")
    with op.batch_alter_table("agent_sessions") as batch:
        batch.alter_column("project_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("mode", sa.String(20), nullable=True,
                                   server_default="legacy_workflow"))
        batch.add_column(sa.Column("next_message_sequence", sa.Integer(), nullable=True,
                                   server_default="1"))
        batch.add_column(sa.Column("next_event_sequence", sa.Integer(), nullable=True,
                                   server_default="1"))
        batch.create_index("ix_agent_sessions_mode", ["mode"])
        batch.create_check_constraint("ck_agent_sessions_mode",
                                      "mode IN ('legacy_workflow', 'conversation')")
        batch.create_check_constraint("ck_agent_sessions_legacy_project",
                                      "mode = 'conversation' OR project_id IS NOT NULL")

    op.execute(sa.text("""
        UPDATE agent_sessions
        SET next_message_sequence = COALESCE(
                (SELECT MAX(m.sequence_no) + 1 FROM agent_messages m
                 WHERE m.session_id = agent_sessions.id), 1),
            next_event_sequence = COALESCE(
                (SELECT MAX(e.sequence_no) + 1 FROM agent_events e
                 WHERE e.session_id = agent_sessions.id), 1),
            mode = COALESCE(mode, 'legacy_workflow')
    """))
    with op.batch_alter_table("agent_sessions") as batch:
        batch.alter_column("mode", existing_type=sa.String(20), nullable=False,
                           server_default=None)
        batch.alter_column("next_message_sequence", existing_type=sa.Integer(), nullable=False,
                           server_default=None)
        batch.alter_column("next_event_sequence", existing_type=sa.Integer(), nullable=False,
                           server_default=None)

    with op.batch_alter_table("agent_messages") as batch:
        batch.add_column(sa.Column("message_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("schema_version", sa.Integer(), nullable=True,
                                   server_default="1"))
        batch.add_column(sa.Column("timestamp_ms", sa.BigInteger(), nullable=True))
        batch.create_unique_constraint("uq_agent_messages_session_message_id",
                                       ["session_id", "message_id"])
    op.execute(sa.text("UPDATE agent_messages SET schema_version = 1 WHERE schema_version IS NULL"))
    with op.batch_alter_table("agent_messages") as batch:
        batch.alter_column("schema_version", existing_type=sa.Integer(), nullable=False,
                           server_default=None)

    with op.batch_alter_table("agent_runs") as batch:
        batch.alter_column("project_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("user_message_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("active_slot", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_agent_runs_session_active_slot",
                                       ["session_id", "active_slot"])
        batch.create_check_constraint("ck_agent_runs_active_slot",
            "active_slot IS NULL OR (active_slot = 1 AND workflow_code = 'conversation')")
        batch.create_index("ix_agent_runs_user_message_id", ["user_message_id"])


def _count(bind, sql: str) -> int:
    return int(bind.execute(sa.text(sql)).scalar() or 0)


def downgrade() -> None:
    bind = op.get_bind()
    unsafe = {
        "conversation_sessions": _count(bind,
            "SELECT COUNT(*) FROM agent_sessions WHERE mode <> 'legacy_workflow' OR project_id IS NULL"),
        "conversation_runs": _count(bind,
            "SELECT COUNT(*) FROM agent_runs WHERE workflow_code = 'conversation' OR project_id IS NULL "
            "OR user_message_id IS NOT NULL OR active_slot IS NOT NULL"),
        "versioned_messages": _count(bind,
            "SELECT COUNT(*) FROM agent_messages WHERE message_id IS NOT NULL OR timestamp_ms IS NOT NULL"),
    }
    if any(unsafe.values()):
        raise RuntimeError(f"0003 downgrade 会丢失 conversation 数据，已拒绝: {unsafe}")

    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_index("ix_agent_runs_user_message_id")
        batch.drop_constraint("ck_agent_runs_active_slot", type_="check")
        batch.drop_constraint("uq_agent_runs_session_active_slot", type_="unique")
        batch.drop_column("active_slot")
        batch.drop_column("user_message_id")
        batch.alter_column("project_id", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("agent_messages") as batch:
        batch.drop_constraint("uq_agent_messages_session_message_id", type_="unique")
        batch.drop_column("timestamp_ms")
        batch.drop_column("schema_version")
        batch.drop_column("message_id")

    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_index("ix_agent_sessions_mode")
        batch.drop_constraint("ck_agent_sessions_legacy_project", type_="check")
        batch.drop_constraint("ck_agent_sessions_mode", type_="check")
        batch.drop_column("next_event_sequence")
        batch.drop_column("next_message_sequence")
        batch.drop_column("mode")
        batch.alter_column("project_id", existing_type=sa.Integer(), nullable=False)
