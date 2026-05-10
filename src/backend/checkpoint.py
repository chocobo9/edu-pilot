from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Checkpoint:
    user_id: str
    session_id: str
    state_json: str
    turn_count: int
    routing_context: str
    timestamp: str = ""


def serialize_state(state) -> str:
    """Serialize LoopState to JSON string."""
    return json.dumps({
        "messages": state.messages,
        "turn_count": state.turn_count,
        "done": state.done,
        "max_turns": state.max_turns,
        "profile": state.profile.filled_fields(),
        "current_route": state.current_route,
    }, ensure_ascii=False)


def deserialize_state(state_json: str):
    """Reconstruct LoopState from JSON string."""
    from src.backend.loop import LoopState
    from src.backend.state import UserProfile

    data = json.loads(state_json)
    profile = UserProfile()
    for field, value in data.get("profile", {}).items():
        if hasattr(profile, field):
            setattr(profile, field, value)
    return LoopState(
        messages=data["messages"],
        turn_count=data["turn_count"],
        done=data.get("done", False),
        max_turns=data.get("max_turns", 20),
        profile=profile,
        current_route=data.get("current_route", "intake"),
    )


class CheckpointStore:
    """SQLite-backed session checkpointing."""

    def __init__(self, db_path: str = "data/edupilot.db") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                turn_count INTEGER,
                routing_context TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def save(self, checkpoint: Checkpoint) -> None:
        """Append a checkpoint snapshot."""
        now = checkpoint.timestamp or datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO checkpoints (user_id, session_id, state_json, turn_count, routing_context, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (checkpoint.user_id, checkpoint.session_id, checkpoint.state_json,
             checkpoint.turn_count, checkpoint.routing_context, now),
        )
        self._conn.commit()

    def load_latest(self, user_id: str) -> Checkpoint | None:
        """Load the most recent checkpoint for a user."""
        row = self._conn.execute(
            """SELECT user_id, session_id, state_json, turn_count, routing_context, timestamp
               FROM checkpoints WHERE user_id = ?
               ORDER BY timestamp DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return Checkpoint(
            user_id=row["user_id"],
            session_id=row["session_id"],
            state_json=row["state_json"],
            turn_count=row["turn_count"],
            routing_context=row["routing_context"] or "",
            timestamp=row["timestamp"] or "",
        )

    def list_sessions(self, user_id: str) -> list[Checkpoint]:
        """List distinct sessions (latest checkpoint per session_id)."""
        rows = self._conn.execute(
            """SELECT user_id, session_id, state_json, turn_count, routing_context, timestamp
               FROM checkpoints WHERE user_id = ?
               GROUP BY session_id
               ORDER BY timestamp DESC""",
            (user_id,),
        ).fetchall()
        return [
            Checkpoint(
                user_id=r["user_id"], session_id=r["session_id"],
                state_json=r["state_json"], turn_count=r["turn_count"],
                routing_context=r["routing_context"] or "", timestamp=r["timestamp"] or "",
            )
            for r in rows
        ]

    def is_recent(self, checkpoint: Checkpoint, max_age_hours: int = 24) -> bool:
        """Check if a checkpoint is fresh enough to resume."""
        if not checkpoint.timestamp:
            return False
        try:
            ts = datetime.fromisoformat(checkpoint.timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - ts
            return age.total_seconds() < max_age_hours * 3600
        except (ValueError, TypeError):
            return False

    def close(self) -> None:
        self._conn.close()
