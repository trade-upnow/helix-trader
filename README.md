# Helix Trader

本地可自托管的**加密货币市场交易策略**机器人控制与监控工具。支持网页端、CLI，以及 Codex / Claude 等 agent 通过自然语言调用。

> 非投资建议。数字资产衍生品交易存在亏损风险。建议先在测试网验证，并自行保管 API 密钥与账户安全。  
> 交易始终在用户本机运行；本仓库不代持密钥、不代跑交易。

## 功能

- 本地启动交易机器人，支持趋势跟随与突破动量策略
- 通过 CLI 或 MCP，让 agent 用自然语言查询状态、预览配置、启动/停止机器人
- 默认偏向测试网；实盘需本地显式开启并经用户确认
- 可选网页控制台查看状态与成交

## 仓库结构

- `backend/`：FastAPI 后端与 Agent MCP/CLI（用户本机执行）
- `frontend/`：Next.js 控制台（可选）
- `docs/`：新手引导、参数说明与本地启动说明
- `examples/mcp/`：本机 MCP 配置示例（技能插件不含此项；见该目录 README）

## 快速开始

新手按 10–15 分钟路径走完整说明：[docs/GETTING_STARTED_AGENT.md](docs/GETTING_STARTED_AGENT.md)。

刚下载仓库时推荐一键初始化：

```bash
bash scripts/setup_backend.sh
# 然后本地编辑 backend/.env（JWT_SECRET、HELIX_USERNAME/PASSWORD 等）
```

手动等价步骤（请用 **Python 3.10+，推荐 3.12**；勿用 macOS 自带多为 3.9 的 `python3`）：

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 仅在本地编辑 .env，不要把真实密钥提交到仓库或发到公开渠道
# 至少填写 HELIX_USERNAME / HELIX_PASSWORD（或使用 ADMIN_*）

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

另开终端：

```bash
cd backend
source .venv/bin/activate
python -m app.agent doctor
python -m app.agent login          # 会缓存 token 到 backend/.helix-agent-token
python -m app.agent mode           # 新进程也可继续用缓存的登录态
python -m app.agent strategies
python -m app.agent preview \
  --strategy trend_following_core \
  --exchange okx \
  --symbol BTC/USDT:USDT \
  --testnet
# 退出本地登录态：python -m app.agent logout
```

保存交易所密钥是**两步**：填进 `.env` 只是输入源，还必须调用保存写入后端数据库（否则 `mode` 仍是 `not_configured`）：

```bash
# 1) 推荐：编辑 backend/.env，填写 HELIX_EXCHANGE_API_KEY / HELIX_EXCHANGE_API_SECRET
# OKX 还需 HELIX_EXCHANGE_PASSPHRASE，见 docs/OKX_CREDENTIALS.md
# 2) 写入后端：
python -m app.agent save-credentials --exchange okx --testnet --confirm-save-credentials

# 或本地交互输入（可跳过 .env），避免进入 shell 历史
python -m app.agent save-credentials --exchange okx --testnet --prompt --confirm-save-credentials

# 或在可信私有 agent 会话中，由用户明确提供密钥后让 agent 调用 save_exchange_credentials
```

启动 MCP server：

```bash
cd backend
source .venv/bin/activate
python -m app.agent mcp
```

MCP 接入说明：[docs/MCP_SETUP.md](docs/MCP_SETUP.md)  
配置示例：[examples/mcp/](examples/mcp/)。

## 用户常说的话（示例）

```text
帮我启动这个机器人
```

```text
我要怎么启动？先用测试网
```

```text
帮我启动机器人，先预览配置；策略你推荐一个就行
```

```text
现在是模拟盘还是实盘？
```

Agent 收到后应自动完成首次配置与网络探测；并询问交易所（OKX / Binance）、推荐趋势策略、做配置预览，确认后再启动。  
密钥保护是 Agent 硬规则，不需要用户提醒。首次配置成功后，应主动询问是否启动本地网页控制台（见 [docs/OPERATIONS.md](docs/OPERATIONS.md)）。
## Agent 能力

| 能力 | 说明 |
|------|------|
| `doctor` | 检查本地环境是否就绪（不回显密钥） |
| `login` / `logout` | 登录并缓存 token / 清除本地登录态 |
| `get_runtime_mode` | 判断当前是测试网、实盘还是未配置，数据来源为 `/api/bot/status.use_testnet` |
| `list_strategies` / `explain_parameters` | 查看策略与参数说明 |
| `preview_bot_config` | 启动前预览配置，不下单 |
| `start_bot` | 启动机器人；默认测试网 |
| `get_bot_status` / `get_recent_trades` | 查看状态与最近成交 |
| `stop_bot` | 停止机器人；若同时平仓需额外确认 |

详细规则：[README_AGENT.md](README_AGENT.md)  
新手快速开始：[docs/GETTING_STARTED_AGENT.md](docs/GETTING_STARTED_AGENT.md)  
Agent 引导剧本：[docs/AGENT_PLAYBOOK.md](docs/AGENT_PLAYBOOK.md)  
OKX 凭证：[docs/OKX_CREDENTIALS.md](docs/OKX_CREDENTIALS.md)  
MCP 配置：[docs/MCP_SETUP.md](docs/MCP_SETUP.md)  
常见问题：[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)  
参数说明：[docs/parameters.md](docs/parameters.md)  
安全要求：[SECURITY.md](SECURITY.md)  
本地启动：[docs/OPERATIONS.md](docs/OPERATIONS.md)

## 安全要点

- API key、secret、passphrase、token 优先放本地环境变量或 `.env`
- 如用户明确选择，也可以在可信私有 agent 会话中直接提供给保存密钥工具；工具不会回显完整密钥
- 不要把密钥贴到聊天、GitHub issue、公开帖子或任何平台介绍页
- 开启实盘需要同时满足：
  1. 本地环境变量 `HELIX_ALLOW_LIVE_TRADING=true`
  2. 工具参数 `confirm_live_trading=true`
  3. 用户明确确认

## 使用说明

- 需自行在本地部署后端；密钥与交易账户由用户自己管理
- 想确认当前是测试网还是实盘，运行 `python -m app.agent mode`，不要靠记忆猜测
- 从测试网切到实盘：先停止机器人，再保存实盘凭证，预览配置，最后显式确认启动
- 先完成 `doctor` 与配置预览，再考虑启动机器人
- 可选网页控制台说明见 [docs/OPERATIONS.md](docs/OPERATIONS.md)
