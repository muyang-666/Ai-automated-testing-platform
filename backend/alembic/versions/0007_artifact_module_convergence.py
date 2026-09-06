"""0007_artifact_module_convergence: node_type 收敛 root/module/test_case + 项目主 Artifact 唯一。

P09.1（Functional Case Domain Convergence）：
- artifact_node.node_type：group / test_point → module（合法值 root/module/test_case）；
- test_artifact：UNIQUE(project_id, artifact_type) 保证每项目一份主 Functional TestArtifact
  （并发 ensure 由数据库裁决；project_id NULL 的私有 Artifact 不受限——MySQL/SQLite 多 NULL 均允许）。

downgrade：唯一约束回退；module → group（损失性：无法还原原 test_point 归属，属可接受回退）。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_artifact_module_convergence"
down_revision: Union[str, None] = "0006_agent_run_artifact_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # 1) node_type 收敛（幂等：仅处理仍存在的旧值）
    op.execute(
        sa.text("UPDATE artifact_node SET node_type = 'module' "
                "WHERE node_type IN ('group', 'test_point')")
    )
    # 2) 每项目唯一主 Functional Artifact（NULL project_id 的私有 Artifact 不受约束）
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_unique_constraints("test_artifact")}
    if "uq_test_artifact_project_type" not in existing:
        with op.batch_alter_table("test_artifact") as batch:
            batch.create_unique_constraint(
                "uq_test_artifact_project_type", ["project_id", "artifact_type"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_unique_constraints("test_artifact")}
    if "uq_test_artifact_project_type" in existing:
        with op.batch_alter_table("test_artifact") as batch:
            batch.drop_constraint("uq_test_artifact_project_type", type_="unique")
    # 损失性回退：module → group（无法区分原 group/test_point）
    op.execute(sa.text("UPDATE artifact_node SET node_type = 'group' WHERE node_type = 'module'"))
