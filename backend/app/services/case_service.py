#业务的功能实现

# 表示这里的 db 参数是 SQLAlchemy 的数据库会话对象。 service 用这个 db 去和数据库打交道
from sqlalchemy.orm import Session

# 说明 service 要操作的是 APICase 这张表对应的 ORM 模型。
from app.models.api_case import APICase
# 说明创建测试用例时，service 接收的不是乱七八糟的 dict，而是已经经过 Pydantic 校验的 APICaseCreate 对象。
from app.schemas.api_case import APICaseCreate


# create_case() 是怎么创建一条测试用例的
# 1. 它需要 db 说明它要操作数据库。
# 2. 它需要 case_data 说明它要根据前端传入的创建数据来生成一条测试用例记录。
# 3. 它返回 APICase 说明最终返回的是一个 ORM 对象。
def create_case(db: Session, case_data: APICaseCreate) -> APICase:
    # db_case = APICase(...) 先在 Python 里创建了一个“测试用例记录对象” 理解成：根据前端传来的数据，先组装出一条“准备入库的测试用例”。
    db_case = APICase(
        name=case_data.name,
        description=case_data.description,
        method=case_data.method.upper(),  # # 无论前端传 post、Post、POST，最后都统一存成大写
        url=case_data.url,
        headers=case_data.headers,
        body=case_data.body,
        expected_result=case_data.expected_result,
    )
    db.add(db_case)       # 把这个对象加入当前数据库会话，准备提交
    db.commit()           # 正式提交事务，把变更真正写进数据库
    db.refresh(db_case)   # 从数据库重新刷新这条对象的数据
    return db_case        # 返回一个 ORM 对象

# 这个函数用来查测试用例列表
def get_case_list(db: Session):
    # db.query(APICase) 表示：查询 APICase 这张表
    # .order_by(APICase.id.desc()) 表示按 id 倒序排列。
    # .all()表示把符合条件的所有记录都取出来，并返回一个列表。
    return db.query(APICase).order_by(APICase.id.desc()).all()

# 这个函数用来按 id 查单条详情
def get_case_by_id(db: Session, case_id: int):
    # .filter(APICase.id == case_id)表示加筛选条件：只找 id 等于 case_id 的记录
    # .first()表示取第一条结果。因为 id 通常是唯一主键，所以最多只有一条匹配记录。
    return db.query(APICase).filter(APICase.id == case_id).first()