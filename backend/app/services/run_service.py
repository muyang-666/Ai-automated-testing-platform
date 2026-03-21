from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.api_case import APICase
from app.models.test_run import TestRun
from app.utils.file_writer import save_test_code_to_file
from app.utils.pytest_runner import run_pytest_file


def _get_test_file_path(case_id: int) -> Path:
    """
    获取测试文件路径
    """
    return (
        Path(__file__).resolve().parent.parent
        / "tests_generated"
        / f"test_case_{case_id}.py"
    )


def _ensure_test_file_exists(api_case: APICase, case_id: int) -> Path:
    """
    确保测试文件存在
    优先规则：
    1. 如果 tests_generated 目录下已有文件，直接用
    2. 如果没有文件，但数据库 generated_test_code 有内容，则写入文件
    3. 否则报错
    """
    test_file_path = _get_test_file_path(case_id)

    if test_file_path.exists():
        return test_file_path

    generated_code = getattr(api_case, "generated_test_code", None)
    if generated_code and str(generated_code).strip():
        save_test_code_to_file(case_id=case_id, code=generated_code)
        return test_file_path

    raise FileNotFoundError(f"测试文件不存在: {test_file_path}")


# 执行测试 核心代码逻辑
def execute_case_test(db: Session, case_id: int):
    # 1. 查测试用例是否存在
    api_case = db.query(APICase).filter(APICase.id == case_id).first()
    if not api_case:
        raise ValueError("测试用例不存在")

    # 2. 确保测试文件存在
    test_file_path = _ensure_test_file_exists(api_case, case_id)

    # 3. 先创建一条 TestRun 执行记录
    test_run = TestRun(
        case_id=case_id,
        status="running",
        started_at=datetime.now(),
    )
    db.add(test_run)
    db.commit()
    db.refresh(test_run)

    try:
        # 4. 执行 pytest
        run_result = run_pytest_file(str(test_file_path))

        # 5. 回写执行结果
        test_run.status = run_result["status"]
        test_run.result = run_result["result"]
        test_run.total_count = run_result["total_count"]
        test_run.passed_count = run_result["passed_count"]
        test_run.failed_count = run_result["failed_count"]
        test_run.log_content = run_result["log_content"]
        test_run.error_message = run_result["error_message"]
        test_run.response_status_code = run_result.get("response_status_code")
        test_run.response_content = run_result.get("response_content")
        test_run.finished_at = datetime.now()

        db.commit()
        db.refresh(test_run)

        # 6. 返回给前端
        return {
            "run_id": test_run.id,
            "case_id": test_run.case_id,
            "status": test_run.status,
            "result": test_run.result,
            "total_count": test_run.total_count,
            "passed_count": test_run.passed_count,
            "failed_count": test_run.failed_count,
            "log_content": test_run.log_content,
            "error_message": test_run.error_message,
            "response_status_code": test_run.response_status_code,
            "response_content": test_run.response_content,
            "started_at": test_run.started_at,
            "finished_at": test_run.finished_at,
            "message": "测试执行完成",
        }

    except Exception as e:
        # 执行过程中异常，也要落库
        test_run.status = "completed"
        test_run.result = "failed"
        test_run.error_message = str(e)
        test_run.log_content = str(e)
        test_run.finished_at = datetime.now()

        db.commit()
        db.refresh(test_run)

        return {
            "run_id": test_run.id,
            "case_id": test_run.case_id,
            "status": test_run.status,
            "result": test_run.result,
            "total_count": test_run.total_count,
            "passed_count": test_run.passed_count,
            "failed_count": test_run.failed_count,
            "log_content": test_run.log_content,
            "error_message": test_run.error_message,
            "response_status_code": test_run.response_status_code,
            "response_content": test_run.response_content,
            "started_at": test_run.started_at,
            "finished_at": test_run.finished_at,
            "message": "测试执行完成",
        }


# 把 TestRun ORM 对象转成前端容易直接使用的字典
def serialize_test_run(test_run: TestRun):
    return {
        "run_id": test_run.id,
        "case_id": test_run.case_id,
        "status": test_run.status,
        "result": test_run.result,
        "total_count": test_run.total_count,
        "passed_count": test_run.passed_count,
        "failed_count": test_run.failed_count,
        "log_content": test_run.log_content,
        "error_message": test_run.error_message,
        "response_status_code": test_run.response_status_code,
        "response_content": test_run.response_content,
        "started_at": test_run.started_at,
        "finished_at": test_run.finished_at,
    }


# 查询执行记录列表
def get_run_list(db: Session):
    runs = db.query(TestRun).order_by(TestRun.id.desc()).all()
    return [serialize_test_run(run) for run in runs]


# 删除执行记录
def delete_run(db: Session, run_id: int) -> bool:
    test_run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not test_run:
        return False

    db.delete(test_run)
    db.commit()
    return True