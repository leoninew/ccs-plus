# ccl run CLI 参数配置 Spec

## 状态

Approved

## Requirement Basis

- Requirement 文档：`docs/requirement/20260608-ccl-run-cli-args.md`
- Requirement 状态：Approved

本 spec 基于已确认需求：`ccl run` 需要显式读取配置中的 CLI 启动参数，并在启动 Claude / Codex 子进程时传递这些参数；不依赖 shell alias，不改变现有 CLI registry / inline alias 语义。

## Overview

新增 family-level CLI args 配置：

```text
CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions
CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access
```

启动流程保持现有结构：

1. 从 `.env` / `--env-file` 和当前环境读取配置。
2. 根据 `run <app>` 的输入解析真实 CLI 名称。
3. 根据真实 CLI 名称解析 app family。
4. 读取 provider、proxy 状态并生成临时配置。
5. 组装子进程命令时插入该 family 的默认 CLI args。
6. 使用 `subprocess.call(command: list[str])` 启动，不经过 shell。

## Design Decisions

### 1. 新增 family-level args 配置

新增两个配置项：

- `CC_PROVIDER_LAUNCH_CLAUDE_ARGS`
- `CC_PROVIDER_LAUNCH_CODEX_ARGS`

它们按 app family 生效，而不是按 CLI name 生效。

原因：

- 当前需求来自 `claude` / `codex` 两类 CLI 的默认启动参数。
- 现有 registry 也是 family 维度：`CC_PROVIDER_LAUNCH_CLAUDE_CLIS` / `CC_PROVIDER_LAUNCH_CODEX_CLIS`。
- 不引入 per-CLI mapping，避免配置格式过早复杂化。

### 2. 参数读取优先级沿用现有 env 规则

参数读取应与 `env_csv()` 现有逻辑一致：

1. 优先读取当前进程环境变量。
2. 若未设置，再读取 `.env` / `--env-file` 中的值。
3. 若都未设置，则为空。

这保证用户可以用 shell 环境临时覆盖 `.env` 配置。

### 3. 使用 `shlex.split()` 解析参数字符串

新增参数解析函数应使用 Python `shlex.split()`：

```python
shlex.split(raw_args)
```

效果：

- `-a never --sandbox danger-full-access` 解析为四个参数。
- `--label "hello world"` 中的 `hello world` 保持为单个参数。
- 引号不闭合等非法输入直接抛出配置错误。

### 4. 参数插入位置

Claude 命令组装：

```python
command = [cli_name, *cli_args, "--settings", str(settings_path)]
```

Codex 命令组装：

```python
command = [cli_name, *cli_args]
```

原因：

- 用户配置的是目标 CLI 参数，应紧跟 CLI 可执行文件。
- Claude launcher 自己追加的 `--settings` 应保留，且靠后更明确由 launcher 控制临时 settings。
- Codex 当前通过环境变量注入配置目录，不需要额外命令参数。

### 5. 不改变 inline alias 解析语义

`ccl run c 1` 的流程保持：

1. `resolve_cli("c") -> "claude"`
2. `app_family("claude") -> "claude"`
3. 读取 `CC_PROVIDER_LAUNCH_CLAUDE_ARGS`
4. 运行 `claude` 并附加 Claude args

`alias` 命令继续展示 CLI alias，不展示启动参数。

## Affected Components

### `cc_provider_launch.py`

需要调整：

- import `shlex`。
- 新增 CLI args 读取 / 解析函数。
- 在 `run()` 组装 Claude / Codex command 前读取对应 family args。
- 参数解析失败时抛出 `LaunchError`，并给出清晰错误。

建议新增函数：

```python
def env_args(env_values: dict[str, Any], key: str) -> list[str]:
    raw = os.environ.get(key) or env_values.get(key) or ""
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        return shlex.split(raw)
    except ValueError as exc:
        raise LaunchError(f"Invalid {key}: {exc}") from exc
```

以及：

```python
def cli_args(env_file: Path, family: str) -> list[str]:
    env_values = dotenv_values(env_file) if env_file.exists() else {}
    key = f"CC_PROVIDER_LAUNCH_{family.upper()}_ARGS"
    return env_args(env_values, key)
```

### `.env.sample`

增加示例配置：

```text
CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions
CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access
```

如果示例不希望默认启用危险参数，可用注释形式展示。

### `docs/README.md`

更新配置说明：

- 说明 `CC_PROVIDER_LAUNCH_*_CLIS` 只配置 CLI 名称和 inline alias。
- 说明 `CC_PROVIDER_LAUNCH_*_ARGS` 配置传给目标 CLI 的默认参数。
- 明确 shell alias 不会被 `ccl run` 自动继承。

### Tests

现有测试文件可能位于 `tests/` 或项目根测试中。需要增加覆盖命令组装或 subprocess 调用参数的测试。

建议测试点：

1. Claude args：配置 `CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions` 后，subprocess command 包含该参数和 `--settings`。
2. Codex args：配置 `CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access` 后，subprocess command 包含拆分后的参数。
3. Inline alias：`run c 1` 解析到 `claude` 后仍使用 Claude args。
4. Empty args：未配置 args 时 command 与旧行为一致。
5. Invalid quoting：配置未闭合引号时报 `LaunchError`。

## Interfaces

### Configuration Interface

新增环境变量：

```text
CC_PROVIDER_LAUNCH_CLAUDE_ARGS=<shell-like args string>
CC_PROVIDER_LAUNCH_CODEX_ARGS=<shell-like args string>
```

示例：

```text
CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions
CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access
```

### Runtime Command Interface

无新增 CLI 参数。

现有命令保持不变：

```bash
ccl run <cli-or-inline-alias> <provider_number> [--db <path>] [--env-file <path>] [--cwd <path>]
```

## Technical Questions

- 暂不支持 per-CLI args。如果同一 family 内多个 CLI 需要不同默认参数，后续再增加更细粒度配置。
- `alias` 命令是否展示 args：本 spec 建议不展示，避免混淆“run 输入 alias”和“CLI 启动参数”。

## Risks

- 配置中包含 Windows path 或复杂引号时，`shlex.split()` 的 POSIX 解析可能与部分用户直觉不同；但当前运行环境是 Bash/Cygwin，shell-like 解析符合主要使用场景。
- `--dangerously-skip-permissions`、`--sandbox danger-full-access` 属于用户明确配置的高权限参数，launcher 只透传，不默认启用。
- 如果目标 CLI 参数顺序敏感，新增 args 插入在 launcher 参数之前可能影响行为；当前 Claude 的 `--settings` 保持 launcher 追加，Codex 无 launcher 参数，风险较低。

## Alternatives Considered

### 读取 shell alias

不采用。

原因：Python 子进程不继承 shell alias；解析用户 shell 初始化文件会依赖具体 shell、加载顺序和交互模式，行为不可预测。

### 使用 `shell=True` 或 `bash -ic`

不采用。

原因：增加 shell 注入风险，也会引入交互 shell 启动开销和平台差异。

### 扩展 `CC_PROVIDER_LAUNCH_*_CLIS` 格式

不采用。

例如 `claude:c:--dangerously-skip-permissions` 会让单个配置同时表达 CLI 名称、inline alias 和启动参数，解析复杂且容易与参数中的 `:` / `,` 冲突。

### per-CLI args 映射

暂不采用。

例如 `CC_PROVIDER_LAUNCH_CLI_ARGS_CLAUDE=...` 或 JSON mapping。当前需求只需要 family 默认参数，先保持简单。

## User Review Notes

- 待用户 review。
