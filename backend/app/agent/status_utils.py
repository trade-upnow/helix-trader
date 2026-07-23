"""Helpers for interpreting /api/bot/status payloads."""

from __future__ import annotations

from typing import Any


def status_has_credential(status: dict[str, Any] | None) -> bool:
    """True only when a saved exchange credential is present.

    Do not treat exchange/session leftovers as credentials; otherwise runtime mode
    can look like live/testnet when nothing is configured.
    """
    if not status:
        return False
    masked = status.get("masked_api_key")
    if isinstance(masked, str) and masked.strip():
        return True
    cred_status = status.get("credential_status")
    if isinstance(cred_status, str) and cred_status.strip():
        return True
    return False
