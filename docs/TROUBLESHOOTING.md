# 常见问题与恢复步骤

新手卡点速查。Agent 遇到错误时，应按下表选工具，而不是盲目重试交易动作。

## 刚下载还跑不起来

**含义**：首次配置未完成。

**恢复（给 Agent）**

```bash
bash scripts/setup_backend.sh
# 再启动后端，然后 doctor / login
```

对用户用人话：「我先帮你做首次配置」，不要让用户自己折腾环境术语。`setup` 会按 OKX 是否可达决定 pip 是否走代理。

## pip / ccxt 安装失败（常见于 macOS Python 3.9）

**含义**：`scripts/setup_backend.sh` 若落到系统 `python3`（多为 3.9），新版依赖可能装不上。

**恢复**

```bash
brew install python@3.12
rm -rf backend/.venv
HELIX_PYTHON=python3.12 bash scripts/setup_backend.sh
# 等价：python3.12 -m venv backend/.venv && ...
```

`doctor` 的 `python_version` 现在要求 **≥ 3.10**（推荐 3.12）。

## 访问不了 OKX / 要不要代理

**含义**：本机到 `www.okx.com` 不通，或代理端口不对。

**探测顺序（doctor / setup 已内置）**

1. 直连 OKX → 通则**不需要代理**（若 `.env` 里还写着代理，可清空）
2. 不通再试默认 `http://127.0.0.1:7890`
3. 仍不通 → 只问用户「本机代理地址/端口是多少」

配置时只填一个：`EXCHANGE_PROXY_URL=http://127.0.0.1:端口`。  
Google 通不等于 OKX 通；以 `doctor.network` 为准。
## Missing access token

**含义**：当前进程没有可用的登录 token。

**恢复**

1. 确认后端已启动
2. 在 `backend/` 执行：`python -m app.agent login`
3. `login` 会写入 `backend/.helix-agent-token`；下一条 CLI 应能直接用
4. 也可设置环境变量 `HELIX_ACCESS_TOKEN`（优先级高于缓存文件）
5. MCP 重启后若失效，重新 `login` 或依赖缓存文件

清理：`python -m app.agent logout`

## Cannot reach Helix API

**含义**：连不上 FastAPI（常见是后端没开或端口不对）。

**恢复**

1. `python -m app.agent health` 或浏览器打开 <http://127.0.0.1:8000/health>
2. 在 `backend/` 启动：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. 检查 `HELIX_API_BASE_URL` 是否指向正确地址
4. MCP 的 `cwd` 是否指向 `backend/`，见 [MCP_SETUP.md](MCP_SETUP.md)

## Save exchange credentials first / mode 仍是 not_configured

**含义**：还没把凭证写入后端数据库。常见误解：（1）已填 `HELIX_EXCHANGE_*` 到 `.env` 但从未 `save-credentials`；（2）已用 `--prompt` 保存成功，却因 `.env` 仍为空而误判「没配好」。

**恢复**

1. 路径 A：`.env` 写入 Key 后 `save-credentials`；或路径 B（推荐首次）：
   ```bash
   python -m app.agent save-credentials --exchange okx --testnet --prompt --confirm-save-credentials
   ```
2. 用 `doctor` / `mode` 确认就绪（`testnet` / `live`，不是 `not_configured`）。**不要 grep `.env` 判断。**

详见 [OKX_CREDENTIALS.md](OKX_CREDENTIALS.md)。

## Selected symbol is unavailable

**含义**：所选交易对在当前交易所/目录中不可用。

**恢复**

```bash
python -m app.agent markets --exchange okx
# 或 binance
```

换一个返回列表里存在的符号，再 `preview`。

## OKX passphrase 错误 / 鉴权失败

**恢复**

1. 确认填的是**创建 API Key 时设置的 API 密码短语**，不是登录密码或资金密码
2. 确认测试网 Key 与实盘 Key 没有混用
3. 重新保存凭证后，再 preview / start
4. 详见 [OKX_CREDENTIALS.md](OKX_CREDENTIALS.md)

## 机器人在跑但没有交易

**优先查看**

- `get_bot_status` 的 `status_message`
- `get_recent_trades`

**可能原因**

- 行情尚未满足策略入场条件（正常现象）
- 交易对不可用或市场数据陈旧
- 未保存凭证 / 凭证无效
- 已有运行中会话，新启动被拒绝

不要为此擅自切实盘或大幅加杠杆。

## 实盘被拦截

**含义**：安全闸未打开或用户未确认。

**恢复（仅在用户明确要实盘时）**

1. `get_runtime_mode` 确认当前模式与已保存凭证
2. 停止测试网机器人
3. 保存实盘凭证（`use_testnet=false`）
4. 本地设置 `HELIX_ALLOW_LIVE_TRADING=true`
5. `preview_bot_config`
6. 用户确认后 `start_bot`，并设置 `confirm_live_trading=true`

## 更新参数被拦截

1. 先 `get_runtime_mode`
2. 若是 `live`：实盘更新也需要 live 确认（`confirm_live_trading=true` + 本地开关）
3. 若是 `testnet`：查看后端返回的具体错误，不要假设是实盘闸

## stop --close-all 后账户里还有仓位

**含义**：`close_all` 只平**本机器人会话管理**的仓位。启动前账户里已有的仓位（例如原先手动开的 BTC 多头）不会被平掉。状态可能出现  
`no bot-managed positions to close (pre-existing exchange positions were left untouched)`。

**恢复**

1. 用交易所网页 / App 自行处理历史仓位
2. 或在 Agent 回复里明确区分「机器人仓位」与「账户已有仓位」
3. 不要假设 `stop --close-all` = 清空整个账户

## 网页控制台

网页是可选增强，不是用户该先问出来的缺口。  
**首次配置成功后，Agent 应主动询问是否启动本地网页**（`frontend/` → `npm install && npm run dev` → http://localhost:3000）。  
登录用 **`ADMIN_USERNAME` / `ADMIN_PASSWORD`**（示例默认 `admin` / `ChangeMe123!`），**不要**用 `CLIENT_USERNAME`（如 `client001`）。见 [OPERATIONS.md](OPERATIONS.md)。

## 交易所凭证解密失败 / encryption key likely changed

**含义**：库里的交易所密钥是用当时的 `API_ENCRYPTION_KEY`（或由 `JWT_SECRET` 派生的密钥）加密的；改过其中之一后旧密文解不开。

**恢复**：把密钥配置改回保存凭证时的值，或重新执行 `save-credentials`。Agent 不要回显密钥值。## doctor 报告多项缺口

按 `doctor` 返回的 `next_steps` 顺序处理：setup / 依赖 → `.env` → 后端健康 → 登录 → 两步凭证 → 代理/OKX 连通性 → preview。  
完整新手路径见 [GETTING_STARTED_AGENT.md](GETTING_STARTED_AGENT.md)。
