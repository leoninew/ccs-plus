# ccl run provider selector Verification

## What changed

- `run` 的第二个位置参数从 `provider_number` 改为通用 `provider` 字符串。
- 新增 provider selector：纯数字按 `list` 编号选择，非数字按当前 app family 下的供应商名称精确匹配。
- 名称无命中或多命中时抛出 `LaunchError`，避免启动错误 provider。
- 补充单元测试覆盖数字编号、唯一名称和重复名称。

## Acceptance

- [x] `ccl run <app> 1` 继续按编号启动。
- [x] `ccl run <app> <provider-name>` 可按唯一供应商名称启动。
- [x] 名称没有命中或命中多个 provider 时给出错误，不启动 CLI。
- [x] 额外 CLI 参数透传行为保持不变。

## Commands

- `python -m unittest tests.test_cc_switch`：通过，16 tests OK。
- `python -m ruff check cc-switch.py tests/test_cc_switch.py`：通过。
- `python -m mypy`：未运行，当前系统 Python 未安装 mypy。
- `uv run mypy`：通过，Success: no issues found in 1 source file。

## Remaining risk

供应商名称匹配为精确匹配；如果用户希望大小写不敏感或别名匹配，需要另行定义规则。
