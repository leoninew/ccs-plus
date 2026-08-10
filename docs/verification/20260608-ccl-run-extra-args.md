# ccl run 额外参数透传 Verification

## 状态

Accepted

## Requirement alignment

- 已支持 `ccl run <app-or-alias> <provider_number> [extra args...]`。
- `argparse.REMAINDER` 捕获 provider number 后的额外 argv token，避免 `-c` 被 launcher 作为未知参数拒绝。
- inline alias 解析仍先发生，额外参数追加到解析后的目标 CLI command。
- 未使用 shell 字符串拼接或 `shell=True`。

## Actual diff summary

- `cc_provider_launch.py`
  - `run` 子命令新增 `cli_args` positional remainder。
  - Claude command 追加 `*args.cli_args`，保留默认 family args 和 `--settings <temporary-settings-path>`。
  - Codex command 追加 `*args.cli_args`，保留默认 family args 和临时配置目录环境变量逻辑。
- `tests/test_cc_provider_launch.py`
  - 增加 `ccl run m 1 -c` 的 argparse 解析覆盖。
  - 增加 Claude inline alias 下默认 family args、`--settings` 和本次 extra args 共存的 command 构建覆盖。
- `docs/requirement/20260608-ccl-run-extra-args.md`
  - 新增轻量范围说明。

## Planned vs actual changed files

- Planned: `cc_provider_launch.py`
- Planned: `tests/test_cc_provider_launch.py`
- Planned: `docs/requirement/20260608-ccl-run-extra-args.md`
- Actual: matched planned, plus `docs/verification/20260608-ccl-run-extra-args.md`

## Acceptance criteria checklist

- [x] `ccl run m 1 -c` 不再因 `-c` 报 `unrecognized arguments`。
- [x] `-c` 被追加到最终目标 CLI command。
- [x] 默认 family args 和本次 extra args 可以共存。
- [x] Claude 启动仍包含 `--settings <temporary-settings-path>`。
- [x] Codex 启动仍保留临时配置目录环境变量逻辑。

## Test results

- `python -m unittest tests.test_cc_provider_launch`：通过，9 tests。
- `python -m ruff check .`：通过。
- `uv run mypy`：通过，Success: no issues found in 1 source file。

## Risks / incomplete items

- `argparse.REMAINDER` 会捕获 provider number 后所有 token；launcher 自己的 `--db`、`--env-file`、`--cwd`、`--mode` 应放在 provider number 之前。

## Conclusion

实现符合轻量范围说明，可以交付。
