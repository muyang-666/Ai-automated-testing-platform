from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.routers.dependencies import get_current_user
from app.schemas.parameter_file import ParameterFileResponse, ParameterFileUpdate
from app.services.permission_service import require_admin_role

router = APIRouter(prefix="/parameter-file", tags=["ParameterFile"])

# 固定只操作这一个文件，避免前端乱改别的文件
PARAMETER_FILE_PATH = Path(__file__).resolve().parent.parent / "utils" / "parameter.py"


@router.get("", response_model=ParameterFileResponse, summary="读取参数文件")
def get_parameter_file(current_user: User = Depends(get_current_user)):
    if not PARAMETER_FILE_PATH.exists():
        # 文件不存在时，先返回空内容，方便前端直接编辑
        return {"content": ""}

    content = PARAMETER_FILE_PATH.read_text(encoding="utf-8")
    return {"content": content}


@router.put("", response_model=ParameterFileResponse, summary="保存参数文件")
def update_parameter_file(
    data: ParameterFileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin_role(db, current_user)
    content = data.content or ""

    # 保存前做一次 Python 语法校验，避免把 parameter.py 写坏
    try:
        compile(content, str(PARAMETER_FILE_PATH), "exec")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"参数文件语法错误: {str(e)}")

    PARAMETER_FILE_PATH.write_text(content, encoding="utf-8")
    return {"content": content}
