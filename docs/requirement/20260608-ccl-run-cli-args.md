# ccl run CLI 参数配置 Requirement

## 状态

Approved

## 背景

当前 `ccl run` 通过 `CC_PROVIDER_LAUNCH_CLAUDE_CLIS` 和 `CC_PROVIDER_LAUNCH_CODEX_CLIS` 配置可启动的 CLI 名称及 inline alias，例如 `claude:c`、`codex:x`。

这些配置只能解决“运行哪个 CLI 可执行文件”和“用户在 `ccl run` 中输入什么简称”的问题，不能表达实际启动该 CLI 时还需要附加的命令行参数。

实际使用中，用户 shell 里可能存在 alias：

```bash
claude='claude --dangerously-skip-permissions'
codex='codex -a never --sandbox danger-full-access'
```

但 `ccl run` 通过 Python `subprocess.call(command: list[str])` 启动子进程，不经过交互式 shell，因此不会展开 shell alias。结果是 `ccl run claude 1` / `ccl run codex 1` 只会执行裸 `claude` / `codex`，缺少用户期望的默认参数。

## 目标

- 为 `ccl run` 增加显式、可配置的 CLI 启动参数能力。
- 保持当前 CLI registry / inline alias 语义：
  - `CC_PROVIDER_LAUNCH_CLAUDE_CLIS` / `CC_PROVIDER_LAUNCH_CODEX_CLIS` 继续只负责 CLI 名称和 `ccl run` 输入 alias。
  - 新配置负责传给目标 CLI 的启动参数。
- 避免依赖 shell alias、interactive shell 或 `shell=True`。
- 支持 Claude 和 Codex 分别配置默认启动参数。
- 参数应只影响本次 `ccl run` 启动的子进程，不修改用户全局 shell alias 或目标 CLI 全局配置。

## 非目标

- 不自动读取或解析用户 shell alias。
- 不把 `CC_PROVIDER_LAUNCH_CLAUDE_CLIS` / `CC_PROVIDER_LAUNCH_CODEX_CLIS` 扩展为同时表达 CLI 名称、`ccl run` alias 和启动参数的复杂格式。
- 不改变 `list` 使用 provider category、`run` 使用 CLI 名称 / inline alias 的现有语义。
- 不改变 provider 选择、proxy/direct 自动选择、临时配置生成逻辑。
- 不引入 `shell=True` 或依赖特定 shell 的启动方式。

## 用户场景

### 场景 1：Claude Code 默认跳过权限提示

用户希望配置后：

```bash
ccl run claude 1
```

实际启动等价于：

```bash
claude --dangerously-skip-permissions --settings <temporary-settings-path>
```

### 场景 2：Codex 默认使用指定 approval / sandbox 参数

用户希望配置后：

```bash
ccl run codex 1
```

实际启动等价于：

```bash
codex -a never --sandbox danger-full-access
```

同时仍由 `ccl run` 注入 Codex 临时配置目录环境变量。

### 场景 3：inline alias 仍只代表 CLI 名称

若配置：

```text
CC_PROVIDER_LAUNCH_CLAUDE_CLIS=claude:c
```

则：

```bash
ccl run c 1
```

仍解析为运行 `claude` CLI，并附加 Claude family 对应的启动参数。

## 需求

### 必须支持

- 新增 Claude family 的默认启动参数配置。
- 新增 Codex family 的默认启动参数配置。
- `ccl run` 在启动目标 CLI 时读取对应 family 的默认启动参数并传递给子进程。
- 参数解析应支持常见 shell-like quoting，例如包含空格的单个参数。
- 当参数配置为空或未设置时，行为与当前一致。
- 启动参数应插入到目标 CLI 命令中，并保留 launcher 自己追加的配置参数：
  - Claude：目标 CLI 参数应与 `--settings <temporary-settings-path>` 共存。
  - Codex：目标 CLI 参数应与临时配置目录环境变量共存。
- 文档应说明 shell alias 不会被 `ccl run` 自动继承，用户需要把期望参数写入 launcher 配置。

### 推荐配置形态

建议新增：

```text
CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions
CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access
```

原因：

- 与现有 `CC_PROVIDER_LAUNCH_<FAMILY>_CLIS` 命名一致。
- 明确区分“CLI 可执行文件配置”和“传给 CLI 的参数配置”。
- 对当前需求足够简单，不需要为每个 CLI name 单独建复杂映射。

## 验收标准

- 设置 `CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions` 后，`ccl run claude 1` 启动命令包含该参数，并仍包含 `--settings <temporary-settings-path>`。
- 设置 `CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access` 后，`ccl run codex 1` 启动命令包含这些参数。
- 未设置新增参数变量时，现有 `ccl run` 行为不变。
- `ccl run c 1` 等 inline alias 入口也能使用对应 family 的参数配置。
- 参数配置中带引号的值可以作为单个参数传递。
- README 或相关文档包含新增配置项示例，并说明 shell alias 不会自动生效。
- 测试覆盖：
  - Claude args 拼接。
  - Codex args 拼接。
  - inline alias 下 args 仍生效。
  - 未设置 args 时保持旧行为。

## Open Questions

- 是否需要支持 per-CLI 参数配置，例如同属 Claude family 的 `claude` 和 `mini-claude` 使用不同默认参数？当前需求建议先不支持。
- 参数解析失败时应直接报错，还是按原始字符串作为单个参数传递？当前建议直接报错，避免静默启动错误命令。

## Decisions

- `CC_PROVIDER_LAUNCH_CLAUDE_CLIS` / `CC_PROVIDER_LAUNCH_CODEX_CLIS` 不扩展语义，继续只表达 CLI 名称和 inline alias。
- 不读取 shell alias；通过显式 env 配置表达 `ccl run` 的启动参数。

## User Review Notes

- 待用户 review。
