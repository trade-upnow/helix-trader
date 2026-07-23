"""OKX public HTTP probe headers (stdlib-only; safe before full deps install).

Cloudflare in front of www.okx.com rejects Python urllib's default User-Agent
(HTTP 403 / error 1010). That applies to direct and proxied requests alike —
never rely on urllib/curl default client fingerprints for OKX probes.
"""

from __future__ import annotations

OKX_PROBE_USER_AGENT_FALLBACK = "python-requests/2.32.3"


def okx_probe_user_agent() -> str:
    try:
        from requests.utils import default_user_agent

        return default_user_agent()
    except ImportError:
        return OKX_PROBE_USER_AGENT_FALLBACK


def okx_probe_request_headers() -> dict[str, str]:
    user_agent = okx_probe_user_agent().strip()
    if not user_agent:
        raise RuntimeError("OKX probe requires a non-empty User-Agent")
    lowered = user_agent.lower()
    if "python-urllib" in lowered:
        raise RuntimeError("OKX probe must not use urllib default User-Agent")
    return {
        "Accept": "application/json",
        "User-Agent": user_agent,
    }
