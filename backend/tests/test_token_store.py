from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app.agent.client import HelixApiClient
from app.agent.token_store import clear_cached_token, load_cached_token, save_cached_token
from app.agent.tools import call_tool


def test_token_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / ".helix-agent-token"
    assert load_cached_token(path) is None
    save_cached_token("abc123token", path)
    assert load_cached_token(path) == "abc123token"
    assert clear_cached_token(path) is True
    assert load_cached_token(path) is None
    assert clear_cached_token(path) is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX file mode check")
def test_token_file_created_with_owner_only_mode(tmp_path: Path) -> None:
    path = tmp_path / ".helix-agent-token"
    save_cached_token("abc123token", path)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_from_env_prefers_env_over_cache(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / ".helix-agent-token"
    save_cached_token("cached-token", path)
    monkeypatch.setattr("app.agent.client.load_cached_token", lambda: load_cached_token(path))
    monkeypatch.delenv("HELIX_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("HELIX_ACCESS_TOKEN", "env-token")
    client = HelixApiClient.from_env()
    assert client.token == "env-token"


def test_from_env_reads_cache_when_env_missing(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / ".helix-agent-token"
    save_cached_token("cached-token", path)
    monkeypatch.setattr("app.agent.client.load_cached_token", lambda: load_cached_token(path))
    monkeypatch.delenv("HELIX_ACCESS_TOKEN", raising=False)
    client = HelixApiClient.from_env()
    assert client.token == "cached-token"


def test_login_persists_token_for_next_client(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / ".helix-agent-token"
    monkeypatch.setattr("app.agent.client.save_cached_token", lambda token: save_cached_token(token, path))
    monkeypatch.setattr("app.agent.client.load_cached_token", lambda: load_cached_token(path))
    monkeypatch.delenv("HELIX_ACCESS_TOKEN", raising=False)

    client = HelixApiClient(base_url="http://example.invalid", token=None)

    def fake_login_raw(*_args, **_kwargs):
        return {"access_token": "persisted-token-xyz", "token_type": "bearer"}

    monkeypatch.setattr(client, "_request_raw", fake_login_raw)
    result = client.login("admin", "secret")
    assert result["access_token_present"] is True
    assert "persisted-token-xyz" not in str(result)
    assert load_cached_token(path) == "persisted-token-xyz"

    next_client = HelixApiClient.from_env()
    assert next_client.token == "persisted-token-xyz"


def test_login_tool_keeps_masked_token_metadata(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / ".helix-agent-token"
    monkeypatch.setattr("app.agent.client.save_cached_token", lambda token: save_cached_token(token, path))
    monkeypatch.delenv("HELIX_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("HELIX_USERNAME", "admin")
    monkeypatch.setenv("HELIX_PASSWORD", "secret")

    client = HelixApiClient(base_url="http://example.invalid", token=None)

    def fake_login_raw(*_args, **_kwargs):
        return {"access_token": "persisted-token-xyz", "token_type": "bearer"}

    monkeypatch.setattr(client, "_request_raw", fake_login_raw)
    wrapped = call_tool("login", {}, client=client)
    assert wrapped["ok"] is True
    result = wrapped["result"]
    assert result["access_token_present"] is True
    assert result["token_type"] == "bearer"
    assert result["access_token_masked"] == "pers...-xyz"
    assert result["token_cache_path"] == str(path)
    assert "persisted-token-xyz" not in str(wrapped)


def test_logout_clears_cache_and_env(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / ".helix-agent-token"
    save_cached_token("to-clear", path)
    monkeypatch.setattr("app.agent.client.clear_cached_token", lambda: clear_cached_token(path))
    monkeypatch.setenv("HELIX_ACCESS_TOKEN", "to-clear")
    client = HelixApiClient(base_url="http://example.invalid", token="to-clear")
    result = call_tool("logout", {}, client=client)
    assert result["ok"] is True
    assert client.token is None
    assert "HELIX_ACCESS_TOKEN" not in os.environ
    assert load_cached_token(path) is None


def test_token_file_is_gitignored() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    assert "backend/.helix-agent-token" in gitignore
