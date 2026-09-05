"""P06 conversation 的模型 Provider/场景来源（收敛自 env snapshot 过渡方案）。

配置来源 = 现有 LLM 配置中心的独立聊天场景 `agent_chat`（scene_code='agent_chat'）。
未绑定/未启用/不可用 → 抛 AgentError(configuration_not_ready)；
绝不返回 Secret；CI 用 Fake Provider（依赖覆盖/worker 注入，不经此函数）。
"""
from sqlalchemy.orm import Session

from app.agents.providers.streaming import ProviderSnapshot
from app.agents.runtime.errors import AgentError
from app.models.llm.llm_model import LLMModel
from app.models.llm.llm_provider import LLMProvider
from app.models.llm.llm_scene_config import LLMSceneConfig

CHAT_SCENE_CODE = "agent_chat"


def resolve_conversation_snapshot(db: Session) -> ProviderSnapshot:
    """解析 agent_chat 场景绑定 → ProviderSnapshot；未就绪抛 configuration_not_ready。"""
    scene = db.query(LLMSceneConfig).filter(
        LLMSceneConfig.scene_code == CHAT_SCENE_CODE).first()
    if scene is None or not scene.enabled or scene.model_id is None:
        raise AgentError("agent_chat 场景未配置或未启用（configuration_not_ready）",
                         error_code="configuration_not_ready")
    model = db.query(LLMModel).filter(
        LLMModel.id == scene.model_id, LLMModel.status == "active",
        LLMModel.is_deleted.is_(False)).first()
    provider = (db.query(LLMProvider).filter(
        LLMProvider.id == model.provider_id, LLMProvider.status == "active",
        LLMProvider.is_deleted.is_(False)).first()
        if model is not None else None)
    if model is None or provider is None:
        raise AgentError("agent_chat 场景绑定的模型/供应商不可用（configuration_not_ready）",
                         error_code="configuration_not_ready")
    return ProviderSnapshot(
        provider_type=provider.provider_type,
        name=provider.name,
        base_url=provider.base_url,
        api_key=provider.api_key,
        model_name=model.model_name,
        timeout_seconds=float(model.timeout_seconds or 60),
        max_tokens=model.max_tokens,
        temperature=model.temperature,
    )


def is_conversation_model_ready(db: Session) -> bool:
    try:
        resolve_conversation_snapshot(db)
        return True
    except AgentError:
        return False
