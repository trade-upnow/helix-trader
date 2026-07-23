# Helix 策略与参数说明

本文供人工用户与 agent 共同使用。内容描述行为与风险，**不构成收益承诺或投资建议**。

## 策略概览

### `trend_following_core`（Helix Momentum X）

- **类型**：趋势跟随
- **思路**：结合快慢均线与动量确认方向
- **较适合**：趋势较清晰的行情
- **主要风险**：震荡市假信号、滞后入场

### `trend_breakout_accel`（Helix Breakout Pro）

- **类型**：突破动量
- **思路**：关注区间突破，并用跟踪保护管理仓位
- **较适合**：波动扩张、突破行情
- **主要风险**：假突破后快速回撤、剧烈波动时提前离场

## 交易标的参数

| 参数 | 含义 | 默认 | 推荐 | 风险 |
|------|------|------|------|------|
| `exchange` | 交易所 | `okx` | `binance` / `okx` | 选错会导致密钥或市场查询失败 |
| `symbol` | 永续合约交易对 | `BTC/USDT:USDT` | 主流永续 | 不可交易符号会阻止启动 |
| `market_type` | 市场类型 | `usdt_perp` | 保持默认 | 非支持类型可能失败 |
| `use_testnet` | 是否测试网 | `true` | 先用 `true` | `false` 可能真实下单 |

### 测试网 / 实盘状态来源

当前到底跑测试网还是实盘，不能靠用户口头描述或启动参数猜测。Agent 必须调用 `get_runtime_mode`，它的数据来源是后端 `/api/bot/status.use_testnet`。

- `mode=testnet`：当前保存的交易所凭证是测试网凭证。
- `mode=live`：当前保存的交易所凭证是实盘凭证。
- `mode=not_configured`：还没有保存交易所凭证。

后端启动机器人时最终使用已保存凭证的 `use_testnet` 状态。因此从测试网切到实盘时，需要先停止机器人，再重新保存实盘凭证，并在启动前预览配置。

### OKX Passphrase

OKX API 需要三项：`api_key`、`api_secret`、`passphrase`。`passphrase` 是用户在 OKX 创建 API Key 时自己设置的 API 密码短语，不是登录密码，也不是资金密码。

保存方式：

```bash
# 本地交互输入，避免进入 shell 历史
python -m app.agent save-credentials --exchange okx --testnet --prompt --confirm-save-credentials

# 或写入 backend/.env
HELIX_EXCHANGE_API_KEY=...
HELIX_EXCHANGE_API_SECRET=...
HELIX_EXCHANGE_PASSPHRASE=...
```

测试网和实盘通常是两套不同 API key，不要混用。

## 仓位与杠杆参数

| 参数 | 含义 | 默认 | 推荐范围 | 风险 |
|------|------|------|----------|------|
| `leverage` | 杠杆倍数 | 3 / 2（策略不同） | 测试网 1-3 | 放大盈亏 |
| `position_size_pct` | 目标仓位占权益百分比 | 15 / 12 | 5-20 | 过高抬升敞口 |
| `max_order_notional_usdt` | 单笔最大名义价值 | 1000 | 测试网 50-500 | 过大冲击大 |
| `max_position_notional_usdt` | 同方向最大名义价值 | 3000 | 测试网 100-1000 | 过大总敞口大 |

## 风控参数

| 参数 | 含义 | 默认 | 推荐范围 | 后果 |
|------|------|------|----------|------|
| `stop_loss_pct` | 止损百分比 | 2 / 1.8 | 1-3 | 触发后平掉对应机器人仓位 |
| `take_profit_pct` | 止盈百分比 | 5 / 6 | 3-8 | 触发后平掉对应机器人仓位 |
| `max_drawdown_pct` | 相对峰值最大回撤 | 12 / 10 | 8-15 | 触发后停止机器人并平仓 |
| `close_all_on_stop` | 停止时是否平仓 | `true` | `true` | `true` 会触发平仓动作 |

## 高级参数（一般勿改）

| 参数 | 说明 | 是否建议普通用户修改 |
|------|------|----------------------|
| `timeframe` | 策略 K 线周期，默认 `15m` | 否 |
| `strategy_state` | 策略运行时状态（机器人维护） | 否 |
| `exchange_scope` | 策略适用交易所范围 | 否 |

## 示例配置

### 保守测试网

```json
{
  "strategy_id": "trend_following_core",
  "exchange": "okx",
  "symbol": "BTC/USDT:USDT",
  "use_testnet": true,
  "leverage": 1,
  "position_size_pct": 5,
  "stop_loss_pct": 2,
  "take_profit_pct": 4,
  "max_drawdown_pct": 8,
  "max_order_notional_usdt": 100,
  "max_position_notional_usdt": 300,
  "close_all_on_stop": true
}
```

### 常规测试网

```json
{
  "strategy_id": "trend_breakout_accel",
  "exchange": "okx",
  "symbol": "BTC/USDT:USDT",
  "use_testnet": true,
  "leverage": 2,
  "position_size_pct": 10,
  "stop_loss_pct": 1.8,
  "take_profit_pct": 6,
  "max_drawdown_pct": 10,
  "max_order_notional_usdt": 300,
  "max_position_notional_usdt": 900,
  "close_all_on_stop": true
}
```

## Agent 解释规范

1. 用自然语言解释参数影响，例如“杠杆从 1 提到 3，盈亏波动大约放大”。
2. 不得把参数描述成“保证盈利”“强制赚钱”。
3. 启动前先调用 `preview_bot_config`，向用户展示最终配置与风险。
4. 用户问测试网/实盘时，先调用 `get_runtime_mode`，明确引用 `/api/bot/status.use_testnet`。
5. 实盘启动或实盘中更新交易风险参数时，必须有用户明确确认，并满足本地安全开关。
