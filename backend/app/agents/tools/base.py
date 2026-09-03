"""Agent 工具协议与 ToolContext。

- 每个工具：Pydantic 输入/输出、read_only/requires_approval 声明；
- 工具不自行 commit 事务、不执行写业务表操作（本阶段全部只读）；
- 权限守卫：查询工具必须经 require_project_read 校验项目读权限，
  跨项目访问直接拒绝。
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.runtime.errors import AgentPermissionError
from app.models.user import User
from app.services import permission_service


@dataclass
class ToolContext:
    """工具执行上下文。"""

    user_id: int
    db: Session
    run_id: int | None = None
    session_id: int | None = None
    project_id: int | None = None
    metadata: dict = field(default_factory=dict)  # 非敏感元数据


@runtime_checkable
class AgentTool(Protocol):
    """工具协议：只定义能力，不执行任意 SQL/Shell/网络。"""

    name: str
    description: str
    read_only: bool
    requires_approval: bool
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    def execute(self, context: ToolContext, payload: BaseModel) -> BaseModel:
        ...


def require_project_read(db: Session, user_id: int, project_id: int | None) -> User:
    """按 permission_service 的确定性规则校验项目读权限；拒绝时抛 AgentPermissionError。"""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise AgentPermissionError(f"用户 {user_id} 不存在或不可用。")
    if not permission_service.can_read_project(db, user, project_id):
        raise AgentPermissionError(
            f"用户 {user_id} 无项目 {project_id} 的读取权限（跨项目访问被拒绝）。"
        )
    return user
