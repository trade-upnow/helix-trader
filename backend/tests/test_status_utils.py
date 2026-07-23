from __future__ import annotations

from app.agent.status_utils import status_has_credential


def test_status_has_credential_requires_masked_or_status() -> None:
    assert status_has_credential(None) is False
    assert status_has_credential({}) is False
    assert status_has_credential({"exchange": "okx", "use_testnet": False}) is False
    assert status_has_credential({"masked_api_key": "****ABCD"}) is True
    assert status_has_credential({"credential_status": "active"}) is True
    assert status_has_credential({"masked_api_key": "   "}) is False
