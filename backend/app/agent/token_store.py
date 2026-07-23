"""Local access-token cache for CLI/MCP sessions."""

from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOKEN_FILE = BACKEND_ROOT / ".helix-agent-token"


def token_file_path() -> Path:
    return DEFAULT_TOKEN_FILE


def load_cached_token(path: Path | None = None) -> str | None:
    token_path = path or DEFAULT_TOKEN_FILE
    if not token_path.exists():
        return None
    try:
        value = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def save_cached_token(token: str, path: Path | None = None) -> Path:
    token_path = path or DEFAULT_TOKEN_FILE
    token_path.parent.mkdir(parents=True, exist_ok=True)
    data = (token.strip() + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    # Create/truncate with owner-only mode when the platform honors it.
    fd = os.open(str(token_path), flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    try:
        token_path.chmod(0o600)
    except OSError:
        # Best-effort on platforms that do not support POSIX modes.
        pass
    return token_path


def clear_cached_token(path: Path | None = None) -> bool:
    token_path = path or DEFAULT_TOKEN_FILE
    if not token_path.exists():
        return False
    try:
        token_path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        raise
    return True
