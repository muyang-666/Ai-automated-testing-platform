from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# 接口返回合同
class TestRunExecuteResponse(BaseModel):
    run_id: int
    case_id: int
    status: str
    result: Optional[str]
    total_count: int
    passed_count: int
    failed_count: int
    log_content: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    message: str