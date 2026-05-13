"""Lightweight skill loader for LLM system prompts.

Scans skills/ subdirectories for SKILL.md files with YAML frontmatter,
caches content, and provides module-level load_skill() accessor.
"""

from __future__ import annotations

import re
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML frontmatter from body. Returns (metadata_dict, body)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    raw_yaml = match.group(1)
    body = text[match.end():]

    metadata: dict[str, str] = {}
    for line in raw_yaml.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    return metadata, body


class SkillLoader:
    """Loads SKILL.md files from the skills directory."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._dir = skills_dir or _SKILLS_DIR
        self._skills: dict[str, tuple[dict[str, str], str]] = {}
        self._scan()

    def _scan(self) -> None:
        for skill_file in self._dir.rglob("SKILL.md"):
            text = skill_file.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(text)
            name = meta.get("name") or skill_file.parent.name
            self._skills[name] = (meta, body.strip())

    def get_descriptions(self) -> str:
        lines: list[str] = []
        for name, (meta, _) in sorted(self._skills.items()):
            desc = meta.get("description", "")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def get_content(self, name: str) -> str:
        if name not in self._skills:
            raise FileNotFoundError(f"Skill not found: {name}")
        return self._skills[name][1]


_singleton: SkillLoader | None = None


def _get_loader() -> SkillLoader:
    global _singleton
    if _singleton is None:
        _singleton = SkillLoader()
    return _singleton


def load_skill(name: str) -> str:
    return _get_loader().get_content(name)
