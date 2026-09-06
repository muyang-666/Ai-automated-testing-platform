"""0008_agent_run_workspace_context: snapshot FunctionCasePage selection per Turn."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_agent_run_workspace_context"
down_revision: Union[str, None] = "0007_artifact_module_convergence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "agent_runs"
COLUMN = "workspace_context_json"


def _column_exists(bind) -> bool:
    return any(column["name"] == COLUMN for column in sa.inspect(bind).get_columns(TABLE))


def upgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(sa.Column(COLUMN, sa.JSON(), nullable=True,
                                   comment="P09.3A Turn UI selection snapshot"))


def downgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind):
        return
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column(COLUMN)
