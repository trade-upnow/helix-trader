"""Safety gates and sensitive-value redaction for the agent layer."""

from __future__ import annotations

import os
import re
from typing import Any


SENSITIVE_ENV_NAMES = (
    "API_KEY",
    "API_SECRET",
    "PASSPHRASE",
    "PASSWORD",
    "TOKEN",
    "JWT_SECRET",
    "API_ENCRYPTION_KEY",
    "ADMIN_PASSWORD",
    "CLIENT_PASSWORD",
    "HELIX_ACCESS_TOKEN",
    "HELIX_PASSWORD",
    "HELIX_EXCHANGE_API_KEY",
    "HELIX_EXCHANGE_API_SECRET",
    "HELIX_EXCHANGE_PASSPHRASE",
)

SENSITIVE_KEYS = {
    "api_key",
    "api_secret",
    "passphrase",
    "password",
    "access_token",
    "token",
    "authorization",
    "jwt_secret",
    "api_encryption_key",
    "admin_password",
    "client_password",
    "api_key_encrypted",
    "api_secret_encrypted",
    "passphrase_encrypted",
    "password_hash",
}

# Metadata about tokens that is already safe / non-secret and must remain readable.
SAFE_TOKEN_METADATA_KEYS = {
    "access_token_masked",
    "access_token_present",
    "token_type",
    "token_cache_path",
    "cleared_token_cache",
    "cleared_env_token",
    # Already masked by the backend; must not run through mask_secret(None) → "****".
    "masked_api_key",
}

LIVE_TRADING_ENV = "HELIX_ALLOW_LIVE_TRADING"


class SafetyError(ValueError):
    """Raised when a trading action violates safety gates."""


def env_flag_enabled(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def live_trading_allowed_by_env() -> bool:
    return env_flag_enabled(LIVE_TRADING_ENV)


def mask_secret(value: str | None, visible: int = 4) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if len(text) <= visible:
        return "*" * len(text)
    return f"{'*' * max(len(text) - visible, 4)}{text[-visible:]}"


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in SAFE_TOKEN_METADATA_KEYS:
        return False
    if lowered in SENSITIVE_KEYS:
        return True
    if any(
        marker in lowered
        for marker in ("secret", "password", "passphrase", "api_key", "authorization")
    ):
        return True
    # Match raw token fields (access_token, refresh_token) but not metadata keys above.
    return lowered == "token" or lowered.endswith("_token") or lowered.startswith("token_")


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (mask_secret(str(item)) if is_sensitive_key(str(key)) else redact_value(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(text: str) -> str:
    patterns = [
        (r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;]+)", r"\1***REDACTED***"),
        (r"(?i)(api[_-]?secret\s*[=:]\s*)([^\s,;]+)", r"\1***REDACTED***"),
        (r"(?i)(passphrase\s*[=:]\s*)([^\s,;]+)", r"\1***REDACTED***"),
        (r"(?i)(password\s*[=:]\s*)([^\s,;]+)", r"\1***REDACTED***"),
        (r"(?i)(access[_-]?token\s*[=:]\s*)([^\s,;]+)", r"\1***REDACTED***"),
        (r"(?i)(bearer\s+)([A-Za-z0-9\-\._~\+\/]+=*)", r"\1***REDACTED***"),
        (r"(?i)(authorization\s*[=:]\s*)([^\s,;]+)", r"\1***REDACTED***"),
    ]
    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


def ensure_live_trading_allowed(*, use_testnet: bool, confirm_live_trading: bool) -> None:
    if use_testnet:
        return
    if not live_trading_allowed_by_env():
        raise SafetyError(
            "Live trading is disabled. Set HELIX_ALLOW_LIVE_TRADING=true in the local "
            "environment AND pass confirm_live_trading=true only after the user explicitly confirms."
        )
    if not confirm_live_trading:
        raise SafetyError(
            "Live trading requires confirm_live_trading=true after an explicit user confirmation. "
            "Prefer testnet (use_testnet=true) first."
        )


def ensure_close_all_confirmed(*, close_all: bool, confirm_close_all: bool) -> None:
    if not close_all:
        return
    if not confirm_close_all:
        raise SafetyError(
            "Stopping with close_all=true requires confirm_close_all=true after an explicit "
            "user confirmation that they want to flatten bot-managed positions. "
            "Phrases like 停止机器人/关掉策略 alone are NOT enough — ask first. "
            "Default stop is close_all=false (stop strategy only)."
        )


def ensure_credential_save_confirmed(*, confirm_save_credentials: bool) -> None:
    if not confirm_save_credentials:
        raise SafetyError(
            "Saving exchange credentials requires confirm_save_credentials=true. "
            "Do not paste secrets into public chats; use local env vars or interactive input."
        )


def summarize_start_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "exchange": config.get("exchange"),
        "symbol": config.get("symbol"),
        "strategy_id": config.get("strategy_id"),
        "market_type": config.get("market_type"),
        "use_testnet": config.get("use_testnet"),
        "leverage": config.get("leverage"),
        "position_size_pct": config.get("position_size_pct"),
        "stop_loss_pct": config.get("stop_loss_pct"),
        "take_profit_pct": config.get("take_profit_pct"),
        "max_drawdown_pct": config.get("max_drawdown_pct"),
        "max_order_notional_usdt": config.get("max_order_notional_usdt"),
        "max_position_notional_usdt": config.get("max_position_notional_usdt"),
        "close_all_on_stop": config.get("close_all_on_stop"),
        "risk_notice": (
            "This may place real market orders if use_testnet=false. "
            "Not investment advice; user bears all trading risk."
        ),
    }


def sensitive_env_presence(names: list[str] | None = None) -> dict[str, str]:
    checked = names or list(SENSITIVE_ENV_NAMES)
    result: dict[str, str] = {}
    for name in checked:
        value = os.getenv(name)
        if value is None or value.strip() == "":
            result[name] = "missing"
        else:
            result[name] = "present"
    return result
