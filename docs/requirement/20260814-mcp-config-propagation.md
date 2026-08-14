# MCP 配置传播
最后修改时间: 2026-08-14 22:18:17

Review status: Accepted

## Background

`ccs-plus launch codex --provider <provider>` 会把 `CODEX_HOME` 设为
`apps.codex.home`，并为自定义 provider 生成独立的 managed profile。
原生 `codex mcp add` 将全局 MCP 写入该进程 `$CODEX_HOME/config.toml`，但
当前 profile 生成逻辑只从 `apps.codex.user_home` 复制 `mcp_servers`，不会
读取 state home 的基础 `config.toml`。因此通过受管环境添加的 MCP 不会进入
后续的 provider profile。

对相邻 CLI 的源码分析结果如下：

- Claude: 每次启动将用户 `mcpServers` 合并进 `apps.claude.home/.claude.json`，
  且保留该目标文件已有的不同名条目，不存在 Codex 的同类覆盖路径。可是 MCP
  来源被硬编码为 `Path.home()/.claude.json`，未使用 `apps.claude.user_home`。
- Grok: 使用稳定的 `apps.grok.home/config.toml`，managed model 写入会保留其
  他配置表；但项目当前不从用户 `~/.grok/config.toml` 同步 MCP。外部执行
  `grok mcp add --scope user` 后，受管启动不会自动携带该用户级 MCP。

## Goal

修复 Codex、Claude 与 Grok 在受管启动中遗漏或未同步的 MCP 配置。

## Non-goal

- 不改变 provider endpoint、API Key、模型、权限或会话隔离语义。
- 不自动修改用户现有的 `~/.codex`、`~/.claude.json`、`~/.grok` 配置。

## User scenarios

1. 用户在带有 `CODEX_HOME=apps.codex.home` 的终端执行 `codex mcp add`，随后
   再通过同一 `ccs-plus` Codex provider 启动，新增服务器可被 profile 加载。
2. 用户同时在默认 Codex user home 和 state home 配置 MCP，启动结果可预测，
   不会静默丢失任一不同名服务器。
3. 用户可以从文档或实现中明确判断 Claude/Grok 的用户级 MCP 是否会被受管启动
   继承。

## Acceptance

- Codex managed profile 合并 state-home 与 user-home 的 `mcp_servers`。
- 为同名 MCP 定义并测试稳定的优先级。
- 不影响已有 provider profile 的连接和认证配置。
- 增加针对 Codex state-home MCP 保留、user-home MCP 合并及同名冲突的测试。
- Claude 从配置的 user home 同级 `.claude.json` 读取 MCP。
- Grok 合并 user-home 与 state-home 的 `mcp_servers`，并保留前者以外的 state
  配置。

## Open questions

不适用。用户已确认三种 CLI 的 MCP 问题均需修复。

## Decisions

- Codex state-home MCP 漏传是缺陷，必须修复。
- Claude 的 `user_home` MCP 来源不一致与 Grok 用户级 MCP 未同步均纳入本次修复。
- 同名 MCP 一律由 user-home 覆盖 state-home。
- Grok 仅同步 MCP，不同步 skills 或 plugins。

## Risk

- 合并两个 MCP 表时可能出现同名服务器配置冲突，必须显式设定优先级并覆盖测试。
- Grok 用户级 MCP 同步会扩大现有隔离 Home 的可见配置范围，但不暴露 skills、plugins、
  endpoint 或认证配置。
