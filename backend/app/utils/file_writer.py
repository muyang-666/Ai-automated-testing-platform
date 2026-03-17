from pathlib import Path


def save_test_code_to_file(case_id: int, code: str) -> str:
    base_dir = Path(__file__).resolve().parent.parent
    test_dir = base_dir / "tests_generated"
    test_dir.mkdir(parents=True, exist_ok=True)

    file_path = test_dir / f"test_case_{case_id}.py"
    file_path.write_text(code, encoding="utf-8")

    return str(file_path)