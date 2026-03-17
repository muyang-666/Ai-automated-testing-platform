from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.ai import AICaseGenerateResponse
from app.schemas.ai_analysis import AIAnalysisGenerateResponse, AIAnalysisResponse
from app.services.ai_service import generate_case_test_code
from app.services.analysis_service import generate_ai_analysis, get_ai_analysis_by_run_id

router = APIRouter(prefix="/ai", tags=["AI"])

# 定义了一个 HTTP 接口
@router.post("/generate-case/{case_id}", response_model=AICaseGenerateResponse, summary="AI生成pytest测试用例")
def generate_ai_case(case_id: int, db: Session = Depends(get_db)):
    try:
        # 这一句是整条链的真正入口。把活交给 service
        result = generate_case_test_code(db, case_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 生成测试用例失败: {str(e)}")


@router.post("/analyze/{run_id}", response_model=AIAnalysisGenerateResponse, summary="AI分析pytest失败日志")
def analyze_run_log(run_id: int, db: Session = Depends(get_db)):
    try:
        return generate_ai_analysis(db, run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 日志分析失败: {str(e)}")


@router.get("/analyze/{run_id}", response_model=AIAnalysisResponse, summary="查看AI日志分析结果")
def get_run_analysis(run_id: int, db: Session = Depends(get_db)):
    analysis = get_ai_analysis_by_run_id(db, run_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="未找到对应的 AI 分析结果")
    return analysis