from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.llm_config import (
    LLMModelCreate,
    LLMModelResponse,
    LLMModelUpdate,
    LLMProviderCreate,
    LLMProviderResponse,
    LLMProviderUpdate,
    LLMSceneConfigResponse,
    LLMSceneConfigUpdate,
    LLMTestRequest,
    LLMTestResponse,
)
from app.services.llm_client_service import test_llm_model
from app.services.llm_config_service import (
    create_model,
    create_provider,
    delete_model,
    delete_provider,
    get_model_by_id,
    get_model_list,
    get_provider_by_id,
    get_provider_list,
    get_scene_config_list,
    update_model,
    update_provider,
    update_scene_config,
)

router = APIRouter(prefix="/llm-config", tags=["LLM Config"])


# ── Provider ──

@router.post("/providers", response_model=LLMProviderResponse, summary="创建供应商")
def create_provider_api(data: LLMProviderCreate, db: Session = Depends(get_db)):
    return create_provider(db, data)


@router.get("/providers", response_model=list[LLMProviderResponse], summary="查询供应商列表")
def list_providers(
    keyword: Optional[str] = Query(default=None, description="按名称搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_provider_list(db, keyword=keyword, status=status)


@router.get("/providers/{provider_id}", response_model=LLMProviderResponse, summary="查询供应商详情")
def get_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = get_provider_by_id(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="供应商不存在")
    from app.services.llm_config_service import _provider_to_response
    return _provider_to_response(provider)


@router.put("/providers/{provider_id}", response_model=LLMProviderResponse, summary="修改供应商")
def update_provider_api(provider_id: int, data: LLMProviderUpdate, db: Session = Depends(get_db)):
    result = update_provider(db, provider_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return result


@router.delete("/providers/{provider_id}", summary="删除供应商")
def delete_provider_api(provider_id: int, db: Session = Depends(get_db)):
    success = delete_provider(db, provider_id)
    if not success:
        raise HTTPException(status_code=404, detail="供应商不存在")
    return {"message": "供应商删除成功"}


# ── Model ──

@router.post("/models", response_model=LLMModelResponse, summary="创建模型")
def create_model_api(data: LLMModelCreate, db: Session = Depends(get_db)):
    return create_model(db, data)


@router.get("/models", response_model=list[LLMModelResponse], summary="查询模型列表")
def list_models(
    provider_id: Optional[int] = Query(default=None, description="按供应商筛选"),
    keyword: Optional[str] = Query(default=None, description="按模型名搜索"),
    status: Optional[str] = Query(default=None, description="按状态筛选"),
    db: Session = Depends(get_db),
):
    return get_model_list(db, provider_id=provider_id, keyword=keyword, status=status)


@router.get("/models/{model_id}", response_model=LLMModelResponse, summary="查询模型详情")
def get_model(model_id: int, db: Session = Depends(get_db)):
    model = get_model_by_id(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    from app.services.llm_config_service import _model_to_response
    return _model_to_response(db, model)


@router.put("/models/{model_id}", response_model=LLMModelResponse, summary="修改模型")
def update_model_api(model_id: int, data: LLMModelUpdate, db: Session = Depends(get_db)):
    result = update_model(db, model_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="模型不存在")
    return result


@router.delete("/models/{model_id}", summary="删除模型")
def delete_model_api(model_id: int, db: Session = Depends(get_db)):
    success = delete_model(db, model_id)
    if not success:
        raise HTTPException(status_code=404, detail="模型不存在")
    return {"message": "模型删除成功"}


# ── Scene Config ──

@router.get("/scenes", response_model=list[LLMSceneConfigResponse], summary="查询业务场景配置")
def list_scene_configs(db: Session = Depends(get_db)):
    return get_scene_config_list(db)


@router.put("/scenes/{config_id}", response_model=LLMSceneConfigResponse, summary="修改业务场景配置")
def update_scene_config_api(config_id: int, data: LLMSceneConfigUpdate, db: Session = Depends(get_db)):
    result = update_scene_config(db, config_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="业务场景配置不存在")
    return result


# ── Test ──

@router.post("/models/{model_id}/test", response_model=LLMTestResponse, summary="测试模型连接")
def test_model_api(model_id: int, data: LLMTestRequest = LLMTestRequest(), db: Session = Depends(get_db)):
    return test_llm_model(db, model_id, prompt=data.prompt)
