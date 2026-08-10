# cc-switch provider CLI launcher

## 当前实现概览

本仓库当前实现的是一个基于 cc-switch SQLite 数据库的 provider CLI launcher，用于按 provider 编号启动 Claude/Codex，并尽量避免写入目标 CLI 的全局配置。

当前入口模块：

```text
src/cc_switch/cli.py
```

核心逻辑在 `src/cc_switch/cli.py`。本地安装后，Python packaging 的 console script 会提供 `ccs` 命令并调用当前仓库的 editable 源码。

## 数据源

默认数据库：

```text
~/.cc-switch/cc-switch.db
```

实现直接使用 Python `sqlite3` 只读访问数据库，不再通过 `pomelo-db` 查询。

provider 查询按以下顺序展示和编号：

```sql
ORDER BY app_type, sort_index IS NULL, sort_index, name
```

同一 app_type 内，缺失 `sort_index` 的 provider 排在最后。运行时通过列表中的 1-based 编号选择 provider，而不是通过 provider id 直接选择。

## 环境配置

Launcher 配置由 **dynaconf** 加载：多 YAML 先做 list-replace 合并为默认值，再由**一个** Dynaconf 实例透明应用 dotenv + 进程 `CCS_*`（嵌套 `CCS_GROUP__KEY`，无需手写 env 解析/合并）。有效优先级（后者覆盖前者）：

1. 项目根 `cc-switch.yaml`
2. 可选 `cc-switch.local.yaml` 或 `CCS_LOCAL_CONFIG`
3. 可选 `~/.cc-switch/cc-switch.yaml`
4. 一个 dotenv 文件（dynaconf `load_dotenv`，`DOTENV_OVERRIDE=False` → 进程环境优先）
5. 进程环境变量 `CCS_*`

默认已内置 claude:c / mini-claude:m / codex:x / grok:g、`CODEX_HOME`，以及 hybrid 用的 user home / sessions；无需 `.env` 也可 `ccs alias`。

dotenv 路径选择（产品策略，只取一个；内容交给 dynaconf）：

1. `CCS_ENV_FILE` 指向的显式文件；
2. 源码 checkout 根目录的 `.env`（同目录需有 `pyproject.toml`，避免 site-packages 误匹配）；
3. 用户配置文件 `~/.cc-switch/.env`。

启动器**不会**按当前工作目录搜索 `.env`（`load_dotenv` 仅在选中路径时开启，避免 dynaconf `find_file` 误匹配）。完整键表见仓库根 [`.env.sample`](../.env.sample)。

```text
# CCS_ENV_FILE=C:/Users/you/.cc-switch/.env
# CCS_CLAUDE__CLIS=claude:c,mini-claude:m
# CCS_CODEX__HOME_ENV=CODEX_HOME
# 本地 bypass / 运行策略（项目 YAML 默认为空）：
# CCS_CLAUDE__ARGS=--dangerously-skip-permissions
# CCS_CODEX__ARGS=-a never --sandbox danger-full-access
```

`CCS_*__CLIS` 为 `cli-full-name[:cli-alias]`，逗号分隔。`CCS_*__ARGS` 为传给目标 CLI 的默认参数（shell-like quoting）。审批/sandbox 类参数属于用户明确选择的运行策略，sample 中默认注释掉。

`ccs run` 直接启动子进程，不经过 interactive shell，因此不会继承 shell alias；需要把默认参数写入 `CCS_CLAUDE__ARGS` / `CCS_CODEX__ARGS` / `CCS_GROK__ARGS`（或 YAML 对应 `args`）。

`list` 读取 CC Switch 主页面已选中的应用，再从数据库展示这些应用的全部 provider 配置。它只读取 `settings.json`，不会写入、补全或添加 `visibleApps`。`is_current` 仅表示某一 app_type 的当前 provider，隐藏的 app 也会保留该标记，不能作为列表筛选条件。`list <category>` 只接受当前已选中的类别；CLI 名称或 alias 会解析为对应的 provider 类别。`run <cli>` 的参数是 CLI 名称，可使用真实 CLI 或配置中的 alias。

## 安装

安装开发依赖：

```bash
make install
```

本地安装 `ccs` 命令：

```bash
pip install -e .
```

`pip install -e .` 通过 editable install 使用当前仓库源码。安装后 `ccs` 命令由 Python packaging 的 console script 提供。

## 命令

### 列出 provider

输出按两级树展示：第一层是 provider 类别，第二层是供应商；供应商前的编号仍用于 `run`。

```bash
ccs list
ccs list claude
ccs list codex
```

### 查看 CLI alias

```bash
ccs alias
```

### 查看 Provider 配置

`show` 使用和 `run` 一致的 CLI / provider selector 解析，但只读取数据库并输出原始 JSON 配置，不启动 CLI、创建临时 Home 或检查 proxy。输出包含 provider 标识、`settings_config` 与 `meta`，其中的密钥不会脱敏。

```bash
ccs show claude 1
ccs show claude "Provider Name"
ccs show g3
```

### 备份/还原供应商表

```bash
ccs backup
ccs restore backup-20260719-103013.zip
```

`backup` / `restore` 使用选定配置文件中的 `CC_SWITCH_BACKUP_DIR`。

- `backup`：从默认数据库 `~/.cc-switch/cc-switch.db` 导出供应商相关表到备份目录，文件名为 `backup-<YYYYMMDD-HHMMSS>.zip`（zip 内含 `providers.json`）。
- `restore <archive>`：在 `CC_SWITCH_BACKUP_DIR` 下按文件名查找 zip，并覆盖目标库中对应表数据；其他表（日志、MCP、skills 等）不动。`<archive>` 只需文件名（例如 `backup-20260719-103013.zip`），即使传入路径也只取 basename。

覆盖表：`providers`、`provider_endpoints`、`provider_health`、`proxy_config`。

备份 zip 含明文密钥，勿提交到版本库。不兼容旧的整库 `cc-switch.db` / `providers.md` / 固定 `providers.zip` 备份格式。

### 启动 CLI

```bash
ccs run <app> <provider_number> [--mode {direct,proxy}] [--cwd <path>]
ccs run <alias><provider_number> [--mode {direct,proxy}] [--cwd <path>] [cli_args...]
```

示例：

```bash
# 真实 CLI 名称
ccs run claude 1
ccs run codex 1

# alias + provider 编号组合简写
ccs run c2
ccs run x1
ccs run m1
ccs run g3

# 组合 alias 已含 provider 编号，后续位置参数直接透传给目标 CLI
ccs run x2 resume xxx

# 单次覆盖数据库中的 proxy_config.proxy_enabled
ccs run claude 1 --mode direct
ccs run claude 1 --mode proxy
```

## 当前支持的启动方式

启动器默认会读取 `proxy_config.proxy_enabled` 自动选择启动方式，也可通过 `run --mode {direct,proxy}` 对本次运行进行覆盖：

- 未传 `--mode` 且 `proxy_enabled = 0`：使用指定 provider 的 direct 配置启动。
- 未传 `--mode` 且 `proxy_enabled = 1`：生成指向 cc-switch 本地 proxy 的临时配置启动；实际 provider 由 cc-switch 当前状态或 failover queue 决定。
- `--mode direct`：本次运行强制 direct，不修改 cc-switch.db。
- `--mode proxy`：本次运行强制连接 cc-switch 本地 proxy，不修改 cc-switch.db。

### direct

Claude：

1. 读取 `providers.settings_config.env`。
2. 生成临时 `claude-settings.json`。
3. 执行：

```bash
claude [CC_PROVIDER_LAUNCH_CLAUDE_ARGS...] --settings <temp>/claude-settings.json
```

例如设置 `CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions` 后，实际启动形态为：

```bash
claude --dangerously-skip-permissions --settings <temp>/claude-settings.json
```

Codex：

1. 读取 `providers.settings_config.auth` 和 `providers.settings_config.config`。
2. 生成临时目录：

```text
<temp>/codex/auth.json
<temp>/codex/config.toml
```

3. 从父进程环境或选定配置文件读取 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV`。默认样例值为 `CODEX_HOME`；该值是**环境变量名**，不是目录路径。
4. 只为 Codex 子进程注入该变量，并指向临时目录：

```text
CODEX_HOME=<temp>/codex
```

5. 执行：

```bash
codex [CC_PROVIDER_LAUNCH_CODEX_ARGS...]
```

若未设置、仅为空白，或不是合法环境变量名，启动器会在创建子进程前报错（错误信息会提示 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV` 与当前选定 env 文件路径），避免 Codex 回退到全局 `~/.codex`。

每次 `ccs run xN` 都创建独立临时 `CODEX_HOME`，其中只写入本次的 `auth.json` 与 `config.toml`（不写回全局用户 Home）。为保留历史会话与用户状态，启动器会把真实 Codex 用户 Home（配置项 `codex.user_home`，默认 `~/.codex`）中除 `auth.json` / `config.toml` 以及所有 `*.sqlite` / `*.sqlite-wal` / `*.sqlite-shm` 外的已有条目链接进临时 Home（Windows 目录用 junction，文件优先 hardlink），因此 `plugins/`、`skills/` 等对子进程可见。生成 temp `config.toml` 时，会把真实 Home `config.toml` 中的 `[marketplaces]` / `[plugins.*]` / `[mcp_servers.*]` 表合并进去（真实侧优先），以便 native plugin 启用状态与已注册 MCP 在 provider 隔离配置下仍生效；模型与 `base_url` 等仍以 provider 配置为准。SQLite 运行库不共享，避免 hardlink + WAL 导致本地 state 损坏；每次临时 Home 由 Codex 自行创建 state DB。固定 launch home 可跨次复用；不使用 `codex --profile` 选择 provider。

例如用户显式选择运行参数后，实际启动形态为：

```bash
CODEX_HOME=<temp>/codex codex -a never --sandbox danger-full-access
```

Grok：

1. 复用 **codex** provider 编号与 `proxy_config`（`gN` / `grok <selector>` 与 `xN` 选同一供应商）。
2. 从 codex `settings_config` 翻译生成临时目录：

```text
<temp>/grok/config.toml
<temp>/grok/auth.json   # 空对象，避免继承全局 OIDC
```

3. 只为 Grok 子进程注入：

```text
GROK_HOME=<temp>/grok
XAI_API_KEY=<from codex auth or proxy token>
```

**不**注入 `CODEX_HOME`。`wire_api = responses` 时写入 `api_backend = "responses"`，并把 `base_url` 规范为带 `/v1` 的 OpenAI 兼容根。

4. 混合 Home（与 Codex 同思路）：临时 `GROK_HOME` 只承载本次 `config.toml` / `auth.json`。若真实 Grok 用户 Home（配置项 `grok.user_home`，默认 `~/.grok`）存在，则确保其中有会话目录（配置项 `grok.sessions_dir`，默认 `sessions`；不存在则创建空目录），再将其余非私有条目链接进临时 Home（私有：`auth.json`、`config.toml`，以及 `*.sqlite` / `*.sqlite-wal` / `*.sqlite-shm`），因此 `installed-plugins/`、`skills/` 等对子进程可见。生成 temp `config.toml` 时合并真实 Home 的 `[marketplace]` / `[plugins]`（真实侧优先），保留已信任插件的启用列表；模型与网关仍由 provider 写入。会话写入经链接回落到真实用户 Home；真实用户 Home 不存在时退化为纯临时 Home。

```bash
ccs run g3
ccs run grok 3 --mode direct
```

### 路由启动

Claude/Codex 都会连接 cc-switch 本地 proxy，但实际 provider 仍由 cc-switch 当前状态或 failover queue 决定。

proxy 启动由 `proxy_config.proxy_enabled = 1` 自动触发，也可通过 `--mode proxy` 单次强制触发；传入的 provider 编号只用于选择和展示 provider 意图，不会强制 proxy 路由到该 provider。

当前实现会读取 `proxy_config`：

```sql
SELECT listen_address, listen_port, enabled, proxy_enabled
FROM proxy_config
WHERE app_type = ?
```

并在启动前检查 proxy 端口是否可连接。

## 当前边界

当前 launcher 的边界是：

- 支持 `list`、`alias`、`backup`、`restore` 和 `run`。
- `backup`/`restore` 仅处理供应商相关表 `backup-<timestamp>.zip`（内含 `providers.json`），不做整库复制。
- `run` 根据 `proxy_config.proxy_enabled` 自动选择 direct 或 proxy 启动，也支持 `--mode direct` / `--mode proxy` 单次覆盖。
- provider 通过列表编号选择。
- 路由启动不强制指定 provider，实际 provider 由 cc-switch 当前状态或 failover queue 决定。
- 不实现请求级 / 会话级 provider override。
- 不修改 cc-switch Rust/Tauri proxy。
- 不负责 Markdown 导出、OMP 同步或 Claude/Codex 多供应商全局配置同步。

## 开发命令

```bash
make install
make dev list
make check
make clean
```

项目依赖见 `pyproject.toml`：

- 运行依赖：`dynaconf`
- 开发依赖：`ruff`, `mypy`
