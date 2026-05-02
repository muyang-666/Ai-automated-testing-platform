from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SceneStepRunResponse(BaseModel):
    id: int
    scene_run_id: int
    scene_step_id: Optional[int]
    case_id: Optional[int]
    step_order: Optional[int]
    step_name: Optional[str]
    status: str
    request_method: Optional[str]
    request_url: Optional[str]
    request_headers_json: Optional[Any]
    request_body_json: Optional[Any]
    response_status_code: Optional[int]
    response_body: Optional[str]
    extracted_variables_json: Optional[Any]
    assertion_results_json: Optional[Any]
    error_message: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class SceneRunResponse(BaseModel):
    id: int
    scene_id: int
    project_id: Optional[int]
    module_id: Optional[int]
    status: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    skipped_steps: int
    context_json: Optional[Any]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class SceneRunDetailResponse(SceneRunResponse):
    steps: list[SceneStepRunResponse] = []
