from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.llm.llm_model import LLMModel
from app.models.llm.llm_provider import LLMProvider
from app.models.llm.llm_scene_config import LLMSceneConfig
from app.schemas.llm.llm_config import (
    LLMModelCreate,
    LLMModelResponse,
    LLMModelUpdate,
    LLMProviderCreate,
    LLMProviderResponse,
    LLMProviderUpdate,
    LLMSceneConfigResponse,
    LLMSceneConfigUpdate,
)

DEFAULT_SCENE_CONFIGS = [
    {
        "scene_code": "agent_chat",
        "scene_name": "Agent 对话",
        "enabled": True,
    },
    {
        "scene_code": "requirement_to_function_case",
        "scene_name": "需求生成功能测试用例",
        "enabled": True,
    },
    {
        "scene_code": "api_doc_to_api_case",
        "scene_name": "接口文档生成接口测试用例",
        "enabled": True,
    },
    {
        "scene_code": "failure_analysis",
        "scene_name": "AI 失败分析",
        "enabled": True,
    },
    {
        "scene_code": "report_summary",
        "scene_name": "报告 AI 总结",
        "enabled": True,
    },
]


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:3] + "*" * (len(api_key) - 7) + api_key[-4:]


def _provider_to_response(provider: LLMProvider) -> LLMProviderResponse:
    return LLMProviderResponse(
        id=provider.id,
        name=provider.name,
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        masked_api_key=mask_api_key(provider.api_key),
        status=provider.status,
        remark=provider.remark,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def _get_provider_name(db: Session, provider_id: int) -> str:
    provider = db.query(LLMProvider).filter(
        LLMProvider.id == provider_id,
        LLMProvider.is_deleted == False,
    ).first()
    return provider.name if provider else ""


def _model_to_response(db: Session, model: LLMModel) -> LLMModelResponse:
    return LLMModelResponse(
        id=model.id,
        provider_id=model.provider_id,
        provider_name=_get_provider_name(db, model.provider_id),
        model_name=model.model_name,
        display_name=model.display_name,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        timeout_seconds=model.timeout_seconds,
        status=model.status,
        remark=model.remark,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _scene_config_to_response(db: Session, config: LLMSceneConfig) -> LLMSceneConfigResponse:
    model_name = ""
    display_name = ""
    provider_name = ""
    if config.model_id:
        model = db.query(LLMModel).filter(
            LLMModel.id == config.model_id,
            LLMModel.is_deleted == False,
        ).first()
        if model:
            model_name = model.model_name
            display_name = model.display_name or ""
            provider_name = _get_provider_name(db, model.provider_id)

    return LLMSceneConfigResponse(
        id=config.id,
        scene_code=config.scene_code,
        scene_name=config.scene_name,
        model_id=config.model_id,
        model_name=model_name,
        display_name=display_name,
        provider_name=provider_name,
        enabled=config.enabled,
        prompt_template=config.prompt_template,
        remark=config.remark,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


# ── Provider CRUD ──

def create_provider(db: Session, data: LLMProviderCreate) -> LLMProviderResponse:
    provider = LLMProvider(
        name=data.name,
        provider_type=data.provider_type,
        base_url=data.base_url,
        api_key=data.api_key,
        status=data.status,
        remark=data.remark,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return _provider_to_response(provider)


def get_provider_list(
    db: Session,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
) -> list[LLMProviderResponse]:
    query = db.query(LLMProvider).filter(LLMProvider.is_deleted == False)
    if keyword:
        query = query.filter(LLMProvider.name.contains(keyword))
    if status:
        query = query.filter(LLMProvider.status == status)
    providers = query.order_by(LLMProvider.id.asc()).all()
    return [_provider_to_response(p) for p in providers]


def get_provider_by_id(db: Session, provider_id: int) -> Optional[LLMProvider]:
    return db.query(LLMProvider).filter(
        LLMProvider.id == provider_id,
        LLMProvider.is_deleted == False,
    ).first()


def update_provider(db: Session, provider_id: int, data: LLMProviderUpdate) -> Optional[LLMProviderResponse]:
    provider = get_provider_by_id(db, provider_id)
    if not provider:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data and (update_data["api_key"] is None or update_data["api_key"] == ""):
        del update_data["api_key"]

    for key, value in update_data.items():
        setattr(provider, key, value)

    db.commit()
    db.refresh(provider)
    return _provider_to_response(provider)


def delete_provider(db: Session, provider_id: int) -> bool:
    provider = get_provider_by_id(db, provider_id)
    if not provider:
        return False
    provider.is_deleted = True
    db.commit()
    return True


# ── Model CRUD ──

def create_model(db: Session, data: LLMModelCreate) -> LLMModelResponse:
    provider = get_provider_by_id(db, data.provider_id)
    if not provider:
        raise HTTPException(status_code=400, detail="供应商不存在或已删除")

    model = LLMModel(
        provider_id=data.provider_id,
        model_name=data.model_name,
        display_name=data.display_name,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
        timeout_seconds=data.timeout_seconds,
        status=data.status,
        remark=data.remark,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return _model_to_response(db, model)


def get_model_list(
    db: Session,
    provider_id: Optional[int] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
) -> list[LLMModelResponse]:
    query = db.query(LLMModel).filter(LLMModel.is_deleted == False)
    if provider_id is not None:
        query = query.filter(LLMModel.provider_id == provider_id)
    if keyword:
        query = query.filter(LLMModel.model_name.contains(keyword))
    if status:
        query = query.filter(LLMModel.status == status)
    models = query.order_by(LLMModel.id.asc()).all()
    return [_model_to_response(db, m) for m in models]


def get_model_by_id(db: Session, model_id: int) -> Optional[LLMModel]:
    return db.query(LLMModel).filter(
        LLMModel.id == model_id,
        LLMModel.is_deleted == False,
    ).first()


def update_model(db: Session, model_id: int, data: LLMModelUpdate) -> Optional[LLMModelResponse]:
    model = get_model_by_id(db, model_id)
    if not model:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "provider_id" in update_data and update_data["provider_id"] is not None:
        provider = get_provider_by_id(db, update_data["provider_id"])
        if not provider:
            raise HTTPException(status_code=400, detail="供应商不存在或已删除")

    for key, value in update_data.items():
        setattr(model, key, value)

    db.commit()
    db.refresh(model)
    return _model_to_response(db, model)


def delete_model(db: Session, model_id: int) -> bool:
    model = get_model_by_id(db, model_id)
    if not model:
        return False
    model.is_deleted = True
    db.commit()
    return True


# ── Scene Config ──

def init_default_scene_configs(db: Session) -> None:
    existing_codes = {row[0] for row in db.query(LLMSceneConfig.scene_code).all()}
    usable_models = (
        db.query(LLMModel)
        .join(LLMProvider, LLMProvider.id == LLMModel.provider_id)
        .filter(
            LLMModel.status == "active",
            LLMModel.is_deleted.is_(False),
            LLMProvider.status == "active",
            LLMProvider.is_deleted.is_(False),
        )
        .all()
    )
    added = False
    for cfg in DEFAULT_SCENE_CONFIGS:
        if cfg["scene_code"] not in existing_codes:
            values = dict(cfg)
            # A fresh single-model installation has no meaningful choice to
            # make.  Bind Agent Chat automatically so the first conversation
            # works; with zero/multiple models the admin must choose explicitly.
            if cfg["scene_code"] == "agent_chat" and len(usable_models) == 1:
                values["model_id"] = usable_models[0].id
            db.add(LLMSceneConfig(**values))
            added = True
    if added:
        db.commit()


def get_scene_config_list(db: Session) -> list[LLMSceneConfigResponse]:
    configs = db.query(LLMSceneConfig).order_by(LLMSceneConfig.id.asc()).all()
    return [_scene_config_to_response(db, c) for c in configs]


def get_scene_config_by_code(db: Session, scene_code: str) -> Optional[LLMSceneConfig]:
    return db.query(LLMSceneConfig).filter(
        LLMSceneConfig.scene_code == scene_code,
    ).first()


def get_scene_config_by_id(db: Session, config_id: int) -> Optional[LLMSceneConfig]:
    return db.query(LLMSceneConfig).filter(
        LLMSceneConfig.id == config_id,
    ).first()


def update_scene_config(db: Session, config_id: int, data: LLMSceneConfigUpdate) -> Optional[LLMSceneConfigResponse]:
    config = get_scene_config_by_id(db, config_id)
    if not config:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)

    db.commit()
    db.refresh(config)
    return _scene_config_to_response(db, config)
