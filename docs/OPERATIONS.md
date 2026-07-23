# Helix AI Trader — 本地启动与运维说明

本文说明如何在开发机上一键拉起 **后端 API（FastAPI）** 与 **前端（Next.js）**，以及常见环境变量与验证方式。

---

## 一、环境要求

| 组件 | 建议版本 |
|------|----------|
| Node.js | 20.x 或以上（与 Next 16 兼容） |
| Python | **3.10+（推荐 3.12）**；macOS 自带 `python3` 常为 3.9，可能导致 ccxt 等依赖安装失败 |
| npm | 随 Node 安装即可 |

---

## 二、仓库结构（与本说明相关）

- `backend/`：FastAPI 服务，默认监听 **8000** 端口。
- `frontend/`：Next.js 应用，开发默认 **3000** 端口。

---

## 三、后端启动

### 3.1 首次准备

```bash
# 推荐一键（会优先选用 python3.12 / 3.11 / 3.10，拒绝过旧的系统 3.9）
bash scripts/setup_backend.sh

# 或手动：
cd backend
python3.12 -m venv .venv   # 不要用 macOS 自带的 python3（多为 3.9）
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3.2 环境变量

复制示例文件并按需修改：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | 默认 `sqlite+aiosqlite:///./helix.db`，数据库文件在 `backend/` 目录下生成/使用。 |
| `JWT_SECRET` | JWT 签名密钥，**生产环境务必改为长随机串**。 |
| `API_ENCRYPTION_KEY` | 可选。用于加密数据库里的交易所 API Key/Secret。**新手可留空**：后端会用 `JWT_SECRET` 派生。一旦保存过交易所凭证，就不要随便改这个值或 `JWT_SECRET`，否则旧凭证解不开，需重新 `save-credentials`。Agent **不要回显**该值，也不要在首次配置时强行让用户填写。 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | 种子管理员账号。**前端网页登录用这对**（示例默认 `admin` / `ChangeMe123!`）。 |
| `CLIENT_USERNAME` / `CLIENT_PASSWORD` | 可选的额外演示账号。**不要引导普通用户用这对登录前端。** |
| `BOT_POLL_SECONDS` | 机器人轮询间隔（秒）。 |
| `EXCHANGE_PROXY_URL` | 可选。直连 OKX 时可留空。需要时填一个即可，如 `http://127.0.0.1:7890`。首次配置时 `doctor` / `setup_backend.sh` 会按「直连 → 7890 → 问用户」自动判断。 |
| `EXCHANGE_HTTP_PROXY` | 可选；单独指定 HTTP 代理，优先于 `EXCHANGE_PROXY_URL`。 |
| `EXCHANGE_HTTPS_PROXY` | 可选；单独指定 HTTPS 代理，优先于 `EXCHANGE_PROXY_URL`。 |

### 3.3 启动命令

在 **`backend/`** 目录、且已激活虚拟环境：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 健康检查：<http://127.0.0.1:8000/health>，应返回 `{"status":"ok"}`。
- 交互式 API 文档：<http://127.0.0.1:8000/docs>。

应用启动时会执行建表/种子数据，并尝试恢复此前处于 running 的会话（见 `app/main.py` 的 `lifespan`）。

若你本机不能直连交易所，可在 `backend/.env` 配置：

```bash
EXCHANGE_PROXY_URL=http://127.0.0.1:7890
```

修改后请重启后端；机器人访问 Binance/OKX 的请求会自动走该代理。

---

## 四、前端启动

### 4.1 首次准备

```bash
cd frontend
npm install
```

### 4.2 环境变量

```bash
cp .env.example .env.local
```

（Next 习惯使用 `.env.local`；也可使用 `.env`，以你本地为准。）

| 变量 | 说明 |
|------|------|
| `NEXT_PUBLIC_API_BASE_URL` | **留空（推荐本地）**：浏览器请求本站 **`/api/*`**，由 `next.config.ts` 的 rewrites 转发到后端（同源、无 CORS、Network 里可见 `localhost:3000/api/...`）。若填写完整 URL（如 `http://127.0.0.1:8000`），则浏览器直连后端。 |
| `BACKEND_PROXY_URL` | 仅服务端用于 rewrites，默认 `http://127.0.0.1:8000`。后端改端口时同步改此项。 |
| `NEXT_PUBLIC_ENABLE_INTERNAL_TESTNET` | 历史开关；当前控制台模拟盘主要以后端凭证中的 `use_testnet` 为准，可按需保留。 |

### 4.3 开发模式

```bash
npm run dev
```

浏览器访问：**<http://localhost:3000>**。  
本项目使用 `next-intl` 且 **`localePrefix: "always"`**，实际页面路径带语言前缀，例如：

- 韩语（默认语言）：<http://localhost:3000/ko>
- 中文：<http://localhost:3000/zh-CN>
- 英文：<http://localhost:3000/en>
- 西语：<http://localhost:3000/es>

登录与客户控制台路径示例：`/ko/login`、`/ko/app`（其它语言把 `ko` 换成对应 locale 即可）。

### 4.4 生产构建（本地验证）

```bash
npm run build
npm run start
```

---

## 五、推荐启动顺序

1. 先启动 **后端**（8000 端口就绪）。
2. 再启动 **前端**（确保 `NEXT_PUBLIC_API_BASE_URL` 指向该后端）。

若前端已开、后启动后端，刷新页面即可；若修改了 `.env.local`，需重启 `npm run dev`。

---

## 六、本地验证清单

1. 打开 <http://127.0.0.1:8000/health> 确认 `ok`。
2. 打开带 locale 的首页，例如 <http://localhost:3000/ko>。
3. 使用 `.env` 中的 **管理员账号**登录前端（`ADMIN_USERNAME` / `ADMIN_PASSWORD`；示例默认 `admin` / `ChangeMe123!`）。**不要**用 `CLIENT_USERNAME`（如 `client001`）。
4. 在控制台保存 API 凭证后，确认浏览器请求发往 `NEXT_PUBLIC_API_BASE_URL`，路径形如 **`/api/auth/*`**、**`/api/bot/*`**、**`/api/strategies/*`**（定义见 `backend/app/api/routes/*.py`）。

---

## 七、常见问题

| 现象 | 可能原因 |
|------|----------|
| 前端报网络/CORS | 确认后端已启动；`NEXT_PUBLIC_API_BASE_URL` 协议与端口是否正确（不要用错 https/http）。 |
| 登录 401 | 前端请用 `ADMIN_USERNAME` / `ADMIN_PASSWORD`；不要用 `CLIENT_*`。或以本地 `.env` 为准；数据库已重建时需用当前种子账号。 |
| 保存凭证后解密失败 | `API_ENCRYPTION_KEY` 或 `JWT_SECRET` 相对保存时发生了变化；重新 `save-credentials`，或恢复原来的密钥配置。 |
| 后端依赖报错 | 确认在 `backend/.venv` 中安装 `requirements.txt`；异步 SQLite 需 `greenlet`（已在依赖中）。 |

---

## 八、端口汇总

| 服务 | 默认地址 |
|------|----------|
| Next 开发服 | http://localhost:3000 |
| FastAPI | http://127.0.0.1:8000 |

如需改端口：前端用 `npm run dev -- -p 3001`；后端改 `uvicorn` 的 `--port`。

---

## 九、Agent / MCP / CLI

Agent 入口在 `backend/app/agent/`。

```bash
cd backend
source .venv/bin/activate
python -m app.agent doctor
python -m app.agent mcp
```

更多说明：

- `README.md`
- `README_AGENT.md`
- [GETTING_STARTED_AGENT.md](GETTING_STARTED_AGENT.md)
- [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md)
- [OKX_CREDENTIALS.md](OKX_CREDENTIALS.md)
- [MCP_SETUP.md](MCP_SETUP.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- `docs/parameters.md`
- `SECURITY.md`
