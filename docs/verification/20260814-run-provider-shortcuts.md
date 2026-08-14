# Provider 快捷启动（run）验证
最后修改时间: 2026-08-14 11:04:32

Flow mode: light

Stage: Verification

Review status: Accepted

## Requirement alignment

实现与 [Requirement](../requirement/20260814-run-provider-shortcuts.md) 一致：列表根据现有 `ProviderRepository.list()` 顺序为每个应用单独编号，`run c1`、`run x1`、`run g1` 使用该编号选择 provider，并复用无覆盖参数的原生 CLI 启动路径。

## Spec alignment

不适用。light 模式未创建独立 Spec。

## Plan alignment

不适用。light 模式依据已接受的 Requirement 实现。

## Actual diff summary

- 新增 `ProviderListEntry`，集中产生应用前缀、组内编号和完整 `ccs-plus run <target>` shortcut。
- `providers list` 的最后一列展示 `Shortcut`；JSON 输出提供 `shortcut`，不再输出独立 `number` 或 `run` 字段。
- 新增 `run <target>` 命令，复用名称启动命令的 `build_launch_spec`、日志和退出码路径。
- 补充 CLI 帮助、快捷目标、大小写匹配、格式错误、越界编号和应用组内编号重置测试；更新 README。

## Expected vs actual files

| 预期文件 | 实际文件 | 状态 |
| --- | --- | --- |
| `src/ccs_plus/cli.py` | `src/ccs_plus/cli.py` | 一致 |
| `tests/test_cli.py` | `tests/test_cli.py` | 一致 |
| `README.md` | `README.md` | 一致 |
| `docs/requirement/20260814-run-provider-shortcuts.md` | `docs/requirement/20260814-run-provider-shortcuts.md` | 一致 |
| `docs/verification/20260814-run-provider-shortcuts.md` | 本文件 | 验证记录 |

## Acceptance checklist

- [x] Claude、Codex、Grok 的编号均从 1 开始，`run` 与列表使用同一排序。
- [x] 表格不显示独立 `No.` 或 `Run` 列，最后的 `Shortcut` 列展示完整命令；JSON 提供 `shortcut`。
- [x] `run c1`、`run x1`、`run g1` 的前缀均被解析，且 `run x2` 选择第二个 Codex provider。
- [x] 非法格式、零编号和越界编号被拒绝，且不会构建或启动原生 CLI。
- [x] README 与 CLI 测试已更新。

## Verification commands

- `git diff --cached --check`：通过。
- `uv run ruff check .`：通过。
- `uv run mypy src`：通过，14 个源文件无问题。
- `uv run pytest tests`：通过，125 项通过。
- `uv run ruff format --check src/ccs_plus/cli.py tests/test_cli.py`：通过。
- `uv run ruff format --check .`：未完全通过；仅 `tests/test_launcher.py` 存在本功能外的既有格式差异。

## Scope deviation

无。JSON 输出使用单一 `shortcut` 字段与最终的 `Shortcut` 列展示保持一致。

## Risks

- provider 的排序变化会改变编号指向；用户应依据当前列表显示的完整 `Shortcut` 执行。
- `tests/test_launcher.py` 的既有格式差异使全项目格式检查未完全通过，但本功能涉及的 Python 文件格式已通过检查。

## Incomplete items

本功能无未完成项。未处理不相关的 `tests/test_launcher.py` 格式差异，也未纳入未跟踪的其他 requirement 文档。

## Conclusion

本功能的需求、实际 diff 和测试结果一致，可交付。
