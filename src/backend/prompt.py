from __future__ import annotations

from src.backend.state import UserProfile, _format_profile, get_base_system_prompt, get_route_prompt


class PromptAssembler:
    """Section-based dynamic prompt construction. Pure string concatenation, no I/O."""

    def __init__(self) -> None:
        self._sections: dict[str, str] = {}

    def add_section(self, name: str, content: str) -> None:
        self._sections[name] = content

    def build(self) -> str:
        return "\n".join(self._sections.values())


def assemble_prompt(
    profile: UserProfile,
    route: str,
    notes: list | None = None,
    summaries: list[str] | None = None,
) -> str:
    """Assemble a complete system prompt from profile, route, notes, and summaries."""
    asm = PromptAssembler()

    asm.add_section("role", get_base_system_prompt())

    profile_text = _format_profile(profile)
    asm.add_section("profile", f"\n## Known Student Information\n{profile_text}")

    if summaries:
        summary_lines = "\n".join(f"- {s}" for s in summaries)
        asm.add_section("summaries", f"\n## Previous Session Context\n{summary_lines}")

    if notes:
        note_lines = []
        for n in notes:
            cat = n.category if hasattr(n, "category") else "note"
            content = n.content if hasattr(n, "content") else str(n)
            note_lines.append(f"- [{cat}] {content}")
        asm.add_section("notes", f"\n## Advisor Notes\n" + "\n".join(note_lines))

    try:
        route_prompt = get_route_prompt(route)
    except FileNotFoundError:
        route_prompt = get_route_prompt("general_qa")
    asm.add_section("route", f"\n## Current Mode\n{route_prompt}")

    return asm.build()
