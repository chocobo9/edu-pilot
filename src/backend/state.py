from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum


@dataclass
class UserProfile:
    gpa: float | None = None
    university: str | None = None
    major: str | None = None
    language_scores: dict | None = None
    target_country: str | None = None
    target_programs: list[str] | None = None
    target_intake: str | None = None
    budget: str | None = None
    work_experience: str | None = None
    nationality: str | None = None

    def completeness(self) -> dict[str, bool]:
        return {f.name: getattr(self, f.name) is not None for f in fields(self)}

    def missing_fields(self) -> list[str]:
        return [k for k, v in self.completeness().items() if not v]

    def filled_fields(self) -> dict[str, object]:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None}


class Intent(Enum):
    INTAKE = "intake"
    SCHOOL_MATCH = "school_match"
    VISA_ADVISORY = "visa_advisory"
    TIMELINE_PLANNING = "timeline"
    GENERAL_QA = "general_qa"


VISA_KEYWORDS = {
    "visa", "permit", "immigration", "work permit", "pgwp", "study permit", "eligibility", "ircc",
    "f1", "f-1", "j1", "j-1", "opt", "cpt",
    "签证", "移民", "工签", "学签", "工作许可", "居留",
}
TIMELINE_KEYWORDS = {
    "timeline", "deadline", "when to apply", "schedule", "calendar", "when should",
    "时间线", "时间表", "截止", "来得及", "什么时候申请", "申请时间",
}
SCHOOL_KEYWORDS = {
    "school", "program", "university", "admission", "tuition", "recommend", "compare", "apply", "college",
    "ivy", "ivy league",
    "学校", "大学", "项目", "申请", "录取", "藤校", "推荐", "选校", "专业",
}


def _keyword_match(text: str, keywords: set[str]) -> bool:
    """Match keywords in text. Uses word boundaries for short ASCII keywords to avoid substring false positives."""
    import re
    for kw in keywords:
        if kw.isascii() and len(kw) <= 4:
            if re.search(r'\b' + re.escape(kw) + r'\b', text):
                return True
        elif kw in text:
            return True
    return False


def classify_intent(user_message: str, current_route: str | None = None) -> Intent:
    """Keyword-based intent classification. No LLM call."""
    lower = user_message.lower()

    if _keyword_match(lower, VISA_KEYWORDS):
        return Intent.VISA_ADVISORY
    if _keyword_match(lower, TIMELINE_KEYWORDS):
        return Intent.TIMELINE_PLANNING
    if _keyword_match(lower, SCHOOL_KEYWORDS):
        return Intent.SCHOOL_MATCH

    if current_route:
        for intent in Intent:
            if intent.value == current_route:
                return intent

    return Intent.GENERAL_QA


CORE_FIELDS = {"gpa", "language_scores", "target_country", "nationality"}


def _core_missing(profile: UserProfile) -> int:
    """Count how many core fields are still missing."""
    return sum(1 for f in CORE_FIELDS if getattr(profile, f) is None)


def determine_route(profile: UserProfile, intent: Intent) -> str:
    """Deterministic routing based on core profile completeness and intent."""
    if intent == Intent.INTAKE or _core_missing(profile) > 2:
        return "intake"
    return intent.value


BASE_SYSTEM_PROMPT = (
    "You are EduPilot, a study-abroad advisory assistant. "
    "Help students with program selection, visa guidance, and application planning. "
    "Be concise and helpful. "
    "IMPORTANT: Only present data returned by your tools. "
    "Never invent, fabricate, or guess programs, schools, deadlines, or requirements. "
    "If a tool returns no results, say so — do not fill in with made-up data."
)

ROUTE_PROMPTS: dict[str, str] = {
    "intake": (
        "You are in INTAKE mode. Your goal is to collect the user's background information.\n"
        "Ask about these fields naturally (don't list them all at once):\n"
        "- GPA and current/previous university\n"
        "- Language test scores (IELTS/TOEFL)\n"
        "- Target country and programs of interest\n"
        "- Budget constraints\n"
        "- Work experience (if any)\n"
        "- Nationality (needed for visa advice)\n\n"
        "Ask 1-2 questions per turn. Be conversational, not interrogative.\n"
        "When the user provides information, use the update_user_profile tool to save it.\n"
        "When you have enough information (at least: GPA, language scores, target country, nationality),\n"
        "transition naturally to giving recommendations."
    ),
    "school_match": (
        "You are in SCHOOL MATCHING mode. The user's profile is available.\n"
        "Use the query_programs tool to find matching programs.\n"
        "Compare 2-3 programs and explain trade-offs (tuition, ranking, location, requirements).\n"
        "If the user's profile is missing key fields, ask for them before searching."
    ),
    "visa_advisory": (
        "You are in VISA ADVISORY mode.\n"
        "Use the check_visa_eligibility tool with the user's nationality and destination.\n"
        "Explain the process step-by-step. Mention processing times and required documents.\n"
        "If applicable, mention special streams (e.g., Canada SDS for Chinese students)."
    ),
    "timeline": (
        "You are in TIMELINE PLANNING mode.\n"
        "Use the calculate_timeline tool to generate a timeline.\n"
        "Present deadlines clearly. Flag any urgent items.\n"
        "Account for: language test prep, application deadlines, visa processing, accommodation."
    ),
    "general_qa": (
        "You are in GENERAL Q&A mode.\n"
        "Answer the user's question based on your knowledge of study abroad processes.\n"
        "If the question requires specific program or visa data, use the appropriate tool."
    ),
}

ROUTE_TOOLS: dict[str, list[str]] = {
    "intake": ["update_user_profile", "get_user_profile", "query_programs", "check_visa_eligibility", "calculate_timeline", "save_note"],
    "school_match": ["query_programs", "get_user_profile", "update_user_profile", "save_note"],
    "visa_advisory": ["check_visa_eligibility", "get_user_profile", "update_user_profile", "save_note"],
    "timeline": ["calculate_timeline", "get_user_profile", "update_user_profile", "save_note"],
    "general_qa": ["save_note"],
}

ROUTE_SEARCH_KEYWORDS: dict[str, list[str]] = {
    "intake": [],
    "school_match": ["school", "program", "university", "admission", "tuition"],
    "visa_advisory": ["visa", "permit", "immigration", "study permit"],
    "timeline": ["timeline", "deadline", "schedule", "calendar"],
    "general_qa": [],
}


def _format_profile(profile: UserProfile) -> str:
    filled = profile.filled_fields()
    if not filled:
        return "No information collected yet."

    lines = []
    for field, value in filled.items():
        label = field.replace("_", " ").title()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def build_system_prompt(
    profile: UserProfile,
    route: str,
    notes: list | None = None,
    summaries: list[str] | None = None,
) -> str:
    """Assemble dynamic system prompt from base + profile + route + memory context."""
    sections = [BASE_SYSTEM_PROMPT]

    profile_section = _format_profile(profile)
    sections.append(f"\n## Known Student Information\n{profile_section}")

    if summaries:
        summary_text = "\n".join(f"- {s}" for s in summaries)
        sections.append(f"\n## Previous Session Context\n{summary_text}")

    if notes:
        note_lines = []
        for n in notes:
            cat = n.category if hasattr(n, "category") else "note"
            content = n.content if hasattr(n, "content") else str(n)
            note_lines.append(f"- [{cat}] {content}")
        sections.append(f"\n## Notes About This Student\n" + "\n".join(note_lines))

    route_prompt = ROUTE_PROMPTS.get(route, ROUTE_PROMPTS["general_qa"])
    sections.append(f"\n## Current Mode\n{route_prompt}")

    return "\n".join(sections)
