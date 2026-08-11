# 加密供应商导入导出计划

最后修改时间: 2026-08-11 09:36:07

Review status: Accepted

Flow mode: standard / 标准模式

## Requirement Basis

依据已接受的 [Requirement](../requirement/20260810-provider-encrypted-export-import.md)：新增加密 JSON 的供应商导入导出，保留现有新增命令，使用初始化即验证的通用 Fernet key，并移除独立命令导出脚本。

## Implementation Steps

1. 在 `pyproject.toml` 添加 `cryptography`，由 `uv.lock` 锁定；在 `.env.example`、语义化 `settings.yaml` 的 `encryption_key` 与 `AppSettings` 定义通用 `CCS_PLUS_ENCRYPTION_KEY`。
2. `load_settings()` 使用 `cryptography.fernet.Fernet` 校验密钥，拒绝空值、示例值和非法编码，使所有依赖设置的正常命令在初始化时失败。
3. 新建 `provider_transfer.py`：提取自定义供应商运行时 endpoint/API Key/model/effort，生成版本化 JSON；以 Fernet token 存储 API Key；解析时解密并构建、校验 `NewProvider`。
4. 在 `cli.py` 增加 `providers export [output_path]`、`providers import <input_path>`；路径省略时在项目 `data/` 生成时间戳文件并创建该目录，导出通过独占创建避免覆盖，导入在完整解析后检查名称冲突。
5. 导入写入路径调用 `build_provider(value, settings.codex.provider_defaults())`，与 `providers add` 共用 Codex 默认策略源。
6. 为 `ProviderRepository` 增加 `add_many()`，在一次 SQLite `BEGIN IMMEDIATE` 事务中插入所有 provider 及 endpoint；`add()` 复用该实现。
7. 删除 `scripts/provider_export.py` 及其独立测试，更新 README 命令和配置说明。
8. 新增 `providers reset [--no-dry-run]`；默认仅列出非官方目标，确认后调用 repository 的单事务清理方法。
9. 覆盖 Fernet round-trip、错误密钥、JSON 记录校验、CLI 默认文件名、导入前全量校验、批量写事务回滚、reset dry-run/执行路径和设置初始化校验。

## Files to Change

- `pyproject.toml`、`uv.lock`
- `.env.example`、`settings.yaml`、`README.md`
- `src/ccs_plus/settings.py`、`src/ccs_plus/provider_transfer.py`、`src/ccs_plus/cli.py`、`src/ccs_plus/database.py`、`src/ccs_plus/adapters.py`
- `tests/conftest.py`、`tests/test_settings.py`、`tests/test_provider_transfer.py`、`tests/test_cli.py`、`tests/test_database.py`
- 删除 `scripts/provider_export.py`、`tests/test_provider_export.py`

## Verification Plan

| 层级 | 验证 |
| --- | --- |
| 设置 | 有效 Fernet key 可加载；示例 key 被拒绝；本地 `.env` 不提交。 |
| 编解码 | 导出 JSON 不含 API Key 明文；同 key 可还原，错误 key 被拒绝。 |
| CLI | `export` 的默认文件名、显式路径、`import` 成功和导入前失败均覆盖；help 短长参数等价。 |
| 数据库 | `add_many` 在后续记录冲突时回滚所有前序插入。 |
| reset | 默认不调用删除；`--no-dry-run` 仅删除非官方 provider，并验证 endpoint 外键级联。 |
| 项目 | 运行 `make check`、`make test`、`git diff --check` 与本地 `load_settings()`。 |

## Assumptions and Risks

- 导入目标使用与导出时相同的通用加密密钥；项目不实现密钥轮换或旧 key fallback。
- 不对真实用户数据库运行导入测试，避免在验证过程中写入实际供应商数据；测试使用临时 SQLite fixture。

## Rollback

- 删除新增 export/import 代码和 `cryptography` 依赖即可恢复到无该功能的版本；不会改写现有供应商数据。
- 已创建的导出 JSON 可删除；其内容只能由拥有 `CCS_PLUS_ENCRYPTION_KEY` 的环境解密。
