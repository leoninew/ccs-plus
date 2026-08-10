# ccl run 组合别名选择器验证

Review status: Accepted

Flow mode: light / 轻量模式

## What changed

- `run` 的 `provider` 位置参数改为可选。
- 当未单独传 `provider` 时，从 `app` 参数中尝试解析已注册 alias + 数字 provider，例如 `c2` -> `c` + `2`，`x1` -> `x` + `1`。
- 组合 alias 会解析为真实 CLI；分离 alias 写法不再走 alias 解析，交由现有 app/provider 获取逻辑处理。
- 保持真实 CLI 名称的 `ccl run <cli> <provider>` 形式不变。
- README 增加组合简写示例并移除分离 alias 示例。
- 增加单元测试覆盖解析、拆分和实际 run 流程。

## Acceptance

- [x] `run c2` 可解析为 alias `c` + provider `2`。
- [x] `run x1` 可解析为 alias `x` + provider `1`。
- [x] 旧 alias 分离形式 `run c 2` / `run x 1` 不再走 alias 解析。
- [x] 真实 CLI 分离形式 `run claude 2` / `run codex 1` 继续可用。
- [x] 组合形式后续 CLI 参数仍可通过 `argparse.REMAINDER` 保留。
- [x] 相关测试通过。

## Commands

```bash
python -m unittest tests.test_cc_switch
# OK: Ran 21 tests

uv run ruff check cc-switch.py tests/test_cc_switch.py && uv run mypy && python -m unittest tests.test_cc_switch
# OK: ruff passed, mypy passed, Ran 21 tests
```

尝试过项目 `Makefile` 入口：

```bash
make check
# 失败：当前环境没有 make 命令
```

已用 `Makefile` 中等价命令 `uv run ruff check ... && uv run mypy` 替代执行。

## Remaining risk

- 组合写法只支持数字 provider selector；provider name 仍使用旧形式。
- 如果未来 alias 本身以数字结尾，会存在解析歧义；当前默认 alias `c` / `x` / `m` 不受影响。
