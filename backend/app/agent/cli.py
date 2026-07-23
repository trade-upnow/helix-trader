"""CLI entry for Helix agent tools."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any

from app.agent import __version__
from app.agent.client import HelixApiClient
from app.agent.tools import call_tool, list_tools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helix-agent",
        description=(
            "Helix trading bot agent CLI. Prefer doctor/preview before trading actions. "
            "Never print secrets to public channels."
        ),
    )
    parser.add_argument("--version", action="version", version=f"helix-agent {__version__}")
    parser.add_argument(
        "--base-url",
        default=None,
        help="Helix API base URL (default HELIX_API_BASE_URL or http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Access token (default HELIX_ACCESS_TOKEN). Do not share publicly.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tools", help="List available tools and risk levels")
    sub.add_parser("health", help="Alias for health_check")
    sub.add_parser("doctor", help="Run local environment checks")
    sub.add_parser("mode", help="Show current runtime mode: testnet, live, or not configured")
    sub.add_parser("status", help="Alias for get_bot_status")
    sub.add_parser("strategies", help="Alias for list_strategies")
    sub.add_parser("trades", help="Alias for get_recent_trades")
    sub.add_parser("params", help="Alias for explain_parameters")
    sub.add_parser("logout", help="Clear local access token cache")

    login = sub.add_parser("login", help="Login using env vars or flags; caches token locally")
    login.add_argument("--username")
    login.add_argument("--password")

    markets = sub.add_parser("markets", help="List markets for an exchange")
    markets.add_argument("--exchange", required=True, choices=["binance", "okx"])

    preview = sub.add_parser("preview", help="Preview bot config without placing orders")
    _add_start_args(preview)

    start = sub.add_parser("start", help="Start bot (default testnet)")
    _add_start_args(start)
    start.add_argument("--confirm-live-trading", action="store_true")

    stop = sub.add_parser("stop", help="Stop bot (default: keep positions; use --close-all to flatten)")
    stop.add_argument(
        "--close-all",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also close bot-managed positions (requires --confirm-close-all)",
    )
    stop.add_argument("--confirm-close-all", action="store_true")

    creds = sub.add_parser(
        "save-credentials",
        help="Save exchange credentials from env, private args, or interactive prompt",
    )
    creds.add_argument("--exchange", required=True, choices=["binance", "okx"])
    creds.add_argument("--api-key", help="Private direct input; prefer env or --prompt")
    creds.add_argument("--api-secret", help="Private direct input; prefer env or --prompt")
    creds.add_argument("--passphrase", help="Private direct input; prefer env or --prompt")
    creds.add_argument("--prompt", action="store_true", help="Prompt locally without echoing secrets")
    creds.add_argument("--testnet", action=argparse.BooleanOptionalAction, default=True)
    creds.add_argument("--confirm-save-credentials", action="store_true")

    update = sub.add_parser("update-config", help="Update running bot risk config")
    update.add_argument("--leverage", type=float, required=True)
    update.add_argument("--position-size-pct", type=float, required=True)
    update.add_argument("--stop-loss-pct", type=float, required=True)
    update.add_argument("--take-profit-pct", type=float, required=True)
    update.add_argument("--max-drawdown-pct", type=float, required=True)
    update.add_argument("--max-order-notional-usdt", type=float, required=True)
    update.add_argument("--max-position-notional-usdt", type=float, required=True)
    update.add_argument("--close-all-on-stop", action=argparse.BooleanOptionalAction, default=None)
    update.add_argument("--confirm-live-trading", action="store_true")

    call = sub.add_parser("call", help="Call a tool by name with JSON arguments")
    call.add_argument("tool_name")
    call.add_argument(
        "--args",
        default="{}",
        help='JSON object of arguments, e.g. \'{"exchange":"okx"}\'',
    )

    return parser


def _add_start_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--strategy", required=True, dest="strategy_id")
    parser.add_argument("--exchange", required=True, choices=["binance", "okx"])
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--market-type", default="usdt_perp")
    parser.add_argument("--leverage", type=float)
    parser.add_argument("--position-size-pct", type=float)
    parser.add_argument("--stop-loss-pct", type=float)
    parser.add_argument("--take-profit-pct", type=float)
    parser.add_argument("--max-drawdown-pct", type=float)
    parser.add_argument("--max-order-notional-usdt", type=float)
    parser.add_argument("--max-position-notional-usdt", type=float)
    parser.add_argument("--close-all-on-stop", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--testnet", action=argparse.BooleanOptionalAction, default=True)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = HelixApiClient.from_env()
    if args.base_url:
        client.base_url = args.base_url.rstrip("/")
    if args.token:
        client.token = args.token

    command = args.command
    if command == "tools":
        _print_json({"tools": list_tools()})
        return 0

    tool_name, tool_args = _map_command(command, args)
    result = call_tool(tool_name, tool_args, client=client)
    _print_json(result)
    return 0 if result.get("ok") else 1


def _map_command(command: str, args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if command == "health":
        return "health_check", {}
    if command == "doctor":
        return "doctor", {}
    if command == "mode":
        return "get_runtime_mode", {}
    if command == "status":
        return "get_bot_status", {}
    if command == "strategies":
        return "list_strategies", {}
    if command == "trades":
        return "get_recent_trades", {}
    if command == "params":
        return "explain_parameters", {}
    if command == "login":
        payload: dict[str, Any] = {}
        if args.username:
            payload["username"] = args.username
        if args.password:
            payload["password"] = args.password
        return "login", payload
    if command == "logout":
        return "logout", {}
    if command == "markets":
        return "list_markets", {"exchange": args.exchange}
    if command == "preview":
        return "preview_bot_config", _start_payload(args)
    if command == "start":
        payload = _start_payload(args)
        payload["confirm_live_trading"] = bool(args.confirm_live_trading)
        return "start_bot", payload
    if command == "stop":
        # CLI stop without --close-all is an explicit operator choice to keep positions.
        return "stop_bot", {
            "close_all": bool(args.close_all),
            "confirm_close_all": bool(args.confirm_close_all),
            "confirm_stop_keep_positions": not bool(args.close_all),
        }
    if command == "save-credentials":
        payload = {
            "exchange": args.exchange,
            "use_testnet": bool(args.testnet),
            "confirm_save_credentials": bool(args.confirm_save_credentials),
        }
        if args.prompt:
            if not args.api_key:
                args.api_key = getpass.getpass("Exchange API key: ")
            if not args.api_secret:
                args.api_secret = getpass.getpass("Exchange API secret: ")
            if args.exchange == "okx" and not args.passphrase:
                args.passphrase = getpass.getpass("OKX passphrase (blank if unused): ")
        if args.api_key:
            payload["api_key"] = args.api_key
        if args.api_secret:
            payload["api_secret"] = args.api_secret
        if args.passphrase:
            payload["passphrase"] = args.passphrase
        return "save_exchange_credentials", payload
    if command == "update-config":
        payload = {
            "leverage": args.leverage,
            "position_size_pct": args.position_size_pct,
            "stop_loss_pct": args.stop_loss_pct,
            "take_profit_pct": args.take_profit_pct,
            "max_drawdown_pct": args.max_drawdown_pct,
            "max_order_notional_usdt": args.max_order_notional_usdt,
            "max_position_notional_usdt": args.max_position_notional_usdt,
        }
        if args.close_all_on_stop is not None:
            payload["close_all_on_stop"] = bool(args.close_all_on_stop)
        payload["confirm_live_trading"] = bool(args.confirm_live_trading)
        return "update_bot_config", payload
    if command == "call":
        try:
            parsed = json.loads(args.args)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid --args JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise SystemExit("--args must be a JSON object")
        return args.tool_name, parsed
    raise SystemExit(f"Unsupported command: {command}")


def _start_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "strategy_id": args.strategy_id,
        "exchange": args.exchange,
        "symbol": args.symbol,
        "market_type": args.market_type,
        "close_all_on_stop": bool(args.close_all_on_stop),
        "use_testnet": bool(args.testnet),
    }
    for key in (
        "leverage",
        "position_size_pct",
        "stop_loss_pct",
        "take_profit_pct",
        "max_drawdown_pct",
        "max_order_notional_usdt",
        "max_position_notional_usdt",
    ):
        value = getattr(args, key, None)
        if value is not None:
            payload[key] = value
    return payload


def _print_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
