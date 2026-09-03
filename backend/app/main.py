# main.py 是项目启动入口，负责创建 FastAPI 应用、注册路由、建表和配置跨域。

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine

from app.models.api_case import APICase
from app.models.auth_session import AuthSession
from app.models.project import Project
from app.models.role import Role
from app.models.requirement_doc import RequirementDoc
from app.models.function_case import FunctionCase
from app.models.scene_run import SceneRun
from app.models.scene_step_run import SceneStepRun
from app.models.test_module import TestModule
from app.models.test_run import TestRun
from app.models.user import User
from app.models.user_project_permission import UserProjectPermission
from app.models.user_role import UserRole
from app.models.ai_analysis import AIAnalysis
from app.models.report import Report
from app.models.scene import Scene
from app.models.scene_step import SceneStep
from app.models.llm.llm_provider import LLMProvider
from app.models.llm.llm_model import LLMModel
from app.models.llm.llm_scene_config import LLMSceneConfig
from app.models.api_document import ApiDocument

from app.routers.auth_router import router as auth_router
from app.routers.case_router import router as case_router
from app.routers.ai_router import router as ai_router
from app.routers.run_router import router as run_router
from app.routers.report_router import router as report_router
from app.routers.mock_router import router as mock_router
from app.routers.scene_router import router as scene_router
from app.routers.parameter_file_router import router as parameter_file_router
from app.routers.project_router import router as project_router
from app.routers.module_router import router as module_router
from app.routers.requirement_doc_router import router as requirement_doc_router
from app.routers.function_case_router import router as function_case_router
from app.routers.user_router import router as user_router
from app.routers.llm.llm_config_router import router as llm_config_router
from app.routers.api_document_router import router as api_document_router
from app.routers.agent.agent_router import router as agent_router
from app.services.auth_service import init_default_auth_data


# 根据 models 里定义的表结构，在数据库里把表建出来。 比如你定义了 APICase 这个模型，它对应数据库里就会生成 api_cases 表。
Base.metadata.create_all(bind=engine) #models 是表结构描述，create_all 是按描述真正建表。

#我要启动一个 FastAPI 后端应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI驱动的自动化测试平台",
)

# 配置中间件CORS  前端和后端端口不同，浏览器默认会拦请求，需要允许跨域。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_init_default_auth_data():
    db = SessionLocal()
    try:
        init_default_auth_data(db)
        from app.services.llm.llm_config_service import init_default_scene_configs
        init_default_scene_configs(db)
    finally:
        db.close()

@app.get("/", summary="健康检查")
def health_check():
    return {
        "message": "AI Test Assistant backend is running",
        "version": settings.APP_VERSION,
    }

# 把“测试用例相关接口”挂到 /cases 这个路径下
app.include_router(auth_router)
app.include_router(case_router)
app.include_router(ai_router)
app.include_router(run_router)
app.include_router(report_router)
app.include_router(mock_router)
app.include_router(parameter_file_router)
app.include_router(project_router)
app.include_router(module_router)
app.include_router(requirement_doc_router)
app.include_router(function_case_router)
app.include_router(user_router)
app.include_router(scene_router)
app.include_router(llm_config_router)
app.include_router(api_document_router)
app.include_router(agent_router)
