from __future__ import annotations

from app.agent.client import HelixApiClient
from app.agent.mcp_server import handle_message


class DummyClient(HelixApiClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://example.invalid", token=None)

    def health(self):
        return {"status": "ok"}

    def get_status(self):
        return {
            "status": "stopped",
            "exchange": "okx",
            "masked_api_key": "****LIVE",
            "credential_status": "active",
            "use_testnet": False,
        }


def test_initialize_and_tools_list() -> None:
    client = DummyClient()
    init = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        },
        client=client,
    )
    assert init is not None
    assert init["result"]["serverInfo"]["name"] == "helix-trader"

    listed = handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        client=client,
    )
    assert listed is not None
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "doctor" in names
    assert "get_runtime_mode" in names
    assert "start_bot" in names


def test_tools_call_health() -> None:
    client = DummyClient()
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "health_check", "arguments": {}},
        },
        client=client,
    )
    assert response is not None
    assert response["result"]["isError"] is False
    assert response["result"]["structuredContent"]["ok"] is True


def test_tools_call_start_live_blocked(monkeypatch) -> None:
    monkeypatch.delenv("HELIX_ALLOW_LIVE_TRADING", raising=False)
    client = DummyClient()
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "start_bot",
                "arguments": {
                    "strategy_id": "trend_following_core",
                    "exchange": "okx",
                    "use_testnet": False,
                    "confirm_live_trading": True,
                },
            },
        },
        client=client,
    )
    assert response is not None
    assert response["result"]["isError"] is True
    assert response["result"]["structuredContent"]["error"]["code"] == "safety_blocked"
