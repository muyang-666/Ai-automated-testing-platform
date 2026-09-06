"""0005_test_artifact_core: 新增 TestArtifact 领域四表（V2-P07）。

- 与 create_all 重叠兼容：表已存在 → 校验列结构一致后通过（绝不静默跳过）；
  不存在 → op.create_table 创建。
- 校验范围：列名/类型/nullable/主键/唯一约束（索引为性能性冗余，不参与结构校验）。
- downgrade 按依赖反序 drop 四表；不触碰既有 agent_* / V1 表。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_test_artifact_core"
down_revision: Union[str, None] = "0004_agent_run_execution_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 表定义（与 models 完全同源；create 与 verify 共用，防漂移）
TEST_ARTIFACT_COLUMNS = [
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
    sa.Column("title", sa.String(length=200), nullable=False),
    sa.Column("artifact_type", sa.String(length=50), nullable=False),
    sa.Column("status", sa.String(length=20), nullable=False),
    sa.Column("current_revision", sa.Integer(), nullable=False),
    sa.Column("root_node_id", sa.Integer(), nullable=True),
    sa.Column("schema_version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
]

ARTIFACT_NODE_COLUMNS = [
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("artifact_id", sa.Integer(), sa.ForeignKey("test_artifact.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("parent_id", sa.Integer(), sa.ForeignKey("artifact_node.id", ondelete="RESTRICT"), nullable=True),
    sa.Column("node_type", sa.String(length=20), nullable=False),
    sa.Column("order_key", sa.Integer(), nullable=False),
    sa.Column("title", sa.String(length=500), nullable=False),
    sa.Column("content_json", sa.JSON(), nullable=True),
    sa.Column("source_refs_json", sa.JSON(), nullable=True),
    sa.Column("created_revision", sa.Integer(), nullable=False),
    sa.Column("deleted_revision", sa.Integer(), nullable=True),
    sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
]

ARTIFACT_REVISION_COLUMNS = [
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("artifact_id", sa.Integer(), sa.ForeignKey("test_artifact.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("revision_no", sa.Integer(), nullable=False),
    sa.Column("base_revision", sa.Integer(), nullable=False),
    sa.Column("actor_type", sa.String(length=20), nullable=False),
    sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    sa.Column("conversation_id", sa.Integer(), nullable=True),
    sa.Column("run_id", sa.Integer(), nullable=True),
    sa.Column("summary", sa.String(length=500), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.UniqueConstraint("artifact_id", "revision_no", name="uq_artifact_revision_no"),
]

ARTIFACT_OPERATION_COLUMNS = [
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("revision_id", sa.Integer(), sa.ForeignKey("artifact_revision.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("op_index", sa.Integer(), nullable=False),
    sa.Column("operation_type", sa.String(length=20), nullable=False),
    sa.Column("target_node_id", sa.Integer(), nullable=True),
    sa.Column("payload_json", sa.JSON(), nullable=True),
    sa.Column("before_json", sa.JSON(), nullable=True),
    sa.Column("after_json", sa.JSON(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    sa.UniqueConstraint("revision_id", "op_index", name="uq_artifact_operation_idx"),
]

TABLES = {
    "test_artifact": TEST_ARTIFACT_COLUMNS,
    "artifact_node": ARTIFACT_NODE_COLUMNS,
    "artifact_revision": ARTIFACT_REVISION_COLUMNS,
    "artifact_operation": ARTIFACT_OPERATION_COLUMNS,
}
# 建表顺序（依赖序）与删表顺序（反依赖序）
CREATE_ORDER = ("test_artifact", "artifact_node", "artifact_revision", "artifact_operation")

# 期望的唯一约束（列名字符串比对；verify 分支里 UniqueConstraint 未附着表，不能读 .columns）
UNIQUE_CONSTRAINTS = {
    "artifact_revision": ("uq_artifact_revision_no", ("artifact_id", "revision_no")),
    "artifact_operation": ("uq_artifact_operation_idx", ("revision_id", "op_index")),
}


def _table_exists(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _verify_table(bind, name: str) -> None:
    inspector = sa.inspect(bind)
    expected = TABLES[name]
    expected_cols = [c for c in expected if isinstance(c, sa.Column)]
    actual = {col["name"]: col for col in inspector.get_columns(name)}
    expected_names = {col.name for col in expected_cols}
    if set(actual) != expected_names:
        missing = expected_names - set(actual)
        extra = set(actual) - expected_names
        raise RuntimeError(f"表 {name} 结构不一致（列集合差异 missing={sorted(missing)} extra={sorted(extra)}）")
    pk_names = {col.name for col in expected_cols if col.primary_key}
    actual_pk = set(inspector.get_pk_constraint(name)["constrained_columns"] or [])
    if pk_names != actual_pk:
        raise RuntimeError(f"表 {name} 结构不一致（主键差异）")
    for col in expected_cols:
        info = actual[col.name]
        # 显式 nullable=False 必须为 NOT NULL；未显式声明（如 created_at）按宽松可空比较
        expected_nullable = col.nullable is not False
        if info["nullable"] != expected_nullable:
            raise RuntimeError(f"表 {name}.{col.name} nullable 不一致")
    unique_names = {(uc["name"], tuple(uc["column_names"])) for uc in inspector.get_unique_constraints(name)}
    entries = [UNIQUE_CONSTRAINTS[name]] if name in UNIQUE_CONSTRAINTS else []
    for unique_name, columns in entries:
        if (unique_name, tuple(columns)) not in unique_names:
            raise RuntimeError(f"表 {name} 缺少唯一约束 {unique_name}({columns})")


def upgrade() -> None:
    bind = op.get_bind()
    for name in CREATE_ORDER:
        if _table_exists(bind, name):
            _verify_table(bind, name)
        else:
            op.create_table(name, *TABLES[name])


def downgrade() -> None:
    for name in reversed(CREATE_ORDER):
        op.drop_table(name)
