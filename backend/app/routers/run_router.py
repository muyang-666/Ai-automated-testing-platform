# （执行测试模块）接请求、拿参数、处理异常、返回响应

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.test_run import TestRunExecuteResponse
from app.services.run_service import execute_case_test

router = APIRouter(prefix="/runs", tags=["Runs"])

# 请求方式：POST
# 地址：/runs/{case_id}/execute
# case_id：前端传进来的测试用例 ID
# db：FastAPI 通过 Depends(get_db) 自动帮你注入数据库会话
# 返回格式：必须符合 TestRunExecuteResponse
@router.post("/{case_id}/execute", response_model=TestRunExecuteResponse, summary="执行指定测试用例")
def execute_test(case_id: int, db: Session = Depends(get_db)):
    try:
        return execute_case_test(db, case_id) # 把活交给 service
    # 把 Python 异常翻译成 HTTP 错误
    except ValueError as e: # 数据库里没有这个 case
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e: # 测试文件不存在
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # 其他未知错误
        raise HTTPException(status_code=500, detail=f"执行测试失败: {str(e)}")