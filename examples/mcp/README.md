# 本机 MCP 配置示例（运行时仓库）

Helix 技能插件**不包含** MCP 配置。用户 clone 本仓库并启动后端后，在这里取模板。

| 文件 | 给谁用 |
|------|--------|
| `claude_desktop.example.json` | Claude Desktop / 多数 JSON 形态 MCP 宿主 |
| `codex.example.toml` | Codex / ChatGPT 桌面 MCP 片段 |
| `.mcp.json.example` | Claude Code / Cursor 等认项目级 `.mcp.json` 的宿主 |

## Agent / 用户怎么做

1. 后端已在跑：`http://127.0.0.1:8000/health` → `ok`  
2. 复制对应示例到宿主要求的位置  
3. 把 `cwd`（或等价字段）改成**本机** `.../helix-trader/backend` 绝对路径  
4. 建议 `command` 用 `backend/.venv/bin/python`  
5. 重启宿主 → 先 `doctor` → 再 `login`  

完整说明：[docs/MCP_SETUP.md](../../docs/MCP_SETUP.md)
