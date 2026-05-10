from __future__ import annotations

import json
import os

from src.backend.tools import ToolRegistry, ToolSpec

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")

_HARDCODED_PROGRAMS: list[dict] = [
    {"id": "sfu-bigdata-msc", "university": "Simon Fraser University", "program": "MSc in Big Data", "country": "Canada", "field": "data_science", "gpa_requirement": 3.0, "tuition_annual_cad": 9200, "duration_months": 24, "intake": ["Fall"]},
    {"id": "ubc-cs-msc", "university": "University of British Columbia", "program": "MSc in Computer Science", "country": "Canada", "field": "computer_science", "gpa_requirement": 3.3, "tuition_annual_cad": 9000, "duration_months": 24, "intake": ["Fall", "Spring"]},
    {"id": "uoft-cs-msc", "university": "University of Toronto", "program": "MSc in Computer Science", "country": "Canada", "field": "computer_science", "gpa_requirement": 3.5, "tuition_annual_cad": 23000, "duration_months": 20, "intake": ["Fall"]},
    {"id": "waterloo-ai-mmath", "university": "University of Waterloo", "program": "MMath in Artificial Intelligence", "country": "Canada", "field": "artificial_intelligence", "gpa_requirement": 3.5, "tuition_annual_cad": 11000, "duration_months": 24, "intake": ["Fall", "Winter"]},
    {"id": "mcgill-cs-msc", "university": "McGill University", "program": "MSc in Computer Science", "country": "Canada", "field": "computer_science", "gpa_requirement": 3.3, "tuition_annual_cad": 7600, "duration_months": 24, "intake": ["Fall", "Winter"]},
    {"id": "columbia-cs-ms", "university": "Columbia University", "program": "MS in Computer Science", "country": "United States", "field": "computer_science", "gpa_requirement": 3.5, "tuition_annual_cad": 82000, "duration_months": 18, "intake": ["Fall"], "tags": ["ivy_league"]},
    {"id": "cornell-cs-ms", "university": "Cornell University", "program": "MS in Computer Science", "country": "United States", "field": "computer_science", "gpa_requirement": 3.5, "tuition_annual_cad": 78000, "duration_months": 20, "intake": ["Fall"], "tags": ["ivy_league"]},
    {"id": "upenn-cis-mse", "university": "University of Pennsylvania", "program": "MSE in Computer and Information Science", "country": "United States", "field": "computer_science", "gpa_requirement": 3.5, "tuition_annual_cad": 80000, "duration_months": 20, "intake": ["Fall"], "tags": ["ivy_league"]},
    {"id": "cmu-cs-ms", "university": "Carnegie Mellon University", "program": "MS in Computer Science", "country": "United States", "field": "computer_science", "gpa_requirement": 3.5, "tuition_annual_cad": 75000, "duration_months": 24, "intake": ["Fall"]},
    {"id": "stanford-cs-ms", "university": "Stanford University", "program": "MS in Computer Science", "country": "United States", "field": "computer_science", "gpa_requirement": 3.6, "tuition_annual_cad": 85000, "duration_months": 21, "intake": ["Fall"]},
    {"id": "mit-eecs-ms", "university": "Massachusetts Institute of Technology", "program": "MS in Electrical Engineering and Computer Science", "country": "United States", "field": "computer_science", "gpa_requirement": 3.7, "tuition_annual_cad": 80000, "duration_months": 24, "intake": ["Fall"]},
    {"id": "columbia-ai-ms", "university": "Columbia University", "program": "MS in Computer Science - Machine Learning Track", "country": "United States", "field": "artificial_intelligence", "gpa_requirement": 3.5, "tuition_annual_cad": 82000, "duration_months": 18, "intake": ["Fall"], "tags": ["ivy_league"]},
    {"id": "cmu-ai-ms", "university": "Carnegie Mellon University", "program": "MS in Artificial Intelligence", "country": "United States", "field": "artificial_intelligence", "gpa_requirement": 3.5, "tuition_annual_cad": 75000, "duration_months": 24, "intake": ["Fall"]},
]


def _load_programs() -> list[dict]:
    path = os.path.join(_DATA_DIR, "schools.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARN] {path} not found, using hardcoded data")
        return _HARDCODED_PROGRAMS


PROGRAMS = _load_programs()


def query_programs(
    country: str = "",
    field: str = "",
    max_gpa_req: float | None = None,
    max_tuition: float | None = None,
    tags: list[str] | None = None,
) -> list[dict]:
    """Search the school/program database with optional filters."""
    results = PROGRAMS
    if country:
        results = [p for p in results if p["country"].lower() == country.lower()]
    if field:
        results = [p for p in results if p["field"].lower() == field.lower()]
    if max_gpa_req is not None:
        results = [p for p in results if p["gpa_requirement"] <= max_gpa_req]
    if max_tuition is not None:
        results = [p for p in results if p["tuition_annual_cad"] <= max_tuition]
    if tags:
        results = [p for p in results if any(t in p.get("tags", []) for t in tags)]
    return results


def register_school_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="query_programs",
        description="Search the school/program database. Use when user asks about programs, schools, or admission requirements.",
        parameters={
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Target country (e.g., 'Canada')"},
                "field": {"type": "string", "description": "Field of study (e.g., 'data_science', 'computer_science')"},
                "max_gpa_req": {"type": "number", "description": "Filter programs where GPA requirement <= this value"},
                "max_tuition": {"type": "number", "description": "Max annual tuition in CAD"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags (e.g., ['ivy_league'])"},
            },
            "required": [],
        },
        handler=query_programs,
    ))
