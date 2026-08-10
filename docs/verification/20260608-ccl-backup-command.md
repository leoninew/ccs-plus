# cc-switch.py backup 子命令验证

Review status: Accepted

## What changed

- `cc-switch.py` 新增 `backup` 子命令。
- `backup` 读取 `CC_SWITCH_BACKUP_DIR`，自动创建目录。
- 复制数据库到备份目录的 `cc-switch.db`。
- 导出所有 provider 的结构化摘要到 `providers.md`。
- `settings_config` 和 `meta` 中明显敏感字段会递归脱敏。

## Acceptance

- [x] `backup` 支持 `--db` 和 `--env-file`。
- [x] 缺少 `CC_SWITCH_BACKUP_DIR` 时通过 `LaunchError` 给出清晰错误。
- [x] 备份目录不存在时自动创建。
- [x] 成功后生成固定文件名 `cc-switch.db`。
- [x] 成功后生成固定文件名 `providers.md`。
- [x] `providers.md` 包含 provider 编号、id、app_type、name、sort_index、settings_config、meta。
- [x] token、api_key、secret、password、authorization 等字段脱敏。

## Commands

- `D:/SourceCodes/agentic/cc-switch/.venv/Scripts/python.exe -m ruff check D:/SourceCodes/agentic/cc-switch/cc-switch.py`
- `D:/SourceCodes/agentic/cc-switch/.venv/Scripts/python.exe -m mypy D:/SourceCodes/agentic/cc-switch/cc-switch.py`
- 使用临时 SQLite DB 和临时 `.env` 运行 `cc-switch.py backup` smoke test，确认：
  - 命令返回 0。
  - 备份目录生成 `cc-switch.db`。
  - 备份目录生成 `providers.md`。
  - provider 名称存在。
  - 原始 token/password 不存在。
  - token 以尾号保留形式脱敏。

## Remaining risk

- 当前使用固定文件名覆盖旧备份，不保留历史版本，符合轻量范围说明。
