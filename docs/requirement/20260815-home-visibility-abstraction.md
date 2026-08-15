# Home Visibility 抽象与三端策略统一
最后修改时间: 2026-08-15 22:24:52

Review status: Accepted

## Background

`ccs-plus` 为 Claude、Codex 和 Grok 使用隔离的 runtime home，同时按需将真实
user home 中的 sessions、skills、plugins、MCP 和扩展配置暴露给受管启动。
现有行为散落在 `home_visibility.py`、`launcher.py` 和 `managed_config.py` 中，
并存在 `sync_claude_mcp_servers`、`sync_codex_user_config`、
`sync_grok_user_mcp_servers` 等 app-specific 顶层过程函数。

Claude plugin 状态已引入 link/copy/skip 差异化处理，因此需要同时审视 Codex
和 Grok 的目录结构与配置语义，避免机械复用 Claude 文件名单或遗漏其他 CLI 的
用户扩展状态。

## Goal

- 建立统一的 `HomeVisibility` 基类和 Claude、Codex、Grok 具体实现。
- 由具体实现完整覆盖各 CLI 的目录共享、状态复制、缓存隔离和配置合并策略。
- 让 launcher 和 managed config 只依赖统一抽象，不再持有 app-specific 的同步过程。
- 基于各 CLI 的实际目录结构与官方行为，明确三端的 visibility 策略并用测试锁定。

## Non-goal

- 不迁移或修复旧版本已经生成的隔离 home、硬链接或历史状态。
- 不共享整个 user home，也不共享认证信息、provider endpoint、API Key 或无关运行状态。
- 不统一三套 CLI 的物理目录格式；各实现仍遵循对应 CLI 的原生布局。
- 不改变 provider 选择、模型、推理强度和权限配置的业务语义。

## User scenarios

1. 用户通过任一受支持 CLI 启动 provider 时，真实 home 中允许继承的扩展和 MCP
   配置能够出现在隔离 home 中。
2. CLI 的索引/状态文件需要初始可见但不应反向写回真实 home 时，系统使用复制而非链接。
3. 可再生 cache、临时安装目录和进程运行目录保持隔离，不因 visibility 共享产生并发污染。
4. 新增或调整某一 CLI 的 visibility 规则时，只需修改对应实现类，不需要在 launcher
   或 managed config 增加新的 app-specific 同步分支。

## Acceptance

- 存在 `HomeVisibility` 基类及 `ClaudeHomeVisibility`、`CodexHomeVisibility`、
  `GrokHomeVisibility` 具体实现，并有统一构造入口。
- launcher 通过统一入口调用 visibility；managed profile 生成通过抽象钩子接收可见配置。
- 产品代码中不再存在 `sync_claude_mcp_servers`、`sync_codex_user_config`、
  `sync_grok_user_mcp_servers` 或同类 app-specific 顶层同步入口。
- Claude 保留 skills/plugins 可见、plugin metadata copy、catalog cache 隔离和 MCP 合并。
- Codex 覆盖 sessions、skills、plugins、MCP、marketplaces、shell policy 与当前项目 trust；
  plugin 进程目录和安装 staging 保持隔离。
- Grok 默认从 `~/.grok` 获取用户扩展；覆盖 skills、plugins、hooks、installed plugins、
  MCP 和 marketplace 配置；plugin registry 使用复制，marketplace cache 保持隔离。
- 同名 MCP 由 user home 覆盖 state home，不同名 state-home MCP 保留。
- README 与配置默认值反映三端实际行为。
- 相关测试、lint、类型检查和 diff whitespace 检查通过。

## Open questions

暂无需要用户确认的未决事项。

## Decisions

- 采用多态 visibility 实现承载 app-specific 行为，不用 launcher 条件分支组织同步步骤。
- link/copy/skip 策略按各 CLI 实际目录结构分别制定，不要求三端使用相同文件名单。
- 本任务作为独立需求记录，不修改已 Accepted 的历史 MCP propagation requirement。
- Grok 的新策略取代历史需求中“仅同步 MCP、不共享 skills/plugins”的范围约束。
- 不提供历史隔离 home 的迁移逻辑；新策略只保证新建或符合当前结构的状态目录。

## Risk

- CLI 升级可能改变内部目录或索引文件语义，需要通过测试和后续版本审视维护策略。
- 目录 junction/symlink 会让隔离运行直接读写真实扩展目录，必须严格排除运行时临时目录。
- 配置合并若错误覆盖 provider、认证或模型配置，会破坏隔离边界；只允许合并明确列出的表。
- Grok visibility 范围扩大后，用户安装的 hooks/plugins 会在受管启动中执行，应视为用户主动
  配置的可信扩展，但不得额外暴露认证和运行缓存。
