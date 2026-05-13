from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., str | dict | list]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' is already registered")
        self._tools[spec.name] = spec

    def schemas(self) -> list[dict]:
        """Return OpenAI-compatible tool schemas for LLM function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec in self._tools.values()
        ]

    def schemas_for_names(self, names: list[str]) -> list[dict]:
        """Return schemas only for tools whose names are in the list. Empty list = all tools."""
        if not names:
            return self.schemas()
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            for spec_name, spec in self._tools.items()
            if spec_name in names
        ]

    def mcp_tool_names(self) -> list[str]:
        """Return names of MCP-registered tools (description starts with '[MCP:')."""
        return [name for name, spec in self._tools.items() if spec.description.startswith("[MCP:")]

    def dispatch(self, name: str, args: dict) -> str:
        """Execute a registered tool by name. Never raises."""
        if name not in self._tools:
            return f"Error: Unknown tool '{name}'"
        try:
            result = self._tools[name].handler(**args)
            if isinstance(result, str):
                return result
            return json.dumps(result)
        except Exception as e:
            return f"Error: {e}"
