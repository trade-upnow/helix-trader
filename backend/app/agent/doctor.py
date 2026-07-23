"""Local environment checks for agents and humans."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from app.agent.client import AgentApiError, HelixApiClient
from app.agent.connectivity import diagnose_okx_network, persist_recommended_exchange_proxy
from app.agent.env import load_backend_env
from app.agent.safety import sensitive_env_presence
from app.agent.status_utils import status_has_credential


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
SETUP_SCRIPT = "scripts/setup_backend.sh"


def run_doctor(client: HelixApiClient | None = None) -> dict[str, Any]:
    load_backend_env()
    client = client or HelixApiClient.from_env()
    checks: list[dict[str, Any]] = []
    next_steps: list[str] = []

    venv_dir = BACKEND_ROOT / ".venv"
    venv_ok = venv_dir.exists()
    checks.append(
        {
            "name": "backend_venv",
            "status": "ok" if venv_ok else "warn",
            "detail": "present" if venv_ok else "missing (run setup script)",
        }
    )

    py_ok = sys.version_info >= (3, 10)
    checks.append(
        {
            "name": "python_version",
            "status": "ok" if py_ok else "fail",
            "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "note": "Recommend Python 3.12. macOS system python3 is often 3.9 and may fail installing ccxt.",
        }
    )
    if not py_ok:
        next_steps.append(
            "Install Python 3.10+ (recommend 3.12), remove backend/.venv, then re-run "
            "`HELIX_PYTHON=python3.12 bash scripts/setup_backend.sh` "
            "(or `python3.12 -m venv backend/.venv`)."
        )

    required_modules = ["fastapi", "uvicorn", "sqlalchemy", "ccxt", "pydantic_settings"]
    missing_modules = [name for name in required_modules if importlib.util.find_spec(name) is None]
    checks.append(
        {
            "name": "python_dependencies",
            "status": "ok" if not missing_modules else "fail",
            "detail": "all present" if not missing_modules else f"missing: {', '.join(missing_modules)}",
        }
    )

    env_path = BACKEND_ROOT / ".env"
    env_ok = env_path.exists()
    checks.append(
        {
            "name": "backend_env_file",
            "status": "ok" if env_ok else "warn",
            "detail": "present" if env_ok else "missing (.env.example can be copied)",
        }
    )

    needs_bootstrap = (not venv_ok) or (not env_ok) or bool(missing_modules)
    if needs_bootstrap:
        next_steps.append(
            f"First-time setup needed. Run `bash {SETUP_SCRIPT}` yourself (it auto-detects "
            "OKX network / proxy for pip). Tell the user in plain language that you are "
            "doing first-time setup — do not ask them about virtualenv jargon."
        )
    if missing_modules and not needs_bootstrap:
        next_steps.append("In backend/, run: pip install -r requirements.txt (use proxy if diagnose says so).")
    if not env_ok and not needs_bootstrap:
        next_steps.append("Copy backend/.env.example to backend/.env, then fill login fields locally.")

    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./helix.db")
    db_file_present = (BACKEND_ROOT / "helix.db").exists()
    checks.append(
        {
            "name": "database_file",
            "status": "ok" if db_file_present or not db_url.startswith("sqlite") else "warn",
            "detail": "present" if db_file_present else "not created yet (appears after first backend start)",
        }
    )

    sensitive = sensitive_env_presence(
        [
            "JWT_SECRET",
            "API_ENCRYPTION_KEY",
            "ADMIN_PASSWORD",
            "CLIENT_PASSWORD",
            "HELIX_ACCESS_TOKEN",
            "HELIX_USERNAME",
            "HELIX_PASSWORD",
            "HELIX_EXCHANGE_API_KEY",
            "HELIX_EXCHANGE_API_SECRET",
            "HELIX_EXCHANGE_PASSPHRASE",
            "HELIX_ALLOW_LIVE_TRADING",
            "EXCHANGE_PROXY_URL",
            "EXCHANGE_HTTP_PROXY",
            "EXCHANGE_HTTPS_PROXY",
        ]
    )
    checks.append(
        {
            "name": "sensitive_env_presence",
            "status": "ok",
            "detail": sensitive,
            "note": "Values are never returned; only presence is reported.",
        }
    )

    api_status = "fail"
    api_detail = "unreachable"
    try:
        health = client.health()
        if health.get("status") == "ok":
            api_status = "ok"
            api_detail = "backend /health ok"
        else:
            api_detail = f"unexpected health payload keys: {sorted(health.keys())}"
    except AgentApiError as exc:
        api_detail = str(exc)
    checks.append({"name": "backend_health", "status": api_status, "detail": api_detail})
    if api_status != "ok":
        next_steps.append(
            "Start backend from backend/: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
        )

    auth_status = "warn"
    auth_detail = (
        "Access token missing; run login (writes backend/.helix-agent-token) "
        "or set HELIX_ACCESS_TOKEN"
    )
    status_payload: dict[str, Any] | None = None
    if client.token:
        try:
            status_payload = client.get_status()
            auth_status = "ok"
            auth_detail = f"authenticated; bot status={status_payload.get('status')}"
        except AgentApiError as exc:
            auth_status = "fail"
            auth_detail = str(exc)
            next_steps.append("Token may be invalid. Re-run login with local credentials.")
    else:
        next_steps.append(
            "Run login using local HELIX_USERNAME/HELIX_PASSWORD (token is cached to "
            "backend/.helix-agent-token for later CLI/MCP commands), or set "
            "HELIX_ACCESS_TOKEN. Do not paste passwords into public chats."
        )
    checks.append({"name": "auth_session", "status": auth_status, "detail": auth_detail})

    if auth_status == "ok":
        try:
            strategies = client.list_strategies()
            checks.append(
                {
                    "name": "strategies_readable",
                    "status": "ok",
                    "detail": f"{len(strategies)} strateg(ies) available",
                }
            )
        except AgentApiError as exc:
            checks.append(
                {"name": "strategies_readable", "status": "fail", "detail": str(exc)}
            )
            next_steps.append("Authenticated strategy listing failed; verify backend logs.")
    else:
        checks.append(
            {
                "name": "strategies_readable",
                "status": "skip",
                "detail": "skipped until authentication succeeds",
            }
        )

    env_exchange_key = sensitive.get("HELIX_EXCHANGE_API_KEY") == "present"
    saved_credential = status_has_credential(status_payload)
    credentials_howto = (
        "Save exchange credentials into the backend DB (required for mode≠not_configured). "
        "Path A (.env as input, good for reuse): put HELIX_EXCHANGE_* in backend/.env, then "
        "`python -m app.agent save-credentials --exchange <okx|binance> --testnet "
        "--confirm-save-credentials`. "
        "Path B (interactive, no .env keys needed): "
        "`python -m app.agent save-credentials --exchange <okx|binance> --testnet "
        "--prompt --confirm-save-credentials`. "
        "Judge readiness with doctor / get_runtime_mode / exchange_credentials — "
        "never by grepping .env for HELIX_EXCHANGE_*."
    )
    if env_exchange_key and not saved_credential:
        checks.append(
            {
                "name": "exchange_credentials",
                "status": "warn",
                "detail": (
                    "HELIX_EXCHANGE_* env vars are present, but no credential is saved "
                    "in the backend database yet (.env alone is not enough)"
                ),
            }
        )
        next_steps.append(credentials_howto)
    elif not env_exchange_key and not saved_credential:
        checks.append(
            {
                "name": "exchange_credentials",
                "status": "warn",
                "detail": (
                    "no saved exchange credential in backend database "
                    "(.env HELIX_EXCHANGE_* also empty — either is fine as input, "
                    "but save-credentials is still required)"
                ),
            }
        )
        next_steps.append(credentials_howto)
    else:
        detail = "saved credential detected in backend database (source of truth for mode)"
        if saved_credential and not env_exchange_key:
            detail = (
                "saved credential detected in backend database; "
                ".env HELIX_EXCHANGE_* may stay empty — interactive/--prompt save path is normal"
            )
        checks.append(
            {
                "name": "exchange_credentials",
                "status": "ok",
                "detail": detail,
            }
        )

    network = diagnose_okx_network()
    proxy_persist = persist_recommended_exchange_proxy(network)
    if proxy_persist.get("applied"):
        load_backend_env()
        network = {
            **network,
            "proxy_persisted_to_env": True,
            "proxy_persist": proxy_persist,
        }
        next_steps.append(
            f"Wrote EXCHANGE_PROXY_URL={proxy_persist['proxy']} to backend/.env. "
            "If uvicorn is already running, restart it once so the backend loads the proxy."
        )
    elif proxy_persist.get("reason") == "already_set":
        network = {**network, "proxy_persist": proxy_persist}
    checks.append(
        {
            "name": "okx_public_connectivity",
            "status": "ok" if network.get("ok") else "warn",
            "detail": {
                "recommendation": network.get("recommendation"),
                "proxy_to_use": network.get("proxy_to_use"),
                "configured_proxy": network.get("configured_proxy"),
                "should_clear_proxy_config": network.get("should_clear_proxy_config"),
                "user_message": network.get("user_message"),
                "attempts": network.get("attempts"),
            },
            "note": "Probe order: direct www.okx.com → configured proxy → http://127.0.0.1:7890 → ask user.",
        }
    )
    if network.get("agent_action"):
        next_steps.append(str(network["agent_action"]))
    if not network.get("ok"):
        next_steps.append(
            "Network not ready for OKX. Speak with network.user_message; only ask the user "
            "for a local proxy URL/port if recommendation is ask_user_for_proxy."
        )

    checks.append(
        {
            "name": "optional_frontend",
            "status": "ok",
            "detail": "available after backend is up",
            "note": (
                "When first-time config succeeds, proactively tell the user there is a local "
                "web console (frontend/ → npm install && npm run dev → http://localhost:3000) "
                "and ask whether to start it. Login with ADMIN_USERNAME/ADMIN_PASSWORD "
                "(example defaults admin / ChangeMe123!); do not suggest CLIENT_USERNAME. "
                "Do not wait for them to ask about a webpage."
            ),
        }
    )

    if sensitive.get("HELIX_ALLOW_LIVE_TRADING") == "present":
        next_steps.append(
            "HELIX_ALLOW_LIVE_TRADING is present. Keep use_testnet=true unless the user "
            "explicitly confirms live trading."
        )

    overall = "ok"
    if any(item["status"] == "fail" for item in checks):
        overall = "fail"
    elif any(item["status"] == "warn" for item in checks):
        overall = "warn"

    if not next_steps:
        next_steps.append(
            "Ready for testnet preview/start. After the user confirms the first successful "
            "setup, proactively offer the local web console."
        )

    return {
        "overall": overall,
        "repo_root": str(REPO_ROOT),
        "backend_root": str(BACKEND_ROOT),
        "api_base_url": client.base_url,
        "setup_script": SETUP_SCRIPT,
        "network": network,
        "checks": checks,
        "next_steps": next_steps,
        "how_to_talk_to_user": [
            "Users usually say “帮我启动机器人”, not “请检查虚拟环境”. Handle setup silently.",
            "Never ask the user to say “不要读取密钥”; that is your hard rule, not their script.",
            "Ask which exchange (okx/binance); do not silently default to OKX.",
            "Offer two strategies; recommend trend_following_core; always preview_bot_config before start.",
            "Do not dump install jargon unless they ask for technical detail.",
            "After first config works, offer the local webpage; login = ADMIN_* not CLIENT_*.",
            "API_ENCRYPTION_KEY may stay empty; never print or casually rotate it after credentials exist.",
            "MCP host config is in this runtime repo examples/mcp/ (and docs/MCP_SETUP.md), not in the skill plugin bundle.",
            "On stop/关掉策略: default close_all=false. If positions exist and user did not ask to flatten, ask 只停策略还是同时平机器人仓 — never invent close_all=true.",
            "Credentials: trust doctor/get_runtime_mode/exchange_credentials. "
            "Never grep .env HELIX_EXCHANGE_* to decide if configured — --prompt saves to DB only.",
        ],
        "security_reminder": (
            "Do not print secrets, tokens, API_ENCRYPTION_KEY, or .env contents. "
            "Do not ask users to paste API keys into public chats. "
            "Never require the user to remind you about secret handling."
        ),
    }
