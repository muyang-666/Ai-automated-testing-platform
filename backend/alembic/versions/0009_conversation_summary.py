"""0009_conversation_summary: P10.1 persistent per-conversation summary (through monotonic)."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_conversation_summary"
down_revision: Union[str, None] = "0008_agent_run_workspace_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "conversation_summary"


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_sessions.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("through_sequence_no", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("source_message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"),
                  onupdate=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("conversation_id", name="uq_conversation_summary_conversation"),
    )
    op.create_index("ix_conversation_summary_conversation_id", TABLE, ["conversation_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    op.drop_index("ix_conversation_summary_conversation_id", table_name=TABLE)
    op.drop_table(TABLE)
