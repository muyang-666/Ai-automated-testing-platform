"""用例生成只读上下文工具。

- load_source_context：需求/接口文档来源快照与内容哈希；
- load_project_module_context：项目与模块摘要；
- list_existing_cases：授权项目内已有功能/接口用例摘要（限量）；
- list_related_api_documents：授权项目内接口文档摘要。

全部只读、带项目读权限校验（跨项目访问抛 AgentPermissionError）。
已知限制：ApiDocument 与 APICase 无直接外键关联，相关文档按项目/模块返回。
"""

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.tools.base import ToolContext, require_project_read
from app.agents.validators.case_validators import case_fingerprint
from app.models.api_case import APICase
from app.models.api_document import ApiDocument
from app.models.function_case import FunctionCase
from app.models.project import Project
from app.models.requirement_doc import RequirementDoc
from app.models.test_module import TestModule


def _canonical_hash(data: dict) -> str:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── load_source_context ──


class LoadSourceContextInput(BaseModel):
    source_type: Literal["requirement", "api_document"]
    source_id: int = Field(..., description="来源 ID")


class LoadSourceContextOutput(BaseModel):
    found: bool
    source: dict[str, Any] = Field(default_factory=dict, description="来源快照")
    source_hash: str | None = Field(default=None, description="来源内容哈希")


class LoadSourceContextTool:
    name = "load_source_context"
    description = "读取需求文本或接口文档的来源快照与内容哈希（含项目权限校验）"
    read_only = True
    requires_approval = False
    input_model = LoadSourceContextInput
    output_model = LoadSourceContextOutput

    def execute(self, context: ToolContext, payload: LoadSourceContextInput) -> LoadSourceContextOutput:
        db: Session = context.db
        if payload.source_type == "requirement":
            obj = (
                db.query(RequirementDoc)
                .filter(RequirementDoc.id == payload.source_id, RequirementDoc.is_deleted == False)
                .first()
            )
            if obj is None:
                return LoadSourceContextOutput(found=False)
            require_project_read(db, context.user_id, obj.project_id)
            snapshot = {
                "type": "requirement",
                "id": obj.id,
                "project_id": obj.project_id,
                "module_id": obj.module_id,
                "title": obj.title,
                "content": obj.content,
                "requirement_type": obj.requirement_type,
                "supplementary_prompt": obj.supplementary_prompt,
            }
        else:
            obj = (
                db.query(ApiDocument)
                .filter(ApiDocument.id == payload.source_id, ApiDocument.is_deleted == False)
                .first()
            )
            if obj is None:
                return LoadSourceContextOutput(found=False)
            require_project_read(db, context.user_id, obj.project_id)
            snapshot = {
                "type": "api_document",
                "id": obj.id,
                "project_id": obj.project_id,
                "module_id": obj.module_id,
                "name": obj.name,
                "method": obj.method,
                "url": obj.url,
                "description": obj.description,
                "content": obj.content,
                "supplementary_prompt": obj.supplementary_prompt,
            }
        return LoadSourceContextOutput(found=True, source=snapshot, source_hash=_canonical_hash(snapshot))


# ── load_project_module_context ──


class LoadProjectModuleContextInput(BaseModel):
    project_id: int = Field(..., description="项目 ID")
    module_id: int | None = Field(default=None, description="模块 ID，可空")


class LoadProjectModuleContextOutput(BaseModel):
    project: dict[str, Any] = Field(default_factory=dict, description="项目摘要")
    module: dict[str, Any] | None = Field(default=None, description="模块摘要")
    module_mismatch: bool = Field(default=False, description="模块不属于该项目")


class LoadProjectModuleContextTool:
    name = "load_project_module_context"
    description = "读取项目与模块摘要（含项目权限校验）"
    read_only = True
    requires_approval = False
    input_model = LoadProjectModuleContextInput
    output_model = LoadProjectModuleContextOutput

    def execute(self, context: ToolContext, payload: LoadProjectModuleContextInput) -> LoadProjectModuleContextOutput:
        db: Session = context.db
        require_project_read(db, context.user_id, payload.project_id)
        project = db.query(Project).filter(Project.id == payload.project_id).first()
        if project is None:
            return LoadProjectModuleContextOutput(project={}, module=None)
        module = None
        module_mismatch = False
        if payload.module_id is not None:
            row = db.query(TestModule).filter(TestModule.id == payload.module_id).first()
            if row is not None:
                if row.project_id != payload.project_id:
                    module_mismatch = True
                else:
                    module = {"id": row.id, "name": row.name, "parent_id": row.parent_id, "path": row.path}
        return LoadProjectModuleContextOutput(
            project={"id": project.id, "name": project.name, "status": project.status},
            module=module,
            module_mismatch=module_mismatch,
        )


# ── list_existing_cases ──


class ListExistingCasesInput(BaseModel):
    project_id: int = Field(..., description="项目 ID")
    case_kind: Literal["function", "api"] = Field(..., description="功能用例或接口用例")
    module_id: int | None = Field(default=None, description="模块筛选，可空")
    requirement_id: int | None = Field(default=None, description="需求筛选（仅功能用例），可空")
    limit: int = Field(default=50, ge=1, le=200, description="返回上限")


class ListExistingCasesOutput(BaseModel):
    total: int = 0
    cases: list[dict[str, Any]] = Field(default_factory=list, description="用例摘要（限量字段）")


class ListExistingCasesTool:
    name = "list_existing_cases"
    description = "查询授权项目内已有功能/接口用例摘要（限量、含项目权限校验）"
    read_only = True
    requires_approval = False
    input_model = ListExistingCasesInput
    output_model = ListExistingCasesOutput

    def execute(self, context: ToolContext, payload: ListExistingCasesInput) -> ListExistingCasesOutput:
        db: Session = context.db
        require_project_read(db, context.user_id, payload.project_id)

        if payload.case_kind == "function":
            query = db.query(FunctionCase).filter(
                FunctionCase.is_deleted == False,
                FunctionCase.project_id == payload.project_id,
            )
            if payload.module_id is not None:
                query = query.filter(FunctionCase.module_id == payload.module_id)
            if payload.requirement_id is not None:
                query = query.filter(FunctionCase.requirement_id == payload.requirement_id)
            total = query.count()
            rows = query.order_by(FunctionCase.id.desc()).limit(payload.limit).all()
            cases = [
                {
                    "id": row.id,
                    "case_code": row.case_code,
                    "case_name": row.case_name,  # 统一字段名，与候选侧 case_name 对齐
                    "case_type": row.case_type,
                    "priority": row.priority,
                    "source": row.source,
                    "module_id": row.module_id,
                    "requirement_id": row.requirement_id,
                    # 安全去重指纹：由 case_fingerprint 同一算法生成；
                    # 不返回 steps_json/expected_result 明文，避免 Secret 泄露
                    "dedup_fingerprint": case_fingerprint(
                        "function",
                        {
                            "case_name": row.case_name,
                            "steps_json": row.steps_json,
                            "expected_result": row.expected_result,
                            "case_type": row.case_type,
                        },
                    ),
                }
                for row in rows
            ]
        else:
            query = db.query(APICase).filter(
                APICase.is_deleted == False,
                APICase.project_id == payload.project_id,
            )
            if payload.module_id is not None:
                query = query.filter(APICase.module_id == payload.module_id)
            total = query.count()
            rows = query.order_by(APICase.id.desc()).limit(payload.limit).all()
            cases = [
                {
                    "id": row.id,
                    "name": row.name,
                    "method": row.method,
                    "url": row.url,
                    "case_type": row.case_type,
                    "priority": row.priority,
                    "source": row.source,
                    "module_id": row.module_id,
                    # 不返回 body/expected_result 明文，仅提供安全去重指纹
                    "dedup_fingerprint": case_fingerprint(
                        "api",
                        {
                            "method": row.method,
                            "url": row.url,
                            "body": row.body,
                            "expected_result": row.expected_result,
                            "case_type": row.case_type,
                        },
                    ),
                }
                for row in rows
            ]
        return ListExistingCasesOutput(total=total, cases=cases)


# ── list_related_api_documents ──


class ListRelatedApiDocumentsInput(BaseModel):
    project_id: int = Field(..., description="项目 ID")
    limit: int = Field(default=50, ge=1, le=200, description="返回上限")


class ListRelatedApiDocumentsOutput(BaseModel):
    total: int = 0
    documents: list[dict[str, Any]] = Field(default_factory=list, description="接口文档摘要")


class ListRelatedApiDocumentsTool:
    name = "list_related_api_documents"
    description = "查询授权项目内接口文档摘要（限量）；ApiDocument 与 APICase 无直接关联，按项目返回"
    read_only = True
    requires_approval = False
    input_model = ListRelatedApiDocumentsInput
    output_model = ListRelatedApiDocumentsOutput

    def execute(self, context: ToolContext, payload: ListRelatedApiDocumentsInput) -> ListRelatedApiDocumentsOutput:
        db: Session = context.db
        require_project_read(db, context.user_id, payload.project_id)
        query = db.query(ApiDocument).filter(
            ApiDocument.is_deleted == False,
            ApiDocument.project_id == payload.project_id,
        )
        total = query.count()
        rows = query.order_by(ApiDocument.id.desc()).limit(payload.limit).all()
        documents = [
            {"id": row.id, "name": row.name, "method": row.method, "url": row.url, "module_id": row.module_id}
            for row in rows
        ]
        return ListRelatedApiDocumentsOutput(total=total, documents=documents)
