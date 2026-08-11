# 供应商管理与 CLI 启动器
最后修改时间: 2026-08-11 09:36:07

流程模式: standard

当前阶段: Requirement / 需求

Review status: Accepted

## Background

本项目将在根目录新建一个基于 `uv` 与 Python 的跨平台命令行应用。`cc-switch/` 仅作为源码和现有用户数据库格式的参考，不是本应用的源码目录。

应用直接读写 cc-switch 数据库，默认路径为用户目录下的 `.cc-switch/cc-switch.db`。供应商数据存于 `providers` 和 `provider_endpoints` 两张表：前者以 `(id, app_type)` 为联合主键，后者通过同一联合键关联并在删除时级联删除。

目标是将指定的 Claude Code、Codex CLI 或 Grok CLI 以指定供应商、工作目录和可选模型/推理强度启动。供应商切换不得为同一 CLI 另建临时 home，否则原生的会话恢复和历史选择器将看不到此前会话。

## Goal

1. 提供 Click 风格子命令的本地 CLI。首版命令面为 `providers list`、`providers add`、`providers show`、`providers delete` 和 `launch <claude|codex|grok>`。
2. 从 cc-switch 数据库展示 `claude`、`codex`、`grokbuild` 供应商；列表显示应用、名称、实际 API endpoint、模型、推理强度和类别，绝不显示 API Key 或 ID。
3. 新增自定义供应商时收集目标 CLI、名称、API endpoint、API Key、模型和可选推理强度；直接写入与 cc-switch 兼容的 `providers` 和 `provider_endpoints` 记录。
4. 新增供应商默认生成无确认开发配置：策略值来自应用配置（`settings.yaml` 的 `apps.*`），写入供应商记录后，`launch` 以该记录实际配置为准。
5. 支持按应用和名称删除唯一的自定义供应商；所有官方供应商均不可修改或删除。
6. 启动器在调用原生交互式 CLI 时复用稳定状态目录，使同一 CLI 在供应商 A、B 间切换后仍能通过原生 `resume`/历史功能看到双方产生的会话。
7. 首版只适配原生协议：Claude 使用 Anthropic Messages，Codex 和 Grok 使用 OpenAI Responses；不实现协议转换或本地代理。

## Non-goal

- 重写或嵌入 cc-switch GUI、代理、测速、计费、MCP 管理、故障转移或会话浏览器。
- 修改或删除 `category = "official"` 的供应商，或已知官方 ID（`claude-official`、`codex-official`、`grokbuild-official`）。
- 在首版中提供供应商编辑，或迁移 cc-switch 既有临时 `CODEX_HOME` 内分散的历史。
- 支持 OpenAI Chat Completions、Anthropic Messages 与 Responses 之间的请求转换，或保证任意第三方 endpoint 兼容目标 CLI。
- 删除 Claude、Codex、Grok 的会话、认证文件、工作目录或不属于本应用的配置项。

## Confirmed Decisions

- 应用是命令行工具，不提供浏览器 UI 或 TUI。
- 使用 `uv` 管理 Python 项目和运行环境，目标平台为 Windows、macOS、Linux。
- 直接读写 cc-switch SQLite 数据库，不建立独立供应商数据库，也不迁移现有供应商数据。
- 官方供应商不可修改、不可删除；首版只新增和删除自定义供应商。
- 历史连续性优先：适配三种 CLI 的稳定状态目录，不迁移旧临时目录中的会话。
- API Key 保持 cc-switch 现有兼容存储路径；本应用生成的 CLI profile/model 配置只能保存 endpoint、协议、模型和环境变量名，不能再复制 API Key。
- 启动器以当前终端的标准输入、输出、错误流直接运行原生交互式 CLI，不另起终端窗口。

## CLI Contract

### Command tree

```text
ccs-plus providers list [--app claude|codex|grok]
ccs-plus providers add <claude|codex|grok> [options]
ccs-plus providers show <name>
ccs-plus providers delete <claude|codex|grok> <name> --yes
ccs-plus launch <claude|codex|grok> --provider <name> [--cwd <path>] [--model <id>] [--effort <level>] [-v]
```

- `providers add` 必填名称、endpoint、API Key、模型；可选推理强度。
- `providers show` 按名称返回匹配记录的 API endpoint、API Key、模型和推理强度；API Key 不脱敏。同名记录可跨应用同时返回。
- `providers delete` 先按应用和名称解析唯一记录，再以内部联合键精确删除；同一应用的重名记录拒绝删除。
- `launch` 按目标应用和供应商名称解析唯一记录，必须校验其 `app_type` 与目标 CLI 对应，CLI 可执行文件可找到。未传 `--cwd` 时使用调用命令的当前工作目录；传入时该目录必须存在。同一应用的重名记录拒绝启动。
- `launch` 从数据库取用 API Key，只注入到子进程环境，命令行、正常输出和错误输出均不可回显 Key。
- 模型和推理强度默认从供应商的实际 `settings_config` 读取。`--model`、`--effort` 仅覆盖本次启动，不回写供应商或全局 CLI 配置。
- `launch -v` 使用标准库 `logging` 的基本 stderr 配置，记录目标 CLI、供应商名称、工作目录、执行参数和退出码；不得记录 API Key、环境变量或 endpoint。

### 推理强度映射

| CLI | 默认模型与覆盖 | 默认推理与覆盖 | 可接受值 |
| --- | --- | --- | --- |
| Claude | `--model <model>` | `--effort <level>` | `low`、`medium`、`high`、`xhigh`、`max` |
| Codex | profile 的 `model`，或 `--model <model>` 覆盖 | 顶层 `model_reasoning_effort`，或本次 `-c` 覆盖 | `minimal`、`low`、`medium`、`high`、`xhigh` |
| Grok | `--model <profile>`，profile 内 `model = <API model id>` | `--reasoning-effort <level>` | `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`；模型专有菜单值也可透传 |

不支持所选模型或上游的 effort 值由原生 CLI/API 返回错误；本应用只做该 CLI 的语法校验，不伪造转换或降级。

## Provider and Permission Rules

### Claude Code

- 自定义 endpoint 必须兼容 Anthropic Messages API。
- 启动器为子进程设置 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN` 和模型相关 `ANTHROPIC_*` 环境变量，并添加 `--model`、可选 `--effort`。
- 添加 `--dangerously-skip-permissions`，实现命令、工作目录写入和网络访问不确认。该参数不提供操作系统级目录隔离；强隔离只能由容器、受限账户等外层机制提供。
- 不设置供应商专属 `CLAUDE_CONFIG_DIR`，也不传 `--no-session-persistence`。必要的临时 `--settings` 文件只能补充会话设置，不能替换配置给定的稳定 Claude state home。

### Codex CLI

- 自定义 endpoint 必须兼容 OpenAI Responses API；生成的 provider 使用 `wire_api = "responses"`。
- 每个本应用管理的供应商在稳定 `CODEX_HOME` 旁创建一个受命名空间保护的 `<profile>.config.toml`。profile 内包含 `model_provider`、`model`、`model_reasoning_effort`（如有）及 `[model_providers.<id>]` 的 `base_url`、`wire_api`、`env_key`；API Key 通过启动器设置的唯一环境变量提供。
- 使用 `--profile <profile>` 启动，保留基础 `config.toml` 和 `CODEX_HOME` 中的 `sessions`、SQLite state、认证及用户配置。
- **新增/导入默认策略**（写入 cc-switch `settings_config.config` 顶层，兼容其 TOML 形态）来自 `settings.yaml` 的 `apps.codex`：
  - 默认：`approval_policy: never`、`sandbox_mode: danger-full-access`
  - 仅当配置的 `sandbox_mode` 为 `workspace-write` 时，才额外写入 `[sandbox_workspace_write] network_access = true`
  - `providers add` 与 `providers import` 共用该默认源；导入不原样恢复备份中的旧 sandbox TOML，而是按当前应用配置重建记录
- **启动以供应商实际配置为准**：从该记录的 `settings_config.config` 读取 `approval_policy` 与 `sandbox_mode`；缺失时启动失败，不回落到硬编码常量。
- **运行时 managed profile**（Codex 0.147+ permission profile 语法）不得混用旧 sandbox 键：
  - 写入 `approval_policy` = 供应商记录中的值
  - 写入 `default_permissions` = `:<sandbox_mode>`（已是 `:` 前缀则原样使用）
  - 不写入 `sandbox_mode`、`sandbox_workspace_write`、自定义 `[permissions]` 表或默认 `[windows] sandbox`
  - 可保留既有 profile 中的 `[projects]` 可信状态
  - argv 使用 `--ask-for-approval <approval_policy>`（来自供应商记录；官方供应商无配置时仍为 `never`）
- 不使用 `--dangerously-bypass-approvals-and-sandbox`（`--yolo`）作为默认路径；全盘/无沙箱语义由供应商记录中的 `sandbox_mode`（默认 `danger-full-access`）表达。
- 启动时不得继承供应商专属或临时的 `CODEX_HOME`；应使用配置的稳定 home，并清除冲突的 `CODEX_SQLITE_HOME`。本机已观察到父进程带有 cc-switch 临时 `CODEX_HOME`，这是必须处理的真实场景。

### Grok CLI

- 自定义 endpoint 必须兼容 OpenAI Responses API。
- 在稳定 `GROK_HOME/config.toml` 中创建本应用命名空间下的 `[model.<profile>]` 表，至少写入真实 `model`、`base_url`、`env_key` 和 `api_backend = "responses"`；API Key 只在启动子进程环境中注入。
- 以 `grok --model <profile>` 选择该表，不修改共享 `[models].default`，从而避免供应商切换改变其他原生启动方式的默认模型。
- 添加 `--sandbox workspace --always-approve`。`workspace` 允许 CWD 和 Grok 自身目录写入、允许子进程联网；`--always-approve` 自动通过全部工具执行确认。
- 不使用供应商专属临时 `GROK_HOME`。Grok 会话存于 `<configured-grok-home>/sessions/<encoded-cwd>/`，state home 改变会直接隔离会话历史。

## Application Configuration

- 配置文件为项目根 `settings.yaml`（语义分组，不再使用 TOML 扁平键或 Dynaconf `default:` 环境层）。
- 结构：
  - `database.path`：cc-switch SQLite 路径
  - `encryption_key`：通用 Fernet key（优先 `.env` 的 `CCS_PLUS_ENCRYPTION_KEY`）
  - `apps.claude.home` / `apps.codex.home` / `apps.grok.home`：稳定 state home
  - `apps.codex.approval_policy` / `apps.codex.sandbox_mode`：仅用于 **新增/导入** 时写入供应商记录的默认策略
- 环境变量前缀 `CCS_PLUS_`，嵌套键用 `__`（例如 `CCS_PLUS_DATABASE__PATH`、`CCS_PLUS_APPS__CODEX__HOME`）。
- 配置只读加载，不提供本应用写入或目录设置子命令。
- **职责分离**：`apps.codex.*` 默认策略只影响 add/import；`launch` 只读数据库中该供应商的实际 `settings_config`。

## Session Persistence

状态目录必须稳定，且三种 CLI 的 state home 只由应用配置提供，绝不从供应商或父进程临时环境推断。默认 `settings.yaml` 将 home 设为项目本地 `data/claude`、`data/codex`、`data/grok`；用户可在 `settings.yaml`、`.env` 或环境变量中改为既有 home。状态目录配置不得按供应商变化。

| CLI | 原生会话位置 | 本应用的供应商切换策略 |
| --- | --- | --- |
| Claude | `<configured-claude-home>/projects/` | 在子进程环境中切换 endpoint/key/model；保留配置的 state home |
| Codex | 配置的 `CODEX_HOME` 下的 `sessions` 和 SQLite 状态 | 同一 home 下按供应商选择 profile；不创建临时 `CODEX_HOME` |
| Grok | `<configured-grok-home>/sessions/<encoded-cwd>/` | 同一 `config.toml` 中的命名 `[model.<profile>]` 表加 `--model`；不替换配置的 `GROK_HOME` |

“历史会话可见”仅承诺新应用启动后创建的会话在同一 CLI、同一工作目录的原生恢复功能中可见。首版不聚合 cc-switch 过去的临时目录会话，也不实现跨 CLI 会话兼容。

## Database Rules

- 默认数据库路径为 `Path.home() / ".cc-switch" / "cc-switch.db"`，并允许显式配置覆盖。
- 使用参数化 SQL、`PRAGMA foreign_keys = ON`、合理 `busy_timeout`、短事务和失败回滚；数据库缺失、锁定、不可写或 schema 不兼容时给出可操作错误。
- 新增操作在一个事务中插入 `providers` 与至少一条 `provider_endpoints`，新记录标记为自定义而非官方。
- 删除命令先按 `(app_type, name)` 解析唯一记录，再以 `(id, app_type)` 为条件验证并删除主记录；外键级联删除对应 endpoint。不得仅按 `id` 删除。
- 清理本应用生成的 Codex profile 或 Grok `[model.<profile>]` 仅限可由本应用命名空间和完整 owner 标识确认的项；清理失败不能回滚已成功提交的供应商删除，但必须报告残留配置和可执行的清理命令。

## Acceptance

1. `uv run` 可在 Windows、macOS、Linux 上运行 Click CLI；`--help` 展示 provider 管理和三种启动子命令。
2. 数据库列表正确展示 Claude、Codex、Grok Build 的实际配置 endpoint、模型和推理强度且不泄露 API Key 或 ID；官方项清晰标识且删除命令拒绝执行。
3. 新增自定义供应商以一次事务写入 cc-switch 兼容记录及 endpoint；新增 Codex 记录在 `settings_config.config` 中持久化来自 `apps.codex` 的 `approval_policy` 与 `sandbox_mode`（默认 `never` / `danger-full-access`）；错误不会留下半完成记录。
4. 删除精确作用于指定 `(id, app_type)` 和级联 endpoint，不影响其他应用同 ID、官方项、CLI 会话或工作目录文件。
5. Claude 启动使用 Anthropic Messages 环境变量与 `--dangerously-skip-permissions`；不改变其稳定状态目录。
6. Codex managed profile 的 `approval_policy` / `default_permissions` 来自供应商实际配置，不混用旧 `sandbox_mode`/`sandbox_workspace_write`；argv 的 `--ask-for-approval` 同步供应商记录；启动时不出现 “Update Model Permissions” 选择器，不使用临时 `CODEX_HOME`。
7. Grok 启动使用受管理的 `[model.<profile>]`、`--model <profile> --sandbox workspace --always-approve`；不修改 `[models].default` 或使用临时 `GROK_HOME`。
8. 对每种 CLI，在同一工作目录用供应商 A 创建会话、再用供应商 B 启动后，原生恢复/历史入口仍能找到 A 的会话。
9. CLI 不存在、配置解析失败、数据库锁定、状态目录不匹配或子进程启动失败时，错误不泄露 API Key，也不覆盖用户未管理的主配置。
10. 应用配置为语义化 `settings.yaml`；add/import 与 launch 的策略职责分离如上。

## Evidence

- 本机版本：Claude Code `2.1.226`、Codex CLI `0.147.0`、Grok `1.0.0`。
- Codex 官方配置参考确认 profile 位于 `$CODEX_HOME/<name>.config.toml`，自定义 provider 使用 `model_providers.<id>`、`env_key`、`wire_api = "responses"`，并定义了顶层权限和网络键：<https://developers.openai.com/codex/config-reference>。
- 本机现场启动证明：即使旧 `approval_policy`、`sandbox_mode`、`sandbox_workspace_write.network_access` 均存在，Codex 0.147.0 仍会显示 “Update Model Permissions”。OpenAI Docs 说明 `default_permissions`/`[permissions]` 与旧 sandbox 设置不可混用，因此运行时 profile 改用工作区网络 permission profile。`doctor` 不接受 `--profile`，不能用于验证该 profile 的最终交互态。
- 本机 Grok `README.md` 确认 `[model.<profile>]` 表名是 picker/`--model` 名称，`model` 字段是 API 实际模型，`env_key` 可替代 `api_key`；会话保存于 `~/.grok/sessions/<encoded-cwd>/`。
- 本机 Claude `--help` 确认 `--settings`、`--model`、`--effort`、`--resume` 和 `--dangerously-skip-permissions`，并明确 `--no-session-persistence` 会禁用磁盘会话保存。

## Risks and Assumptions

- 无确认权限只应面向可信工作目录和可信供应商。Claude 没有与 Codex/Grok 等价的工作区级 OS 沙箱。
- 默认 Codex `sandbox_mode = danger-full-access` 取消工作区文件边界，只适用于可信工作目录；若需保留工作区边界，应在 `settings.yaml` 将 `apps.codex.sandbox_mode` 改为 `workspace-write` 后重新 add/import（既有记录需手动更新或重建）。
- 供应商 endpoint 可接收 API Key、提示词和代码上下文；本应用只验证 URL、协议声明和 CLI 配置语法，不能验证供应商的安全性或完整协议兼容性。
- 直接写 cc-switch 数据库会与正在运行的 cc-switch 竞争 SQLite 锁，必须重试有限次数并保留失败上下文。
- Grok 的共享 `config.toml` 与 Codex 的 profile 由其他工具同时改动时，实施需要文件锁、原子写入、语法验证和 ownership 检查，避免覆盖用户配置。
- 无法在不发起真实模型请求的情况下完全证明第三方 endpoint 的模型/协议兼容性；首版的验收以 CLI 配置解析、原生状态位置和可选的用户发起连接测试为界。

## Open Questions

暂无需要用户确认的未决事项。

## User Review Notes

- 2026-08-09：用户要求进入 Plan / 计划阶段，并要求在计划中展开讨论实现层面的不明确事项。
- 2026-08-09：用户指定使用 Dynaconf 与 `.env`，不使用 `.secrets.toml`；三种 CLI state home 均由配置提供，随附默认配置使用本地 `data/` 目录。
- 2026-08-09：用户要求列表只展示应用、名称、endpoint、模型、推理强度和类别；`show <name>` 只显示核心配置且 API Key 不脱敏，删除使用应用与名称；`launch` 默认当前工作目录并允许以 `--cwd` 覆盖，模型和推理强度以供应商配置为默认值、可用命令行覆盖。
- 2026-08-09：用户要求所有面向 CLI 的供应商引用使用名称；`launch --provider` 改为供应商名称，由应用类型限定并拒绝重名歧义。
- 2026-08-09：用户重申启动器的既定权限目标为工作目录内文件操作、命令执行和网络请求均无需逐项授权；Codex 保持 `workspace-write` 目录边界，不改为全盘访问。
- 2026-08-09：用户要求 `launch` 增加 `-v`/`--verbose`，使用基本 `logging` 输出无密钥的启动关键日志。
- 2026-08-09：用户明确要求添加 Codex 供应商即在 cc-switch 数据库中持久化免确认配置；仅在 `launch` 临时传递参数或生成 profile 不足以满足该要求。
- 2026-08-09：用户反馈重新添加后的 Codex 供应商仍重复要求选择 sandbox。确认原因是托管 profile 重建时丢失了 Codex 写回的 Windows sandbox 和项目可信状态；改为默认 `elevated` 并保留既有有效选择，网络开关同时以 CLI config 覆盖。
- 2026-08-09：用户提供现场输出，确认旧 sandbox 参数已传入但 Codex 0.147.0 仍出现 “Update Model Permissions”。改为当前 permission profile 语法，避免同一运行时 profile 混用旧 sandbox 设置。
- 2026-08-11：用户要求纠正实现——在应用配置中定义 Codex 默认 `approval_policy` / `sandbox_mode`（目标值为 `never` 与 `danger-full-access`），add/import 使用该值写入供应商记录；`launch` 以数据库中的供应商实际配置为准，不再在 managed profile / argv 中硬编码策略。
- 2026-08-11：用户要求重组配置：不再使用 TOML 扁平翻译形态；采用语义化 `settings.yaml`（`database` / `encryption_key` / `apps`），并关闭 Dynaconf environment 层。
