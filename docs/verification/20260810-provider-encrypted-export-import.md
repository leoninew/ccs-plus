# 加密供应商导入导出验证记录

最后修改时间: 2026-08-10 16:01:14

Review status: Draft

Flow mode: standard / 标准模式

Current stage: Verification / 验证

## Requirement Alignment

实现保持 `providers add` 不变，并新增 `providers export [file]` 和 `providers import <file>`。导出 JSON 的 API Key 仅以 Fernet token 形式保存；导入会先解析、解密并校验所有记录与目标库名称冲突，再通过一次 `add_many()` 事务写入。

通用密钥为 `CCS_PLUS_ENCRYPTION_KEY`。`AppSettings` 初始化使用 `Fernet` 验证密钥格式，空值、示例值和非法 key 会立即抛出 `ProviderError`。`.env.example` 只含占位值；本地 `.env` 生成随机 key 并由 `.gitignore` 排除。

## Spec Alignment

不适用。本 feature 使用 standard / 标准模式，直接依据 Requirement 制定 Plan。

## Plan Alignment

- 已新增 `cryptography` 生产依赖并锁定到 `uv.lock`。
- 已新增 `provider_transfer.py`，使用版本化 JSON 与直接 Fernet 加解密。
- 已实现可选导出路径、时间戳默认文件名、独占创建、完整导入预校验和名称冲突拒绝。
- 已将 repository 新增路径归并到 `add_many()` 的单事务实现。
- 已删除旧 `scripts/provider_export.py` 和其测试，README 已改为 CLI 用法。

## Actual Diff Summary

- 配置：新增通用 `encryption_key` 设置与 `.env.example` 占位值；`AppSettings` 添加并校验该字段。
- 传输：新增 Fernet JSON 的序列化、反序列化与输入校验模块。
- 命令：新增 export/import，默认导出为项目 `data/providers-YYYYMMDD-HHMMSS.json`，目录不存在时创建。
- 命令：新增 reset，默认输出非官方 provider 预览；`--no-dry-run` 才以事务删除。
- 数据：供应商批量导入使用单个 SQLite 事务，避免半完成写入。
- 测试与文档：新增相关测试、README 用法和本阶段记录；移除独立脚本路径。

## Expected vs Actual Changes

| 预期变更 | 实际状态 |
| --- | --- |
| 保留 `providers add` 并新增 export/import | 已完成。 |
| API Key 使用 Fernet 加密 | 已完成；JSON 断言不含测试 API Key 明文。 |
| 通用密钥在初始化时验证 | 已完成；设置加载与测试覆盖。 |
| 默认 `data/` 时间戳导出文件 | 已完成；CLI 测试覆盖。 |
| reset dry-run 与显式删除 | 已完成；CLI 与 repository 测试覆盖。 |
| 导入前全量校验和原子写入 | 已完成；CLI 和 repository 测试覆盖。 |
| 移除旧脚本 | 已完成。 |

## Acceptance Criteria

- [x] export/import 均在 `providers` 组下，且 `-h`/`--help` 等价。
- [x] API Key 不以明文写入导出 JSON。
- [x] 配置 key 不存在、为占位值或非法时设置加载失败。
- [x] 正确 key 可完成 round-trip，错误 key 无法解密。
- [x] 默认文件名符合 `data/providers-YYYYMMDD-HHMMSS.json`，并在必要时创建目录。
- [x] reset 默认不写库，`--no-dry-run` 仅删除非官方供应商和关联 endpoint。
- [x] 导入在遇到无效 endpoint 时不调用写入；数据库后续冲突时整批回滚。
- [x] 旧独立导出脚本已删除。

## Test Results

| 命令 | 结果 |
| --- | --- |
| `uv run python -c "from ccs_plus.settings import load_settings; load_settings(); print('configuration-valid')"` | 通过，确认本地 `.env` 的密钥有效且未输出密钥。 |
| `make check` | 通过：Ruff format、Ruff lint、mypy 均无问题。 |
| `make test` | 通过：`53 passed in 5.33s`。 |
| `git diff --check` | 通过，无空白错误。 |

## Scope Differences

无。交互式备份口令方案已按最终需求替换为通用 `CCS_PLUS_ENCRYPTION_KEY`。

## Risks

- 持有同一 `CCS_PLUS_ENCRYPTION_KEY` 即可解密备份；应与备份文件分开保存和传输。
- 当前不支持密钥轮换；更换密钥前须先使用旧 key 解密并重新导出。

## Incomplete Items

- 未对真实用户数据库执行导入，避免验证阶段修改用户供应商数据；临时 SQLite fixture 已覆盖事务和校验行为。

## Conclusion

自动化验证通过，实际改动与 Requirement 和 Plan 一致。本文保持 `Draft`，等待用户确认验证记录结论。
