# database.py 是数据库基础设施，负责提供数据库连接
# engine、会话工厂 SessionLocal、模型基类 Base，以及通过 get_db 给接口注入数据库会话。
# database.py 的作用是：统一管理数据库连接和会话。

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def is_sqlite_database(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def ensure_mysql_database_exists(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "mysql" or not url.database:
        return

    database_name = url.database.replace("`", "``")
    server_url = url.set(database="")
    server_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with server_engine.connect() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        server_engine.dispose()


ensure_mysql_database_exists(settings.DATABASE_URL)

# 数据库连接。MySQL 会先确保库存在；SQLite 测试环境仍可通过 DATABASE_URL 覆盖。
engine = create_engine( # engine:Python程序和数据库之间的连接发动机
    settings.DATABASE_URL, #数据库地址
    connect_args={"check_same_thread": False} if is_sqlite_database(settings.DATABASE_URL) else {},
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 真正操作数据库，不是直接用 engine，而是用 session   SessionLocal 不是一次具体连接，而是一个“生产数据库会话的工厂”。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) #后面每次请求来了，都可以用它造一个 db session 出来

# 后面你所有的模型类都要继承这个 Base。 Base：所有 ORM 模型的父类
Base = declarative_base()
#ORM:对象关系映射（ORM）是一种程序设计技术，用于将不同类型的数据进行转换，实现面向对象编程语言与数据库之间的交互。它可以创建一个虚拟对象数据库，方便编程语言的使用。


# 给路由提供数据库会话。 每来一个请求，就给它发一个数据库操作工具，请求结束再回收
def get_db():
    db = SessionLocal() #创建一个数据库会话
    try:
        yield db #把这个会话交给当前接口使用
    finally:
        db.close() #请求处理完后，关闭会话，释放资源
