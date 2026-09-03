"""仅手动联调：临时 SQLite + Fake LLM + 固定测试用户，绝不导入生产 app.main。

运行：.venv/Scripts/python.exe backend/tests/manual/agent_preview_server.py
仅监听 127.0.0.1:8011；退出时清理临时数据库。不要部署此入口。
"""

import os
import sys
import tempfile
from pathlib import Path
from threading import Event, Thread


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    with tempfile.TemporaryDirectory(prefix="testmind-agent-integration-") as temporary:
        os.environ.update(
            DATABASE_URL="sqlite:///" + (Path(temporary) / "integration.sqlite3").as_posix(),
            LLM_PROVIDER="mock", LLM_API_KEY="", LLM_MODEL="", LLM_BASE_URL="",
        )
        import uvicorn
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from app.core.database import Base, SessionLocal, engine
        from app.models import Project, User, Role, UserRole, UserProjectPermission, RequirementDoc, ApiDocument, LLMProvider, LLMModel, LLMSceneConfig, FunctionCase, APICase
        from app.routers.agent_router import router
        from app.routers.dependencies import get_current_user
        from app.agents.bootstrap import build_default_skill_registry, build_default_tool_registry
        from app.agents.runtime.runner import AgentRunner
        from app.agents.skills.case_generation.schemas import AnalyzeAndPlanOutput, GenerateFunctionCandidatesOutput, GenerateApiCandidatesOutput
        from app.schemas.llm_gateway import LLMResult
        from app.workers.agent_worker import AgentWorker

        class FixtureGateway:
            def complete(self, provider, model, request, response_model=None):
                if response_model is AnalyzeAndPlanOutput:
                    payload = {"atomic_clauses": [
                        {"clause_id": "REQ-001", "text": "合法输入登录成功", "priority": "P0"},
                        {"clause_id": "REQ-002", "text": "缺少账号时拒绝登录", "priority": "P1"},
                    ], "coverage_plan": [
                        {"clause_id": "REQ-001", "dimension": "正常场景"},
                        {"clause_id": "REQ-002", "dimension": "异常场景"},
                    ]}
                elif response_model is GenerateFunctionCandidatesOutput:
                    payload = {"candidates": [
                        {"case_name": "合法账号登录", "case_type": "正常场景", "steps_json": ["输入合法账号", "点击登录"], "expected_result": "进入首页", "covered_clause_ids": ["REQ-001"]},
                        {"case_name": "空账号拦截", "case_type": "异常场景", "steps_json": ["清空账号", "点击登录"], "expected_result": "提示账号必填", "covered_clause_ids": ["REQ-002"]},
                    ]}
                elif response_model is GenerateApiCandidatesOutput:
                    payload = {"candidates": [
                        {"name": "登录正常请求", "method": "POST", "url": "https://example.invalid/login", "headers": {"Content-Type": "application/json"}, "body": {"username": "fixture-user"}, "expected_result": {"code": 200}, "case_type": "正常场景", "covered_clause_ids": ["REQ-001"]},
                        {"name": "缺少账号请求", "method": "POST", "url": "https://example.invalid/login", "headers": {"Content-Type": "application/json"}, "body": {}, "expected_result": {"code": 400}, "case_type": "异常场景", "covered_clause_ids": ["REQ-002"]},
                    ]}
                else:
                    raise RuntimeError(f"隔离联调出现未预期模型调用：{response_model}")
                return LLMResult(content="", parsed=response_model.model_validate(payload), provider_name="Fixture only", model_name="fake", prompt_tokens=20, completion_tokens=30, duration_ms=1, finish_reason="stop")

        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            db.add_all([
                Project(id=1, name="隔离联调项目", status="active", is_deleted=False),
                User(id=1, username="fixture-user", password_hash="unused", salt="unused", status="active", is_deleted=False),
                Role(id=1, code="tester", name="测试人员", status="active"),
            ])
            db.flush()
            db.add_all([UserRole(user_id=1, role_id=1), UserProjectPermission(user_id=1, project_id=1, can_operate=True)])
            db.add(RequirementDoc(id=1, project_id=1, title="联调登录需求", content="合法账号可登录，缺少账号时拒绝。", status="confirmed", is_deleted=False))
            db.add(RequirementDoc(id=2, project_id=1, title="来源变更联调", content="合法账号可登录，缺少账号时拒绝。", status="confirmed", is_deleted=False))
            db.add(ApiDocument(id=1, project_id=1, name="联调登录接口", method="POST", url="https://example.invalid/login", content="合法账号返回 code=200，缺少账号返回 code=400。", status="active", is_deleted=False))
            db.add(LLMProvider(id=1, name="Fixture only", provider_type="openai_compatible", base_url="https://example.invalid", api_key="unused-fixture", status="active", is_deleted=False))
            db.flush()
            db.add(LLMModel(id=1, provider_id=1, model_name="fake", status="active", is_deleted=False))
            db.flush()
            for code in ("requirement_to_function_case", "api_doc_to_api_case"):
                db.add(LLMSceneConfig(scene_code=code, scene_name=code, model_id=1, enabled=True))
            db.commit()

        app = FastAPI(title="TestMind isolated integration (DO NOT DEPLOY)")
        app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5175"], allow_methods=["*"], allow_headers=["*"])
        app.include_router(router)

        def fixture_user():
            with SessionLocal() as db:
                return db.get(User, 1)

        app.dependency_overrides[get_current_user] = fixture_user

        @app.get("/fixture/info")
        def info():
            with SessionLocal() as db:
                return {"mode": "isolated", "function_cases": [{"id": row.id, "name": row.case_name} for row in db.query(FunctionCase).all()], "api_cases": [{"id": row.id, "name": row.name} for row in db.query(APICase).all()]}

        @app.post("/fixture/change-source")
        def change_source():
            with SessionLocal() as db:
                row = db.get(RequirementDoc, 2)
                row.content += " 新增一条联调需求。"
                db.commit()
            return {"changed": True}

        stop = Event()
        worker = AgentWorker(SessionLocal, lambda hook: AgentRunner(
            build_default_skill_registry(gateway_factory=FixtureGateway), build_default_tool_registry(), on_step_boundary=hook,
        ), worker_id="isolated-integration")

        def pump():
            while not stop.wait(0.2):
                worker.run_once()

        thread = Thread(target=pump, daemon=True)
        thread.start()
        try:
            uvicorn.run(app, host="127.0.0.1", port=8011, log_level="warning")
        finally:
            stop.set()
            thread.join(timeout=10)
            engine.dispose()


if __name__ == "__main__":
    main()
