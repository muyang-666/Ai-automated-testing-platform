from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.parameter_file import ParameterFileResponse, ParameterFileUpdate

router = APIRouter(prefix="/parameter-file", tags=["ParameterFile"])

# 固定只操作这一个文件，避免前端乱改别的文件
PARAMETER_FILE_PATH = Path(__file__).resolve().parent.parent / "utils" / "parameter.py"


@router.get("", response_model=ParameterFileResponse, summary="读取参数文件")
def get_parameter_file():
    if not PARAMETER_FILE_PATH.exists():
        # 文件不存在时，先返回空内容，方便前端直接编辑
        return {"content": ""}

    content = PARAMETER_FILE_PATH.read_text(encoding="utf-8")
    return {"content": content}


@router.put("", response_model=ParameterFileResponse, summary="保存参数文件")
def update_parameter_file(data: ParameterFileUpdate):
    content = data.content or ""

    # 保存前做一次 Python 语法校验，避免把 parameter.py 写坏
    try:
        compile(content, str(PARAMETER_FILE_PATH), "exec")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"参数文件语法错误: {str(e)}")

    PARAMETER_FILE_PATH.write_text(content, encoding="utf-8")
    return {"content": content}