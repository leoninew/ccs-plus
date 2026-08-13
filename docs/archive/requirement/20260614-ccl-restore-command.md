# ccl restore 子命令需求

Review status: Accepted

Flow mode: light / 轻量模式

## Goal

新增 `restore` 子命令，对等于现有 `backup` 的数据库复制方向：

- `backup` 将默认数据库路径 `~/.cc-switch/cc-switch.db` 复制到 `CC_SWITCH_BACKUP_DIR/cc-switch.db`。
- `restore` 将 `CC_SWITCH_BACKUP_DIR/cc-switch.db` 复制回默认数据库路径 `~/.cc-switch/cc-switch.db`。

## Non-goal

- 所有子命令都不暴露 `--db` / `--env-file` CLI 参数；默认数据库路径和默认 `.env` 是约定配置。
- 不恢复 `providers.md`，只恢复数据库文件 `cc-switch.db`。

## Acceptance

- 所有子命令都不接受 `--db` / `--env-file`。
- `ccl backup` / `ccl restore` 可从默认 `.env` 读取 `CC_SWITCH_BACKUP_DIR`。
- `ccl restore` 可将备份目录下的 `cc-switch.db` 复制回 `~/.cc-switch/cc-switch.db`。
- 目标目录不存在时自动创建。
- 备份数据库不存在时给出清晰错误。
- README 包含 `restore` 的约定用法。
- 相关测试通过。

## Risk

- `restore` 会覆盖目标数据库文件；这是命令的预期行为。
