from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.services.exchange.ccxt_adapter import CcxtExchangeAdapter


class _FakeExchange:
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        self.httpProxy = None
        self.http_proxy = None
        self.httpsProxy = None
        self.https_proxy = None
        # Simulate older/newer ccxt default that conflicts when both are set.
        self.aiohttp_proxy = "http://should-be-cleared:1"

    def set_sandbox_mode(self, enabled: bool) -> None:
        self.sandbox = enabled


def test_settings_proxy_url_covers_http_and_https() -> None:
    settings = Settings(
        exchange_proxy_url="http://127.0.0.1:7890",
        exchange_http_proxy=None,
        exchange_https_proxy=None,
    )
    assert settings.resolved_exchange_http_proxy == "http://127.0.0.1:7890"
    assert settings.resolved_exchange_https_proxy == "http://127.0.0.1:7890"


def test_adapter_sets_https_proxy_without_aiohttp_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.exchange.ccxt_adapter.ccxt",
        type("ccxt", (), {"okx": _FakeExchange}),
    )
    adapter = CcxtExchangeAdapter(
        exchange_id="okx",
        api_key="k",
        api_secret="s",
        passphrase="p",
        use_testnet=True,
        market_type="usdt_perp",
        http_proxy="http://127.0.0.1:7890",
        https_proxy="http://127.0.0.1:7890",
    )
    assert adapter.exchange.httpsProxy == "http://127.0.0.1:7890"
    assert adapter.exchange.https_proxy == "http://127.0.0.1:7890"
    assert adapter.exchange.httpProxy is None
    assert adapter.exchange.http_proxy is None
    assert adapter.exchange.aiohttp_proxy is None
