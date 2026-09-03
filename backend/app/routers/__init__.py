from app.routers.case_router import router as case_router
from app.routers.ai_router import router as ai_router
from app.routers.auth_router import router as auth_router
from app.routers.run_router import router as run_router
from app.routers.module_router import router as module_router
from app.routers.project_router import router as project_router
from app.routers.report_router import router as report_router
from app.routers.requirement_doc_router import router as requirement_doc_router
from app.routers.function_case_router import router as function_case_router
from app.routers.llm.llm_config_router import router as llm_config_router
from app.routers.api_document_router import router as api_document_router
from app.routers.user_router import router as user_router

__all__ = [
    "case_router",
    "ai_router",
    "auth_router",
    "run_router",
    "module_router",
    "project_router",
    "report_router",
    "requirement_doc_router",
    "function_case_router",
    "llm_config_router",
    "api_document_router",
    "user_router",
]
