# ccs 供应商表 JSON/zip 备份与还原 验证

最后修改时间: 2026-07-19 10:51:28

Review status: Accepted

Flow mode: light / 轻量模式

## Requirement alignment

对照 `docs/requirement/20260719-ccl-provider-json-backup-restore.md`（含实现过程中补充的 zip 时间戳与 `restore <archive>` 约定）：

- 仅操作四表：`providers` / `provider_endpoints` / `provider_health` / `proxy_config` — 已实现。
- 备份产物：`CC_SWITCH_BACKUP_DIR/backup-<YYYYMMDD-HHMMSS>.zip`，内含 `providers.json` — 已实现。
- JSON schema：`format` / `version` / `exported_at` / `source_db` / `tables` — 已实现。
- 还原事务：子表先删、父表后插，保留 `provider_endpoints.id` — 已实现。
- 不触碰日志等其他表 — 单元测试与副本库 smoke 均确认。
- 移除整库 copy / `providers.md` / 旧路径 fallback — 已实现。
- 错误路径：缺 `CC_SWITCH_BACKUP_DIR`、缺 zip、非法文件名、format/version 校验 — 已覆盖或具备 `LaunchError`。
- `docs/README.md` 已同步。

说明：requirement 顶部 Goal/Non-goal 仍残留早期“单 JSON / 不实现压缩包”表述，后续 User scenarios / Acceptance / Decisions 已更新为 zip 时间戳方案；**实现与最终 Acceptance/Decisions 一致**。建议后续整理 requirement 文首措辞（非阻塞）。

## Spec alignment

不适用（light / 轻量模式无独立 spec）。

## Plan alignment

不适用（light / 轻量模式无独立 plan；按 requirement 实现）。

## Actual diff summary

暂存区变更（当前分支 `develop`）：

- `src/cc_switch/cli.py`：重写 backup/restore 为供应商表 zip 导出/导入；删除整库复制与 markdown 摘要逻辑。
- `tests/test_cc_switch.py`：round-trip、缺文件、非法 archive 名测试。
- `docs/README.md`：备份/还原约定更新。
- `docs/requirement/20260719-ccl-provider-json-backup-restore.md`：需求记录。

## Expected vs actual changed files

| 预期范围 | 实际 |
|---|---|
| `src/cc_switch/cli.py` | 是 |
| `tests/test_cc_switch.py` | 是 |
| `docs/README.md` | 是 |
| `docs/requirement/20260719-...md` | 是 |
| 其他业务模块 | 无 |

未发现超出供应商备份/还原范围的功能改动。diff 行数偏大，主要因 `cli.py`/测试文件整段替换与格式化，而非无关功能混入。

## Acceptance checklist

- [x] 四表固定集合导出/覆盖还原
- [x] 产物 `backup-<YYYYMMDD-HHMMSS>.zip`（内含 `providers.json`）
- [x] JSON 含 format/version/exported_at/source_db/tables
- [x] 字段原样序列化（含密钥明文）
- [x] 事务删除/插入顺序与 endpoint id 保留
- [x] 其他表不被 restore 修改
- [x] 无整库 copy / providers.md / 旧格式 fallback
- [x] 缺配置/缺文件/非法名等 `LaunchError`
- [x] 单元测试覆盖 round-trip 与缺文件；补充非法 archive 名
- [x] README 同步
- [x] `restore` 必填 archive，并在 `CC_SWITCH_BACKUP_DIR` 下按 basename 查找

## Test / command results

项目约定命令（Python + uv + Makefile/pytest/ruff/mypy）：

`	ext
uv run ruff check src tests
# All checks passed!

uv run ruff format --check src tests
# 3 files already formatted

uv run mypy src
# Success: no issues found in 2 source files

uv run pytest tests/test_cc_switch.py -q
# 40 passed, 3 subtests passed
`

副本库 smoke（`C:\Users\leon\Downloads\temp\cc-switch.db`）：

`	ext
LIVE_SMOKE_PASS backup-20260719-035100.zip providers 16 logs 52275
`

覆盖：backup 生成时间戳 zip → 篡改 providers/endpoints → restore 指定 archive 名 → 供应商数据恢复且 `proxy_request_logs` 行数不变。

## Missed or expanded scope

- 相对最初 Goal 文案：交付形态从“单 JSON”演进为“时间戳 zip + restore 参数”，属用户在实现过程中明确追加的需求，已写入 requirement 后半与 README。
- Non-goal 中“不实现压缩包”与最终 zip 决策冲突；以 Decisions/Acceptance 为准，建议清理 requirement 文首。
- 未实现多版本清理策略、交互确认、`--force`（符合 non-goal）。

## Risks

- 备份 zip 含明文密钥，需保护 `CC_SWITCH_BACKUP_DIR`。
- restore 会改写 current provider / proxy 配置；cc-switch 代理运行中可能导致状态不一致。
- 日志表可能残留已删除 provider 的历史引用（可接受）。
- 同一秒内两次 backup 可能生成同名 zip 并互相覆盖（时间戳精度到秒）。

## Incomplete items

- requirement 文首 Goal/Non-goal 与最终 Decisions 措辞未统一（文档整理项，不阻塞交付）。

## Conclusion

验证通过。实现满足最终验收标准与用户追加的 zip/时间戳/restore 参数约定；自动化检查与副本库 smoke 均通过，可交付。