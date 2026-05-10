from __future__ import annotations

from datetime import date, timedelta

from src.backend.tools import ToolRegistry, ToolSpec

INTAKE_MONTHS = {
    "fall": 9,
    "winter": 1,
    "spring": 5,
}

MILESTONES_BEFORE_INTAKE = [
    (-12, "Start researching programs and requirements"),
    (-10, "Take language test (IELTS/TOEFL)"),
    (-8, "Prepare application materials (SOP, references, transcripts)"),
    (-6, "Submit applications (check individual deadlines)"),
    (-4, "Receive admission decisions"),
    (-3, "Accept offer and pay deposit"),
    (-3, "Apply for study permit / visa"),
    (-2, "Apply for scholarships and funding"),
    (-1, "Arrange housing and book flights"),
    (0, "Arrive and begin orientation"),
]


def _parse_intake(target_intake: str) -> date | None:
    """Parse 'Fall 2027' or '2027 Fall' into a date."""
    parts = target_intake.strip().split()
    if len(parts) != 2:
        return None

    season, year = (parts[0].lower(), parts[1]) if not parts[0].isdigit() else (parts[1].lower(), parts[0])

    try:
        year_int = int(year)
    except ValueError:
        return None

    month = INTAKE_MONTHS.get(season)
    if month is None:
        return None

    return date(year_int, month, 1)


def calculate_timeline(
    target_intake: str,
    current_date: str | None = None,
) -> dict:
    """Generate an application timeline with key deadlines."""
    intake_date = _parse_intake(target_intake)
    if intake_date is None:
        return {"error": f"Could not parse intake '{target_intake}'. Use format like 'Fall 2027'."}

    today = date.fromisoformat(current_date) if current_date else date.today()

    milestones = []
    for months_offset, description in MILESTONES_BEFORE_INTAKE:
        target = intake_date + timedelta(days=months_offset * 30)
        status = "completed" if target < today else ("upcoming" if target <= today + timedelta(days=60) else "future")
        milestones.append({
            "date": target.isoformat(),
            "description": description,
            "status": status,
        })

    return {
        "target_intake": target_intake,
        "intake_date": intake_date.isoformat(),
        "generated_on": today.isoformat(),
        "milestones": milestones,
    }


def register_timeline_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="calculate_timeline",
        description=(
            "Generate an application timeline with key deadlines. "
            "Use when user asks about timeline, when to apply, or next steps."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target_intake": {
                    "type": "string",
                    "description": "Target intake period (e.g., 'Fall 2027')",
                },
                "current_date": {
                    "type": "string",
                    "description": "Today's date in YYYY-MM-DD format (optional)",
                },
            },
            "required": ["target_intake"],
        },
        handler=calculate_timeline,
    ))
