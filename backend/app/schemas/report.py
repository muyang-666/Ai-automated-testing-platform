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


class ReportOverview(BaseModel):
    project_count: int
    module_count: int
    api_case_count: int
    function_case_count: int
    requirement_count: int
    scene_count: int


class ReportApiTestSummary(BaseModel):
    total_runs: int
    passed_runs: int
    failed_runs: int
    pass_rate: float


class ReportSceneChainSummary(BaseModel):
    total_runs: int
    passed_runs: int
    failed_runs: int
    error_runs: int
    pass_rate: float


class RecentApiRun(BaseModel):
    id: int
    case_id: int
    status: str
    result: str | None = None
    response_status_code: int | None = None
    created_at: datetime | None = None


class RecentSceneRun(BaseModel):
    id: int
    scene_id: int
    status: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    skipped_steps: int
    duration_ms: int | None = None
    created_at: datetime | None = None


class ReportSummaryResponse(BaseModel):
    overview: ReportOverview
    api_test: ReportApiTestSummary
    scene_chain: ReportSceneChainSummary
    recent_api_runs: list[RecentApiRun]
    recent_scene_runs: list[RecentSceneRun]
