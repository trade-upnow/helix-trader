from __future__ import annotations

import pytest

from app.agent import okx_probe


def test_okx_probe_request_headers_always_sets_user_agent() -> None:
    headers = okx_probe.okx_probe_request_headers()
    assert headers["Accept"] == "application/json"
    ua = headers["User-Agent"]
    assert ua.strip()
    assert "python-urllib" not in ua.lower()


def test_okx_probe_rejects_urllib_default_user_agent(monkeypatch) -> None:
    monkeypatch.setattr(okx_probe, "okx_probe_user_agent", lambda: "Python-urllib/3.12")
    with pytest.raises(RuntimeError, match="urllib default"):
        okx_probe.okx_probe_request_headers()
