# Helix Trader — Agent 指南

本文给 Codex、Claude 及其他 Agent 使用。

## 这是什么

围绕现有 Helix 交易后端的**本机**控制与监控层。  
Agent 应调用结构化工具（MCP）或 CLI，不要在工具可用时自己拼 HTTP。

## 硬规则

1. 用户常说「帮我启动这个机器人」，不是「请检查虚拟环境」。自行跑 `doctor` / `bash scripts/setup_backend.sh`，对人话说明。
2. 优先只读工具。
3. `start_bot` 之前必须先 `preview_bot_config`。
4. 绝不打印密钥、token 或 `.env` 内容。**不要让用户提醒你**「不要读取或展示任何密钥值」。
5. 凭证必须以**后端数据库为准**：`doctor` / `get_runtime_mode` / `exchange_credentials`。可用 Path A（`.env` 的 `HELIX_EXCHANGE_*` + `save-credentials`）或 Path B（`save-credentials --prompt`，可不写 `.env`）。**禁止**用 `grep .env` 判断是否已配置；`--prompt` 成功后 `.env` 里可以仍是空的。
6. 默认 `use_testnet=true`。
7. 实盘需要 `HELIX_ALLOW_LIVE_TRADING=true` + `confirm_live_trading=true` + 用户明确确认。
8. 用户问模拟盘还是实盘时，调用 `get_runtime_mode`。模式为 `testnet` / `live` / `not_configured`。不要把未配置当成实盘。
9. 实盘下的 `update_bot_config` 同样需要实盘确认。
10. 「停止机器人 / 关掉策略」本身只表示**停策略**（`close_all=false`）。若有仓且用户未选择，**先问**只停还是同时平机器人仓——绝不要擅自 `close_all=true`。平仓路径：`close_all=true` + `confirm_close_all=true`（仅机器人管理仓）。有仓且保留仓位：`close_all=false` + `confirm_stop_keep_positions=true`。
11. 用风险/行为解释参数，永不承诺收益。
12. 启动流程：`doctor`（看 `network`）→ 如需则 setup/login → **问交易所（`okx` / `binance`，不要静默默认 OKX）** → `get_runtime_mode` → 如需保存凭证 → `list_strategies` → **问策略（推荐 `trend_following_core`；另一选项 `trend_breakout_accel`）** → **必须 `preview_bot_config`** → 用户确认 → `start_bot`。
13. 不可跳过预览。用户不选策略时，用推荐的趋势策略做 preview，并明确说明后再 start。
14. 首次配置网络：先直连探测 `www.okx.com` → 再试 `http://127.0.0.1:7890` → 仍不通再问用户代理地址/端口。该探测只判断代理可达，不等于选用 OKX。pip/setup 安装也走可用代理。
15. 首次配置成功后，**主动**提供本地网页控制台（`frontend/` → http://localhost:3000）。登录用 `ADMIN_USERNAME` / `ADMIN_PASSWORD`（示例默认 `admin` / `ChangeMe123!`）。**不要**指向 `CLIENT_USERNAME`。不要等用户问「怎么没网页」。
16. `API_ENCRYPTION_KEY`：新手留空（由 `JWT_SECRET` 派生）。不要打印。已保存交易所凭证后不要擅自轮换，除非用户会重新保存凭证。
17. MCP 配置只在本**运行时**仓库：[examples/mcp/](examples/mcp/) + [docs/MCP_SETUP.md](docs/MCP_SETUP.md)。不要在 Helix 技能插件包里找 `.mcp.json`。
18. 新手剧本：[docs/AGENT_PLAYBOOK.md](docs/AGENT_PLAYBOOK.md)。

## 用户常说

```text
帮我启动这个机器人
```

```text
我要怎么启动？先用测试网
```

```text
帮我启动机器人，先用测试网；你帮我选策略并预览一下
```

```text
现在是模拟盘还是实盘？
```

把这些当作默认入口。不要让用户抄技术清单。  
未指定交易所/策略时：先问交易所，推荐趋势策略，再 preview。

## 引导安装（Agent 侧）

```bash
bash scripts/setup_backend.sh
# 优先 python3.12/3.11/3.10（不要用 macOS 自带 3.9）；会探测 OKX 以决定 pip 代理
# 覆盖：HELIX_PYTHON=python3.12 bash scripts/setup_backend.sh
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 启动 MCP / CLI

```bash
cd backend
source .venv/bin/activate
python -m app.agent mcp
# 或
python -m app.agent doctor
python -m app.agent login
python -m app.agent mode
```

`login` 会把 access token 缓存到 `backend/.helix-agent-token`。清除：`python -m app.agent logout`。

## 首次配置成功后

告诉用户本机有网页可看状态与成交，并询问是否启动。  
登录：`backend/.env` 里的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`（不是 `CLIENT_*`）。

```bash
cd frontend
npm install
npm run dev
# http://localhost:3000 — 后端仍在 :8000
```

详见：[docs/OPERATIONS.md](docs/OPERATIONS.md)。

## 文档索引

- 新手路径：[docs/GETTING_STARTED_AGENT.md](docs/GETTING_STARTED_AGENT.md)
- 剧本：[docs/AGENT_PLAYBOOK.md](docs/AGENT_PLAYBOOK.md)
- OKX 凭证：[docs/OKX_CREDENTIALS.md](docs/OKX_CREDENTIALS.md)
- MCP 配置：[docs/MCP_SETUP.md](docs/MCP_SETUP.md)
- 排错：[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- 参数：[docs/parameters.md](docs/parameters.md)
- 运维 / 前端：[docs/OPERATIONS.md](docs/OPERATIONS.md)
