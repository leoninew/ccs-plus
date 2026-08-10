# cc-switch 指定供应商 CLI 启动器 Plan

## 当前实现落点

仓库根目录已有：

```text
scripts/ccl.sh
cc_provider_launch.py
```

职责划分：

- `scripts/ccl.sh`：薄 Bash 入口，负责定位 Python 脚本并透传参数；兼容 Windows + Cygwin 路径。
- `cc_provider_launch.py`：核心逻辑，负责参数解析、数据库读取、临时配置生成、CLI 启动和清理。

## 当前命令行参数

Python 支持入口：

```bash
./scripts/ccl.sh list [app] [--db <path>] [--env-file <path>]
./scripts/ccl.sh alias [--env-file <path>]
./scripts/ccl.sh run <app> <provider_number> [--db <path>] [--env-file <path>] [--cwd <path>]
```

参数规则：

- `list <app>` 的 app 是 provider 类别。
- `run <app>` 的 app 是 `.env` / `--env-file` 中注册的 CLI 名称，可使用 inline alias。
- 默认 `.env.sample` 注册：
  - `claude:c,mini-claude:m` -> `app_type = claude`
  - `codex:x` -> `app_type = codex`
- `provider_number` 是 `list` 输出中的 1-based 编号，不是 provider id。
- 启动方式由 `proxy_config.proxy_enabled` 自动决定。
- 默认数据库：`~/.cc-switch/cc-switch.db`。
- `--cwd` 默认当前工作目录。
- 启动前输出脱敏摘要。

## 数据库读取层

已实现函数：

```text
list_providers(db_path, app)
provider_by_number(db_path, app, provider_number)
load_proxy_config(db_path, app)
```

读取 providers：

```sql
SELECT id, app_type, name, settings_config, meta, sort_index
FROM providers
ORDER BY app_type, sort_index, name
```

读取 proxy_config：

```sql
SELECT listen_address, listen_port, enabled, proxy_enabled
FROM proxy_config
WHERE app_type = ?
```

处理：

- 使用只读连接。
- `settings_config` JSON decode。
- `meta` JSON decode，空值视为 `{}`。
- 错误信息不包含 token。

## 脱敏与安全输出

已实现：

```text
redact_secret(value)
is_secret_key(key)
first_secret(mapping)
log_launch_summary(summary)
```

脱敏字段包括：

- 任意 key 名包含 `token` / `api_key` / `apikey` / `secret` / `password` / `authorization` 的字段。
- Claude/Codex 常见 API key 字段。

当前输出摘要：

- provider name
- API URL
- 脱敏 API key

当前未输出完整 CLI 命令、临时配置路径或完整配置原文。

## 启动方式判断

```text
proxy_config.proxy_enabled = 0 -> direct
proxy_config.proxy_enabled = 1 -> 路由启动
```

路由启动会检查本地 proxy 端口可连接。

## Claude direct

逻辑：

1. 从 `settings_config.env` 提取 Claude 环境变量。
2. 校验至少存在认证字段：
   - `ANTHROPIC_AUTH_TOKEN` 或 `ANTHROPIC_API_KEY`
3. 生成临时 settings：

```json
{
  "env": { ... }
}
```

4. 启动：

```bash
claude --settings <temp-settings.json>
```

已实现函数：

```text
build_claude_direct(provider, temp_dir)
```

## Claude 路由启动

逻辑：

1. 读取 `proxy_config`。
2. 确认 `proxy_enabled = 1`。
3. 探测代理端口是否可连接。
4. 生成临时 settings：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://<listen_address>:<listen_port>",
    "ANTHROPIC_AUTH_TOKEN": "PROXY_MANAGED"
  }
}
```

5. 启动：

```bash
claude --settings <temp-settings.json>
```

实际 provider 由 cc-switch 当前 provider / failover queue 决定。

## Codex 配置生成

已实现配置生成，实际启动受 Codex 配置目录 override 机制约束。

逻辑：

1. 从 `settings_config.auth` 提取 auth JSON。
2. 从 `settings_config.config` 提取 TOML 字符串。
3. 在临时目录生成：

```text
<temp>/codex/auth.json
<temp>/codex/config.toml
```

Direct 启动：

- 写 provider 原始 auth/config。

路由启动：

- auth 写代理占位认证。
- config 改写：
  - `base_url = "http://<listen_address>:<listen_port>/v1"`
  - `wire_api = "responses"`

## Codex 临时配置目录启动

当前实现策略：

- 如果设置 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV`，则把该环境变量设置为临时 Codex 配置目录并启动 Codex。
- 如果未设置：
  - 报错并停止。
  - 不写全局 `~/.codex`。

## 临时目录生命周期

已使用：

```text
tempfile.TemporaryDirectory(prefix="cc-provider-launch-")
```

要求：

- CLI 进程运行期间临时目录存在。
- CLI 退出后自动清理。

## 依赖

运行依赖：

```text
python-dotenv
```

开发依赖：

```text
ruff
mypy
```

## 验证建议

### 静态验证

```bash
python cc_provider_launch.py --help
python cc_provider_launch.py run --help
python cc_provider_launch.py list
python cc_provider_launch.py list claude
python cc_provider_launch.py alias
python cc_provider_launch.py run claude 1
python cc_provider_launch.py run codex 1
```

### 项目检查

```bash
make lint
make typecheck
make check
```

### 安全验证

- 检查输出不包含真实 token。
- 检查错误路径不打印完整 `settings_config`。

### 行为验证

- Claude direct：确认执行命令形态为 `claude --settings <temp-settings.json>`。
- Claude 路由启动：确认 settings 指向 cc-switch proxy。
- Codex direct/路由启动：确认临时 `auth.json` / `config.toml` 生成逻辑正确。
- 若 Codex config override 已配置：实际启动 Codex。
- 若 Codex config override 未配置：给出 blocker，不污染全局配置。

## 当前边界

- Codex 实际启动依赖 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV` 指定配置目录 override 环境变量；未设置时报错并避免写全局配置。
- 路由启动会连接 cc-switch proxy，但不会强制使用命令行选择的 provider。
- 端口可连接不代表 proxy 一定能成功转发；转发成功依赖 cc-switch 当前 provider 和代理状态。
- 如果 CLI 自身在启动后读取其他全局配置，启动器只保证不主动写全局文件。

## 后续方向

1. 在输出摘要中明确提示路由启动的实际路由由 current provider / failover queue 决定。
2. 支持 provider id / name 选择。
3. 增加路由状态只读展示。
