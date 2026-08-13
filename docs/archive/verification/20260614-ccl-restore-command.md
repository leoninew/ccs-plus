# ccl restore 子命令验证

Review status: Accepted

Flow mode: light / 轻量模式

## What changed

- 新增 `restore` 子命令。
- `backup` / `restore` 从默认 `.env` 读取 `CC_SWITCH_BACKUP_DIR`。
- `backup` 将默认数据库路径 `~/.cc-switch/cc-switch.db` 复制到 `CC_SWITCH_BACKUP_DIR/cc-switch.db`。
- `restore` 从 `CC_SWITCH_BACKUP_DIR/cc-switch.db` 复制回默认数据库路径 `~/.cc-switch/cc-switch.db`。
- 所有子命令都不暴露 `--db` / `--env-file` 参数。
- README 增加 `backup` / `restore` 用法说明。
- 增加 `restore_files` 单元测试，覆盖恢复复制和备份数据库缺失错误。

## Acceptance

- [x] `ccl backup` / `ccl restore` 使用默认 `.env` 和默认数据库路径。
- [x] 所有子命令 help 都不显示 `--db` / `--env-file`。
- [x] 可将备份目录下的 `cc-switch.db` 复制回目标数据库路径。
- [x] 目标目录不存在时自动创建。
- [x] 备份数据库不存在时给出清晰错误。
- [x] README 包含 `restore` 约定用法。
- [x] 相关检查通过。

## Commands

```bash
python cc-switch.py list --help && python cc-switch.py alias --help && python cc-switch.py backup --help && python cc-switch.py restore --help && python cc-switch.py run --help
# OK: all subcommand help output omits --db and --env-file

uv run ruff check cc-switch.py tests/test_cc_switch.py && uv run mypy && python -m unittest tests.test_cc_switch
# OK: ruff passed, mypy passed, Ran 23 tests
```

## Remaining risk

- `restore` 会覆盖默认数据库文件；这是命令预期行为。
