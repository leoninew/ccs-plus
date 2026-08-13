# cc-switch 指定供应商 CLI 启动器 Spec

## 当前实现目标

当前实现是一个独立启动器：用 Bash + Python 从 cc-switch 数据库读取 Claude / Codex provider 配置，生成临时配置并启动对应 CLI。启动方式由 `proxy_config.proxy_enabled` 自动决定，同时不主动修改全局配置或 cc-switch 当前 provider。

## 当前文件结构

```text
scripts/ccl.sh
cc_provider_launch.py
```

## 约束

- 默认数据库：`~/.cc-switch/cc-switch.db`。
- 不主动修改：
  - `~/.claude/settings.json`
  - `~/.codex/auth.json`
  - `~/.codex/config.toml`
  - cc-switch 数据库里的 current provider
  - cc-switch local settings 当前 provider
  - cc-switch proxy takeover 状态
- 临时文件放在 `tempfile.TemporaryDirectory()` 创建的临时目录中。
- 进程退出后清理临时目录。
- stdout/stderr 不输出完整 API key、token、auth 配置。
- 不修改 Rust/Tauri 代码。
- 不实现请求级 provider override。
- 路由启动不保证使用命令行选择的 provider。

## 启动入口

```bash
./scripts/ccl.sh list [app] [--db <path>] [--env-file <path>]
./scripts/ccl.sh alias [--env-file <path>]
./scripts/ccl.sh run <app> <provider_number> [--db <path>] [--env-file <path>] [--cwd <path>]
```

### app

`list <app>` 的 app 是 provider 类别，例如 `claude` / `codex`。

`run <app>` 的 app 是 `.env` 或 `--env-file` 中注册的 CLI 名称，也可使用 inline alias。

默认示例：

```text
CC_PROVIDER_LAUNCH_CLAUDE_CLIS=claude:c,mini-claude:m
CC_PROVIDER_LAUNCH_CODEX_CLIS=codex:x
```

### provider_number

`provider_number` 是 provider 列表中的 1-based 编号，不是数据库 provider id。

provider 按以下顺序编号：

```sql
ORDER BY app_type, sort_index, name
```

## 启动方式判断

启动器读取 `proxy_config.proxy_enabled` 自动选择方式：

- `proxy_enabled = 0`：direct 启动，使用 provider 编号对应配置。
- `proxy_enabled = 1`：路由启动，生成指向 cc-switch 本地 proxy 的临时配置。

路由启动时，provider 编号只用于选择和展示 provider 意图；实际路由由 cc-switch 当前 provider / failover queue 决定。

## 数据读取

从 SQLite 表 `providers` 读取：

```sql
SELECT id, app_type, name, settings_config, meta, sort_index
FROM providers
WHERE app_type = ?
ORDER BY app_type, sort_index, name
```

从 SQLite 表 `proxy_config` 读取代理地址和路由开关：

```sql
SELECT listen_address, listen_port, enabled, proxy_enabled
FROM proxy_config
WHERE app_type = ?
```

读取规则：

- 使用只读 SQLite 连接。
- `settings_config` 按 JSON 解析。
- `meta` 按 JSON 解析，空值视为 `{}`。
- provider 编号越界时报错。
- app 未注册时报错。
- 路由启动时，如果 proxy 未启用或不可连接，给出清晰错误。

## Claude direct 行为

从 provider `settings_config.env` 提取 Claude 所需环境变量。

要求至少存在：

- `ANTHROPIC_AUTH_TOKEN` 或
- `ANTHROPIC_API_KEY`

生成临时 settings 文件：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "...",
    "ANTHROPIC_AUTH_TOKEN": "...",
    "ANTHROPIC_API_KEY": "...",
    "ANTHROPIC_MODEL": "..."
  }
}
```

启动：

```bash
claude --settings <temp-settings.json>
```

## Claude 路由启动行为

从 `proxy_config` 读取代理地址，生成临时 settings：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:<port>",
    "ANTHROPIC_AUTH_TOKEN": "PROXY_MANAGED"
  }
}
```

启动：

```bash
claude --settings <temp-settings.json>
```

## Codex direct 行为

从 provider `settings_config` 提取 Codex 配置：

```json
{
  "auth": { ... },
  "config": "...toml..."
}
```

生成临时目录结构：

```text
<temp>/codex/
  auth.json
  config.toml
```

实际启动依赖进程级配置目录 override。

当前实现只在设置了以下环境变量时启动 Codex：

```text
CC_PROVIDER_LAUNCH_CODEX_HOME_ENV=<Codex 配置目录环境变量名>
```

否则报错并停止，不 fallback 到写全局 `~/.codex`。

## Codex 路由启动行为

生成临时 Codex 配置：

- auth 写入占位 token：`OPENAI_API_KEY=PROXY_MANAGED`
- config 设置：
  - `base_url = "http://127.0.0.1:<port>/v1"`
  - `wire_api = "responses"`

不写全局 Codex 配置。

## 错误处理

当前实现处理：

- 数据库不存在。
- provider 编号越界。
- app 未在 `.env` / `--env-file` 注册。
- `settings_config` / `meta` 不是合法 JSON object。
- Claude direct 缺少认证字段。
- Codex provider 缺少 `auth` 或 `config`。
- 路由启动缺少 proxy_config。
- 路由启动代理未启用或不可连接。
- Codex 临时配置目录机制未配置。

## 脱敏要求

输出中必须脱敏：

- API key
- auth token
- Authorization header
- `OPENAI_API_KEY`
- `ANTHROPIC_AUTH_TOKEN`
- `ANTHROPIC_API_KEY`
- key 名包含 `token` / `api_key` / `apikey` / `secret` / `password` / `authorization` 的字段

当前脱敏格式保留末 4 位，例如：

```text
****abcd
```

## 验收命令

```bash
./scripts/ccl.sh list
./scripts/ccl.sh list claude
./scripts/ccl.sh list codex
./scripts/ccl.sh alias
./scripts/ccl.sh run claude 1
./scripts/ccl.sh run codex 1
```

若 Codex 临时配置目录机制未配置，实际启动应明确报错并不写全局配置。

## 非目标

- 不支持请求级 / 会话级指定 provider 路由。
- 不修改 cc-switch proxy。
- 不支持 GUI。
- 不实现独立协议转换代理。
- launcher 不负责 Markdown 导出、OMP 同步或 Claude/Codex 多供应商全局配置同步。

## 仍待议事项

- Codex CLI 的临时配置目录 override 机制具体环境变量名是什么。
- 是否需要后续支持 provider id / name 查询。
- 是否需要在输出摘要中更明确提示路由启动的实际路由由 current provider / failover queue 决定。
