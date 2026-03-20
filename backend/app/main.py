# main.py 是项目启动入口，负责创建 FastAPI 应用、注册路由、建表和配置跨域。

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.models import APICase, TestRun, AIAnalysis, Report
from app.routers.ai_router import router as ai_router
from app.routers.case_router import router as case_router
from app.routers.run_router import router as run_router
from app.routers.report_router import router as report_router
from app.routers.mock_router import router as mock_router
from app.routers.parameter_file_router import router as parameter_file_router

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
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", summary="健康检查")
def health_check():
    return {
        "message": "AI Test Assistant backend is running",
        "version": settings.APP_VERSION,
    }

# 把“测试用例相关接口”挂到 /cases 这个路径下
app.include_router(case_router)
app.include_router(ai_router)
app.include_router(run_router)
app.include_router(report_router)
app.include_router(mock_router)
app.include_router(parameter_file_router)