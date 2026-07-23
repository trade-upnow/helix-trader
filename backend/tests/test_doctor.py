from __future__ import annotations

from typing import Any

from app.agent.client import AgentApiError, HelixApiClient
from app.agent.doctor import SETUP_SCRIPT, run_doctor


def _ok_network(**overrides: Any) -> dict[str, Any]:
    base = {
        "ok": True,
        "recommendation": "direct",
        "proxy_to_use": None,
        "configured_proxy": None,
        "should_clear_proxy_config": False,
        "user_message": "本机可直连 OKX，无需代理。",
        "agent_action": "Do not ask the user for a proxy.",
        "attempts": [],
    }
    base.update(overrides)
    return base


class UnreachableClient(HelixApiClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://127.0.0.1:9", token=None)

    def health(self) -> dict[str, Any]:
        raise AgentApiError("Cannot reach Helix API")


class AuthedNoCredentialClient(HelixApiClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://127.0.0.1:8000", token="fake")

    def health(self) -> dict[str, Any]:
        return {"status": "ok"}

    def get_status(self) -> dict[str, Any]:
        return {"status": "stopped", "exchange": "okx", "use_testnet": False}

    def list_strategies(self) -> list[dict[str, Any]]:
        return [{"id": "trend_following_core"}]


def test_doctor_never_returns_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_EXCHANGE_API_KEY", "should-not-appear-in-output")
    monkeypatch.setenv("ADMIN_PASSWORD", "also-secret")
    monkeypatch.setattr("app.agent.doctor.diagnose_okx_network", lambda: _ok_network())
    report = run_doctor(UnreachableClient())
    dumped = str(report)
    assert "should-not-appear-in-output" not in dumped
    assert "also-secret" not in dumped
    presence = next(item for item in report["checks"] if item["name"] == "sensitive_env_presence")
    assert presence["detail"]["HELIX_EXCHANGE_API_KEY"] == "present"
    assert report["overall"] in {"fail", "warn", "ok"}
    assert report["next_steps"]
    assert report["how_to_talk_to_user"]


def test_doctor_guides_two_step_credentials_when_env_present_but_unsaved(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_EXCHANGE_API_KEY", "present-but-unsaved")
    monkeypatch.setattr("app.agent.doctor.diagnose_okx_network", lambda: _ok_network())
    report = run_doctor(AuthedNoCredentialClient())
    cred = next(item for item in report["checks"] if item["name"] == "exchange_credentials")
    assert cred["status"] == "warn"
    assert "env vars are present" in cred["detail"]
    assert any("Path A" in step and "Path B" in step for step in report["next_steps"])
    assert any("never by grepping .env" in step for step in report["next_steps"])
    assert "present-but-unsaved" not in str(report)


def test_doctor_ok_when_saved_credential_even_if_env_empty(monkeypatch) -> None:
    monkeypatch.delenv("HELIX_EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("HELIX_EXCHANGE_API_SECRET", raising=False)
    monkeypatch.setattr("app.agent.doctor.diagnose_okx_network", lambda: _ok_network())

    class SavedCredClient(AuthedNoCredentialClient):
        def get_status(self) -> dict[str, Any]:
            return {
                "status": "stopped",
                "exchange": "okx",
                "use_testnet": True,
                "masked_api_key": "****ABCD",
                "credential_status": "active",
            }

    report = run_doctor(SavedCredClient())
    cred = next(item for item in report["checks"] if item["name"] == "exchange_credentials")
    assert cred["status"] == "ok"
    assert "interactive/--prompt" in cred["detail"]
    assert any("Never grep .env" in tip for tip in report["how_to_talk_to_user"])


def test_doctor_mentions_setup_script_and_offers_frontend(monkeypatch, tmp_path) -> None:
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    monkeypatch.setattr("app.agent.doctor.BACKEND_ROOT", fake_backend)
    monkeypatch.setattr("app.agent.doctor.REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "app.agent.doctor.diagnose_okx_network",
        lambda: _ok_network(
            ok=False,
            recommendation="ask_user_for_proxy",
            user_message="请告诉我本机代理地址",
            agent_action="Ask the user only for the local proxy URL/port.",
        ),
    )
    report = run_doctor(UnreachableClient())
    assert report["setup_script"] == SETUP_SCRIPT
    assert any(SETUP_SCRIPT in step for step in report["next_steps"])
    frontend = next(item for item in report["checks"] if item["name"] == "optional_frontend")
    assert "proactively" in frontend["note"]
    assert "ADMIN_USERNAME" in frontend["note"]
    assert "CLIENT_USERNAME" in frontend["note"]
    assert report["network"]["recommendation"] == "ask_user_for_proxy"
    assert any("proxy" in step.lower() for step in report["next_steps"])
    assert any("API_ENCRYPTION_KEY" in tip for tip in report["how_to_talk_to_user"])
    assert any("examples/mcp" in tip for tip in report["how_to_talk_to_user"])
    assert any("close_all=false" in tip for tip in report["how_to_talk_to_user"])
    assert any("Never grep .env" in tip for tip in report["how_to_talk_to_user"])
