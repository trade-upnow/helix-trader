"""Strategy and parameter metadata shared by MCP, CLI, and docs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


RiskLevel = str  # "readonly" | "credential" | "trading" | "destructive"


PARAMETER_SPECS: dict[str, dict[str, Any]] = {
    "exchange": {
        "description": "交易所标识。当前支持 binance 与 okx。",
        "type": "string",
        "allowed_values": ["binance", "okx"],
        "default": "okx",
        "recommended_range": "binance | okx",
        "risk": "选择错误会导致密钥保存或交易对查询失败。",
        "user_editable": True,
    },
    "symbol": {
        "description": "永续合约交易对，使用 ccxt 风格符号。",
        "type": "string",
        "default": "BTC/USDT:USDT",
        "recommended_range": "例如 BTC/USDT:USDT、ETH/USDT:USDT",
        "risk": "未知或不可交易符号会阻止启动。",
        "user_editable": True,
    },
    "market_type": {
        "description": "市场类型。当前包装层默认使用 USDT 永续。",
        "type": "string",
        "default": "usdt_perp",
        "recommended_range": "usdt_perp",
        "risk": "非支持类型可能导致交易所适配失败。",
        "user_editable": True,
    },
    "use_testnet": {
        "description": "是否使用测试网。默认 True，强烈建议先在测试网验证。",
        "type": "boolean",
        "default": True,
        "recommended_range": "True（测试）/ False（仅在显式确认后）",
        "risk": "False 表示可能在实盘账户下单，资金有真实亏损风险。",
        "user_editable": True,
    },
    "leverage": {
        "description": "杠杆倍数。放大收益的同时也放大亏损。",
        "type": "number",
        "default": 3,
        "recommended_range": "测试网 1-3；谨慎实盘通常不超过 5",
        "risk": "杠杆越高，爆仓与回撤风险越大。",
        "user_editable": True,
    },
    "position_size_pct": {
        "description": "单次目标仓位占账户权益的百分比（再乘杠杆形成名义敞口）。",
        "type": "number",
        "default": 15,
        "recommended_range": "5-20",
        "risk": "比例过高会快速抬升敞口，增加连续亏损压力。",
        "user_editable": True,
    },
    "stop_loss_pct": {
        "description": "相对入场价的止损百分比。触发后关闭机器人管理的对应仓位。",
        "type": "number",
        "default": 2,
        "recommended_range": "1-3",
        "risk": "过小可能频繁止损；过大则单笔亏损更大。",
        "user_editable": True,
    },
    "take_profit_pct": {
        "description": "相对入场价的止盈百分比。触发后关闭机器人管理的对应仓位。",
        "type": "number",
        "default": 5,
        "recommended_range": "3-8",
        "risk": "过小可能过早离场；过大则可能回吐浮盈。",
        "user_editable": True,
    },
    "max_drawdown_pct": {
        "description": "相对会话峰值权益的最大回撤百分比。触发后停止机器人并平掉机器人仓位。",
        "type": "number",
        "default": 12,
        "recommended_range": "8-15",
        "risk": "过小会导致策略过早停止；过大则允许更深亏损。",
        "user_editable": True,
    },
    "max_order_notional_usdt": {
        "description": "单笔市价单最大名义价值（USDT）。用于分批下单时的单批上限。",
        "type": "number",
        "default": 1000,
        "recommended_range": "测试网 50-500；按账户规模自行收紧",
        "risk": "过大可能导致单次冲击过大。",
        "user_editable": True,
    },
    "max_position_notional_usdt": {
        "description": "同方向机器人仓位最大名义价值（USDT）。达到上限后跳过加仓。",
        "type": "number",
        "default": 3000,
        "recommended_range": "测试网 100-1000；按账户规模自行收紧",
        "risk": "过大意味着允许更大总敞口。",
        "user_editable": True,
    },
    "close_all_on_stop": {
        "description": "停止机器人时是否尝试平掉机器人管理的仓位。",
        "type": "boolean",
        "default": True,
        "recommended_range": "True（默认安全）",
        "risk": "True 会触发平仓动作；False 可能留下未管理仓位需人工处理。",
        "user_editable": True,
    },
    "timeframe": {
        "description": "策略使用的 K 线周期。由策略默认参数提供。",
        "type": "string",
        "default": "15m",
        "recommended_range": "通常保持策略默认值",
        "risk": "随意修改可能改变信号频率与策略行为。",
        "user_editable": False,
        "advanced": True,
    },
    "strategy_state": {
        "description": "策略运行时状态（例如突破跟踪）。由机器人自动维护，不建议人工修改。",
        "type": "object",
        "default": {},
        "recommended_range": "不要手动设置",
        "risk": "手动改写可能导致错误平仓或错误持仓逻辑。",
        "user_editable": False,
        "advanced": True,
        "internal": True,
    },
}


STRATEGY_SPECS: dict[str, dict[str, Any]] = {
    "trend_following_core": {
        "id": "trend_following_core",
        "name": "Helix Momentum X",
        "summary": "趋势跟随策略：结合快慢均线与动量确认方向。",
        "suitable_for": "有较清晰趋势的行情；震荡市可能反复开平。",
        "main_risks": [
            "震荡市假突破导致来回止损",
            "信号滞后，趋势末端入场风险",
        ],
        "risk_level": "medium",
        "default_params": {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "leverage": 3,
            "position_size_pct": 15,
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_drawdown_pct": 12,
            "max_order_notional_usdt": 1000,
            "max_position_notional_usdt": 3000,
            "exchange_scope": ["binance", "okx"],
        },
    },
    "trend_breakout_accel": {
        "id": "trend_breakout_accel",
        "name": "Helix Breakout Pro",
        "summary": "突破动量策略：关注区间突破并使用跟踪保护。",
        "suitable_for": "波动扩张、突破行情；低波动盘整时信号较少。",
        "main_risks": [
            "假突破后快速回撤",
            "跟踪止损在剧烈波动中可能提前离场",
        ],
        "risk_level": "medium-high",
        "default_params": {
            "symbol": "BTC/USDT:USDT",
            "timeframe": "15m",
            "leverage": 2,
            "position_size_pct": 12,
            "stop_loss_pct": 1.8,
            "take_profit_pct": 6,
            "max_drawdown_pct": 10,
            "max_order_notional_usdt": 1000,
            "max_position_notional_usdt": 3000,
            "exchange_scope": ["binance", "okx"],
        },
    },
}


EXAMPLE_CONFIGS: list[dict[str, Any]] = [
    {
        "name": "conservative_testnet",
        "risk_level": "low",
        "description": "保守测试网配置，适合首次在本机验证。",
        "config": {
            "strategy_id": "trend_following_core",
            "exchange": "okx",
            "symbol": "BTC/USDT:USDT",
            "use_testnet": True,
            "leverage": 1,
            "position_size_pct": 5,
            "stop_loss_pct": 2,
            "take_profit_pct": 4,
            "max_drawdown_pct": 8,
            "max_order_notional_usdt": 100,
            "max_position_notional_usdt": 300,
            "close_all_on_stop": True,
        },
    },
    {
        "name": "standard_testnet",
        "risk_level": "medium",
        "description": "常规测试网配置，接近策略默认参数但限制名义价值。",
        "config": {
            "strategy_id": "trend_breakout_accel",
            "exchange": "okx",
            "symbol": "BTC/USDT:USDT",
            "use_testnet": True,
            "leverage": 2,
            "position_size_pct": 10,
            "stop_loss_pct": 1.8,
            "take_profit_pct": 6,
            "max_drawdown_pct": 10,
            "max_order_notional_usdt": 300,
            "max_position_notional_usdt": 900,
            "close_all_on_stop": True,
        },
    },
    {
        "name": "live_preview_only",
        "risk_level": "high",
        "description": "实盘前预览模板。默认仍标记为测试网；切到实盘前必须显式确认。",
        "config": {
            "strategy_id": "trend_following_core",
            "exchange": "okx",
            "symbol": "BTC/USDT:USDT",
            "use_testnet": True,
            "leverage": 2,
            "position_size_pct": 8,
            "stop_loss_pct": 2,
            "take_profit_pct": 5,
            "max_drawdown_pct": 10,
            "max_order_notional_usdt": 200,
            "max_position_notional_usdt": 600,
            "close_all_on_stop": True,
        },
    },
]


TOOL_RISK_LEVELS: dict[str, RiskLevel] = {
    "health_check": "readonly",
    "doctor": "readonly",
    "login": "credential",
    "logout": "readonly",
    "list_strategies": "readonly",
    "list_markets": "readonly",
    "get_runtime_mode": "readonly",
    "explain_parameters": "readonly",
    "get_bot_status": "readonly",
    "get_recent_trades": "readonly",
    "preview_bot_config": "readonly",
    "save_exchange_credentials": "credential",
    "start_bot": "trading",
    "update_bot_config": "trading",
    "stop_bot": "destructive",
}


def get_parameter_spec(name: str) -> dict[str, Any] | None:
    spec = PARAMETER_SPECS.get(name)
    return deepcopy(spec) if spec else None


def list_parameter_specs() -> dict[str, dict[str, Any]]:
    return deepcopy(PARAMETER_SPECS)


def get_strategy_spec(strategy_id: str) -> dict[str, Any] | None:
    spec = STRATEGY_SPECS.get(strategy_id)
    return deepcopy(spec) if spec else None


def list_strategy_specs() -> list[dict[str, Any]]:
    return [deepcopy(item) for item in STRATEGY_SPECS.values()]


def enrich_strategy_payload(strategy_id: str, default_params: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = get_strategy_spec(strategy_id) or {
        "id": strategy_id,
        "name": strategy_id,
        "summary": "Unknown strategy registered by backend.",
        "suitable_for": "Unknown",
        "main_risks": [],
        "risk_level": "unknown",
        "default_params": default_params or {},
    }
    params = deepcopy(default_params or spec.get("default_params") or {})
    parameter_docs = {
        key: get_parameter_spec(key)
        for key in params.keys()
        if get_parameter_spec(key) is not None
    }
    return {
        **spec,
        "default_params": params,
        "parameter_docs": parameter_docs,
        "disclaimer": "参数说明仅帮助理解风险与行为，不构成收益承诺或投资建议。",
    }


def explain_config(config: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in config.items():
        spec = get_parameter_spec(key)
        if spec is None:
            lines.append(f"{key}={value}")
            continue
        lines.append(
            f"{key}={value} — {spec['description']} "
            f"(推荐: {spec['recommended_range']}; 风险: {spec['risk']})"
        )
    return lines


def merge_preview_config(
    *,
    strategy_id: str,
    exchange: str,
    symbol: str = "BTC/USDT:USDT",
    market_type: str = "usdt_perp",
    leverage: float | None = None,
    position_size_pct: float | None = None,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    max_drawdown_pct: float | None = None,
    max_order_notional_usdt: float | None = None,
    max_position_notional_usdt: float | None = None,
    close_all_on_stop: bool = True,
    use_testnet: bool = True,
) -> dict[str, Any]:
    strategy = get_strategy_spec(strategy_id)
    defaults = deepcopy((strategy or {}).get("default_params") or {})
    merged = {
        **defaults,
        "strategy_id": strategy_id,
        "exchange": exchange,
        "symbol": symbol,
        "market_type": market_type,
        "leverage": leverage if leverage is not None else defaults.get("leverage", 3),
        "position_size_pct": (
            position_size_pct
            if position_size_pct is not None
            else defaults.get("position_size_pct", 15)
        ),
        "stop_loss_pct": (
            stop_loss_pct if stop_loss_pct is not None else defaults.get("stop_loss_pct", 2)
        ),
        "take_profit_pct": (
            take_profit_pct
            if take_profit_pct is not None
            else defaults.get("take_profit_pct", 5)
        ),
        "max_drawdown_pct": (
            max_drawdown_pct
            if max_drawdown_pct is not None
            else defaults.get("max_drawdown_pct", 12)
        ),
        "max_order_notional_usdt": (
            max_order_notional_usdt
            if max_order_notional_usdt is not None
            else defaults.get("max_order_notional_usdt", 1000)
        ),
        "max_position_notional_usdt": (
            max_position_notional_usdt
            if max_position_notional_usdt is not None
            else defaults.get("max_position_notional_usdt", 3000)
        ),
        "close_all_on_stop": close_all_on_stop,
        "use_testnet": use_testnet,
    }
    return merged
