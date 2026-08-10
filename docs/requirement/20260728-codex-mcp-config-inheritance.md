# Codex MCP 配置继承

最后修改时间: 2026-07-28 11:47:42

Review status: Accepted

Flow mode: light / 轻量模式

## Goal

通过 `ccs run` 启动 Codex 时，将真实 `~/.codex/config.toml` 中的 `[mcp_servers]` 合并到临时 `CODEX_HOME/config.toml`，使已注册的 MCP（如 `mks-ttyd`）可用。

## Non-goal

- 不链接或覆盖整个真实 `config.toml`。
- 不改变 provider 的模型、网关、认证及 `CODEX_HOME` 隔离。
- 不新增 MCP 配置格式或管理命令。

## Acceptance

- direct 与 proxy 启动都包含用户配置中的 `[mcp_servers]`。
- provider 的模型和网关配置保持不变。
- 新建 Codex 会话后可发现并启动 `mks-ttyd mcp`。
- 相关单元测试通过。

## Open questions

暂无。沿用现有用户表覆盖 provider 同名表的语义。

## Decisions

- 在现有结构化 TOML 白名单合并中加入 `mcp_servers`。
- 用户的 MCP 配置为完整顶层表，避免同名服务的隐式合并冲突。

## Risk

带内联 `env` 值的 MCP 配置会进入临时文件；本任务的 `mks-ttyd` 不含该类配置。
