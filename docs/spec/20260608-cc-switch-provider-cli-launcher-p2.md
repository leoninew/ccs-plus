# cc-switch 指定供应商 CLI 启动器 P2 Spec

## 目标

P2 在现有启动器基础上移除用户可见的 `--mode` 参数，改为根据 cc-switch 数据库中的 `proxy_config.proxy_enabled` 自动选择 direct 或路由启动。

P2 不实现请求级 / 会话级指定 provider 路由；路由启动复用 cc-switch 已有本地 proxy 能力。

## 约束

- 启动器文件：
  - `scripts/ccl.sh`
  - `cc_provider_launch.py`
- 命令入口保持：`run <app> <provider_number>`。
- provider 通过 `list` 输出的 1-based 编号选择。
- 不修改：
  - cc-switch 当前 provider
  - `providers.is_current`
  - local settings 当前 provider 字段
  - Claude / Codex 全局配置文件
  - proxy takeover 全局开关
- 不修改 cc-switch Rust/Tauri 代码。
- API key/token 不得输出到日志。

## 命令形态

```bash
./scripts/ccl.sh run claude <provider_number>
./scripts/ccl.sh run codex <provider_number>
```

`--mode` 参数不再存在。

## 启动方式选择

读取 `proxy_config`：

```sql
SELECT listen_address, listen_port, enabled, proxy_enabled
FROM proxy_config
WHERE app_type = ?
```

选择规则：

```text
proxy_enabled = 0 -> direct
proxy_enabled = 1 -> route through cc-switch proxy
```

注意：只用 `proxy_enabled` 判断是否路由，不用 `enabled` 判断。

## Direct 行为

### Claude

生成临时 `claude-settings.json`，内容来自指定 provider 的 `settings_config.env`。

启动：

```bash
claude --settings <temp>/claude-settings.json
```

### Codex

生成临时目录：

```text
<temp>/codex/auth.json
<temp>/codex/config.toml
```

只有设置 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV` 时才启动 Codex，避免写入全局 `~/.codex`。

## 路由启动行为

### Claude

生成临时 settings：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:<port>",
    "ANTHROPIC_AUTH_TOKEN": "PROXY_MANAGED"
  }
}
```

启动后请求进入 cc-switch proxy，实际 provider 由 cc-switch 当前 provider / failover queue 决定。

### Codex

生成临时 Codex 配置：

```toml
base_url = "http://127.0.0.1:<port>/v1"
wire_api = "responses"
```

`auth.json` 写入：

```json
{
  "OPENAI_API_KEY": "PROXY_MANAGED"
}
```

启动后请求进入 cc-switch proxy，实际 provider 由 cc-switch 当前 provider / failover queue 决定。

## Provider 编号语义

- Direct：provider 编号决定本次使用的 provider 配置。
- 路由：provider 编号只用于选择和展示 provider 意图，不强制 cc-switch proxy 使用该 provider。

## 错误处理

- 数据库不存在：报错。
- provider 编号越界：提示运行 `ccl list <app>`。
- app 未注册：列出注册的 CLI。
- `proxy_enabled = 1` 但 proxy 端口不可连接：报错。
- Claude direct 缺少认证字段：报错。
- Codex 缺少 `auth` 或 `config`：报错。
- Codex 未设置配置目录 override：报错并拒绝启动。

## 验收标准

```bash
python cc_provider_launch.py --help
python cc_provider_launch.py run --help
python cc_provider_launch.py list
python cc_provider_launch.py alias
python cc_provider_launch.py run claude 1
python cc_provider_launch.py run codex 1
make check
```

期望：

- help 不显示 `--mode`。
- `proxy_config.proxy_enabled = 0` 时走 direct。
- `proxy_config.proxy_enabled = 1` 时走本地 proxy。
- 不修改 cc-switch current provider。
- 不修改全局 live config。
- 输出不泄露 API key/token。

## 非目标

- 不实现 provider override。
- 不实现并发不同 provider 路由隔离。
- 不持久化任何 launcher session。
- 不改变 failover queue 语义。
- 不让远程客户端注册路由 session。
