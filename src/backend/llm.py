from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str
    raw: dict


class LLMClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("LLM_API_KEY environment variable is required")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self._client = httpx.Client(timeout=60.0)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Single LLM call. Returns parsed response with .content and .tool_calls."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        resp = self._client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code >= 400:
            print(f"[LLM Error {resp.status_code}] {resp.text}")
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        tool_calls: list[ToolCall] = []
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                try:
                    arguments = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    arguments = {}
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=arguments,
                ))

        return LLMResponse(
            content=msg.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
        )

    def close(self) -> None:
        self._client.close()
