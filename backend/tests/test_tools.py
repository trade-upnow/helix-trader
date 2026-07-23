from __future__ import annotations

from typing import Any

import pytest

from app.agent.client import HelixApiClient
from app.agent.tools import call_tool, list_tools


class FakeClient(HelixApiClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://example.invalid", token="fake-token")
        self.started: dict[str, Any] | None = None
        self.stopped: dict[str, Any] | None = None
        self.updated: dict[str, Any] | None = None

    def health(self) -> dict[str, Any]:
        return {"status": "ok"}

    def list_strategies(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "trend_following_core",
                "default_params": {
                    "symbol": "BTC/USDT:USDT",
                    "timeframe": "15m",
                    "leverage": 3,
                    "position_size_pct": 15,
                    "stop_loss_pct": 2,
                    "take_profit_pct": 5,
                    "max_drawdown_pct": 12,
                    "max_order_notional_usdt": 1000,
                    "max_position_notional_usdt": 3000,
                },
            }
        ]

    def get_status(self) -> dict[str, Any]:
        return {"status": "stopped", "balance": 1000}

    def get_trades(self) -> list[dict[str, Any]]:
        return [{"id": "1", "symbol": "BTC/USDT:USDT", "side": "buy"}]

    def start_bot(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.started = payload
        return {"detail": "Bot started", "session_id": "sess-1"}

    def stop_bot(self, *, close_all: bool = False) -> dict[str, Any]:
        self.stopped = {"close_all": close_all}
        return {"detail": "Bot stopped"}

    def save_credentials(self, **kwargs: Any) -> dict[str, Any]:
        return {"masked_api_key": "****ABCD"}

    def update_bot_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.updated = payload
        return {"detail": "Config applied", "config": payload}


class LiveCredentialClient(FakeClient):
    def get_status(self) -> dict[str, Any]:
        return {
            "status": "stopped",
            "exchange": "okx",
            "masked_api_key": "****LIVE",
            "credential_status": "active",
            "use_testnet": False,
        }


class SavedTestnetCredentialClient(FakeClient):
    def get_status(self) -> dict[str, Any]:
        return {
            "status": "stopped",
            "exchange": "okx",
            "masked_api_key": "****TEST",
            "credential_status": "active",
            "use_testnet": True,
        }


def test_list_tools_has_risk_annotations() -> None:
    tools = list_tools()
    names = {item["name"] for item in tools}
    assert "doctor" in names
    assert "start_bot" in names
    start = next(item for item in tools if item["name"] == "start_bot")
    assert start["annotations"]["risk_level"] == "trading"


def test_preview_does_not_start(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    result = call_tool(
        "preview_bot_config",
        {
            "strategy_id": "trend_following_core",
            "exchange": "okx",
            "use_testnet": True,
        },
        client=client,
    )
    assert result["ok"] is True
    assert result["result"]["places_orders"] is False
    assert client.started is None


def test_start_live_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_ALLOW_LIVE_TRADING", raising=False)
    client = FakeClient()
    result = call_tool(
        "start_bot",
        {
            "strategy_id": "trend_following_core",
            "exchange": "okx",
            "use_testnet": False,
            "confirm_live_trading": True,
        },
        client=client,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "safety_blocked"
    assert client.started is None


def test_start_blocks_when_saved_credential_is_live_even_if_request_says_testnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HELIX_ALLOW_LIVE_TRADING", raising=False)
    client = LiveCredentialClient()
    result = call_tool(
        "start_bot",
        {
            "strategy_id": "trend_following_core",
            "exchange": "okx",
            "use_testnet": True,
        },
        client=client,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "safety_blocked"
    assert client.started is None


def test_start_allows_when_saved_credential_is_testnet_even_if_request_says_live() -> None:
    client = SavedTestnetCredentialClient()
    result = call_tool(
        "start_bot",
        {
            "strategy_id": "trend_following_core",
            "exchange": "okx",
            "use_testnet": False,
        },
        client=client,
    )
    assert result["ok"] is True
    assert client.started is not None
    assert result["result"]["started_config"]["actual_credential_use_testnet"] is True


def test_start_testnet_ok() -> None:
    client = FakeClient()
    result = call_tool(
        "start_bot",
        {
            "strategy_id": "trend_following_core",
            "exchange": "okx",
            "use_testnet": True,
            "leverage": 1,
        },
        client=client,
    )
    assert result["ok"] is True
    assert client.started is not None
    assert client.started["use_testnet"] is True


def test_get_runtime_mode_reports_data_source() -> None:
    client = SavedTestnetCredentialClient()
    result = call_tool("get_runtime_mode", {}, client=client)
    assert result["ok"] is True
    assert result["result"]["mode"] == "testnet"
    assert result["result"]["use_testnet"] is True
    assert result["result"]["data_source"] == "/api/bot/status.use_testnet"


def test_get_runtime_mode_not_configured_without_saved_credential() -> None:
    client = FakeClient()
    result = call_tool("get_runtime_mode", {}, client=client)
    assert result["ok"] is True
    assert result["result"]["mode"] == "not_configured"
    assert result["result"]["use_testnet"] is None


def test_get_runtime_mode_ignores_exchange_alone_looking_like_live() -> None:
    class ExchangeOnlyClient(FakeClient):
        def get_status(self) -> dict[str, Any]:
            return {"status": "stopped", "exchange": "okx", "use_testnet": False}

    result = call_tool("get_runtime_mode", {}, client=ExchangeOnlyClient())
    assert result["ok"] is True
    assert result["result"]["mode"] == "not_configured"
    assert result["result"]["use_testnet"] is None


def test_stop_bot_explains_preexisting_positions_untouched() -> None:
    client = FakeClient()
    result = call_tool(
        "stop_bot",
        {"close_all": True, "confirm_close_all": True},
        client=client,
    )
    assert result["ok"] is True
    assert result["result"]["scope"]["closes_bot_managed_positions"] is True
    assert result["result"]["scope"]["closes_preexisting_account_positions"] is False
    assert "pre-existing" in result["result"]["warning"].lower() or "untouched" in result["result"]["warning"]


def test_update_config_blocks_live_without_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_ALLOW_LIVE_TRADING", raising=False)
    client = LiveCredentialClient()
    result = call_tool(
        "update_bot_config",
        {
            "leverage": 2,
            "position_size_pct": 10,
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_drawdown_pct": 10,
            "max_order_notional_usdt": 200,
            "max_position_notional_usdt": 600,
        },
        client=client,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "safety_blocked"
    assert client.updated is None


def test_update_config_allows_live_with_dual_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_ALLOW_LIVE_TRADING", "true")
    client = LiveCredentialClient()
    result = call_tool(
        "update_bot_config",
        {
            "leverage": 2,
            "position_size_pct": 10,
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_drawdown_pct": 10,
            "max_order_notional_usdt": 200,
            "max_position_notional_usdt": 600,
            "confirm_live_trading": True,
        },
        client=client,
    )
    assert result["ok"] is True
    assert client.updated is not None
    assert result["result"]["runtime_mode"]["mode"] == "live"


def test_stop_close_all_requires_confirm() -> None:
    client = FakeClient()
    result = call_tool("stop_bot", {"close_all": True, "confirm_close_all": False}, client=client)
    assert result["ok"] is False
    assert client.stopped is None


def test_stop_defaults_to_keep_positions_when_flat() -> None:
    client = FakeClient()
    result = call_tool("stop_bot", {}, client=client)
    assert result["ok"] is True
    assert client.stopped == {"close_all": False}
    assert result["result"]["close_all"] is False
    assert result["result"]["stopped"] is True


def test_stop_without_choice_refuses_when_positions_exist() -> None:
    class WithPositions(FakeClient):
        def get_status(self) -> dict[str, Any]:
            return {
                "status": "running",
                "positions": [{"symbol": "BTC/USDT:USDT", "side": "long", "size": 0.01}],
            }

    client = WithPositions()
    result = call_tool("stop_bot", {"close_all": False}, client=client)
    assert result["ok"] is True
    assert client.stopped is None
    assert result["result"]["needs_user_choice"] is True
    assert result["result"]["open_positions"] == 1
    assert "MUST ask" in result["result"]["agent_action"]
    assert "平" in result["result"]["ask_user"]


def test_stop_keep_positions_after_explicit_confirm() -> None:
    class WithPositions(FakeClient):
        def get_status(self) -> dict[str, Any]:
            return {
                "status": "running",
                "positions": [{"symbol": "BTC/USDT:USDT", "side": "long", "size": 0.01}],
            }

    client = WithPositions()
    result = call_tool(
        "stop_bot",
        {"close_all": False, "confirm_stop_keep_positions": True},
        client=client,
    )
    assert result["ok"] is True
    assert client.stopped == {"close_all": False}
    assert result["result"]["stopped"] is True


def test_list_strategies_includes_docs() -> None:
    client = FakeClient()
    result = call_tool("list_strategies", {}, client=client)
    assert result["ok"] is True
    strategies = result["result"]["strategies"]
    assert strategies[0]["parameter_docs"]["leverage"]["user_editable"] is True


def test_save_credentials_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_EXCHANGE_API_KEY", "key-123456")
    monkeypatch.setenv("HELIX_EXCHANGE_API_SECRET", "secret-123456")
    client = FakeClient()
    result = call_tool(
        "save_exchange_credentials",
        {"exchange": "okx", "confirm_save_credentials": True, "use_testnet": True},
        client=client,
    )
    assert result["ok"] is True
    assert result["result"]["masked_api_key"] == "****ABCD"
    assert "key-123456" not in str(result)
    assert result["result"]["credential_source"] == "local_environment"
    assert "backend database" in result["result"]["storage_note"]
    assert "do not grep .env" in result["result"]["storage_note"]


def test_save_credentials_direct_args_are_redacted() -> None:
    client = FakeClient()
    result = call_tool(
        "save_exchange_credentials",
        {
            "exchange": "okx",
            "api_key": "direct-key-123456",
            "api_secret": "direct-secret-123456",
            "confirm_save_credentials": True,
            "use_testnet": True,
        },
        client=client,
    )
    assert result["ok"] is True
    assert result["result"]["credential_source"] == "tool_arguments"
    assert "direct-key-123456" not in str(result)
    assert "direct-secret-123456" not in str(result)
