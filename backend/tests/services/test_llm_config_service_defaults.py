from app.models.llm.llm_model import LLMModel
from app.models.llm.llm_provider import LLMProvider
from app.models.llm.llm_scene_config import LLMSceneConfig
from app.services.llm.llm_config_service import init_default_scene_configs


def test_agent_chat_default_auto_binds_the_only_usable_model(db_session):
    provider = LLMProvider(
        name="Only Provider", provider_type="openai_compatible",
        base_url="https://example.invalid", api_key="synthetic-key",
        status="active", is_deleted=False,
    )
    db_session.add(provider)
    db_session.flush()
    model = LLMModel(
        provider_id=provider.id, model_name="only-model", status="active",
        is_deleted=False,
    )
    db_session.add(model)
    db_session.commit()

    init_default_scene_configs(db_session)

    scene = db_session.query(LLMSceneConfig).filter(
        LLMSceneConfig.scene_code == "agent_chat",
    ).one()
    assert scene.scene_name == "Agent 对话"
    assert scene.enabled is True
    assert scene.model_id == model.id


def test_agent_chat_default_does_not_guess_between_multiple_models(db_session):
    provider = LLMProvider(
        name="Provider", provider_type="openai_compatible",
        base_url="https://example.invalid", api_key="synthetic-key",
        status="active", is_deleted=False,
    )
    db_session.add(provider)
    db_session.flush()
    db_session.add_all([
        LLMModel(provider_id=provider.id, model_name="model-a", status="active", is_deleted=False),
        LLMModel(provider_id=provider.id, model_name="model-b", status="active", is_deleted=False),
    ])
    db_session.commit()

    init_default_scene_configs(db_session)

    scene = db_session.query(LLMSceneConfig).filter(
        LLMSceneConfig.scene_code == "agent_chat",
    ).one()
    assert scene.model_id is None
