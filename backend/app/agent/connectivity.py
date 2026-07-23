"""Lightweight exchange connectivity probes for doctor (no secrets echoed)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from app.agent.env import DEFAULT_ENV_FILE, load_backend_env
from app.agent.okx_probe import okx_probe_request_headers


OKX_PUBLIC_TIME_URL = "https://www.okx.com/api/v5/public/time"
OKX_HOST = "www.okx.com"
DEFAULT_LOCAL_PROXY = "http://127.0.0.1:7890"
MAX_ERROR_CHARS = 800


def configured_exchange_proxy() -> Optional[str]:
    for key in ("EXCHANGE_HTTPS_PROXY", "EXCHANGE_PROXY_URL", "EXCHANGE_HTTP_PROXY"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return None


def probe_okx_public_time(
    timeout_seconds: float = 8.0,
    *,
    proxy: Optional[str] = None,
    use_env_proxy: bool = True,
) -> dict[str, Any]:
    """Hit OKX public time API.

    If ``proxy`` is provided, use it. Else when ``use_env_proxy`` is True, use
    EXCHANGE_* env vars. Pass ``use_env_proxy=False`` and ``proxy=None`` for a
    direct (no-proxy) probe.
    """
    if proxy is None and use_env_proxy:
        proxy = configured_exchange_proxy()
    return _probe(proxy=proxy, timeout_seconds=timeout_seconds)


def diagnose_okx_network(timeout_seconds: float = 5.0) -> dict[str, Any]:
    """First-time / doctor network diagnosis for agents.

    Order: direct OKX → configured proxy (if any) → default 7890 → ask user.
    """
    attempts: list[dict[str, Any]] = []
    configured = configured_exchange_proxy()

    direct = _probe(proxy=None, timeout_seconds=timeout_seconds)
    attempts.append({"mode": "direct", "proxy": None, **direct})
    if direct.get("ok"):
        return {
            "ok": True,
            "recommendation": "direct",
            "proxy_to_use": None,
            "configured_proxy": configured,
            "should_clear_proxy_config": bool(configured),
            "user_message": (
                "本机可直连 OKX，无需代理。"
                + (" 若 .env 里还写着代理地址，可以删掉或留空。" if configured else "")
            ),
            "agent_action": (
                "Do not ask the user for a proxy. Prefer leaving EXCHANGE_PROXY_URL empty. "
                "If a proxy is already set and unused, suggest removing it."
            ),
            "attempts": attempts,
        }

    if configured:
        via_configured = _probe(proxy=configured, timeout_seconds=timeout_seconds)
        attempts.append({"mode": "configured", "proxy": configured, **via_configured})
        if via_configured.get("ok"):
            return {
                "ok": True,
                "recommendation": "use_configured",
                "proxy_to_use": configured,
                "configured_proxy": configured,
                "should_clear_proxy_config": False,
                "user_message": f"已通过当前代理访问 OKX（{configured}）。",
                "agent_action": "Keep the existing EXCHANGE_PROXY_URL. Use the same proxy for pip/setup if installing deps.",
                "attempts": attempts,
            }

    if configured != DEFAULT_LOCAL_PROXY:
        via_default = _probe(proxy=DEFAULT_LOCAL_PROXY, timeout_seconds=timeout_seconds)
        attempts.append({"mode": "default_7890", "proxy": DEFAULT_LOCAL_PROXY, **via_default})
        if via_default.get("ok"):
            return {
                "ok": True,
                "recommendation": "use_default_7890",
                "proxy_to_use": DEFAULT_LOCAL_PROXY,
                "configured_proxy": configured,
                "should_clear_proxy_config": False,
                "user_message": (
                    f"直连不通，但本机默认代理 {DEFAULT_LOCAL_PROXY} 可以访问 OKX。"
                    "我会用这个代理继续配置。"
                ),
                "agent_action": (
                    f"Set EXCHANGE_PROXY_URL={DEFAULT_LOCAL_PROXY} in backend/.env (do not echo secrets). "
                    "Use the same proxy for pip/npm install during setup."
                ),
                "attempts": attempts,
            }

    last_detail = attempts[-1].get("detail") if attempts else "unreachable"
    if _looks_like_cloudflare_client_block(last_detail):
        last_detail = (
            f"{last_detail} "
            "(Cloudflare 常拦截 urllib 等默认客户端指纹；直连/代理探测均需显式 User-Agent，与 ccxt 一致。)"
        )
    return {
        "ok": False,
        "recommendation": "ask_user_for_proxy",
        "proxy_to_use": None,
        "configured_proxy": configured,
        "should_clear_proxy_config": False,
        "user_message": (
            "目前访问不了 OKX（www.okx.com）。请告诉我本机代理地址，"
            "例如 http://127.0.0.1:7890（端口按你的客户端为准）。"
        ),
        "agent_action": (
            "Ask the user only for the local proxy URL/port, in plain language. "
            "After they provide it, write EXCHANGE_PROXY_URL and retry this diagnosis; "
            "use the same proxy for dependency installs."
        ),
        "detail": last_detail,
        "attempts": attempts,
    }


def persist_recommended_exchange_proxy(
    network: dict[str, Any],
    *,
    env_path: Path | None = None,
) -> dict[str, Any]:
    """Write EXCHANGE_PROXY_URL when diagnosis recommends a proxy and .env has none."""
    target = env_path or DEFAULT_ENV_FILE
    proxy = (network.get("proxy_to_use") or "").strip()
    if not network.get("ok") or not proxy:
        return {"applied": False, "reason": "no_proxy_recommended", "env_path": str(target)}

    if not target.exists():
        return {"applied": False, "reason": "env_file_missing", "env_path": str(target)}

    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    key = "EXCHANGE_PROXY_URL"
    updated = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            current = line.split("=", 1)[1].strip()
            if current:
                return {
                    "applied": False,
                    "reason": "already_set",
                    "env_path": str(target),
                    "existing_proxy": current,
                }
            new_lines.append(f"{key}={proxy}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={proxy}")
    target.write_text("\n".join(new_lines) + ("\n" if new_lines else ""), encoding="utf-8")
    os.environ[key] = proxy
    return {"applied": True, "proxy": proxy, "env_path": str(target)}


def _okx_api_success(payload: Any) -> bool:
    return isinstance(payload, dict) and str(payload.get("code")) == "0"


def _looks_like_cloudflare_client_block(detail: str | None) -> bool:
    if not detail:
        return False
    lowered = detail.lower()
    return "403" in lowered and ("1010" in lowered or "browser_signature" in lowered)


def _probe(*, proxy: Optional[str], timeout_seconds: float) -> dict[str, Any]:
    """Probe OKX public time; direct and proxied paths share explicit probe headers."""
    headers = okx_probe_request_headers()
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers) if handlers else urllib.request.build_opener()
    request = urllib.request.Request(OKX_PUBLIC_TIME_URL, headers=headers)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload: Any
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"raw": raw[:MAX_ERROR_CHARS]}
            api_ok = response.status == 200 and _okx_api_success(payload)
            detail = "OKX public time reachable"
            if response.status == 200 and not api_ok:
                detail = _clip(f"HTTP 200 but unexpected OKX payload: {raw[:200]}")
            return {
                "ok": api_ok,
                "status_code": response.status,
                "proxy_configured": bool(proxy),
                "url": OKX_PUBLIC_TIME_URL,
                "host": OKX_HOST,
                "detail": detail,
                "response_code": payload.get("code") if isinstance(payload, dict) else None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": exc.code,
            "proxy_configured": bool(proxy),
            "url": OKX_PUBLIC_TIME_URL,
            "host": OKX_HOST,
            "detail": _clip(f"HTTP {exc.code}: {body or exc.reason}"),
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "status_code": None,
            "proxy_configured": bool(proxy),
            "url": OKX_PUBLIC_TIME_URL,
            "host": OKX_HOST,
            "detail": _clip(f"URL error: {exc.reason}"),
        }
    except Exception as exc:  # noqa: BLE001 - surface full probe failure to doctor
        return {
            "ok": False,
            "status_code": None,
            "proxy_configured": bool(proxy),
            "url": OKX_PUBLIC_TIME_URL,
            "host": OKX_HOST,
            "detail": _clip(f"{type(exc).__name__}: {exc}"),
        }


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_ERROR_CHARS:
        return text
    return text[: MAX_ERROR_CHARS - 3] + "..."
