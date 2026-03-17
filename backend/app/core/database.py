# database.py 是数据库基础设施，负责提供数据库连接
# engine、会话工厂 SessionLocal、模型基类 Base，以及通过 get_db 给接口注入数据库会话。
# database.py 的作用是：统一管理数据库连接和会话。

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

#数据库位置 数据库是一个本地文件
engine = create_engine( # engine:Python程序和数据库之间的连接发动机
    settings.DATABASE_URL, #数据库地址
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
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