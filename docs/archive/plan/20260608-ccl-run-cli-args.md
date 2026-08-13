# ccl run CLI 参数配置 Plan

## 状态

Approved

## 输入文档

- Requirement：`docs/requirement/20260608-ccl-run-cli-args.md`，状态 Approved
- Spec：`docs/spec/20260608-ccl-run-cli-args.md`，状态 Approved

## Implementation Steps

### 1. 更新配置解析

文件：`cc_provider_launch.py`

- 增加 `import shlex`。
- 新增 `env_args(env_values, key)`：
  - 从 `os.environ` 优先读取配置。
  - fallback 到 `.env` / `--env-file` 的 `dotenv_values`。
  - 空值返回 `[]`。
  - 非空值用 `shlex.split()` 拆分。
  - `ValueError` 转换为 `LaunchError`，错误信息包含配置 key。
- 新增 `cli_args(env_file, family)`：
  - 生成配置 key：`CC_PROVIDER_LAUNCH_<FAMILY>_ARGS`。
  - 调用 `env_args()` 返回参数列表。

### 2. 更新 `run()` 命令组装

文件：`cc_provider_launch.py`

- 在解析出 `family` 后、组装 `command` 前读取：

```python
args_for_cli = cli_args(env_file, family)
```

- Claude 分支改为：

```python
command = [cli_name, *args_for_cli, "--settings", str(settings_path)]
```

- Codex 分支改为：

```python
command = [cli_name, *args_for_cli]
```

- 保持：
  - provider 选择不变。
  - proxy/direct 自动选择不变。
  - Codex `extra_env` 逻辑不变。
  - `subprocess.call(command: list[str])` 不变。

### 3. 更新示例配置

文件：`.env.sample`

- 增加注释形式示例，避免默认启用高权限参数：

```text
# CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions
# CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access
```

### 4. 更新 README

文件：`docs/README.md`

- 在 CLI 配置说明附近补充：
  - `CC_PROVIDER_LAUNCH_*_CLIS` 只配置 CLI 名称和 inline alias。
  - `CC_PROVIDER_LAUNCH_*_ARGS` 配置传给目标 CLI 的默认启动参数。
  - `ccl run` 不经过 interactive shell，因此不会继承 shell alias。
- 在 run 示例附近补充配置示例。

### 5. 更新测试

文件：根据现有测试结构确定，预计为 `tests/test_cc_provider_launch.py` 或类似文件。

增加测试覆盖：

1. `CC_PROVIDER_LAUNCH_CLAUDE_ARGS` 被插入 Claude command，且 `--settings` 仍存在。
2. `CC_PROVIDER_LAUNCH_CODEX_ARGS` 被 `shlex.split()` 拆分后插入 Codex command。
3. inline alias 入口仍读取 family args。
4. 未设置 args 时 command 与旧行为一致。
5. 非法 quoting 抛出 `LaunchError`。

## Files to Change

- `cc_provider_launch.py`
- `.env.sample`
- `docs/README.md`
- 测试文件（待实施时根据实际文件名确认）

## Verification Plan

### 自动化测试

优先运行项目现有测试：

```bash
pytest
```

如果项目测试命令由 `pyproject.toml` 或 Makefile 定义，实施时以项目实际命令为准。

### 手工/诊断验证

在不真实启动目标 CLI 的前提下，优先通过测试 mock `subprocess.call()` 验证 command list。

如需手工验证，可使用临时 env-file 配置：

```text
CC_PROVIDER_LAUNCH_CLAUDE_CLIS=claude:c
CC_PROVIDER_LAUNCH_CLAUDE_ARGS=--dangerously-skip-permissions
CC_PROVIDER_LAUNCH_CODEX_CLIS=codex:x
CC_PROVIDER_LAUNCH_CODEX_ARGS=-a never --sandbox danger-full-access
```

然后运行：

```bash
python cc_provider_launch.py run c 1 --env-file <temp-env-file>
python cc_provider_launch.py run x 1 --env-file <temp-env-file>
```

实际执行目标 CLI 会进入交互进程，因此手工验证只作为必要时的补充；核心验证应由单元测试完成。

## Blockers

- 无已知 blocker。

## Assumptions

- 现有测试可以 mock `launch_subprocess()` 或 `subprocess.call()`，避免真实启动 Claude/Codex。
- 当前需求只需要 family-level args，不需要 per-CLI args。
- Cygwin/Bash 环境下使用 `shlex.split()` 的 POSIX 语义符合用户配置习惯。

## Risks

- `shlex.split()` 对 Windows 风格路径和反斜杠可能有转义语义；文档需建议复杂参数使用引号。
- 用户配置的是高权限 CLI 参数，launcher 不应默认启用，只提供注释示例。
- 如果目标 CLI 后续改变参数顺序规则，可能需要调整 args 插入位置。

## Rollback

- 删除 `CC_PROVIDER_LAUNCH_*_ARGS` 配置即可恢复旧运行行为。
- 若代码变更需回滚，撤销 `cc_provider_launch.py` 中 args 解析和 command 拼接改动，并移除文档/测试更新。

## User Review Notes

- 待用户 review。
