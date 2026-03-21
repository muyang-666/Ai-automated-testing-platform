from datetime import datetime
from pydantic import BaseModel


# 返回给前端的报告结构
class ReportResponse(BaseModel):
    id: int
    report_name: str
    report_type: str
    summary: str
    total_count: int
    passed_count: int
    failed_count: int
    pass_rate: float
    risk_summary: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True