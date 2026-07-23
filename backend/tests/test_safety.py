from __future__ import annotations

import os

import pytest

from app.agent.safety import (
    SafetyError,
    ensure_close_all_confirmed,
    ensure_credential_save_confirmed,
    ensure_live_trading_allowed,
    mask_secret,
    redact_text,
    redact_value,
)


def test_mask_secret() -> None:
    assert mask_secret("abcd1234").endswith("1234")
    assert "abcd" not in mask_secret("abcd1234")


def test_redact_value_masks_sensitive_keys() -> None:
    payload = {
        "api_key": "super-secret-key",
        "nested": {"access_token": "tokensecret9999", "status": "ok"},
    }
    redacted = redact_value(payload)
    assert redacted["nested"]["status"] == "ok"
    assert "super-secret-key" not in str(redacted)
    assert "tokensecret9999" not in str(redacted)


def test_redact_value_keeps_safe_token_metadata() -> None:
    payload = {
        "detail": "Login succeeded",
        "token_type": "bearer",
        "access_token_present": True,
        "access_token_masked": "abcd...wxyz",
        "token_cache_path": "/tmp/backend/.helix-agent-token",
        "access_token": "raw-secret-token-value",
        "cleared_token_cache": True,
        "cleared_env_token": False,
    }
    redacted = redact_value(payload)
    assert redacted["token_type"] == "bearer"
    assert redacted["access_token_present"] is True
    assert redacted["access_token_masked"] == "abcd...wxyz"
    assert redacted["token_cache_path"] == "/tmp/backend/.helix-agent-token"
    assert redacted["cleared_token_cache"] is True
    assert redacted["cleared_env_token"] is False
    assert "raw-secret-token-value" not in str(redacted)


def test_redact_text_patterns() -> None:
    text = "Authorization: Bearer abcdefghijklmnop api_key=ABCDEFG1234"
    redacted = redact_text(text)
    assert "abcdefghijklmnop" not in redacted
    assert "ABCDEFG1234" not in redacted


def test_live_trading_blocked_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_ALLOW_LIVE_TRADING", raising=False)
    with pytest.raises(SafetyError):
        ensure_live_trading_allowed(use_testnet=False, confirm_live_trading=True)


def test_live_trading_blocked_without_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_ALLOW_LIVE_TRADING", "true")
    with pytest.raises(SafetyError):
        ensure_live_trading_allowed(use_testnet=False, confirm_live_trading=False)


def test_live_trading_allowed_with_dual_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELIX_ALLOW_LIVE_TRADING", "true")
    ensure_live_trading_allowed(use_testnet=False, confirm_live_trading=True)


def test_testnet_skips_live_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HELIX_ALLOW_LIVE_TRADING", raising=False)
    ensure_live_trading_allowed(use_testnet=True, confirm_live_trading=False)


def test_close_all_requires_confirm() -> None:
    with pytest.raises(SafetyError):
        ensure_close_all_confirmed(close_all=True, confirm_close_all=False)
    ensure_close_all_confirmed(close_all=True, confirm_close_all=True)


def test_credential_save_requires_confirm() -> None:
    with pytest.raises(SafetyError):
        ensure_credential_save_confirmed(confirm_save_credentials=False)
    ensure_credential_save_confirmed(confirm_save_credentials=True)
