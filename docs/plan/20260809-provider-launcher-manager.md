# 供应商管理与 CLI 启动器计划
最后修改时间: 2026-08-09 18:00:36

流程模式: standard

当前阶段: Plan / 计划

Review status: Accepted

## Requirement Basis

依据 [Requirement](/D:/SourceCodes/mywork/cc-switch2/docs/requirement/20260809-provider-launcher-manager.md) 中已接受的范围：以 `uv` + Python 构建跨平台 Click CLI，直接读写 cc-switch SQLite 数据库，提供自定义供应商新增/删除和 Claude、Codex、Grok 启动器；官方供应商不可修改或删除；不做 API 协议转换和历史迁移。

本计划采用“数据库为供应商真相源，CLI 配置为可重建适配层”的模型。这样既能兼容 cc-switch 记录，又能让各 CLI 保持共享的稳定会话目录。

## Proposed Architecture

### Package and dependencies

创建 Python 3.11+ 的 `uv` 项目，命令入口暂定为 `ccs-plus`。依赖保持轻量：

- `click`：命令、参数、隐藏式 API Key 提示和错误退出码。
- `rich`：终端表格、状态和不泄露密钥的错误展示。
- `dynaconf`：加载本应用的 `settings.toml`、`.env` 与环境变量；数据库路径和三种 CLI 的 state home 均由配置解析。
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
  settings.py          # Dynaconf 配置加载与目录解析，不存供应商/API Key
  adapters.py          # cc-switch settings_config <-> 三种运行时配置
  managed_config.py    # Codex profile、Grok model 表的锁、备份、原子写
  launcher.py          # argv/env/cwd 构造和交互式子进程运行
tests/
  test_database.py
  test_adapters.py
  test_managed_config.py
  test_launcher.py
  test_cli.py
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
- 没有目录设置子命令。数据库路径、Claude/Codex/Grok state home 只由 Dynaconf 配置决定；供应商和 API Key 始终来自 cc-switch 数据库。

## Data and Configuration Flow

### Database read and list

1. 通过 Dynaconf 解析数据库路径和 state home。默认 `settings.toml` 保持 cc-switch 用户数据库路径，并将 state home 设为项目本地 `data/claude`、`data/codex`、`data/grok`；`settings.toml`、`.env` 和环境变量可覆盖，且不提供命令行目录设置命令。
2. 用只读连接检查 `providers`、`provider_endpoints` 的列和联合键语义；schema 不兼容时停止，不执行迁移。
3. 按 `app_type` 映射 CLI 参数：`claude -> claude`、`codex -> codex`、`grok -> grokbuild`。
4. 从 `settings_config` 提取实际模型、推理强度和请求 endpoint 供列表展示；配置不可解析时 endpoint 才回退到 `provider_endpoints`，不输出 JSON 中的认证字段或 ID。

### Add: atomic database write only

1. 以 cc-switch 实际配置格式为唯一依据校验名称、endpoint、模型和 effort；不自动补 `/v1`、不改写路径、不做 API 探测。接受 cc-switch 可保存的绝对 `http`/`https` endpoint。
2. 生成确定性的 provider ID。运行时 profile/model 名和环境变量名在 `launch` 时才由该 ID 派生，避免新增阶段产生文件系统副作用。
3. 生成 cc-switch 兼容记录：
   - Claude：`settings_config.env` 内的 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、模型槽位。
   - Codex：`settings_config.auth.OPENAI_API_KEY` 与 Responses TOML `config`；该 TOML 顶层同时持久化 `approval_policy = "never"`、`sandbox_mode = "workspace-write"` 和 `sandbox_workspace_write.network_access = true`，使添加完成后的记录本身即具备最小免确认策略。
   - Grok：`settings_config.config` 内的原生 Responses TOML。
4. 以一次 SQLite 写事务插入 `providers` 与至少一个 `provider_endpoints`；开启 foreign keys、短 `BEGIN IMMEDIATE` 事务、`busy_timeout` 和参数绑定。新增记录设为自定义、`is_current = 0`，不改变 cc-switch 当前选择。
5. 不在新增时创建 Codex profile、修改 Grok `config.toml` 或创建目录。数据库提交失败时没有需要补偿的 CLI 配置副作用。

### Launch: idempotent reconciliation and child-only secrets

1. 按 `(app_type, name)` 查询唯一记录；官方项仅使用原生 CLI 的现有登录态，不生成或改写官方 supplier 记录；同一应用的重名记录报错而不猜测目标。
2. 支持 cc-switch 中已有的自定义供应商：以该记录的实际 `settings_config`（Claude env、Codex auth/config、Grok config）作为路由、认证和模型的唯一来源。新增记录也生成同一格式。配置解析失败时中止启动并报告格式错误，绝不猜测 endpoint、重写协议或启动代理。
3. 在启动前幂等地生成或更新本应用拥有的 Codex profile、Grok model 表。它们不含 API Key，且由数据库实际配置编译而来；cc-switch 数据库保留旧 sandbox TOML 以兼容其格式，而 Codex 0.147+ profile 使用 `default_permissions` 和命名 profile（继承 `:workspace`、写入、网络开启、`"*"` 公网 allow），不混用旧键。profile 默认 `[windows] sandbox = "elevated"`，并保留 Codex 写回的 Windows mode 与项目可信表；启动参数只保留 `--ask-for-approval never`。
4. 用 Dynaconf 给出的 state home 覆盖临时环境。清除会使历史分叉的冲突变量，尤其是临时 `CODEX_HOME`/`CODEX_SQLITE_HOME`、`CLAUDE_CONFIG_DIR`、`GROK_HOME`。
5. 只把该供应商的 API Key 注入子进程环境；自定义 provider 同时清理可能覆盖其 endpoint/认证的同类环境变量。API Key 不进入 argv、profile、日志或本应用设置。
6. 在 `--cwd` 指定的目录或调用命令的当前工作目录运行原生 CLI，等待其退出并透传退出码；模型与推理强度优先使用供应商配置，命令行覆盖仅作用于当前子进程。

### CLI-specific launch assembly

| CLI | 配置和环境 | argv 关键项 | 会话保持 |
| --- | --- | --- | --- |
| Claude | 子进程 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、模型 env | `claude --model ... [--effort ...] --dangerously-skip-permissions` | 保持稳定 `.claude`；不传 `--no-session-persistence` |
| Codex | 稳定 home 内 profile，profile 使用 `env_key`、工作区网络 permission profile，子进程设置唯一 Key 变量 | `codex --profile ... --model ... --ask-for-approval never` | 保持同一 `CODEX_HOME` 和默认 SQLite state |
| Grok | 稳定 `config.toml` 中的 `[model.<profile>]`，子进程设置唯一 Key 变量 | `grok --model <profile> [--reasoning-effort ...] --sandbox workspace --always-approve` | 保持同一 `.grok/sessions/<encoded-cwd>`，不修改 `[models].default` |

### Delete

1. 按 `(app_type, name)` 解析唯一目标记录，拒绝 `category = "official"`、已知官方 ID、找不到的记录及同一应用内重名。
2. 在 SQLite 事务中仅删除该联合键的 `providers` 行，让外键级联清理 endpoint；不修改 `is_current` 所属的其他记录。
3. 数据库提交后不操作任何文件或目录：不清理 Codex profile、不修改 Grok `config.toml`、不清理缓存、认证或会话。
4. 已遗留的本应用管理 profile/model 表不含 API Key；后续不能由本应用选中相应已删除 supplier。删除命令成功与否完全由数据库事务决定。

## Configuration Ownership and Concurrency

- Codex profile 是独立文件，文件名和首行注释共同标识 owner。只有二者均匹配才允许启动时覆盖或重建；重建时保留 Codex 写回的 `[windows]` sandbox 选择和 `[projects]` 可信状态，避免再次出现本机 sandbox/工作目录设置；`providers delete` 不删除该文件。
- Grok 使用共享 `config.toml`，必须通过 `portalocker` 锁和 `tomlkit` 保留其他表、注释、顺序；变更在同目录临时文件中完成并原子替换。
- Dynaconf 配置文件由用户管理，只读加载，不提供本应用写入或目录设置命令；内容限数据库路径、state home 和非密钥运行参数。
- SQLite 不改变 `journal_mode`；每次连接显式 `PRAGMA foreign_keys = ON`、`busy_timeout`，写入保持最短。
- 供应商新增/删除只涉及 SQLite，因此各自保持单一事务原子性。文件系统配置只在启动时幂等编译；启动前配置写失败不会改变数据库，下一次启动可重试。

## Implementation Steps

1. 初始化 `uv` Python 项目、`pyproject.toml`、包入口、Dynaconf `settings.toml`、`.env.example`、`.gitignore` 和开发测试依赖；默认 state home 指向本地 `data/`，固定 Python 下限与 `ccs-plus` script。
2. 实现 domain 类型、错误模型、CLI app type 映射、官方项判断、API Key redaction 和 endpoint/effort 校验。
3. 实现 SQLite repository：schema preflight、列表/单项查询、全事务新增、官方保护删除和针对临时数据库的测试夹具。
4. 实现 cc-switch settings adapter：新增记录生成、已知历史记录解析、Claude/Codex/Grok 的模型和认证提取、无协议转换的失败路径。
5. 实现 Dynaconf settings loader、基于配置的 state home 解析、Codex profile 生成/owner 校验、Grok TOML 增改、文件锁、备份与原子写；不实现目录设置命令。
6. 实现 launcher：CLI 探测、argv/env 构造、cwd 校验、环境清理、交互式子进程、退出码和失败消息。
7. 连接 Click 命令，实现隐藏 API Key 输入、Rich 表格/JSON 输出和 `--yes` 删除保护；不实现 config state-home 命令。
8. 补齐单元与子进程桩测试，运行 lint/test；对本机三个原生 CLI 做不含 API Key 的诊断测试。

## Verification Plan

| 层级 | 验证 |
| --- | --- |
| 数据库 | 临时 SQLite 按参考 schema 验证新增一次事务、endpoint 级联、联合键精确删除、official 拒绝、锁超时、schema 错误和删除不触发文件操作 |
| adapter | 固定 JSON/TOML fixture 验证三种新增格式、所有已知历史 cc-switch provider 的实际配置解析、模型/effort 覆盖、密钥不进入 profile/日志 |
| 配置文件 | Codex profile 的 `default_permissions`/命名 profile 与旧 sandbox 键互斥；Grok 只变更带 owner 的 model 表，保留用户表/注释；文件写失败时恢复 |
| launcher | 以测试替身捕获 `argv`、`cwd`、`env`，验证无 shell、无 API Key argv、state home 稳定、免确认参数正确且不传冲突的旧 sandbox flag、子进程退出码透传 |
| Click CLI | `--help`、列表过滤/JSON、核心配置 show、隐藏输入、可选 cwd、模型/effort 覆盖、`--yes`、错误退出码；确认不存在目录设置命令 |
| 本机诊断 | `codex doctor` 不支持 `--profile`，不能验证 permission profile 最终交互态；以 `--strict-config` 验证 generated profile 语法，并由人工启动确认不出现 “Update Model Permissions”；三种 CLI 的 `--help` 验证生成参数仍被当前安装版本识别 |
| 人工实网验收 | 每个 CLI 在同一 cwd 用供应商 A 创建会话，切换 B 后用原生 resume/历史入口确认 A 可见；该步骤只由用户使用真实供应商完成 |

## Files to Change

- 新建 `pyproject.toml`、`settings.toml`、`.env.example`、`.gitignore`、`src/ccs_plus/` 和 `tests/`。
- 更新 [Requirement](/D:/SourceCodes/mywork/cc-switch2/docs/requirement/20260809-provider-launcher-manager.md) 的接受状态与 review note。
- 新建本计划文档；实现后新建对应 Verification 文档。
- 不修改 `cc-switch/` 引用源码、其数据库数据、cc-switch 临时目录或任何 CLI 会话目录；仅在启动时以原子方式生成本应用管理的 Codex profile 或 Grok model 表。

## Resolved Decisions

1. 使用 `dynaconf`，支持 `settings.toml`、`.env` 和环境变量，不使用 `.secrets.toml`。数据库路径及所有 state home 由配置指定；默认 state home 位于本地 `data/`，不提供目录设置子命令。
2. 支持 cc-switch 中已有的自定义供应商启动。运行时配置以数据库保存的实际 `settings_config` 为依据，新增供应商使用相同格式；不实现代理或协议转换。
3. endpoint 不施加独立的 `/v1` 补全、HTTPS 强制或其他通用规范化规则，按 cc-switch 的实际 per-app 配置和原始值使用。
4. `providers delete` 只删除数据库记录及其外键 endpoint，不操作任何文件和目录。
5. 命令名称确定为 `ccs-plus`。

## Assumptions and Risks

- 用户在人工实网验收时拥有可用、可信的第三方 endpoint；本应用不探测 API Key 有效性，避免创建额外网络流量。
- Claude 的 `--dangerously-skip-permissions` 没有工作区级强隔离。用户要求的是免确认能力，不能将它描述为安全沙箱。
- Codex 的 `workspace-write` 会继续保护工作目录内的 `.git`、`.codex` 等元数据；这与“目录内普通源文件可修改”的权限目标兼容，但不等同于全盘或所有隐藏元数据可写。
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

2026-08-09：用户重申工作目录内文件修改、命令执行和网络请求不应逐项授权。Codex 维持 `workspace-write`、`approval_policy = "never"` 和 `network_access = true`，不以 `danger-full-access` 破坏目录边界。

2026-08-09：用户要求 `launch` 提供 `-v`/`--verbose`，使用基本 logging 输出无密钥的启动关键日志。

2026-08-09：用户明确要求新增 Codex 供应商的 cc-switch `settings_config.config` 直接携带 `approval_policy = "never"`、`sandbox_mode = "workspace-write"` 与 `sandbox_workspace_write.network_access = true`；profile 和启动参数只承担运行时适配与既有记录兼容。

2026-08-09：用户反馈 Codex 重新启动后仍要求设置 sandbox。计划补充 Windows 原生 sandbox 持久化：托管 profile 默认写入 `elevated`，并保留 Codex 已写回的 `unelevated` 选择和项目可信状态。`--yolo` 继续不使用，因为它不再保留工作目录边界。

2026-08-09：用户提供现场输出，确认 Codex 0.147.0 即使接受旧 sandbox 参数仍显示 “Update Model Permissions”。按官方 permission profiles 文档，运行时 profile 迁移到 `default_permissions` + 工作区网络 profile，且不再传递或生成冲突的旧 sandbox 设置；数据库中的 cc-switch 兼容 TOML 保留不变。

暂无需要用户确认的未决事项。
