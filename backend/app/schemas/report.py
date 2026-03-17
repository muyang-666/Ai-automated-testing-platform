from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# 表示“生成报告”接口返回什么
class ReportGenerateResponse(BaseModel):
    run_id: int
    summary: str
    total_count: int
    passed_count: int
    failed_count: int
    pass_rate: float
    risk_summary: Optional[str]
    message: str
    created_at: datetime

# 表示“查看报告记录”接口返回什么。
class ReportResponse(BaseModel):
    id: int
    run_id: int
    summary: str
    total_count: int
    passed_count: int
    failed_count: int
    pass_rate: float
    risk_summary: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True