from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# 执行测试接口返回合同
class TestRunExecuteResponse(BaseModel):
    run_id: int
    case_id: int
    status: str
    result: Optional[str] = None
    total_count: int
    passed_count: int
    failed_count: int
    log_content: Optional[str] = None
    error_message: Optional[str] = None
    response_status_code: Optional[int] = None
    response_content: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    message: str

# 执行记录列表返回合同
class TestRunListResponse(BaseModel):
    run_id: int
    case_id: int
    status: str
    result: Optional[str] = None
    total_count: int
    passed_count: int
    failed_count: int
    log_content: Optional[str] = None
    error_message: Optional[str] = None
    response_status_code: Optional[int] = None
    response_content: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

class TestRunDeleteResponse(BaseModel):
    message: str