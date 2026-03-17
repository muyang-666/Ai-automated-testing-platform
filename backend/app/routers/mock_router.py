from fastapi import APIRouter

router = APIRouter(prefix="/mock", tags=["Mock"])


@router.post("/login", summary="本地模拟登录接口")
def mock_login():
    return {
        "code": 200,
        "message": "success",
        "username": "test"
    }