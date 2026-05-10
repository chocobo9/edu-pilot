from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


@dataclass
class RemoteToolSpec:
    name: str
    description: str
    parameters: dict
    server_name: str


class MCPConnection:
    """Minimal MCP client over stdio (JSON-RPC 2.0)."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.server_name = config.name
        self._request_id = 0
        env = {**os.environ, **(config.env or {})}
        command = shutil.which(config.command) or config.command
        self._process = subprocess.Popen(
            [command] + config.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC 2.0 request and return the result."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }
        line = json.dumps(request) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        self._process.stdin.flush()

        response_line = self._process.stdout.readline()
        if not response_line:
            return {}
        response = json.loads(response_line)
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response.get("result", {})

    def list_tools(self) -> list[dict]:
        result = self.send_request("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self.send_request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", json.dumps(content))
        return json.dumps(result)

    def close(self) -> None:
        try:
            self._process.stdin.close()
        except Exception:
            pass
        try:
            self._process.kill()
            self._process.wait(timeout=5)
        except Exception:
            pass


class MCPManager:
    """Manages multiple MCP server connections and unified tool dispatch."""

    def __init__(self) -> None:
        self._connections: dict[str, MCPConnection] = {}
        self._remote_tools: dict[str, RemoteToolSpec] = {}
        self._tool_to_server: dict[str, str] = {}

    def connect(self, config: MCPServerConfig) -> None:
        try:
            conn = MCPConnection(config)
            self._connections[config.name] = conn
        except Exception as e:
            print(f"[WARN] MCP server '{config.name}' failed to start: {e}")

    def discover_tools(self) -> list[RemoteToolSpec]:
        """Discover tools from all connected servers."""
        all_tools: list[RemoteToolSpec] = []
        for server_name, conn in self._connections.items():
            try:
                raw_tools = conn.list_tools()
                for t in raw_tools:
                    spec = RemoteToolSpec(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        parameters=t.get("inputSchema", {}),
                        server_name=server_name,
                    )
                    self._remote_tools[spec.name] = spec
                    self._tool_to_server[spec.name] = server_name
                    all_tools.append(spec)
            except Exception as e:
                print(f"[WARN] Tool discovery failed for '{server_name}': {e}")
        return all_tools

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        server_name = self._tool_to_server.get(tool_name)
        if not server_name or server_name not in self._connections:
            return f"Error: MCP tool '{tool_name}' not found"
        return self._connections[server_name].call_tool(tool_name, arguments)

    def disconnect_all(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
        self._remote_tools.clear()
        self._tool_to_server.clear()


def load_mcp_configs(config_path: str = "data/mcp_servers.json") -> list[MCPServerConfig]:
    """Load MCP server configs from JSON file. Returns empty list if file doesn't exist."""
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        return [
            MCPServerConfig(
                name=c["name"],
                command=c["command"],
                args=c.get("args", []),
                env=c.get("env"),
            )
            for c in data
        ]
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"[WARN] Failed to load MCP config: {e}")
        return []


def register_mcp_tools(registry, mcp_manager: MCPManager, existing_names: set[str] | None = None) -> None:
    """Discover MCP tools and register into ToolRegistry. Adds mcp_ prefix on name conflicts."""
    from src.backend.tools import ToolSpec

    existing = existing_names or set()
    remote_tools = mcp_manager.discover_tools()
    for rt in remote_tools:
        name = rt.name
        if name in existing:
            name = f"mcp_{name}"
        existing.add(name)

        registry.register(ToolSpec(
            name=name,
            description=f"[MCP:{rt.server_name}] {rt.description}",
            parameters=rt.parameters,
            handler=lambda _rt=rt, **args: mcp_manager.call_tool(_rt.name, args),
        ))
