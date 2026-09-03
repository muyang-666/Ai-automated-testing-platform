'''V2-R01 目录整理：agent API Schema 包。

唯一实现位于 .api（原 schemas/agent.py 原文迁移）；本 __init__ 仅显式重导出原公开 Schema，
保留必要包级访问。新代码请直接 from app.schemas.agent.api import ...。'''
from app.schemas.agent.api import (
    AgentResponseBase,
    AgentSessionCreate,
    AgentSessionResponse,
    AgentMessageCreate,
    AgentMessageResponse,
    AgentEventResponse,
    AgentSessionDetailResponse,
    CaseGenerationRunRequest,
    RunResponse,
    StepResponse,
    ArtifactResponse,
    ApprovalResolveRequest,
    ApprovalResponse,
    SaveCandidatesRequest,
    SaveCandidatesResponse,
)

__all__ = ['AgentResponseBase', 'AgentSessionCreate', 'AgentSessionResponse', 'AgentMessageCreate', 'AgentMessageResponse', 'AgentEventResponse', 'AgentSessionDetailResponse', 'CaseGenerationRunRequest', 'RunResponse', 'StepResponse', 'ArtifactResponse', 'ApprovalResolveRequest', 'ApprovalResponse', 'SaveCandidatesRequest', 'SaveCandidatesResponse']
