from __future__ import annotations

from pathlib import Path

from app.agent.env import load_backend_env


def test_load_backend_env_does_not_override_existing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "HELIX_API_BASE_URL=http://127.0.0.1:8000",
                "HELIX_PASSWORD=from-file",
                "HELIX_EXCHANGE_API_KEY='quoted-key'",
                "HELIX_EXCHANGE_API_SECRET=secret-value # local comment",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HELIX_PASSWORD", "already-set")
    monkeypatch.delenv("HELIX_API_BASE_URL", raising=False)
    monkeypatch.delenv("HELIX_EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("HELIX_EXCHANGE_API_SECRET", raising=False)

    load_backend_env(env_file)

    assert __import__("os").environ["HELIX_PASSWORD"] == "already-set"
    assert __import__("os").environ["HELIX_API_BASE_URL"] == "http://127.0.0.1:8000"
    assert __import__("os").environ["HELIX_EXCHANGE_API_KEY"] == "quoted-key"
    assert __import__("os").environ["HELIX_EXCHANGE_API_SECRET"] == "secret-value"
