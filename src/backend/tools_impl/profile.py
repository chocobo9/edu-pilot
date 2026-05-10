from __future__ import annotations

import json
from typing import Callable

from src.backend.state import UserProfile
from src.backend.tools import ToolRegistry, ToolSpec

VALID_FIELDS = {f.name for f in __import__("dataclasses").fields(UserProfile)}

def _parse_language_scores(value: str) -> dict | str:
    """Parse language scores: try JSON first, then common formats like 'IELTS 7.0'."""
    try:
        return json.loads(value)
    except (ValueError, json.JSONDecodeError):
        pass
    import re
    m = re.match(r"(?i)(ielts|toefl|duolingo)\s*[:\s]?\s*([\d.]+)", value)
    if m:
        return {m.group(1).lower(): float(m.group(2))}
    return value


FIELD_PARSERS: dict[str, Callable[[str], object]] = {
    "gpa": float,
    "language_scores": _parse_language_scores,
    "target_programs": json.loads,
}


def _parse_field_value(field: str, value: str) -> object:
    parser = FIELD_PARSERS.get(field)
    if parser:
        try:
            return parser(value)
        except (ValueError, json.JSONDecodeError):
            return value
    return value


def register_profile_tools(
    registry: ToolRegistry,
    get_profile: Callable[[], UserProfile],
    set_field: Callable[[str, object], None],
    save_note: Callable[[str, str], str] | None = None,
) -> None:
    """Register get/update profile tools with callback access to live profile."""

    def _get_handler() -> dict:
        return get_profile().filled_fields()

    def _update_handler(field: str, value: str) -> str:
        if field not in VALID_FIELDS:
            return f"Error: Unknown field '{field}'. Valid fields: {', '.join(sorted(VALID_FIELDS))}"
        parsed = _parse_field_value(field, value)
        set_field(field, parsed)
        return f"Updated {field} = {parsed}"

    registry.register(ToolSpec(
        name="get_user_profile",
        description="Retrieve the current user's stored profile. Use to check what information has already been collected.",
        parameters={"type": "object", "properties": {}},
        handler=_get_handler,
    ))

    registry.register(ToolSpec(
        name="update_user_profile",
        description=(
            "Update a specific field in the user's profile. "
            "Use when user provides or corrects background information."
        ),
        parameters={
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": sorted(VALID_FIELDS),
                    "description": "The profile field to update",
                },
                "value": {
                    "type": "string",
                    "description": "The value to set. For gpa: number as string (e.g. '3.5'). For language_scores: JSON like '{\"ielts\": 7.0}' or 'IELTS 7.0'. For target_programs: JSON array like '[\"computer_science\"]'.",
                },
            },
            "required": ["field", "value"],
        },
        handler=_update_handler,
    ))

    if save_note:
        registry.register(ToolSpec(
            name="save_note",
            description=(
                "Save a note about the student's preferences, constraints, or decisions. "
                "Use for information that doesn't fit structured profile fields."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The note content to save",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["preference", "constraint", "context", "decision"],
                        "description": "Category of the note",
                    },
                },
                "required": ["content", "category"],
            },
            handler=save_note,
        ))
