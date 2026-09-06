"""0006_agent_run_artifact_context: AgentRun 增加 P08.2 Turn 可信快照列。

新增列 agent_runs.artifact_context_json（JSON，nullable）：
{artifact_id, project_id, requirement_id} —— submit Turn 时固化，
Runner 只使用 Run 快照，不读取可变的 Session focus。

与 create_all 重叠兼容（参照 0004 改列先例）：
- 列已存在 → 校验后直接返回（不静默跳过）；
- 缺失 → batch_alter_table.add_column。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_agent_run_artifact_context"
down_revision: Union[str, None] = "0005_test_artifact_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "agent_runs"
COLUMN = "artifact_context_json"


def _column_exists(bind, name: str) -> bool:
    return any(c["name"] == name for c in sa.inspect(bind).get_columns(TABLE))


def upgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, COLUMN):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(sa.Column(COLUMN, sa.JSON(), nullable=True,
                                   comment="P08.2 Turn 可信快照 {artifact_id, project_id, requirement_id}"))


def downgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, COLUMN):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
