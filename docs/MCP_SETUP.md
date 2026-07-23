# MCP 配置与验证

把 Helix Agent 接到 Claude Desktop / Codex 等 MCP 宿主。配置前请先完成本地后端启动。

## 前置条件

1. 已安装后端依赖（见 [GETTING_STARTED_AGENT.md](GETTING_STARTED_AGENT.md)）
2. 后端正在运行：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. <http://127.0.0.1:8000/health> 返回 `{"status":"ok"}`

MCP 进程本身**不会**替你启动 FastAPI；后端挂了时，工具会报无法连接。

## 替换绝对路径（cwd）

示例都在**本运行时仓库**（技能包里没有 MCP 配置文件）：

| 文件 | 用途 |
|------|------|
| [examples/mcp/README.md](../examples/mcp/README.md) | 索引 |
| [examples/mcp/claude_desktop.example.json](../examples/mcp/claude_desktop.example.json) | Claude Desktop 等 |
| [examples/mcp/codex.example.toml](../examples/mcp/codex.example.toml) | Codex |
| [examples/mcp/.mcp.json.example](../examples/mcp/.mcp.json.example) | Claude Code / Cursor 项目级 `.mcp.json` |

把其中的：

```text
/ABSOLUTE/PATH/TO/helix-trader/backend
```

换成你机器上的真实路径，例如：

```text
/Users/you/code/helix-trader/backend
```

要点：

- `cwd` 必须指向 **`backend/`**，因为模块入口是 `python -m app.agent mcp`
- `command` 建议使用该目录虚拟环境里的 `python`（如 `backend/.venv/bin/python`）
- 不要把真实 `HELIX_ACCESS_TOKEN`、交易所密钥写进会提交的配置文件
- Agent：配 MCP 时只指向本仓库 `examples/mcp/`；技能插件包内没有 MCP 模板

## Claude Desktop 示例要点

```json
{
  "mcpServers": {
    "helix-trader": {
      "command": "python",
      "args": ["-m", "app.agent", "mcp"],
      "cwd": "/ABSOLUTE/PATH/TO/helix-trader/backend",
      "env": {
        "HELIX_API_BASE_URL": "http://127.0.0.1:8000",
        "HELIX_ALLOW_LIVE_TRADING": "false"
      }
    }
  }
}
```

## Codex 示例要点

```toml
[mcp_servers.helix-trader]
command = "python"
args = ["-m", "app.agent", "mcp"]
cwd = "/ABSOLUTE/PATH/TO/helix-trader/backend"

[mcp_servers.helix-trader.env]
HELIX_API_BASE_URL = "http://127.0.0.1:8000"
HELIX_ALLOW_LIVE_TRADING = "false"
```

## 连接后如何验证

1. 重启 MCP 宿主，确认 `helix-trader` 已加载
2. 让 agent **先调用** `doctor`（或 CLI：`python -m app.agent doctor`）
3. 再让 agent 调用 `login`（使用本地 `.env` 中的用户名密码，不要在公开聊天贴密码）
4. 调用 `get_runtime_mode` / `list_strategies` 做只读验证

若宿主支持查看 tools/list，应能看到 `doctor`、`login`、`preview_bot_config`、`start_bot` 等工具。

## 登录态说明

优先级：

1. 环境变量 `HELIX_ACCESS_TOKEN`
2. 本地缓存文件 `backend/.helix-agent-token`
3. 空（需要先 `login`）

行为建议：

- 在同一 MCP 进程内调用 `login` 后，后续工具可继续用该 token
- MCP 进程重启后：重新 `login`，或依赖本地 token 缓存文件，或在私有本地 env 中设置 `HELIX_ACCESS_TOKEN`
- 清理本地登录态：`logout` 工具 / `python -m app.agent logout`

## 安全

- 默认保持 `HELIX_ALLOW_LIVE_TRADING=false`
- Agent 规则见 [README_AGENT.md](../README_AGENT.md) 与 [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md)
- 出错排查见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
