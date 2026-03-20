from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.api_case import APICase
from app.models.test_run import TestRun
from app.utils.pytest_runner import run_pytest_file

# 执行测试 核心代码逻辑
def execute_case_test(db: Session, case_id: int):
    # 1.查测试用例是否存在
    api_case = db.query(APICase).filter(APICase.id == case_id).first()
    if not api_case:
        raise ValueError("测试用例不存在")

    # 2.拼出测试文件路径，并检查文件是否存在
    test_file_path = Path(__file__).resolve().parent.parent / "tests_generated" / f"test_case_{case_id}.py"
    if not test_file_path.exists():
        raise FileNotFoundError(f"测试文件不存在: {test_file_path}")

    # 3.先创建一条 TestRun 执行记录
    test_run = TestRun(  # 创建 ORM 对象
        case_id=case_id,
        status="running",
        started_at=datetime.now(),
    )
    db.add(test_run) # 加入会话
    db.commit()      # 真正写入数据库
    db.refresh(test_run)  # 把数据库生成的新值同步回来，比如 test_run.id

    try:
        # 4.真正运行 pytest
        run_result = run_pytest_file(str(test_file_path))
        # 5.把 pytest 结果写回 TestRun。这段是把执行结果灌回数据库。
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

        # 6.返回给前端
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

    # 执行中失败：pytest 报错、断言失败、运行异常
    except Exception as e:
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