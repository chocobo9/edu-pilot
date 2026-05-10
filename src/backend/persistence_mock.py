from __future__ import annotations

import json
import os
from dataclasses import asdict, fields

from src.backend.state import UserProfile


class ProfileStore:
    """JSON-file persistence for user profiles.
    Same interface as future Module D MemoryStore — drop-in replaceable."""

    def __init__(self, data_dir: str = "help/"):
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def _profile_path(self, user_id: str) -> str:
        return os.path.join(self._data_dir, f"{user_id}_profile.json")

    def _session_path(self, user_id: str) -> str:
        return os.path.join(self._data_dir, f"{user_id}_session.json")

    def save_profile(self, user_id: str, profile: UserProfile) -> None:
        data = asdict(profile)
        with open(self._profile_path(user_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_profile(self, user_id: str) -> UserProfile | None:
        path = self._profile_path(user_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        profile = UserProfile()
        for field in fields(UserProfile):
            if field.name in data and data[field.name] is not None:
                setattr(profile, field.name, data[field.name])
        return profile

    def save_session(self, user_id: str, session_data: dict) -> None:
        with open(self._session_path(user_id), "w", encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

    def load_session(self, user_id: str) -> dict | None:
        path = self._session_path(user_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
