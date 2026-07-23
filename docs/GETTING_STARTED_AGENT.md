# 新手 Agent 快速开始（10–15 分钟）

目标：从下载仓库到完成**测试网预览/启动**。默认不下单、不进实盘。

> 非投资建议。请先用测试网，并自行保管密钥。

> 给 Agent：用户通常只会说「帮我启动这个机器人」。密钥保护、环境安装、网络探测都由你完成；不要让用户背技术检查清单。

## 0. 首次配置（Agent 侧）

在仓库根目录：

```bash
bash scripts/setup_backend.sh
```

脚本会：

- 准备本地 Python 环境并安装依赖（优先 `python3.12` / `3.11` / `3.10`，**不用** macOS 自带常为 3.9 的 `python3`）
- 缺少配置文件时从示例复制
- **先探测能否访问 www.okx.com**：直连通则不用代理；不通再试 `http://127.0.0.1:7890`；仍不通则提示需要代理端口
- 若安装需要代理，pip 会走同一代理

若本机只有 3.9：先 `brew install python@3.12`，再  
`HELIX_PYTHON=python3.12 bash scripts/setup_backend.sh`（或 `python3.12 -m venv backend/.venv`）。

然后在本地编辑 `backend/.env`（不要把真实密钥贴到聊天）：

| 变量 | 说明 |
|------|------|
| `HELIX_USERNAME` / `HELIX_PASSWORD` | Agent CLI 登录用；也可直接用 `ADMIN_USERNAME` / `ADMIN_PASSWORD` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | **前端网页登录用这对**（示例默认 `admin` / `ChangeMe123!`）。不要引导用户用 `CLIENT_*` |
| `JWT_SECRET` | 改成足够长的随机串 |
| `API_ENCRYPTION_KEY` | 可选，新手**留空即可**（用 `JWT_SECRET` 派生）。已保存交易所凭证后不要乱改 |
| `EXCHANGE_PROXY_URL` | 可选；只有访问交易所需要时才填 |

## 1. 启动后端

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：<http://127.0.0.1:8000/health> 应返回 `{"status":"ok"}`。

## 2. CLI 最小闭环

```bash
cd backend
source .venv/bin/activate
python -m app.agent doctor
python -m app.agent login
python -m app.agent mode
python -m app.agent strategies
# 先问用户交易所（okx / binance）与策略；默认推荐趋势 trend_following_core
python -m app.agent preview \
  --strategy trend_following_core \
  --exchange okx \
  --symbol BTC/USDT:USDT \
  --testnet
```

说明：

- `login` 会缓存 token 到 `backend/.helix-agent-token`
- 未保存交易所凭证时 `mode` 为 `not_configured`
- `doctor` 的 `network` 字段给出直连/代理建议与可对用户说的话
- **预览不能省**：启动前必须把 preview 摘要给用户确认
- CLI 示例里的 `--exchange okx` 只是示范；Agent 对话里要先问用户选 OKX 还是 Binance

## 3. 保存测试网交易所凭证（两步）

**本地填了密钥 ≠ 已保存到后端。** 先确认用户选的交易所，再保存：

```bash
# 路径 A（长期复用）：.env 作输入源，再写入后端
# 在 backend/.env 填写 HELIX_EXCHANGE_API_KEY / SECRET（OKX 还需 PASSPHRASE）
python -m app.agent save-credentials --exchange okx --testnet --confirm-save-credentials

# 路径 B（推荐临时/首次）：交互输入，不必在 .env 写交易所密钥
python -m app.agent save-credentials --exchange okx --testnet --prompt --confirm-save-credentials
```

成功后凭证在**后端数据库**；`.env` 里 `HELIX_EXCHANGE_*` 为空也正常。判断是否配好：用 `doctor` / `mode`，不要 grep `.env`。  
OKX 详见 [OKX_CREDENTIALS.md](OKX_CREDENTIALS.md)。

## 4. 用户常说的话（示例）

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

Agent 应主动问：用哪个交易所（OKX / Binance）、要哪个策略（默认推荐趋势），再 preview。  
完整应答流程见 [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md)。
## 5. 首次配置成功后：主动问网页

不要等用户问「怎么没网页」。配置跑通后主动说：

> 本机还有网页控制台，可以看状态和成交。要不要一起启动？  
> 登录用管理员账号（`.env` 里的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`，示例默认 `admin` / `ChangeMe123!`），不用 `client001`。

```bash
cd frontend
npm install
npm run dev
# http://localhost:3000 ，依赖后端 :8000
```

详见 [OPERATIONS.md](OPERATIONS.md)。

### Agent 如何处理 `API_ENCRYPTION_KEY`

- **用途**：加密写入数据库的交易所 API Key / Secret / Passphrase。
- **默认做法**：留空；后端用 `JWT_SECRET` 派生，本地自用够了。
- **不要**：回显该值；首次配置时逼用户生成；在已保存凭证后擅自更换（会导致「cannot be decrypted」，需重新保存凭证）。
- **可选进阶**：用户明确要独立加密密钥时，再生成一次稳定的 url-safe base64（32 字节）写入 `.env`，之后保持不变。

## 6. MCP（可选，配置在运行时仓库）

Helix 技能插件目录不含 MCP 文件。用**本 GitHub 运行时仓库**：

- 索引：[examples/mcp/README.md](../examples/mcp/README.md)
- 说明：[MCP_SETUP.md](MCP_SETUP.md)

Agent 应复制对应示例、改用户本机 `backend` 绝对路径，再重启宿主。

## 7. 停机时关于仓位

默认 `stop` **只停策略、不平仓**。用户明确要求平仓时用 `stop --close-all --confirm-close-all`；**只平机器人管理的仓位**，不会自动平启动前账户里已有的仓。

## 8. 卡住了

见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。

## 验收清单

- [ ] setup 能装好依赖（需要时代理自动用于 pip）
- [ ] `doctor.network` 能给出直连 / 7890 / 问用户代理之一
- [ ] 未保存凭证时 `mode` 为 `not_configured`
- [ ] 保存测试网凭证后可 preview
- [ ] 首次成功后 Agent 会主动询问是否启动网页
