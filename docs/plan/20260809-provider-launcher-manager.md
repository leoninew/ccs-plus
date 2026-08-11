# 供应商管理与 CLI 启动器计划
最后修改时间: 2026-08-11 09:36:07

流程模式: standard

当前阶段: Plan / 计划

Review status: Accepted

## Requirement Basis

依据 [Requirement](../requirement/20260809-provider-launcher-manager.md) 中已接受的范围：以 `uv` + Python 构建跨平台 Click CLI，直接读写 cc-switch SQLite 数据库，提供自定义供应商新增/删除和 Claude、Codex、Grok 启动器；官方供应商不可修改或删除；不做 API 协议转换和历史迁移。

本计划采用“数据库为供应商真相源，CLI 配置为可重建适配层”的模型。这样既能兼容 cc-switch 记录，又能让各 CLI 保持共享的稳定会话目录。

2026-08-11 起补充：应用配置改为语义化 `settings.yaml`；Codex 默认策略来自 `apps.codex`；`launch` 只消费供应商实际配置。

## Proposed Architecture

### Package and dependencies

创建 Python 3.11+ 的 `uv` 项目，命令入口暂定为 `ccs-plus`。依赖保持轻量：

- `click`：命令、参数、隐藏式 API Key 提示和错误退出码。
- `rich`：终端表格、状态和不泄露密钥的错误展示。
- `dynaconf` + `pyyaml`：加载语义化 `settings.yaml`、`.env` 与环境变量（无 Dynaconf environment 层）；解析 `database.path`、`encryption_key` 与 `apps.*`。
- `tomlkit`：读取、保留注释并修改 Grok 的共享 `config.toml`，以及生成 Codex profile。
- `portalocker`：跨平台文件锁，序列化对 Grok 配置和本应用配置的写入。
- 标准库 `sqlite3`、`json`、`subprocess`、`pathlib`：数据库、配置与启动。
- `pytest`：测试；生产依赖不引入 ORM、Web 框架或外部密钥服务。

### Module boundaries

```text
pyproject.toml
src/ccs_plus/
  __main__.py          # python -m 入口
  cli.py               # Click 命令组、参数和退出码
  domain.py            # Provider、AppKind、错误和纯数据转换
  database.py          # SQLite schema 检查、查询、事务新增/删除
  settings.py          # settings.yaml 加载与路径/应用默认策略解析，不存供应商/API Key
  adapters.py          # cc-switch settings_config <-> 三种运行时配置；add 写入 apps.codex 默认策略
  managed_config.py    # Codex profile、Grok model 表的锁、备份、原子写；策略来自 RuntimeProvider
  launcher.py          # argv/env/cwd 构造和交互式子进程运行
tests/
  test_database.py
  test_adapters.py
  test_managed_config.py
  test_launcher.py
  test_cli.py
  test_settings.py
```

`cc-switch/` 不被修改，也不成为 Python 包依赖。其源码只用于固定数据库字段和现有 settings 格式。

## Command Design

```text
ccs-plus providers list [--app claude|codex|grok] [--json]
ccs-plus providers add <claude|codex|grok> --name <name> --endpoint <url> --model <id>
                                   [--api-key <key>] [--effort <level>] [--notes <text>]
ccs-plus providers show <name>
ccs-plus providers delete <claude|codex|grok> <name> --yes
ccs-plus launch <claude|codex|grok> --provider <name> [--cwd <path>]
                   [--model <id>] [--effort <level>] [-v]
```

- 未传 `--api-key` 时，`providers add` 使用隐藏输入提示；显式传参仅为非交互自动化保留，正常输出和异常均不得回显其值。
- `providers list` 默认只读，显示实际配置中的 endpoint、模型、推理强度；`--json` 使用稳定字段、对 API Key 和 ID 不做序列化。
- `providers show` 以名称查询，输出 API endpoint、API Key、模型和推理强度；同名可返回多个应用记录，API Key 按用户明确要求不脱敏。
- `providers delete` 强制 `--yes`，先以 `(app_type, name)` 解析唯一项，再检查官方标记并以 `(id, app_type)` 删除。
- `launch` 与 CLI 子进程共享当前终端的标准流，用 `shell=False` 的参数数组执行，绝不将 endpoint、模型或工作目录拼接为 shell 字符串。
- `launch` 未传 `--cwd` 时使用当前工作目录；模型与推理强度默认取自供应商配置，`--model`、`--effort` 仅覆盖该次启动。
- `launch -v` 通过标准库 `logging.basicConfig` 输出 stderr 日志，记录 CLI、供应商名称、cwd、argv 和退出码；环境变量、API Key 与 endpoint 不记入日志。
- 没有目录设置子命令。数据库路径、Claude/Codex/Grok state home 与 Codex 默认策略只由 `settings.yaml` 决定；供应商和 API Key 始终来自 cc-switch 数据库。

## Data and Configuration Flow

### Application settings (`settings.yaml`)

```yaml
database:
  path: "~/.cc-switch/cc-switch.db"
encryption_key: ""   # prefer CCS_PLUS_ENCRYPTION_KEY
apps:
  claude:
    home: data/claude
  codex:
    home: data/codex
    approval_policy: never
    sandbox_mode: danger-full-access
  grok:
    home: data/grok
```

- `environments=False`：YAML 根级即 schema，不再使用 `default:` 包装。
- 环境覆盖示例：`CCS_PLUS_DATABASE__PATH`、`CCS_PLUS_APPS__CODEX__HOME`、`CCS_PLUS_APPS__CODEX__SANDBOX_MODE`、`CCS_PLUS_ENCRYPTION_KEY`。
- `AppSettings` 暴露 `claude`/`codex`/`grok` 子结构；`codex.provider_defaults()` 供 add/import 使用。

### Database read and list

1. 通过 `load_settings()` 解析数据库路径与 state home。默认 home 为项目本地 `data/{claude,codex,grok}`；`settings.yaml`、`.env` 和环境变量可覆盖，且不提供命令行目录设置命令。
2. 用只读连接检查 `providers`、`provider_endpoints` 的列和联合键语义；schema 不兼容时停止，不执行迁移。
3. 按 `app_type` 映射 CLI 参数：`claude -> claude`、`codex -> codex`、`grok -> grokbuild`。
4. 从 `settings_config` 提取实际模型、推理强度和请求 endpoint 供列表展示；配置不可解析时 endpoint 才回退到 `provider_endpoints`，不输出 JSON 中的认证字段或 ID。

### Add / import: atomic database write only

1. 以 cc-switch 实际配置格式为唯一依据校验名称、endpoint、模型和 effort；不自动补 `/v1`、不改写路径、不做 API 探测。接受 cc-switch 可保存的绝对 `http`/`https` endpoint。
2. 生成确定性的 provider ID。运行时 profile/model 名和环境变量名在 `launch` 时才由该 ID 派生，避免新增阶段产生文件系统副作用。
3. 生成 cc-switch 兼容记录：
   - Claude：`settings_config.env` 内的 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、模型槽位。
   - Codex：`settings_config.auth.OPENAI_API_KEY` 与 Responses TOML `config`；顶层 `approval_policy` / `sandbox_mode` 取自 `apps.codex`（默认 `never` / `danger-full-access`）。仅当 `sandbox_mode == workspace-write` 时写入 `sandbox_workspace_write.network_access = true`。
   - Grok：`settings_config.config` 内的原生 Responses TOML。
4. `providers import` 解密备份得到 `NewProvider` 后，同样调用 `build_provider(..., codex.provider_defaults())` 重建记录，不回放备份中的旧 sandbox TOML。
5. 以一次 SQLite 写事务插入 `providers` 与至少一个 `provider_endpoints`；开启 foreign keys、短 `BEGIN IMMEDIATE` 事务、`busy_timeout` 和参数绑定。新增记录设为自定义、`is_current = 0`，不改变 cc-switch 当前选择。
6. 不在新增时创建 Codex profile、修改 Grok `config.toml` 或创建目录。数据库提交失败时没有需要补偿的 CLI 配置副作用。

### Launch: idempotent reconciliation and child-only secrets

1. 按 `(app_type, name)` 查询唯一记录；官方项仅使用原生 CLI 的现有登录态，不生成或改写官方 supplier 记录；同一应用的重名记录报错而不猜测目标。
2. 支持 cc-switch 中已有的自定义供应商：以该记录的实际 `settings_config`（Claude env、Codex auth/config、Grok config）作为路由、认证、模型与权限策略的唯一来源。配置解析失败时中止启动并报告格式错误，绝不猜测 endpoint、重写协议或启动代理。
3. 在启动前幂等地生成或更新本应用拥有的 Codex profile、Grok model 表。它们不含 API Key，且由数据库实际配置编译而来：
   - Codex managed profile：`approval_policy` 与 `default_permissions = ":<sandbox_mode>"` 取自供应商记录；不写旧 sandbox 键、不写自定义 permissions 表、不写默认 `[windows] sandbox`；可保留 `[projects]` 可信状态。
   - argv：`--ask-for-approval <approval_policy>` 同步供应商记录（官方无配置时 `never`）。
4. 用配置中的 state home 覆盖临时环境。清除会使历史分叉的冲突变量，尤其是临时 `CODEX_HOME`/`CODEX_SQLITE_HOME`、`CLAUDE_CONFIG_DIR`、`GROK_HOME`。
5. 只把该供应商的 API Key 注入子进程环境；自定义 provider 同时清理可能覆盖其 endpoint/认证的同类环境变量。API Key 不进入 argv、profile、日志或本应用设置。
6. 在 `--cwd` 指定的目录或调用命令的当前工作目录运行原生 CLI，等待其退出并透传退出码；模型与推理强度优先使用供应商配置，命令行覆盖仅作用于当前子进程。

### CLI-specific launch assembly

| CLI | 配置和环境 | argv 关键项 | 会话保持 |
| --- | --- | --- | --- |
| Claude | 子进程 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、模型 env | `claude --model ... [--effort ...] --dangerously-skip-permissions` | 保持稳定 Claude home；不传 `--no-session-persistence` |
| Codex | 稳定 home 内 profile，`env_key` + 供应商策略映射的 permission profile，子进程设置唯一 Key 变量 | `codex --profile ... --model ... --ask-for-approval <provider.approval_policy>` | 保持同一 `CODEX_HOME` 和默认 SQLite state |
| Grok | 稳定 `config.toml` 中的 `[model.<profile>]`，子进程设置唯一 Key 变量 | `grok --model <profile> [--reasoning-effort ...] --sandbox workspace --always-approve` | 保持同一 `.grok/sessions/<encoded-cwd>`，不修改 `[models].default` |

### Delete

1. 按 `(app_type, name)` 解析唯一目标记录，拒绝 `category = "official"`、已知官方 ID、找不到的记录及同一应用内重名。
2. 在 SQLite 事务中仅删除该联合键的 `providers` 行，让外键级联清理 endpoint；不修改 `is_current` 所属的其他记录。
3. 数据库提交后不操作任何文件或目录：不清理 Codex profile、不修改 Grok `config.toml`、不清理缓存、认证或会话。
4. 已遗留的本应用管理 profile/model 表不含 API Key；后续不能由本应用选中相应已删除 supplier。删除命令成功与否完全由数据库事务决定。

## Configuration Ownership and Concurrency

- Codex profile 是独立文件，文件名和首行注释共同标识 owner。只有二者均匹配才允许启动时覆盖或重建；重建时按供应商策略写入 permission profile，并保留 `[projects]` 可信状态；不再默认写入 `[windows] sandbox`；`providers delete` 不删除该文件。
- Grok 使用共享 `config.toml`，必须通过 `portalocker` 锁和 `tomlkit` 保留其他表、注释、顺序；变更在同目录临时文件中完成并原子替换。
- `settings.yaml` 由用户管理，只读加载，不提供本应用写入或目录设置命令；内容为数据库路径、encryption key、state home 与应用默认策略。
- SQLite 不改变 `journal_mode`；每次连接显式 `PRAGMA foreign_keys = ON`、`busy_timeout`，写入保持最短。
- 供应商新增/删除只涉及 SQLite，因此各自保持单一事务原子性。文件系统配置只在启动时幂等编译；启动前配置写失败不会改变数据库，下一次启动可重试。

## Implementation Steps

1. 初始化 `uv` Python 项目、`pyproject.toml`、包入口、语义化 `settings.yaml`、`.env.example`、`.gitignore` 和开发测试依赖；默认 state home 指向本地 `data/`，固定 Python 下限与 `ccs-plus` script。
2. 实现 domain 类型、错误模型、CLI app type 映射、官方项判断、API Key redaction 和 endpoint/effort 校验。
3. 实现 SQLite repository：schema preflight、列表/单项查询、全事务新增、官方保护删除和针对临时数据库的测试夹具。
4. 实现 cc-switch settings adapter：新增记录生成（Codex 策略来自 `CodexAppConfig`）、已知历史记录解析（含 `approval_policy`/`sandbox_mode` 提取到 `RuntimeProvider`）、Claude/Codex/Grok 的模型和认证提取、无协议转换的失败路径。
5. 实现 settings loader、基于配置的 state home 与 Codex 默认策略解析、Codex profile 生成/owner 校验（策略来自 RuntimeProvider）、Grok TOML 增改、文件锁、备份与原子写；不实现目录设置命令。
6. 实现 launcher：CLI 探测、argv/env 构造（Codex `--ask-for-approval` 来自供应商记录）、cwd 校验、环境清理、交互式子进程、退出码和失败消息。
7. 连接 Click 命令，实现隐藏 API Key 输入、Rich 表格/JSON 输出和 `--yes` 删除保护；add/import 传入 `settings.codex.provider_defaults()`。
8. 补齐单元与子进程桩测试，运行 lint/test；对本机三个原生 CLI 做不含 API Key 的诊断测试。

## Verification Plan

| 层级 | 验证 |
| --- | --- |
| 数据库 | 临时 SQLite 按参考 schema 验证新增一次事务、endpoint 级联、联合键精确删除、official 拒绝、锁超时、schema 错误和删除不触发文件操作 |
| adapter | 固定 fixture 验证三种新增格式、`apps.codex` 策略写入、历史记录解析（含策略字段）、模型/effort 覆盖、密钥不进入 profile/日志 |
| settings | 语义化 YAML 加载、嵌套环境覆盖、缺失 `apps.codex` 策略拒绝、Fernet key 校验、`.secrets.*` 不加载 |
| 配置文件 | Codex profile 的 `default_permissions` 来自供应商 `sandbox_mode` 且与旧 sandbox 键互斥；Grok 只变更带 owner 的 model 表，保留用户表/注释；文件写失败时恢复 |
| launcher | 捕获 `argv`/`cwd`/`env`：无 shell、无 API Key argv、state home 稳定、`--ask-for-approval` 跟随供应商、不传冲突旧 sandbox flag、退出码透传 |
| Click CLI | `--help`、列表过滤/JSON、核心配置 show、隐藏输入、可选 cwd、模型/effort 覆盖、`--yes`、错误退出码；确认不存在目录设置命令 |
| 本机诊断 | 人工启动确认不出现 “Update Model Permissions”；三种 CLI 的 `--help` 验证生成参数仍被当前安装版本识别 |
| 人工实网验收 | 每个 CLI 在同一 cwd 用供应商 A 创建会话，切换 B 后用原生 resume/历史入口确认 A 可见；该步骤只由用户使用真实供应商完成 |

## Files to Change

- 新建/维护 `pyproject.toml`、`settings.yaml`、`.env.example`、`.gitignore`、`src/ccs_plus/` 和 `tests/`。
- 更新 [Requirement](../requirement/20260809-provider-launcher-manager.md) 的策略与配置章节。
- 维护本计划文档与对应 Verification 文档。
- 不修改 `cc-switch/` 引用源码、其数据库数据、cc-switch 临时目录或任何 CLI 会话目录；仅在启动时以原子方式生成本应用管理的 Codex profile 或 Grok model 表。

## Resolved Decisions

1. 使用 `dynaconf` 加载语义化 `settings.yaml`（`environments=False`）、`.env` 和环境变量，不使用 `.secrets.toml`/`.secrets.yaml`。数据库路径、state home 与 Codex 默认策略由配置指定；默认 state home 位于本地 `data/`，不提供目录设置子命令。
2. 支持 cc-switch 中已有的自定义供应商启动。运行时配置以数据库保存的实际 `settings_config` 为依据；新增/导入使用 `apps.codex` 默认策略写入相同字段形态；不实现代理或协议转换。
3. endpoint 不施加独立的 `/v1` 补全、HTTPS 强制或其他通用规范化规则，按 cc-switch 的实际 per-app 配置和原始值使用。
4. `providers delete` 只删除数据库记录及其外键 endpoint，不操作任何文件和目录。
5. 命令名称确定为 `ccs-plus`。
6. Codex 默认 `sandbox_mode` 为 `danger-full-access`（可在 `settings.yaml` 覆盖）；launch 不回读 `apps.codex` 默认值，只读供应商记录。

## Assumptions and Risks

- 用户在人工实网验收时拥有可用、可信的第三方 endpoint；本应用不探测 API Key 有效性，避免创建额外网络流量。
- Claude 的 `--dangerously-skip-permissions` 没有工作区级强隔离。用户要求的是免确认能力，不能将它描述为安全沙箱。
- 默认 `danger-full-access` 取消工作区文件边界；仅适用于可信目录。需要边界时改配置后重建供应商。
- 已存在的旧供应商记录可能仍为 `workspace-write`；launch 会按其实际配置启动，不会自动升级。
- Grok/Codex 的配置格式随 CLI 升级可能变化。启动前的语法检查和清晰错误优先于静默兼容猜测。
- 供应商数据库内的 API Key 继续沿用 cc-switch 的兼容存储，属于系统既有风险；本应用不能把密钥复制到配置、日志、profile 或本应用设置。
- 删除供应商后，Codex profile 和 Grok model 表会保留为无密钥孤立配置。这是明确的范围约束；它们不会被启动器选中，手工管理仍由用户负责。
- 外部进程可同时修改 Grok `config.toml` 或 cc-switch 数据库。文件锁只能约束合作进程，实施时必须保留备份、原子写和可诊断错误。

## Rollback

- 删除本应用代码/虚拟环境不影响 cc-switch 数据库以外的现有数据；但已新增供应商需要通过 `providers delete` 或 SQLite 备份恢复。
- 供应商删除不触碰 Codex profile、Grok model 表、认证或会话；因此删除数据库记录不需要文件系统回滚。
- 每次写共享 Grok 配置前保存同目录备份，遇到解析或替换失败立即恢复；不触碰 Claude/Codex/Grok 的会话和认证文件。

## User Review Notes

2026-08-09：用户确认使用 Dynaconf/.env、不使用 `.secrets.toml`、配置式目录、兼容历史 cc-switch 实际配置、删除不操作文件或目录，并确定命令名为 `ccs-plus`。默认配置的三种 state home 使用本地 `data/`，该目录和 `.env` 将被 Git 忽略。

2026-08-09：用户要求 `launch` 省略 `--cwd` 时使用当前工作目录，传入时才覆盖；模型和推理强度从供应商配置读取，仍可使用 `--model`、`--effort` 作单次覆盖。

2026-08-09：用户要求所有用户可见的供应商参数使用名称；`launch --provider` 使用应用限定的供应商名称，内部才使用 ID。

2026-08-09：用户曾要求 Codex 维持 `workspace-write` 目录边界；该决策已被 2026-08-11 的 full-access 与配置驱动策略取代。

2026-08-09：用户要求 `launch` 提供 `-v`/`--verbose`，使用基本 logging 输出无密钥的启动关键日志。

2026-08-09：用户要求新增 Codex 供应商即在数据库持久化免确认配置；后续改为配置驱动的默认策略字段，而非写死 `workspace-write`。

2026-08-09：现场确认 Codex 0.147.0 在旧 sandbox 键下仍显示 “Update Model Permissions”；运行时改用 `default_permissions`，不与旧键混用。

2026-08-11：用户要求配置中定义 Codex `approval_policy`/`sandbox_mode`（默认 `never`/`danger-full-access`），add/import 使用该值，launch 以供应商实际配置为准。

2026-08-11：用户要求重组配置为语义化 YAML，不再使用 TOML 扁平翻译结构。

暂无需要用户确认的未决事项。
