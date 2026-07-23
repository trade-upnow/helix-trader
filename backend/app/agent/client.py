"""HTTP adapter that reuses the existing FastAPI bot APIs."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from app.agent.env import load_backend_env
from app.agent.safety import redact_text, redact_value
from app.agent.token_store import clear_cached_token, load_cached_token, save_cached_token


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class AgentApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(redact_text(message))
        self.status_code = status_code
        self.payload = redact_value(payload)


@dataclass
class HelixApiClient:
    base_url: str = DEFAULT_BASE_URL
    token: Optional[str] = None
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "HelixApiClient":
        load_backend_env()
        base_url = os.getenv("HELIX_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        # Priority: process env > local token cache > empty.
        token = os.getenv("HELIX_ACCESS_TOKEN") or load_cached_token() or None
        timeout_raw = os.getenv("HELIX_HTTP_TIMEOUT_SECONDS", "30")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 30.0
        return cls(base_url=base_url, token=token, timeout_seconds=timeout_seconds)

    def with_token(self, token: str | None) -> "HelixApiClient":
        return HelixApiClient(
            base_url=self.base_url,
            token=token,
            timeout_seconds=self.timeout_seconds,
        )

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health", auth=False)

    def login(self, username: str, password: str) -> dict[str, Any]:
        # Login must read the raw token before redaction, then only return a masked view.
        payload = self._request_raw(
            "POST",
            "/api/auth/login",
            body={"username": username, "password": password},
            auth=False,
        )
        token = payload.get("access_token") if isinstance(payload, dict) else None
        token_path = None
        if isinstance(token, str) and token:
            self.token = token
            os.environ["HELIX_ACCESS_TOKEN"] = token
            token_path = str(save_cached_token(token))
        return {
            "detail": "Login succeeded",
            "token_type": payload.get("token_type", "bearer") if isinstance(payload, dict) else "bearer",
            "access_token_present": bool(token),
            "access_token_masked": _mask_token(token) if isinstance(token, str) else None,
            "token_cache_path": token_path,
            "note": (
                "Token stored in process memory, HELIX_ACCESS_TOKEN, and local cache file "
                "backend/.helix-agent-token for later CLI/MCP commands. "
                "Do not paste it into chats or public posts. Use logout to clear the cache."
            ),
        }

    def logout(self) -> dict[str, Any]:
        cleared_file = clear_cached_token()
        had_env = bool(os.environ.pop("HELIX_ACCESS_TOKEN", None))
        self.token = None
        return {
            "detail": "Logged out",
            "cleared_token_cache": cleared_file,
            "cleared_env_token": had_env,
            "note": "Local token cache and HELIX_ACCESS_TOKEN were cleared for this process.",
        }

    def list_strategies(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/strategies")

    def list_markets(self, exchange: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"exchange": exchange})
        return self.request("GET", f"/api/bot/markets?{query}")

    def save_credentials(
        self,
        *,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: str | None = None,
        use_testnet: bool = True,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/api/bot/credentials",
            body={
                "exchange": exchange,
                "api_key": api_key,
                "api_secret": api_secret,
                "passphrase": passphrase,
                "use_testnet": use_testnet,
            },
        )

    def get_status(self) -> dict[str, Any]:
        return self.request("GET", "/api/bot/status")

    def get_trades(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/bot/trades")

    def start_bot(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/bot/start", body=payload)

    def update_bot_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", "/api/bot/config", body=payload)

    def stop_bot(self, *, close_all: bool = False) -> dict[str, Any]:
        return self.request("POST", "/api/bot/stop", body={"close_all": close_all})

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        return redact_value(self._request_raw(method, path, body=body, auth=auth))

    def _request_raw(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        if auth:
            if not self.token:
                raise AgentApiError(
                    "Missing access token. Call login first or set HELIX_ACCESS_TOKEN locally."
                )
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            detail: Any
            try:
                detail = json.loads(raw) if raw else {"detail": exc.reason}
            except json.JSONDecodeError:
                detail = {"detail": raw or str(exc.reason)}
            message = _extract_detail(detail) or f"HTTP {exc.code}"
            raise AgentApiError(message, status_code=exc.code, payload=detail) from None
        except urllib.error.URLError as exc:
            raise AgentApiError(
                f"Cannot reach Helix API at {self.base_url}: {exc.reason}"
            ) from None


def _extract_detail(payload: Any) -> str | None:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if detail is not None:
            return str(detail)
    return None


def _mask_token(token: str) -> str:
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}...{token[-4:]}"
