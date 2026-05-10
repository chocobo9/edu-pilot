from __future__ import annotations

import os

from src.backend.tools import ToolRegistry, ToolSpec

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")

_HARDCODED_VISA_RULES: dict[str, dict] = {
    "canada": {
        "study_permit": {
            "documents": ["acceptance_letter", "proof_of_identity", "proof_of_funds", "language_test_results", "statement_of_purpose"],
            "proof_of_funds": {"tuition": "first year", "living_cad": 20635},
            "work_rights": {"on_campus": "20 hours/week during semester", "off_campus": "20 hours/week with valid study permit", "coop": "requires co-op work permit"},
            "pgwp": {"eligible": True, "duration": "up to 3 years depending on program length"},
        },
        "nationalities": {
            "chinese": {"processing_weeks": "4-8", "special_streams": [{"name": "Student Direct Stream (SDS)", "benefit": "faster processing", "requirements": ["GIC of 20635 CAD", "IELTS 6.0+ overall"]}]},
            "indian": {"processing_weeks": "4-8", "special_streams": [{"name": "Student Direct Stream (SDS)", "benefit": "faster processing", "requirements": ["GIC of 20635 CAD", "IELTS 6.0+ overall"]}]},
            "korean": {"processing_weeks": "4-8", "special_streams": []},
        },
        "default_processing_weeks": "8-16",
    },
}


def _load_visa_rules() -> dict[str, dict]:
    path = os.path.join(_DATA_DIR, "visa_rules.yaml")
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"[WARN] {path} not found, using hardcoded data")
        return _HARDCODED_VISA_RULES
    except ImportError:
        print("[WARN] pyyaml not installed, using hardcoded data")
        return _HARDCODED_VISA_RULES


VISA_RULES: dict[str, dict] = _load_visa_rules()


def check_visa_eligibility(
    nationality: str,
    destination_country: str,
    program_type: str = "master",
) -> dict:
    """Rule-based visa path determination."""
    country_key = destination_country.strip().lower()
    nationality_key = nationality.strip().lower()

    if country_key not in VISA_RULES:
        return {"error": f"No visa rules available for '{destination_country}'"}

    rules = VISA_RULES[country_key]
    permit = rules["study_permit"]

    result: dict = {
        "destination": destination_country,
        "nationality": nationality,
        "program_type": program_type,
        "visa_type": "study_permit",
        "documents_required": permit["documents"],
        "proof_of_funds": permit["proof_of_funds"],
        "work_rights": permit["work_rights"],
        "post_graduation": permit["pgwp"],
    }

    nat_rules = rules.get("nationalities", {}).get(nationality_key)
    if nat_rules:
        result["processing_time_weeks"] = nat_rules["processing_weeks"]
        result["special_streams"] = nat_rules["special_streams"]
    else:
        result["processing_time_weeks"] = rules["default_processing_weeks"]
        result["special_streams"] = []

    return result


def register_visa_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="check_visa_eligibility",
        description=(
            "Check visa requirements and processing timeline. "
            "Use when user asks about visa, work permit, or immigration."
        ),
        parameters={
            "type": "object",
            "properties": {
                "nationality": {
                    "type": "string",
                    "description": "User's nationality (e.g., 'Chinese', 'Indian')",
                },
                "destination_country": {
                    "type": "string",
                    "description": "Target country (e.g., 'Canada')",
                },
                "program_type": {
                    "type": "string",
                    "enum": ["bachelor", "master", "phd"],
                    "description": "Type of program",
                },
            },
            "required": ["nationality", "destination_country"],
        },
        handler=check_visa_eligibility,
    ))
