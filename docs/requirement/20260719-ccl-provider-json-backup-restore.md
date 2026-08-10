# ccs 供应商表 JSON 备份与还原

最后修改时间: 2026-07-19 03:38:13

Review status: Accepted

Flow mode: light / 轻量模式

## Background

现有 `ccs backup` / `ccs restore` 整库复制 `cc-switch.db` 并额外写脱敏 `providers.md`。备份体量大、还原会覆盖非供应商数据（请求日志、MCP、skills 等），与 launcher 只关心供应商配置的职责不符。

## Goal

- 重写 `backup` / `restore`：仅操作供应商相关表。
- 备份：相关表整表导出为单一 JSON 文件。
- 还原：按备份 JSON 覆盖目标库中对应表数据。
- 彻底移除整库 `cc-switch.db` 复制与 `providers.md` 导出，不做旧格式兼容。

## Non-goal

- 不备份/还原 `proxy_request_logs`、`usage_daily_rollups`、`stream_check_logs`、`mcp_*`、`skills*`、`prompts`、`settings`、`model_pricing`、`session_log_sync`、`proxy_live_backup`。
- 不实现增量备份、多版本历史、压缩包、远程上传、交互确认或 `--force`。
- 不兼容旧产物 `cc-switch.db` / `providers.md` 作为 restore 输入。
- 不改变 `list` / `alias` / `run` 行为。

## User scenarios

1. 用户配置 `CC_SWITCH_BACKUP_DIR` 后执行 `ccs backup`，备份目录生成 `backup-<YYYYMMDD-HHMMSS>.zip`（内含 `providers.json`），为供应商相关表全量行数据（含密钥明文）。
2. 用户执行 `ccs restore backup-<timestamp>.zip`，在 `CC_SWITCH_BACKUP_DIR` 下查找该文件并覆盖目标库供应商相关表；其他表不动。
3. 缺少备份目录配置、源库不存在、JSON 缺失/格式非法时给出清晰错误。

## Acceptance

- 备份/还原表集合固定为：`providers`、`provider_endpoints`、`provider_health`、`proxy_config`。
- 备份产物文件名：`CC_SWITCH_BACKUP_DIR/backup-<YYYYMMDD-HHMMSS>.zip`（内含 `providers.json`；每次新建，不覆盖历史备份）。
- JSON 含 `format`、`version`、`exported_at`、`source_db`、`tables`；`format` 为 `cc-switch-provider-backup`，当前 `version` 为 `1`。
- 表数据为整表 `SELECT *` 行对象列表；字段原样序列化（含 token）。
- 还原在事务中按 FK 安全顺序：先删子表再删父表，再按父→子插入；`provider_endpoints.id` 尽量保留。
- 还原只覆盖上述四表，不触碰其他表。
- 删除整库 copy 与 `providers.md` 相关逻辑；无旧路径 fallback。
- 缺少 `CC_SWITCH_BACKUP_DIR`、备份 JSON 不存在、format/version 不匹配、目标库/表不可用时 `LaunchError`。
- 单元测试覆盖 backup round-trip 与 restore 缺文件错误。
- `docs/README.md` 同步新约定。

## Open questions

不适用（沿用评估默认：四表 + 直接覆盖 + 保留 endpoint id）。

## Decisions

- 表集合：`providers` + `provider_endpoints` + `provider_health` + `proxy_config`。
- 产物为时间戳 zip：`backup-<YYYYMMDD-HHMMSS>.zip`（内含 `providers.json`）；`restore` 必填 archive 参数；移除 `cc-switch.db` 与 `providers.md`。
- 还原语义：四表全量替换，非逐行 upsert。
- 不做旧备份兼容。

## Risk

- JSON 含明文密钥；备份目录勿提交版本库。
- 还原会改写 `is_current` / failover / `proxy_enabled`；cc-switch 运行中可能状态不一致，建议停代理后再 restore。
- 日志表可能残留已删除 provider 的历史引用（可接受）。
