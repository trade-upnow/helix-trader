"""Shared tool schemas and handlers for MCP and CLI."""

from __future__ import annotations

import os
from typing import Any, Callable

from app.agent.client import AgentApiError, HelixApiClient
from app.agent.doctor import run_doctor
from app.agent.status_utils import status_has_credential
from app.agent.metadata import (
    EXAMPLE_CONFIGS,
    TOOL_RISK_LEVELS,
    enrich_strategy_payload,
    explain_config,
    get_parameter_spec,
    list_parameter_specs,
    list_strategy_specs,
    merge_preview_config,
)
from app.agent.safety import (
    SafetyError,
    ensure_close_all_confirmed,
    ensure_credential_save_confirmed,
    ensure_live_trading_allowed,
    redact_value,
    summarize_start_config,
)


ToolHandler = Callable[[HelixApiClient, dict[str, Any]], dict[str, Any]]


def _start_properties() -> dict[str, Any]:
    return {
        "strategy_id": {
            "type": "string",
            "enum": ["trend_following_core", "trend_breakout_accel"],
        },
        "exchange": {"type": "string", "enum": ["binance", "okx"]},
        "symbol": {"type": "string", "default": "BTC/USDT:USDT"},
        "market_type": {"type": "string", "default": "usdt_perp"},
        "leverage": {"type": "number"},
        "position_size_pct": {"type": "number"},
        "stop_loss_pct": {"type": "number"},
        "take_profit_pct": {"type": "number"},
        "max_drawdown_pct": {"type": "number"},
        "max_order_notional_usdt": {"type": "number"},
        "max_position_notional_usdt": {"type": "number"},
        "close_all_on_stop": {"type": "boolean", "default": True},
        "use_testnet": {"type": "boolean", "default": True},
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "health_check",
        "description": "Check whether the local Helix backend /health endpoint is reachable.",
        "risk_level": TOOL_RISK_LEVELS["health_check"],
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "doctor",
        "description": (
            "Run first-time readiness checks for when the user asks to start the bot. "
            "Includes OKX network diagnosis (direct → default 7890 → ask user for proxy), "
            "credential two-step guidance, and how_to_talk_to_user hints. "
            "Never returns secret values. Speak to users in plain language."
        ),
        "risk_level": TOOL_RISK_LEVELS["doctor"],
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "login",
        "description": (
            "Log in to the local Helix API. Prefer HELIX_USERNAME/HELIX_PASSWORD env vars. "
            "Do not ask users to paste passwords into public chats. Returns only a masked token view. "
            "Persists token to backend/.helix-agent-token for later CLI/MCP commands."
        ),
        "risk_level": TOOL_RISK_LEVELS["login"],
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "logout",
        "description": (
            "Clear the local Helix access token cache and HELIX_ACCESS_TOKEN from the current process. "
            "Does not revoke the JWT server-side."
        ),
        "risk_level": TOOL_RISK_LEVELS["logout"],
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_strategies",
        "description": "List available strategies with default params, docs, and risk notes.",
        "risk_level": TOOL_RISK_LEVELS["list_strategies"],
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_markets",
        "description": "List tradeable symbols for an exchange from the backend market catalog.",
        "risk_level": TOOL_RISK_LEVELS["list_markets"],
        "inputSchema": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string", "enum": ["binance", "okx"]},
            },
            "required": ["exchange"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explain_parameters",
        "description": "Explain strategy/runtime parameters, defaults, recommended ranges, and risks.",
        "risk_level": TOOL_RISK_LEVELS["explain_parameters"],
        "inputSchema": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional parameter names. Omit to return all.",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_runtime_mode",
        "description": (
            "Report testnet, live, or not_configured. not_configured means no exchange "
            "credential is saved yet (filling HELIX_EXCHANGE_* in .env alone is not enough). "
            "Source of truth is the saved ApiCredential via /api/bot/status."
        ),
        "risk_level": TOOL_RISK_LEVELS["get_runtime_mode"],
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_bot_status",
        "description": "Get current bot status, balances, positions, and active config.",
        "risk_level": TOOL_RISK_LEVELS["get_bot_status"],
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_recent_trades",
        "description": "Get recent bot trade records for the authenticated user.",
        "risk_level": TOOL_RISK_LEVELS["get_recent_trades"],
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "preview_bot_config",
        "description": (
            "Dry-run merge of strategy defaults and user overrides. Does not place orders. "
            "Always call this before start_bot."
        ),
        "risk_level": TOOL_RISK_LEVELS["preview_bot_config"],
        "inputSchema": {
            "type": "object",
            "properties": _start_properties(),
            "required": ["strategy_id", "exchange"],
            "additionalProperties": False,
        },
    },
    {
        "name": "save_exchange_credentials",
        "description": (
            "Save exchange API credentials to the local Helix backend. "
            "Prefer HELIX_EXCHANGE_* env vars or local interactive input. Direct secret "
            "arguments are accepted only in trusted private agent sessions. Requires "
            "confirm_save_credentials=true. Never publish secrets."
        ),
        "risk_level": TOOL_RISK_LEVELS["save_exchange_credentials"],
        "inputSchema": {
            "type": "object",
            "properties": {
                "exchange": {"type": "string", "enum": ["binance", "okx"]},
                "api_key": {
                    "type": "string",
                    "description": "Optional direct secret. Prefer HELIX_EXCHANGE_API_KEY.",
                },
                "api_secret": {
                    "type": "string",
                    "description": "Optional direct secret. Prefer HELIX_EXCHANGE_API_SECRET.",
                },
                "passphrase": {
                    "type": "string",
                    "description": "Optional OKX passphrase. Prefer HELIX_EXCHANGE_PASSPHRASE.",
                },
                "use_testnet": {"type": "boolean", "default": True},
                "confirm_save_credentials": {"type": "boolean", "default": False},
            },
            "required": ["exchange", "confirm_save_credentials"],
            "additionalProperties": False,
        },
    },
    {
        "name": "start_bot",
        "description": (
            "Start the trading bot. Default use_testnet=true. Live trading requires "
            "HELIX_ALLOW_LIVE_TRADING=true and confirm_live_trading=true after explicit user confirmation."
        ),
        "risk_level": TOOL_RISK_LEVELS["start_bot"],
        "inputSchema": {
            "type": "object",
            "properties": {
                **_start_properties(),
                "confirm_live_trading": {"type": "boolean", "default": False},
            },
            "required": ["strategy_id", "exchange"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_bot_config",
        "description": "Update runtime risk parameters of a running bot session.",
        "risk_level": TOOL_RISK_LEVELS["update_bot_config"],
        "inputSchema": {
            "type": "object",
            "properties": {
                "leverage": {"type": "number"},
                "position_size_pct": {"type": "number"},
                "stop_loss_pct": {"type": "number"},
                "take_profit_pct": {"type": "number"},
                "max_drawdown_pct": {"type": "number"},
                "max_order_notional_usdt": {"type": "number"},
                "max_position_notional_usdt": {"type": "number"},
                "close_all_on_stop": {"type": "boolean"},
                "confirm_live_trading": {"type": "boolean", "default": False},
            },
            "required": [
                "leverage",
                "position_size_pct",
                "stop_loss_pct",
                "take_profit_pct",
                "max_drawdown_pct",
                "max_order_notional_usdt",
                "max_position_notional_usdt",
            ],
            "additionalProperties": False,
        },
    },
    {
        "name": "stop_bot",
        "description": (
            "Stop the bot. Default close_all=false (stop strategy only; leave positions). "
            "When the user only says 停止机器人/关掉策略/停止策略 without choosing flatten, "
            "do NOT invent close_all=true. Prefer get_bot_status, then ask: "
            "只停止策略（保留仓位），还是同时平掉机器人管理的仓位？ "
            "If open positions exist and close_all is still false without "
            "confirm_stop_keep_positions=true, this tool refuses to stop and returns ask_user. "
            "Paths after user chooses: (1) keep positions → close_all=false + "
            "confirm_stop_keep_positions=true; (2) flatten → close_all=true + "
            "confirm_close_all=true. close_all only flattens bot-managed positions."
        ),
        "risk_level": TOOL_RISK_LEVELS["stop_bot"],
        "inputSchema": {
            "type": "object",
            "properties": {
                "close_all": {"type": "boolean", "default": False},
                "confirm_close_all": {"type": "boolean", "default": False},
                "confirm_stop_keep_positions": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Required when close_all=false and open positions exist: "
                        "user explicitly chose stop-only / keep positions."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "description": item["description"],
            "inputSchema": item["inputSchema"],
            "annotations": {"risk_level": item["risk_level"]},
        }
        for item in TOOL_DEFINITIONS
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None, client: HelixApiClient | None = None) -> dict[str, Any]:
    client = client or HelixApiClient.from_env()
    args = arguments or {}
    handlers: dict[str, ToolHandler] = {
        "health_check": _health_check,
        "doctor": _doctor,
        "login": _login,
        "logout": _logout,
        "list_strategies": _list_strategies,
        "list_markets": _list_markets,
        "explain_parameters": _explain_parameters,
        "get_runtime_mode": _get_runtime_mode,
        "get_bot_status": _get_bot_status,
        "get_recent_trades": _get_recent_trades,
        "preview_bot_config": _preview_bot_config,
        "save_exchange_credentials": _save_exchange_credentials,
        "start_bot": _start_bot,
        "update_bot_config": _update_bot_config,
        "stop_bot": _stop_bot,
    }
    handler = handlers.get(name)
    if handler is None:
        return _error_result(f"Unknown tool: {name}")
    try:
        result = handler(client, args)
        return {
            "ok": True,
            "tool": name,
            "risk_level": TOOL_RISK_LEVELS.get(name, "unknown"),
            "result": redact_value(result),
        }
    except SafetyError as exc:
        return _error_result(str(exc), tool=name, code="safety_blocked")
    except AgentApiError as exc:
        return _error_result(str(exc), tool=name, code="api_error", status_code=exc.status_code)
    except Exception as exc:  # noqa: BLE001 - surface clean agent errors
        return _error_result(str(exc), tool=name, code="internal_error")


def _error_result(
    message: str,
    *,
    tool: str | None = None,
    code: str = "error",
    status_code: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "tool": tool,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if status_code is not None:
        payload["error"]["status_code"] = status_code
    return payload


def _health_check(client: HelixApiClient, _: dict[str, Any]) -> dict[str, Any]:
    return {"health": client.health(), "api_base_url": client.base_url}


def _doctor(client: HelixApiClient, _: dict[str, Any]) -> dict[str, Any]:
    return run_doctor(client)


def _login(client: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    username = args.get("username") or os.getenv("HELIX_USERNAME") or os.getenv("ADMIN_USERNAME")
    password = args.get("password") or os.getenv("HELIX_PASSWORD") or os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        raise SafetyError(
            "Username/password missing. Set HELIX_USERNAME and HELIX_PASSWORD locally, "
            "or pass them only through a private local channel. Do not paste into public chats."
        )
    return client.login(str(username), str(password))


def _logout(client: HelixApiClient, _: dict[str, Any]) -> dict[str, Any]:
    return client.logout()


def _list_strategies(client: HelixApiClient, _: dict[str, Any]) -> dict[str, Any]:
    remote = client.list_strategies()
    enriched = []
    for item in remote:
        strategy_id = str(item.get("id"))
        enriched.append(enrich_strategy_payload(strategy_id, item.get("default_params") or {}))
    if not enriched:
        enriched = [enrich_strategy_payload(spec["id"], spec["default_params"]) for spec in list_strategy_specs()]
    return {
        "strategies": enriched,
        "example_configs": EXAMPLE_CONFIGS,
        "disclaimer": "Strategy docs describe behavior and risk only; they are not performance guarantees.",
    }


def _list_markets(client: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    exchange = str(args["exchange"])
    markets = client.list_markets(exchange)
    return {"exchange": exchange, "count": len(markets), "markets": markets[:200]}


def _explain_parameters(_: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    names = args.get("names")
    if names:
        docs = {name: get_parameter_spec(str(name)) for name in names}
    else:
        docs = list_parameter_specs()
    return {
        "parameters": docs,
        "strategies": list_strategy_specs(),
        "example_configs": EXAMPLE_CONFIGS,
        "disclaimer": "Parameter guidance is educational only and not investment advice.",
    }


def _get_bot_status(client: HelixApiClient, _: dict[str, Any]) -> dict[str, Any]:
    return {"status": client.get_status()}


def _get_runtime_mode(client: HelixApiClient, _: dict[str, Any]) -> dict[str, Any]:
    status = client.get_status()
    has_credential = status_has_credential(status)
    if not has_credential:
        mode = "not_configured"
        use_testnet = None
    else:
        use_testnet = bool(status.get("use_testnet", False))
        mode = "testnet" if use_testnet else "live"

    return {
        "mode": mode,
        "use_testnet": use_testnet,
        "status": status.get("status"),
        "exchange": status.get("exchange"),
        "selected_symbol": status.get("selected_symbol"),
        "runtime_symbol": status.get("runtime_symbol"),
        "masked_api_key": status.get("masked_api_key"),
        "credential_status": status.get("credential_status"),
        "is_stopping": status.get("is_stopping"),
        "data_source": "/api/bot/status.use_testnet",
        "explanation": (
            "The backend starts sessions from the saved ApiCredential.use_testnet flag. "
            "If mode is live, starting or updating trading risk config requires live-trading confirmation."
            if has_credential
            else "No exchange credential is saved yet, so runtime mode is not configured."
        ),
    }


def _get_recent_trades(client: HelixApiClient, _: dict[str, Any]) -> dict[str, Any]:
    return {"trades": client.get_trades()}


def _preview_bot_config(_: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    config = _build_start_config(args)
    return {
        "preview_only": True,
        "places_orders": False,
        "config": config,
        "summary": summarize_start_config(config),
        "human_readable": explain_config(config),
        "next_step": "If the user confirms, call start_bot with the same parameters.",
    }


def _save_exchange_credentials(client: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    ensure_credential_save_confirmed(
        confirm_save_credentials=bool(args.get("confirm_save_credentials", False))
    )
    exchange = str(args["exchange"])
    api_key = args.get("api_key") or os.getenv("HELIX_EXCHANGE_API_KEY")
    api_secret = args.get("api_secret") or os.getenv("HELIX_EXCHANGE_API_SECRET")
    passphrase = args.get("passphrase") or os.getenv("HELIX_EXCHANGE_PASSPHRASE")
    use_testnet = bool(args.get("use_testnet", True))
    if not api_key or not api_secret:
        raise SafetyError(
            "Exchange API key/secret missing. Set HELIX_EXCHANGE_API_KEY and "
            "HELIX_EXCHANGE_API_SECRET locally (and HELIX_EXCHANGE_PASSPHRASE for OKX). "
            "Do not paste secrets into public chats."
        )
    response = client.save_credentials(
        exchange=exchange,
        api_key=str(api_key),
        api_secret=str(api_secret),
        passphrase=str(passphrase) if passphrase else None,
        use_testnet=use_testnet,
    )
    return {
        "detail": "Credentials saved to the Helix backend database",
        "exchange": exchange,
        "use_testnet": use_testnet,
        "masked_api_key": response.get("masked_api_key"),
        "credential_source": (
            "tool_arguments"
            if args.get("api_key") or args.get("api_secret") or args.get("passphrase")
            else "local_environment"
        ),
        "storage_note": (
            "Saved into the backend database. You do not need HELIX_EXCHANGE_* in backend/.env "
            "after a successful save (especially with --prompt). "
            "Judge readiness with doctor / get_runtime_mode — do not grep .env."
        ),
        "security_note": (
            "Secrets were not returned. Prefer local env vars or interactive local input; "
            "only provide secrets to an agent in a trusted private session."
        ),
    }


def _start_bot(client: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    config = _build_start_config(args)
    actual_use_testnet = _resolve_actual_credential_use_testnet(client, config)
    ensure_live_trading_allowed(
        use_testnet=actual_use_testnet,
        confirm_live_trading=bool(args.get("confirm_live_trading", False)),
    )
    payload = {
        "strategy_id": config["strategy_id"],
        "exchange": config["exchange"],
        "symbol": config["symbol"],
        "market_type": config["market_type"],
        "leverage": config["leverage"],
        "position_size_pct": config["position_size_pct"],
        "stop_loss_pct": config["stop_loss_pct"],
        "take_profit_pct": config["take_profit_pct"],
        "max_drawdown_pct": config["max_drawdown_pct"],
        "max_order_notional_usdt": config["max_order_notional_usdt"],
        "max_position_notional_usdt": config["max_position_notional_usdt"],
        "close_all_on_stop": config["close_all_on_stop"],
        "use_testnet": config["use_testnet"],
    }
    response = client.start_bot(payload)
    return {
        "detail": response.get("detail", "Bot started"),
        "session_id": response.get("session_id"),
        "started_config": {
            **summarize_start_config(config),
            "actual_credential_use_testnet": actual_use_testnet,
        },
        "human_readable": explain_config(config),
        "warning": (
            "Bot may place market orders according to strategy signals. "
            "Monitor status and stop if needed."
        ),
    }


def _update_bot_config(client: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    runtime_mode = _get_runtime_mode(client, {})
    if runtime_mode["mode"] == "live":
        ensure_live_trading_allowed(
            use_testnet=False,
            confirm_live_trading=bool(args.get("confirm_live_trading", False)),
        )
    payload = {
        "leverage": float(args["leverage"]),
        "position_size_pct": float(args["position_size_pct"]),
        "stop_loss_pct": float(args["stop_loss_pct"]),
        "take_profit_pct": float(args["take_profit_pct"]),
        "max_drawdown_pct": float(args["max_drawdown_pct"]),
        "max_order_notional_usdt": float(args["max_order_notional_usdt"]),
        "max_position_notional_usdt": float(args["max_position_notional_usdt"]),
    }
    if "close_all_on_stop" in args:
        payload["close_all_on_stop"] = bool(args["close_all_on_stop"])
    response = client.update_bot_config(payload)
    return {
        "detail": response.get("detail", "Config applied"),
        "config": response.get("config"),
        "runtime_mode": runtime_mode,
        "human_readable": explain_config(response.get("config") or payload),
    }


def _count_open_positions(status: dict[str, Any] | None) -> int:
    if not status:
        return 0
    positions = status.get("positions")
    if not isinstance(positions, list):
        return 0
    count = 0
    for item in positions:
        if not isinstance(item, dict):
            continue
        size = item.get("size", item.get("contracts", item.get("amount")))
        try:
            if size is not None and abs(float(size)) > 0:
                count += 1
                continue
        except (TypeError, ValueError):
            pass
        # Treat presence of a symbol/side as an open position when size is opaque.
        if item.get("symbol") or item.get("side"):
            count += 1
    return count


def _stop_bot(client: HelixApiClient, args: dict[str, Any]) -> dict[str, Any]:
    close_all = bool(args.get("close_all", False))
    confirm_close_all = bool(args.get("confirm_close_all", False))
    confirm_stop_keep_positions = bool(args.get("confirm_stop_keep_positions", False))
    ensure_close_all_confirmed(
        close_all=close_all,
        confirm_close_all=confirm_close_all,
    )
    pre_status: dict[str, Any] | None = None
    try:
        pre_status = client.get_status()
    except Exception:
        pre_status = None
    open_positions = _count_open_positions(pre_status)

    # Ambiguous "stop" while positions exist: force the agent to ask the user first.
    if not close_all and open_positions > 0 and not confirm_stop_keep_positions:
        return {
            "stopped": False,
            "needs_user_choice": True,
            "close_all": False,
            "open_positions": open_positions,
            "ask_user": (
                "检测到当前有持仓。请明确选择："
                "（1）只停止策略、保留仓位；"
                "（2）停止策略并平掉机器人管理的仓位。"
                "「停止机器人/关掉策略」本身不等于平仓。"
            ),
            "agent_action": (
                "MUST ask the user and wait. Do not invent close_all=true. "
                "After they choose: (1) stop_bot with close_all=false and "
                "confirm_stop_keep_positions=true; "
                "(2) stop_bot with close_all=true and confirm_close_all=true."
            ),
            "scope": {
                "closes_bot_managed_positions": False,
                "closes_preexisting_account_positions": False,
            },
        }

    response = client.stop_bot(close_all=close_all)
    return {
        "stopped": True,
        "detail": response.get("detail", "Bot stop requested"),
        "close_all": close_all,
        "open_positions_before_stop": open_positions,
        "scope": {
            "closes_bot_managed_positions": close_all,
            "closes_preexisting_account_positions": False,
        },
        "warning": (
            "close_all=true only flattens positions managed by this bot session. "
            "Positions that already existed on the exchange before the bot started "
            "are left untouched. Check exchange UI or status.positions for leftovers."
            if close_all
            else "Bot stopped without requesting close-all (positions left as-is)."
        ),
    }


def _build_start_config(args: dict[str, Any]) -> dict[str, Any]:
    use_testnet = args.get("use_testnet")
    if use_testnet is None:
        use_testnet = True
    return merge_preview_config(
        strategy_id=str(args["strategy_id"]),
        exchange=str(args["exchange"]),
        symbol=str(args.get("symbol") or "BTC/USDT:USDT"),
        market_type=str(args.get("market_type") or "usdt_perp"),
        leverage=_optional_float(args.get("leverage")),
        position_size_pct=_optional_float(args.get("position_size_pct")),
        stop_loss_pct=_optional_float(args.get("stop_loss_pct")),
        take_profit_pct=_optional_float(args.get("take_profit_pct")),
        max_drawdown_pct=_optional_float(args.get("max_drawdown_pct")),
        max_order_notional_usdt=_optional_float(args.get("max_order_notional_usdt")),
        max_position_notional_usdt=_optional_float(args.get("max_position_notional_usdt")),
        close_all_on_stop=bool(args.get("close_all_on_stop", True)),
        use_testnet=bool(use_testnet),
    )


def _resolve_actual_credential_use_testnet(client: HelixApiClient, config: dict[str, Any]) -> bool:
    """Backend starts with the saved credential's use_testnet flag.

    The /api/bot/start schema accepts use_testnet, but the current backend stores
    BotSession.use_testnet from ApiCredential.use_testnet. The safety gate must
    therefore inspect current credential status instead of trusting the requested
    start payload.
    """

    status = client.get_status()
    has_credential = status_has_credential(status)
    if not has_credential:
        # Start will fail with "Save exchange credentials first"; keep the
        # requested value for the preview/error path rather than demanding live
        # confirmation when no credential exists.
        return bool(config["use_testnet"])
    actual = bool(status.get("use_testnet", False))
    requested = bool(config["use_testnet"])
    if actual != requested:
        if actual:
            # Requested live but saved credential is testnet. Backend will still
            # use testnet; this is safe and reflected in the returned summary.
            return True
        # Requested testnet but backend will use a live credential. Return False
        # so the normal live-trading dual-confirm gate is enforced.
        return False
    return actual


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
