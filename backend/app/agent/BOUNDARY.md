# 打包边界

本包只是适配层。

除非有阻塞性缺陷，否则不要为了 Agent 打包去改这些模块：

- `app/services/strategies/trend_following.py`
- `app/services/bot_manager.py`
- `app/services/exchange/ccxt_adapter.py`

允许改动的范围：

- MCP / CLI / HTTP 客户端
- 安全门禁与脱敏
- `doctor` / 安装检查
- 参数元数据
- 适配层相关文档与测试
