"""Minimal MCP stdio server for Helix agent tools.

Implements enough of the Model Context Protocol for tools/list and tools/call
without requiring the official SDK (keeps Python 3.9 compatibility).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from app.agent import __version__
from app.agent.client import HelixApiClient
from app.agent.tools import call_tool, list_tools


SERVER_NAME = "helix-trader"
PROTOCOL_VERSION = "2024-11-05"


def run_stdio_server() -> None:
    client = HelixApiClient.from_env()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue
        response = handle_message(message, client=client)
        if response is not None:
            _write(response)


def handle_message(message: dict[str, Any], *, client: HelixApiClient) -> dict[str, Any] | None:
    if message.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32600, "message": "Invalid Request"},
        }

    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    # Notifications have no id and no response.
    if msg_id is None and method and not str(method).startswith("tools/"):
        if method == "notifications/initialized":
            return None
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": __version__},
                "instructions": (
                    "Helix trader control tools. Always run doctor and preview_bot_config "
                    "before start_bot. Never expose API keys, tokens, or .env contents."
                ),
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                raise ValueError("tools/call requires string name")
            if not isinstance(arguments, dict):
                raise ValueError("tools/call arguments must be an object")
            payload = call_tool(name, arguments, client=client)
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    }
                ],
                "structuredContent": payload,
                "isError": not bool(payload.get("ok")),
            }
        elif method == "shutdown":
            result = {}
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": str(exc)},
        }

    if msg_id is None:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str))
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
