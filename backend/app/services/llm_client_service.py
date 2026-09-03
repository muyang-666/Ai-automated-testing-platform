"""V1 LLM Client 兼容层。

保留 V1 函数签名与字符串返回合同，内部改为调用新 LLMGateway：

- get_model_config_by_scene：抛 LLMConfigurationError（ValueError 子类），
  消息文案与 V1 完全一致（被 T01 Baseline 冻结）；
- call_llm_with_model：薄包装，返回模型文本字符串；
- call_llm_by_scene：只在"配置不可用"（LLMConfigurationError）时回退 .env；
  Provider 调用失败（超时/HTTP/限流等）直接向上抛，绝不二次回退；
- test_llm_model：返回 {success, output, error} 字典合同不变；
- _call_llm_with_env / _env_available：.env 兼容入口保留 V1 行为。
"""

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.exceptions.llm_errors import LLMConfigurationError
from app.models.llm_model import LLMModel
from app.models.llm_provider import LLMProvider
from app.models.llm_scene_config import LLMSceneConfig
from app.schemas.llm_gateway import LLMMessage, LLMRequest
from app.services.llm_gateway import LLMGateway

_gateway = LLMGateway()


def get_model_config_by_scene(db: Session, scene_code: str) -> dict:
    scene_config = db.query(LLMSceneConfig).filter(
        LLMSceneConfig.scene_code == scene_code,
    ).first()
    if not scene_config:
        raise LLMConfigurationError(f"业务场景不存在: {scene_code}")
    if not scene_config.enabled:
        raise LLMConfigurationError(f"业务场景未启用: {scene_code}")
    if not scene_config.model_id:
        raise LLMConfigurationError(f"业务场景未绑定模型: {scene_code}")

    model = db.query(LLMModel).filter(
        LLMModel.id == scene_config.model_id,
        LLMModel.is_deleted == False,
        LLMModel.status == "active",
    ).first()
    if not model:
        raise LLMConfigurationError(f"绑定的模型不可用: model_id={scene_config.model_id}")

    provider = db.query(LLMProvider).filter(
        LLMProvider.id == model.provider_id,
        LLMProvider.is_deleted == False,
        LLMProvider.status == "active",
    ).first()
    if not provider:
        raise LLMConfigurationError(f"模型所属供应商不可用: provider_id={model.provider_id}")

    return {
        "scene_config": scene_config,
        "model": model,
        "provider": provider,
    }


def call_llm_with_model(
    provider: LLMProvider,
    model: LLMModel,
    prompt: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    request = LLMRequest(
        messages=[LLMMessage(role="user", content=prompt)],
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=float(model.timeout_seconds),
    )
    result = _gateway.complete(provider, model, request)
    return result.content


def _apply_prompt_template(template: str | None, prompt: str) -> str:
    if not template:
        return prompt
    if "{input}" in template:
        return template.replace("{input}", prompt)
    return template + "\n\n" + prompt


def _call_llm_with_env(prompt: str, temperature: float = 0.0, max_tokens: int = 2048) -> str:
    """使用 .env 配置直接调用 LLM，不依赖数据库配置。保留 V1 行为。"""
    base_url = settings.LLM_BASE_URL.rstrip("/")
    if not base_url.endswith("/chat/completions"):
        url = f"{base_url}/chat/completions"
    else:
        url = base_url

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = httpx.post(url=url, headers=headers, json=payload, timeout=60.0)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _env_available() -> bool:
    """检查 .env 是否配置了可用的 LLM。"""
    provider = settings.LLM_PROVIDER.lower()
    if provider == "mock" or not settings.LLM_API_KEY:
        return False
    if not settings.LLM_BASE_URL or not settings.LLM_MODEL:
        return False
    return True


def call_llm_by_scene(db: Session, scene_code: str, prompt: str) -> str:
    """按业务场景调用 LLM。优先使用配置中心绑定的模型，未配置则回退到 .env。

    只有"配置不可用"（LLMConfigurationError）时才回退 .env；
    Provider 调用失败（超时/HTTP/限流等）直接向上抛，绝不二次回退。
    """
    try:
        config = get_model_config_by_scene(db, scene_code)
    except LLMConfigurationError:
        if not _env_available():
            raise LLMConfigurationError(
                f"业务场景 '{scene_code}' 未在配置中心绑定模型，"
                f"且 .env 中也未配置有效的 LLM（LLM_PROVIDER={settings.LLM_PROVIDER}）。"
                f"请在模型管理页面绑定模型，或在 .env 中配置 LLM。"
            )
        # 回退到 .env 配置
        return _call_llm_with_env(prompt)

    scene_config = config["scene_config"]
    model = config["model"]
    provider = config["provider"]
    final_prompt = _apply_prompt_template(scene_config.prompt_template, prompt)
    return call_llm_with_model(provider, model, final_prompt)


def test_llm_model(db: Session, model_id: int, prompt: str | None = None) -> dict:
    model = db.query(LLMModel).filter(
        LLMModel.id == model_id,
        LLMModel.is_deleted == False,
    ).first()
    if not model:
        return {"success": False, "output": "", "error": "模型不存在或已删除"}

    provider = db.query(LLMProvider).filter(
        LLMProvider.id == model.provider_id,
        LLMProvider.is_deleted == False,
    ).first()
    if not provider:
        return {"success": False, "output": "", "error": "模型所属供应商不存在或已删除"}

    test_prompt = prompt or "请回复：模型连接测试成功"

    try:
        output = call_llm_with_model(provider, model, test_prompt)
        return {"success": True, "output": output, "error": None}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}
