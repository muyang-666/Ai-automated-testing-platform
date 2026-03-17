from datetime import datetime
from typing import Optional

from pydantic import BaseModel

# 查看已存在的分析记录
class AIAnalysisResponse(BaseModel):
    id: int # ai_analyses 表中的某条真实记录
    run_id: int
    analysis_type: str
    content: str
    risk_level: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True # 允许 Pydantic 直接从 ORM 对象属性里读取值

# 触发生成分析
class AIAnalysisGenerateResponse(BaseModel):
    run_id: int
    analysis_type: str
    content: str
    risk_level: Optional[str]
    message: str
    created_at: datetime