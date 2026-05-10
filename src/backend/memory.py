from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class MemoryEvent:
    user_id: str
    field: str
    value: str
    source_turn: int
    timestamp: str = ""
    confidence: float = 1.0


@dataclass
class Note:
    id: int | None
    user_id: str
    content: str
    category: str
    source_turn: int
    timestamp: str = ""


class MemoryStore:
    """SQLite-backed persistent memory for user profiles, notes, events, and summaries."""

    def __init__(self, db_path: str = "data/edupilot.db") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL,
                source_turn INTEGER,
                confidence REAL DEFAULT 1.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                source_turn INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                turn_count INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    def save_profile(self, user_id: str, profile) -> None:
        """UPSERT profile as JSON. Stores only filled fields."""
        from src.backend.state import UserProfile
        profile_data = profile.filled_fields() if isinstance(profile, UserProfile) else {}
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO user_profiles (user_id, profile_json, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET profile_json = ?, updated_at = ?""",
            (user_id, json.dumps(profile_data, ensure_ascii=False), now, now,
             json.dumps(profile_data, ensure_ascii=False), now),
        )
        self._conn.commit()
        self._dump_debug(user_id)

    def load_profile(self, user_id: str):
        """Load profile from SQLite. Returns UserProfile or None."""
        from src.backend.state import UserProfile
        from dataclasses import fields
        row = self._conn.execute(
            "SELECT profile_json FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["profile_json"])
        profile = UserProfile()
        for f in fields(UserProfile):
            if f.name in data and data[f.name] is not None:
                setattr(profile, f.name, data[f.name])
        return profile

    def log_event(self, event: MemoryEvent) -> None:
        """Insert an audit log entry into memory_events."""
        self._conn.execute(
            """INSERT INTO memory_events (user_id, field, value, source_turn, confidence, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event.user_id, event.field, event.value, event.source_turn,
             event.confidence, event.timestamp or datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def add_note(self, user_id: str, content: str, category: str, source_turn: int) -> None:
        """Insert a free-text note."""
        self._conn.execute(
            """INSERT INTO user_notes (user_id, content, category, source_turn)
               VALUES (?, ?, ?, ?)""",
            (user_id, content, category, source_turn),
        )
        self._conn.commit()
        self._dump_debug(user_id)

    def load_notes(self, user_id: str, limit: int = 20) -> list[Note]:
        """Load recent notes for a user."""
        rows = self._conn.execute(
            """SELECT id, user_id, content, category, source_turn, timestamp
               FROM user_notes WHERE user_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [
            Note(
                id=r["id"], user_id=r["user_id"], content=r["content"],
                category=r["category"], source_turn=r["source_turn"],
                timestamp=r["timestamp"] or "",
            )
            for r in rows
        ]

    def delete_notes(self, note_ids: list[int]) -> None:
        """Delete notes by their IDs."""
        if not note_ids:
            return
        placeholders = ",".join("?" for _ in note_ids)
        self._conn.execute(
            f"DELETE FROM user_notes WHERE id IN ({placeholders})", note_ids
        )
        self._conn.commit()

    def save_summary(self, user_id: str, session_id: str, summary: str, turn_count: int) -> None:
        """Save a conversation summary."""
        self._conn.execute(
            """INSERT INTO conversation_summaries (user_id, session_id, summary, turn_count)
               VALUES (?, ?, ?, ?)""",
            (user_id, session_id, summary, turn_count),
        )
        self._conn.commit()

    def search_summaries(self, user_id: str, keywords: list[str], limit: int = 3) -> list[str]:
        """Search summaries by keyword (SQL LIKE)."""
        if not keywords:
            return []
        conditions = " OR ".join("summary LIKE ?" for _ in keywords)
        params = [user_id] + [f"%{kw}%" for kw in keywords] + [limit]
        rows = self._conn.execute(
            f"""SELECT summary FROM conversation_summaries
                WHERE user_id = ? AND ({conditions})
                ORDER BY timestamp DESC LIMIT ?""",
            params,
        ).fetchall()
        return [r["summary"] for r in rows]

    def load_recent_summaries(self, user_id: str, limit: int = 2) -> list[str]:
        """Load the most recent summaries regardless of content."""
        rows = self._conn.execute(
            """SELECT summary FROM conversation_summaries
               WHERE user_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [r["summary"] for r in rows]

    def dream(self, user_id: str, session_summary: str, llm) -> None:
        """Post-session memory consolidation. Deduplicates notes, upgrades profile."""
        try:
            notes = self.load_notes(user_id, limit=100)
            profile = self.load_profile(user_id)
            if not notes:
                return

            prompt = (
                "Review these notes and profile for a study-abroad student. Return JSON:\n"
                '{"notes_to_delete": [<note id integers - duplicates or obsolete>],\n'
                ' "notes_to_merge": [{"delete_ids": [<ids>], "merged_content": "...", "category": "..."}],\n'
                ' "profile_upgrades": {"<field>": "<value>"}}\n'
                "Rules:\n"
                "- notes_to_delete: IDs of notes that are exact or near duplicates\n"
                "- notes_to_merge: groups of related notes to combine into one\n"
                "- profile_upgrades: ONLY for fields that are currently null/missing\n"
                "If nothing to change, return empty arrays/object."
            )

            from src.backend.state import UserProfile
            profile = profile or UserProfile()
            response = llm.chat([
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({
                    "profile": profile.filled_fields(),
                    "missing_fields": profile.missing_fields(),
                    "notes": [{"id": n.id, "content": n.content, "category": n.category} for n in notes],
                    "session_summary": session_summary,
                }, ensure_ascii=False)},
            ])

            result = json.loads(response.content)

            if ids := result.get("notes_to_delete", []):
                self.delete_notes([i for i in ids if isinstance(i, int)])

            for merge in result.get("notes_to_merge", []):
                del_ids = [i for i in merge.get("delete_ids", []) if isinstance(i, int)]
                if del_ids:
                    self.delete_notes(del_ids)
                if merged := merge.get("merged_content"):
                    self.add_note(user_id, merged, merge.get("category", "context"), source_turn=-1)

            if upgrades := result.get("profile_upgrades", {}):
                for field, value in upgrades.items():
                    if hasattr(profile, field) and getattr(profile, field) is None:
                        setattr(profile, field, value)
                self.save_profile(user_id, profile)

        except Exception:
            pass

    def _dump_debug(self, user_id: str) -> None:
        """Write debug snapshot to data/debug/{user_id}_memory.md. Silent on failure."""
        try:
            if self._db_path == ":memory:":
                return
            debug_dir = os.path.join(os.path.dirname(self._db_path), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            path = os.path.join(debug_dir, f"{user_id}_memory.md")

            profile = self.load_profile(user_id)
            notes = self.load_notes(user_id, limit=50)

            lines = [f"# Memory Debug: {user_id}\n"]

            lines.append("## Profile")
            if profile:
                for k, v in profile.filled_fields().items():
                    lines.append(f"- {k}: {v}")
                missing = profile.missing_fields()
                if missing:
                    lines.append(f"- _missing_: {', '.join(missing)}")
            else:
                lines.append("_(no profile)_")

            lines.append("\n## Notes")
            if notes:
                for n in notes:
                    lines.append(f"- [{n.category}] {n.content} (turn {n.source_turn})")
            else:
                lines.append("_(no notes)_")

            events = self._conn.execute(
                "SELECT field, value, source_turn FROM memory_events WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20",
                (user_id,),
            ).fetchall()
            lines.append("\n## Events")
            if events:
                for e in events:
                    lines.append(f"- {e['field']}={e['value']} (turn {e['source_turn']})")
            else:
                lines.append("_(no events)_")

            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass

    def close(self) -> None:
        self._conn.close()
