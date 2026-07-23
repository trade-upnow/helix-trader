# OKX 凭证与 Passphrase 说明

在 Helix 中使用 OKX 前，需要准备 API 凭证。本文说明字段含义、测试网/实盘差异、权限建议与保存方式。

## 三个字段分别是什么

| 字段 | 含义 |
|------|------|
| `api_key` | OKX 创建 API Key 后显示的 Key |
| `api_secret` | 创建时显示的 Secret（只显示一次，请本地保管） |
| `passphrase` | **创建 API Key 时你自己设置的 API 密码短语** |

重要：

- Passphrase **不是** OKX 登录密码。
- Passphrase **不是** 资金密码 / 交易密码。
- 填错会导致鉴权失败；工具侧不会回显完整密钥值。

## 测试网与实盘是两套 Key

- OKX 测试网（demo）与实盘（live）的 API Key **分开创建、分开保存**。
- Helix 的运行模式由**已保存凭证**的 `use_testnet` 决定，不是启动时临时“口头切换”。
- 从测试网切到实盘的推荐顺序：
  1. 停止当前机器人
  2. 保存实盘凭证（`use_testnet=false`）
  3. 本地设置 `HELIX_ALLOW_LIVE_TRADING=true`
  4. `preview_bot_config`
  5. 用户确认后 `start_bot`，并带 `confirm_live_trading=true`

## 最小权限建议

创建 API Key 时：

- 只开通你确实需要的**合约交易**相关权限
- **不要**开通提现权限
- 若平台支持 IP 白名单，优先限制到你的机器出口 IP
- 新手请先用测试网 Key 验证整条链路

## 在 Helix 里怎么保存（两步）

**填进 `.env` ≠ 已保存到后端。** 运行模式读的是本地数据库里的 `ApiCredential`，不是环境变量本身。  
`--prompt` 成功后 `.env` 里 `HELIX_EXCHANGE_*` 仍可为空——这是正常路径。Agent **不要**用 grep `.env` 判断是否已配置。

任选一种输入源（不要公开粘贴密钥），然后必须执行保存：

1. **路径 A：本地 `.env` 作输入源**（适合长期复用）  
   在 `backend/.env` 填写：
   - `HELIX_EXCHANGE_API_KEY`
   - `HELIX_EXCHANGE_API_SECRET`
   - `HELIX_EXCHANGE_PASSPHRASE`  
   再执行：
   ```bash
   python -m app.agent save-credentials --exchange okx --testnet --confirm-save-credentials
   ```
2. **路径 B：CLI 交互输入**（推荐首次/临时；不必写 `.env` 交易所密钥）  
   ```bash
   python -m app.agent save-credentials --exchange okx --testnet --prompt --confirm-save-credentials
   ```
3. **可信私有 Agent 会话**  
   用户明确提供后，由 Agent 调用 `save_exchange_credentials`；不得回显完整密钥。

保存后用这些判断是否就绪（不要看 `.env` 是否有交易所密钥）：

```bash
python -m app.agent doctor
python -m app.agent mode
python -m app.agent status
```

确认结果：

- 未保存前：`mode` 应为 `not_configured`（不要当成实盘）
- 保存测试网后：`mode` 应为 `testnet`，并看到脱敏 `masked_api_key`

## 安全禁忌

- 不要把 Key / Secret / Passphrase / token 贴到聊天、Issue、截图公开处
- 不要把实盘 Key 提交进 Git
- 怀疑泄露时：立刻在 OKX 作废旧 Key，再创建新 Key 并重新保存
- Agent 文档与日志侧应只出现脱敏信息（如 masked key）

更多排错见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。
