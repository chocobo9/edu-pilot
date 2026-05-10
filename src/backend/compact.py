from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

TOKEN_THRESHOLD = 12000
KEEP_RECENT = 6
HARD_CAP_MESSAGES = 40


@dataclass
class CompactionRecord:
    original_turn_count: int
    original_message_count: int
    compacted_message_count: int
    summary: str
    timestamp: str
    transcript_path: str


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: ~4 chars per token."""
    return sum(len(str(m)) for m in messages) // 4


def save_transcript(messages: list[dict], user_id: str, turn_count: int) -> str:
    """Save full message history to disk. Returns path, empty string on failure."""
    try:
        transcript_dir = os.path.join("data", "transcripts")
        os.makedirs(transcript_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{user_id}_{turn_count}_{ts}.json"
        path = os.path.join(transcript_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return ""


def _find_safe_split(messages: list[dict], keep_recent: int = KEEP_RECENT) -> int:
    """Find a split point that never breaks tool_call/tool_result pairs."""
    if len(messages) <= keep_recent:
        return 0
    split = len(messages) - keep_recent
    while split > 0 and messages[split].get("role") == "tool":
        split -= 1
    if split > 0 and messages[split].get("tool_calls"):
        pass
    return max(split, 0)


def compact_messages(
    messages: list[dict], llm, keep_recent: int = KEEP_RECENT,
) -> tuple[list[dict], str]:
    """Summarize old messages, keep recent ones. Returns (new_messages, summary)."""
    split = _find_safe_split(messages, keep_recent)
    if split == 0:
        return messages, ""

    old = messages[:split]
    recent = messages[split:]

    try:
        user_assistant = [m for m in old if m.get("role") in ("user", "assistant") and m.get("content")]
        if not user_assistant:
            return messages, ""

        response = llm.chat([
            {"role": "system", "content": (
                "Summarize this study-abroad advisory conversation excerpt in 3-5 sentences. "
                "Capture: what the student asked, what was recommended, key decisions made, "
                "and any tool results mentioned. Be specific (include school names, visa types, etc)."
            )},
            {"role": "user", "content": json.dumps(user_assistant, ensure_ascii=False)},
        ])
        summary = response.content or ""
        if not summary:
            raise ValueError("Empty summary")

        compacted = [
            {"role": "system", "content": f"[Conversation summary - earlier turns]\n{summary}"},
            *recent,
        ]
        return compacted, summary

    except Exception:
        if len(messages) > HARD_CAP_MESSAGES:
            safe_split = _find_safe_split(messages, keep_recent)
            return [
                {"role": "system", "content": "[Earlier conversation truncated]"},
                *messages[safe_split:],
            ], ""
        return messages, ""
