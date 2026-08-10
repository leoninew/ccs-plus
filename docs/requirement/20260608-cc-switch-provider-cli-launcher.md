# cc-switch 指定供应商 CLI 启动器 Requirement

## 背景

cc-switch 已经在数据库中保存 Claude / Codex 等应用的供应商配置，并支持两种运行方式：

1. 非路由场景：直接把供应商配置用于本次 CLI 进程。
2. 路由场景：Claude / Codex 指向 cc-switch 本地代理，由代理按当前供应商或故障转移队列转发请求。

当前实现基于 cc-switch 数据库，用 Bash + Python 实现独立启动器，用于启动 Claude Code CLI 或 Codex CLI，并尽量不影响 cc-switch 或目标 CLI 的全局配置。

## 目标

实现脚本化启动方案，支持：

- 从 cc-switch SQLite 数据库读取指定 app family 的 provider 配置。
- 列出 Claude / Codex provider，并按排序结果生成编号。
- 启动 Claude Code CLI。
- 启动 Codex CLI；若 Codex 配置目录 override 未配置，则拒绝写全局配置。
- 自动读取 `proxy_config.proxy_enabled` 判断启动方式：
  - `proxy_enabled = 0`：使用 provider 编号对应配置 direct 启动。
  - `proxy_enabled = 1`：生成指向 cc-switch 本地代理的临时配置，实际 provider 由 cc-switch 当前状态或故障转移队列决定。
- 通过临时配置文件、临时配置目录或进程级环境变量完成，不写入用户全局配置。
- 脚本退出后清理临时文件。

## 当前范围

### 必须支持

- 默认读取数据库：`~/.cc-switch/cc-switch.db`。
- 支持 `claude` app family。
- 支持 `codex` app family。
- 支持通过 provider 列表编号指定供应商。
- 支持：
  - `list`：按类别树形列出 providers。
  - `alias`：展示已配置 CLI alias。
  - `run`：自动按 `proxy_config.proxy_enabled` 选择 direct 或路由启动。
- 明确说明路由启动不能指定 provider 且完全不影响全局状态。

### 已实现命令形态

```bash
./scripts/ccl.sh list
./scripts/ccl.sh list claude
./scripts/ccl.sh list codex
./scripts/ccl.sh alias
./scripts/ccl.sh run claude 1
./scripts/ccl.sh run codex 1
```

### 当前配置项

`.env.sample` 提供：

```text
CC_PROVIDER_LAUNCH_CLAUDE_CLIS=claude:c,mini-claude:m
CC_PROVIDER_LAUNCH_CODEX_CLIS=codex:x
```

可通过 `--env-file` 指定其他配置文件。

Codex 实际启动需要额外配置：

```text
CC_PROVIDER_LAUNCH_CODEX_HOME_ENV=<Codex 配置目录环境变量名>
```

否则运行会报错，避免写入全局 `~/.codex`。

## 非目标

- 不重写 cc-switch proxy 的协议转换能力。
- 不修改 cc-switch 全局 current provider。
- 不修改 Claude / Codex 的全局配置文件。
- 不支持所有第三方供应商的边缘格式。
- 不实现 GUI。
- 不实现请求级 / 会话级指定 provider 路由。
- launcher 不负责 Markdown 导出、OMP 同步或 Claude/Codex 多供应商全局配置同步。
- 不通过 provider id / provider name 直接运行。

## 约束

- 不应写入或覆盖：
  - `~/.claude/settings.json`
  - `~/.codex/auth.json`
  - `~/.codex/config.toml`
  - cc-switch 数据库中的 current provider 状态
  - cc-switch proxy takeover 状态
- 脚本实现直接使用 Python `sqlite3` 读取数据库。
- 若需要路由到指定 provider 且不影响全局状态，需要 cc-switch proxy 提供请求级 provider override。
- 临时文件必须创建在安全的临时目录中，并在进程退出后清理。
- API key/token 不应打印到控制台日志。

## 验收标准

- 可以通过 Bash 入口调用 Python 逻辑。
- `list` 可以按类别树形列出 provider，供应商前保留编号。
- direct 启动时，启动器不修改全局配置文件。
- 路由启动时，启动器只把 CLI 指向 cc-switch 本地代理，不修改当前 provider。
- 找不到数据库、provider 编号越界、代理未运行或 Codex 配置目录 override 未配置时，给出清晰错误。
- 临时配置文件在退出后被清理。
- 输出中不泄露 API key/token。
- 文档明确说明：路由启动不能保证“路由到指定 provider”，只能路由到 cc-switch 当前 provider / failover queue。

## 风险

- Codex CLI 的临时配置目录机制仍需要确认具体环境变量或参数。
- 不同 provider 的 `settings_config` 格式可能差异较大。
- 路由到指定 provider 且不影响全局状态，需要 cc-switch proxy 支持请求级 provider override。
- 如果复用当前 cc-switch proxy，则同时运行的其他 Claude/Codex 请求会共享 cc-switch 当前 provider / failover queue。

## 待议事项

- Codex CLI 是否有稳定的配置目录环境变量或参数？
- 是否需要支持通过 provider id / provider name 选择，还是继续只支持编号？
- 是否需要支持 failover queue 作为一种显式展示能力？
