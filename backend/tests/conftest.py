"""pytest 全局配置。

在导入任何 app 模块之前，强制把测试环境锁定为：
- 内存 SQLite（禁止连接真实 MySQL）；
- mock LLM（禁止调用真实 LLM、禁止读取真实 API Key、禁止网络）。

pydantic-settings 中环境变量优先级高于 backend/.env，因此这里无条件覆盖，
即使 shell 会话或 .env 中存在真实 DATABASE_URL / LLM 配置也不会被沿用。

内存 SQLite 使用 StaticPool 共享单连接：TestClient 会在其他线程执行 FastAPI
startup，默认 SingletonThreadPool 会让每个线程看到独立的空数据库，
因此这里在测试模块导入前替换 engine/SessionLocal。
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_MODEL"] = ""

import pytest  # noqa: E402
from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.core.database as db_module  # noqa: E402
import app.models  # noqa: E402, F401  导入即注册全部表模型
from app.core.database import Base  # noqa: E402

# 替换为共享单连接的引擎：所有 Session（含 TestClient 线程与 Worker）看到同一内存库
db_module.engine.dispose()
_shared_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_shared_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """启用 SQLite 外键约束，与 MySQL 行为对齐。

    SQLite 默认不强制外键，若不开则会漏掉 MySQL 才暴露的 FK 问题
    （T08.1 会话创建 500 即属此类）。PRAGMA 按连接生效，因此挂到 connect 事件。
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


db_module.engine = _shared_engine
db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_shared_engine)


@pytest.fixture()
def db_session():
    """每条测试独立重建全部表：测试之间互不污染、不依赖执行顺序。"""
    Base.metadata.drop_all(bind=db_module.engine)
    Base.metadata.create_all(bind=db_module.engine)
    session = db_module.SessionLocal()
    try:
        # 确认外键已开启，避免再次漏掉 MySQL 才暴露的问题
        foreign_keys = session.execute(text("PRAGMA foreign_keys")).scalar()
        assert foreign_keys == 1, "隔离 SQLite 未启用外键检查"
        yield session
    finally:
        session.close()
