"""Small allowlisted Markdown Skill catalog for P08."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

MAX_SKILL_BYTES = 32 * 1024
_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    version: str
    description: str
    content: str
    sha256: str

    def summary(self) -> dict:
        return {"name": self.name, "version": self.version,
                "description": self.description, "sha256": self.sha256}


class SkillCatalog:
    def __init__(self, root: Path, names: tuple[str, ...] = ("test-design",)):
        self.root = root.resolve()
        self._skills: dict[str, SkillDefinition] = {}
        for name in names:
            if not name or any(char not in _NAME_CHARS for char in name):
                raise ValueError("invalid skill name")
            path = (self.root / name / "SKILL.md").resolve()
            if self.root not in path.parents or path.name != "SKILL.md":
                raise ValueError("skill path escapes catalog root")
            raw = path.read_bytes()
            if not raw or len(raw) > MAX_SKILL_BYTES:
                raise ValueError("skill file size invalid")
            content = raw.decode("utf-8")
            meta = _frontmatter(content)
            if meta.get("name") != name or not meta.get("version") or not meta.get("description"):
                raise ValueError("skill frontmatter invalid")
            if name in self._skills:
                raise ValueError("duplicate skill name")
            self._skills[name] = SkillDefinition(name=name, version=meta["version"],
                description=meta["description"], content=content,
                sha256=hashlib.sha256(raw).hexdigest())

    def list(self) -> list[dict]:
        return [self._skills[name].summary() for name in sorted(self._skills)]

    def load(self, name: str) -> SkillDefinition:
        if name not in self._skills:
            raise KeyError("unknown skill")
        return self._skills[name]


def _frontmatter(content: str) -> dict[str, str]:
    lines = content.splitlines()
    if len(lines) < 4 or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return result
        key, separator, value = line.partition(":")
        if not separator or key.strip() in result:
            return {}
        result[key.strip()] = value.strip().strip('"')
    return {}


@lru_cache(maxsize=1)
def default_skill_catalog() -> SkillCatalog:
    backend_root = Path(__file__).resolve().parents[3]
    return SkillCatalog(backend_root / "skills")


def skill_system_summary() -> str:
    rows = default_skill_catalog().list()
    return "Available Skills (load with load_skill when relevant):\n" + "\n".join(
        f"- {row['name']} v{row['version']} [{row['sha256'][:12]}]: {row['description']}"
        for row in rows
    )
