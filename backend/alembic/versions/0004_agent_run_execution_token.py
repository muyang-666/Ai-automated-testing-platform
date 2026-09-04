"""0004: add agent_runs.execution_token (P05-D fencing generation).

Revision ID: 0004_agent_run_execution_token
Revises: 0003_conversation_persistence

Adds the monotonic execution-generation counter used for lease fencing.
Nullable: historical rows (created before P05-D) have no token yet; every new
claim sets ``execution_token = COALESCE(execution_token, 0) + 1`` atomically,
so all future executions are fenced. Downgrade drops the column only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_agent_run_execution_token"
down_revision: Union[str, None] = "0003_conversation_persistence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等：create_all 已建出 head 结构时只校验并返回（与 0002/0003 同约定）。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    runs = {column["name"]: column for column in inspector.get_columns("agent_runs")}
    if "worker_id" not in runs or "heartbeat_at" not in runs:
        raise RuntimeError("0004 前置列缺失：agent_runs.worker_id/heartbeat_at 不存在")
    if "execution_token" in runs:
        column = runs["execution_token"]
        if column.get("nullable") is not True:
            raise RuntimeError("已存在的 agent_runs.execution_token 不应 nullable")
        return  # 结构已一致（create_all 先建表场景），不重复添加
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("execution_token", sa.Integer(), nullable=True,
                                   comment="P05-D fencing 执行代次"))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("execution_token")
