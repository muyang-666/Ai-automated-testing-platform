from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AICaseGenerateResponse(BaseModel):
    case_id: int
    case_name: str
    generated_test_code: str
    file_path: Optional[str]
    message: str
    generated_at: datetime