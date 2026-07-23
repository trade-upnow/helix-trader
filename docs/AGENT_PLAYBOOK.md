# Agent 引导剧本

给 Codex / Claude 等 agent 使用。格式：用户可能问什么 → 先调用哪些工具 → 怎么回答 → 不能做什么。

硬规则见 [README_AGENT.md](../README_AGENT.md)。

---

## 对用户说话的总原则

1. 用户常见说法是「帮我启动这个机器人」「我要怎么启动」，不是「请检查虚拟环境」。
2. **密钥保护是你的硬规则**，不要让用户念「不要读取或展示任何密钥值」。
3. 首次配置时自己跑 `doctor` / `scripts/setup_backend.sh`，不要把安装细节甩给小白。
4. 网络：先探测 `www.okx.com` 直连 → 再试 `http://127.0.0.1:7890` → 仍不通才问用户要代理端口。
5. 首次配置跑通后，**主动**告诉用户有本地网页控制台，并询问要不要启动（不要等用户问「怎么没网页」）。登录用 `ADMIN_USERNAME` / `ADMIN_PASSWORD`（示例默认 `admin` / `ChangeMe123!`），**不要**让用户用 `CLIENT_USERNAME`。
6. `API_ENCRYPTION_KEY`：新手留空即可；不要回显、不要乱改。已保存交易所凭证后改密钥会导致解密失败，需重新保存凭证。
7. 配 MCP 只用**本仓库（运行时）**的 `examples/mcp/` 与 `docs/MCP_SETUP.md`；Helix 技能插件目录里不含 MCP 配置文件。

---

## 场景 A：这份代码是干嘛的？

**用户可能问**

- “这份仓库是做什么的？”
- “Helix Trader 能帮我赚钱吗？”

**应先调用**

1. 可选：`health_check` 或 `doctor`

**应怎么回答**

- 定位：本地交易机器人控制与监控工具，支持网页 / CLI / MCP agent。
- 不是收益承诺产品，不替代投资决策。
- 下一步：直接说「我可以帮你完成首次配置并启动测试网」，而不是甩一串安装术语。

**不能做什么**

- 不承诺收益、胜率或“稳赚”。
- 不读取或展示任何密钥值（你自己遵守，无需用户提醒）。

---

## 场景 B：支持什么策略？

**用户可能问**

- “有哪些策略？”
- “趋势和突破有什么区别？”

**应先调用**

1. `list_strategies`
2. 如需参数细节：`explain_parameters`

**应怎么回答**

- 用工具返回解释 `trend_following_core` 与 `trend_breakout_accel`：适用市场、关键参数、风险点。
- 明确：策略可能长时间无成交，取决于行情与过滤条件。

**不能做什么**

- 不把策略说成保证盈利。
- 不在未 preview 的情况下直接启动。

---

## 场景 C：帮我启动机器人（最常见）

**用户可能问**

- “帮我启动这个机器人”
- “我要怎么启动”
- “帮我跑起来”
- “用 OKX 测试网跑起来”

**你必须做的事（对用户少说术语，对工具按序调用）**

1. `doctor`（看 `network` / `next_steps` / `how_to_talk_to_user`）
2. 若缺本地环境：执行 `bash scripts/setup_backend.sh`（脚本会按网络自动决定 pip 是否走代理）
3. 启动后端（若未启动）
4. 必要时 `login`
5. **先问用户选哪个交易所**：`okx` 或 `binance`（不要默认替用户选 OKX；用户已明确说出时除外）
6. 看 `get_runtime_mode`；若是 `not_configured`，按用户选的交易所保存测试网凭证（OKX 需要 Passphrase）。两条路径任选：A. `.env` 填 `HELIX_EXCHANGE_*` 再 `save-credentials`；B. `save-credentials --prompt`（不写 `.env` 也行）。**不要用 grep .env 判断是否已配置**；以 `doctor` / `mode` / `exchange_credentials` 为准
7. `list_strategies`，用人话介绍两个策略，并**默认推荐趋势跟随** `trend_following_core`；若用户要突破则用 `trend_breakout_accel`
8. **必须** `preview_bot_config`，把配置摘要给用户看（策略 / 交易所 / 交易对 / 杠杆与风控）
9. **用户确认预览后** 才 `start_bot`（默认测试网）
10. 首次配置成功后，主动问要不要开本地网页；并告知登录用管理员账号 `ADMIN_USERNAME` / `ADMIN_PASSWORD`（默认常见为 `admin` / `ChangeMe123!`，以本地 `.env` 为准），**不要用** `CLIENT_USERNAME` / `client001`。见 [OPERATIONS.md](OPERATIONS.md)

**策略怎么问（保留预览，不要跳过）**

- 先说：目前有两个策略——趋势跟随（推荐新手/默认）、突破动量。
- 用户不选时，按 `trend_following_core` 做 preview，并说明「我先按推荐的趋势策略给你预览，你确认后再启动」。
- **没有 preview、用户未确认配置，不能 start。**

**交易所怎么问**

- 问：「你想用哪个交易所的测试网？OKX 还是 Binance？」
- 只有用户明确指定后，才按该交易所保存凭证 / preview / start。
- 网络探测用 `www.okx.com` 判断代理是否需要，这是连通性探测，**不等于**默认选用 OKX 交易所。

**网络怎么跟用户说**

- 用 `doctor.network.user_message` 的口径。
- 直连通：说不需要代理；若本地还写着代理，可建议去掉。
- 仅默认 7890 通：说会用本机常见代理端口继续，并写入配置。
- 都不通：只问「你的代理地址/端口是多少」，例如 `http://127.0.0.1:7890`。

**应怎么回答**

- 先用人话汇报进度：「我先帮你检查本机和网络 → 你选交易所和策略 → 保存测试网凭证 → 预览配置 → 你确认后启动」。
- 明确当前是测试网还是实盘；未配置就说还没配好交易所，不要说成实盘。
- 实盘必须本地开关 + 工具确认 + 用户明确同意。

**不能做什么**

- 一上来让用户自己装虚拟环境、念安全咒语。
- 跳过 preview 直接 start。
- 不经询问就默认 OKX / 默认某个策略并直接启动。
- 把「已填本地配置」说成「已配置交易所」。
- 等用户问「怎么没网页」才提前端。

---

## 场景 D：需要哪些配置？ / Passphrase

**用户可能问**

- “我要准备什么才能跑起来？”
- “OKX Passphrase 是什么？”

**应先调用**

1. `doctor`
2. 若问模式：`get_runtime_mode`

**应怎么回答**

用人话列缺口（不要甩术语清单）：

- 登录账号：网页控制台用 **管理员账号**（`ADMIN_USERNAME` / `ADMIN_PASSWORD`）；不要推 `CLIENT_*`
- `API_ENCRYPTION_KEY`：可留空，不必让用户纠结；用途是加密库里的交易所密钥
- 交易所 API（OKX 需要 Key / Secret / Passphrase；Passphrase 是创建 API 时自己设的短语，不是登录密码）
- 凭证要保存进后端（只写本地文件还不够）
- 网络：按上面的自动探测结果说明是否需要代理

OKX 细节见 [OKX_CREDENTIALS.md](OKX_CREDENTIALS.md)。

**不能做什么**

- 不要求用户把密钥贴到公开聊天。
- 不打印本地配置文件内容。

---

## 场景 E：为什么没正常运行 / 报错了？

**用户可能问**

- “为什么启动失败？”
- “机器人在跑但没有成交？”
- “Missing access token 是什么意思？”

**按错误分类调用**

| 现象 | 优先工具 | 恢复方向 |
|------|----------|----------|
| 首次还不能跑 | `doctor` | 跑 setup、起后端；对人少说安装术语 |
| 后端连不上 | `doctor` / `health_check` | 启动后端服务 |
| Missing access token | `login` | 重新登录 |
| mode=`not_configured` | `get_runtime_mode` | 保存交易所凭证（两步） |
| 访问不了 OKX | `doctor.network` | 直连→7890→问用户代理 |
| 交易对不可用 | `list_markets` | 换可用交易对 |
| 已启动但无成交 | `get_bot_status`、`get_recent_trades` | 看状态说明，可能是行情未满足 |
| 用户说停止/关掉策略 | 先 `get_bot_status`；有仓且未说平仓 → **先问**只停还是停并平 | 勿默认 `close_all=true` |
| stop 后账户仍有仓 | `get_bot_status` | 只平机器人仓，不平历史仓 |
| 实盘被拦截 | `get_runtime_mode` | 检查 live 开关与确认 |

详细映射见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。

**不能做什么**

- 反复调用 `start_bot` 碰运气。
- 为“看起来没成交”擅自提高杠杆或切实盘。

---

## 用户常说的话（示例，不是让用户背诵的脚本）

```text
帮我启动这个机器人
```

```text
我要怎么启动？先用测试网
```

```text
帮我启动机器人，先预览一下；策略你推荐一个就行
```

```text
现在是模拟盘还是实盘？
```

Agent 收到这类话后，按场景 C 自动推进：问交易所 → 推荐趋势策略 → preview → 确认后启动。  
不要要求用户改口成技术检查清单。