"""Prompt 资源加载：instructions.md 与 prompts/*.md（版本化文本资源）。"""

from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent


def load_instructions() -> str:
    return (_BASE_DIR / "instructions.md").read_text(encoding="utf-8")


def load_prompt(name: str) -> str:
    """name 形如 analyze_and_plan_v1，读取 prompts/<name>.md。"""
    return (_BASE_DIR / "prompts" / f"{name}.md").read_text(encoding="utf-8")
