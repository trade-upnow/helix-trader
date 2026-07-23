from __future__ import annotations

import urllib.error
from typing import Any

from app.agent import connectivity


class _FakeResponse:
    def __init__(self, *, status: int = 200, body: bytes = b'{"code":"0"}') -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def _patch_probe(monkeypatch, outcomes: dict[str | None, dict[str, Any]]) -> None:
    def fake_probe(*, proxy, timeout_seconds):  # noqa: ARG001
        key = proxy
        if key in outcomes:
            return dict(outcomes[key])
        return {
            "ok": False,
            "status_code": None,
            "proxy_configured": bool(proxy),
            "url": connectivity.OKX_PUBLIC_TIME_URL,
            "host": connectivity.OKX_HOST,
            "detail": f"fail for {proxy}",
        }

    monkeypatch.setattr(connectivity, "_probe", fake_probe)


def test_probe_okx_public_time_success(monkeypatch) -> None:
    monkeypatch.delenv("EXCHANGE_PROXY_URL", raising=False)
    monkeypatch.delenv("EXCHANGE_HTTPS_PROXY", raising=False)
    monkeypatch.delenv("EXCHANGE_HTTP_PROXY", raising=False)

    captured: dict[str, str] = {}

    class FakeOpener:
        def open(self, request: Any, timeout: float = 0) -> _FakeResponse:
            assert "okx.com" in request.full_url
            captured["user_agent"] = request.get_header("User-agent") or ""
            return _FakeResponse()

    monkeypatch.setattr(connectivity.urllib.request, "build_opener", lambda *a, **k: FakeOpener())
    result = connectivity.probe_okx_public_time(use_env_proxy=False)
    assert result["ok"] is True
    assert result["status_code"] == 200
    assert captured["user_agent"]
    assert "python-requests" in captured["user_agent"] or "requests" in captured["user_agent"].lower()


def test_diagnose_prefers_direct(monkeypatch) -> None:
    monkeypatch.setenv("EXCHANGE_PROXY_URL", "http://127.0.0.1:7890")
    _patch_probe(
        monkeypatch,
        {
            None: {"ok": True, "detail": "direct ok", "proxy_configured": False},
        },
    )
    result = connectivity.diagnose_okx_network()
    assert result["ok"] is True
    assert result["recommendation"] == "direct"
    assert result["should_clear_proxy_config"] is True
    assert "无需代理" in result["user_message"]


def test_diagnose_falls_back_to_default_7890(monkeypatch) -> None:
    monkeypatch.delenv("EXCHANGE_PROXY_URL", raising=False)
    monkeypatch.delenv("EXCHANGE_HTTPS_PROXY", raising=False)
    monkeypatch.delenv("EXCHANGE_HTTP_PROXY", raising=False)
    _patch_probe(
        monkeypatch,
        {
            None: {"ok": False, "detail": "direct fail", "proxy_configured": False},
            connectivity.DEFAULT_LOCAL_PROXY: {
                "ok": True,
                "detail": "7890 ok",
                "proxy_configured": True,
            },
        },
    )
    result = connectivity.diagnose_okx_network()
    assert result["ok"] is True
    assert result["recommendation"] == "use_default_7890"
    assert result["proxy_to_use"] == connectivity.DEFAULT_LOCAL_PROXY


def test_diagnose_asks_user_when_all_fail(monkeypatch) -> None:
    monkeypatch.delenv("EXCHANGE_PROXY_URL", raising=False)
    _patch_probe(
        monkeypatch,
        {
            None: {"ok": False, "detail": "direct fail", "proxy_configured": False},
            connectivity.DEFAULT_LOCAL_PROXY: {
                "ok": False,
                "detail": "7890 fail",
                "proxy_configured": True,
            },
        },
    )
    result = connectivity.diagnose_okx_network()
    assert result["ok"] is False
    assert result["recommendation"] == "ask_user_for_proxy"
    assert "代理" in result["user_message"]


def test_probe_okx_public_time_keeps_error_detail(monkeypatch) -> None:
    class FakeOpener:
        def open(self, request: Any, timeout: float = 0) -> Any:
            raise urllib.error.URLError("proxy tunnel failed for www.okx.com")

    monkeypatch.setattr(connectivity.urllib.request, "build_opener", lambda *a, **k: FakeOpener())
    result = connectivity.probe_okx_public_time(proxy="http://127.0.0.1:9", use_env_proxy=False)
    assert result["ok"] is False
    assert "proxy tunnel failed" in result["detail"]


def test_persist_recommended_exchange_proxy_writes_empty_slot(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EXCHANGE_PROXY_URL=\nJWT_SECRET=x\n", encoding="utf-8")
    network = {
        "ok": True,
        "proxy_to_use": connectivity.DEFAULT_LOCAL_PROXY,
    }
    result = connectivity.persist_recommended_exchange_proxy(network, env_path=env_file)
    assert result["applied"] is True
    assert f"EXCHANGE_PROXY_URL={connectivity.DEFAULT_LOCAL_PROXY}" in env_file.read_text(encoding="utf-8")


def test_persist_skips_when_proxy_already_set(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("EXCHANGE_PROXY_URL=http://127.0.0.1:8888\n", encoding="utf-8")
    network = {"ok": True, "proxy_to_use": connectivity.DEFAULT_LOCAL_PROXY}
    result = connectivity.persist_recommended_exchange_proxy(network, env_path=env_file)
    assert result["applied"] is False
    assert result["reason"] == "already_set"
