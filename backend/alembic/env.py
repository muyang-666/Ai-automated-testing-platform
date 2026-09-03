"""Alembic 环境配置。

- 数据库 URL 解析顺序：调用方显式传入的 sqlalchemy.url > settings.DATABASE_URL；
- MySQL 安全护栏：未显式设置 ALEMBIC_ALLOW_MYSQL=1 时拒绝执行，
  防止误对生产 MySQL 执行 migration；
- target_metadata 为 Base.metadata，供未来 autogenerate 使用。
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  导入即注册全部表模型
from app.core.config import settings
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    return url or settings.DATABASE_URL


def _guard_mysql(url: str) -> None:
    if url.startswith("mysql") and os.environ.get("ALEMBIC_ALLOW_MYSQL") != "1":
        raise RuntimeError(
            "拒绝在未显式确认的情况下对 MySQL 执行 migration。"
            "确需执行时请显式设置环境变量 ALEMBIC_ALLOW_MYSQL=1。"
        )


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连接数据库。"""
    url = _resolve_url()
    _guard_mysql(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：真实执行 migration。"""
    url = _resolve_url()
    _guard_mysql(url)
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
