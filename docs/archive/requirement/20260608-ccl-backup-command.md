# cc-switch.py backup 子命令范围说明

Review status: Accepted

## Goal

- 为 `cc-switch.py` 增加 `backup` 子命令。
- 从 `.env` 读取备份目录，建议变量名为 `CC_SWITCH_BACKUP_DIR`。
- 将当前 `cc-switch.db` 复制到备份目录。
- 将 `list` 展示的供应商关键配置整理为结构化 Markdown 文件并写入同一备份目录。

## Non-goal

- 不改变 `list`、`alias`、`run` 现有行为。
- 不改变 cc-switch 数据库 schema。
- 不实现压缩包、增量备份、远程上传或定时备份。
- 不备份除数据库副本和 provider Markdown 摘要以外的文件。

## Acceptance

- `cc-switch.py backup` 支持 `--db` 和 `--env-file`。
- `.env` 缺少备份目录配置时给出清晰错误。
- 备份目录不存在时自动创建。
- 成功后备份目录包含固定文件名 `cc-switch.db`，允许覆盖旧副本。
- 成功后备份目录包含固定文件名 `providers.md`。
- `providers.md` 覆盖 `list` 可展示供应商的关键配置：编号、id、app_type、name、sort_index、settings_config/meta 摘要。
- 明显敏感字段（如 token、api_key、secret、password、authorization）必须脱敏。

## Risk

- “关键配置”需要避免泄露完整密钥，Markdown 生成需复用或扩展现有脱敏逻辑。
- 固定文件名覆盖旧备份，适合简单备份；不保留历史版本。
