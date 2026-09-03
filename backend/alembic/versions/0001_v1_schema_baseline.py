"""0001: V1 schema baseline（no-op 标记）

Revision ID: 0001_v1_schema_baseline
Revises:
Create Date: 2026-09-01

本迁移为空操作。它只代表一个事实：V1 的 21 张业务表已存在，
且它们是由 Base.metadata.create_all() 创建的，没有历史 migration。

用途：
- 现有数据库通过 `alembic stamp 0001_v1_schema_baseline` 接入 Alembic；
- 后续迁移（如 0002_agent_platform_tables）以此为基础叠加；
- 完整的 V1 schema migration（含 21 张表 DDL）属于遗留项，不在 V2.1-T02 范围。

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_v1_schema_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """空迁移：V1 表由 create_all 维护，这里只做基线标记。"""
    pass


def downgrade() -> None:
    """空迁移：不删除任何 V1 表。"""
    pass
