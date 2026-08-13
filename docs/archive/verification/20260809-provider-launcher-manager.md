# 供应商管理与 CLI 启动器验证记录
最后修改时间: 2026-08-11 10:00:00

流程模式: standard

当前阶段: Verification / 验证

Review status: Accepted

## Requirement Alignment

对照 [Requirement](../requirement/20260809-provider-launcher-manager.md)：

| 需求点 | 结论 |
| --- | --- |
| 语义化 `settings.yaml`（`database` / `encryption_key` / `apps`） | 通过；`load_settings()` 读取并通过本地校验 |
| `apps.codex` 默认 `approval_policy=never`、`sandbox_mode=danger-full-access` | 通过；默认文件与 settings 测试覆盖 |
| add/import 写入配置默认策略 | 通过；`build_provider(..., provider_defaults())` + CLI/adapter 测试 |
| launch 以供应商实际配置为准 | 通过；`RuntimeProvider` 提取策略，managed profile / argv 使用之 |
| managed profile 不混用旧 sandbox 键 | 通过；`default_permissions = ":<sandbox_mode>"`，无 `sandbox_mode` 写入 |
| 稳定 state home，无临时 CODEX_HOME | 通过；launcher 测试覆盖 |
| API Key 不进 argv/profile/日志 | 通过；launcher/managed config 测试覆盖 |

## Spec Alignment

不适用。本 feature 使用 standard / 标准模式。

## Plan Alignment

对照 [Plan](../plan/20260809-provider-launcher-manager.md)：

- 配置：`settings.yaml` + `environments=False` + 嵌套 `CCS_PLUS_*` 覆盖 — 已实现。
- adapter：Codex 策略来自 `CodexAppConfig`；仅 `workspace-write` 写 `sandbox_workspace_write` — 已实现。
- managed_config / launcher：策略来自供应商记录 — 已实现。
- 测试：settings / adapters / managed_config / launcher / cli — 已覆盖。

## Actual Diff Summary

相对 `develop` 上一次提交（`7d729df`），当前暂存差异 **26 文件，+583 / -213**：

- 配置：`settings.toml` → 语义化 `settings.yaml`；`.env.example` / README 更新。
- 核心：`settings.py`、`adapters.py`、`domain.py`、`managed_config.py`、`launcher.py`、`cli.py`。
- 依赖：`pyyaml` 进入 `pyproject.toml` / `uv.lock`。
- 测试：settings/adapters/launcher/managed_config/cli 等同步。
- 文档：requirement / plan / verification（20260809 与 20260810）同步。

## Expected vs Actual Changes

| 预期 | 实际 |
| --- | --- |
| 语义化 YAML 配置 | 已完成 |
| Codex 默认策略可配置且默认 full-access | 已完成 |
| add/import 使用配置默认 | 已完成 |
| launch 读供应商实际策略 | 已完成 |
| 过程文档对齐 | 已完成 |
| 实网 CLI 交互验收 | 未执行（人工项） |

## Acceptance Criteria

- [x] 配置加载：`database.path`、三类 home、`apps.codex` 策略、Fernet key 校验。
- [x] 新增 Codex 供应商写入 `approval_policy` / `sandbox_mode`（默认 never / danger-full-access）。
- [x] import 重建记录使用当前 `apps.codex` 默认，不回放旧 sandbox TOML。
- [x] launch managed profile：`approval_policy` + `default_permissions` 来自供应商；无旧 sandbox 键。
- [x] launch argv：`--ask-for-approval` 跟随供应商 `approval_policy`。
- [x] 单元/CLI 测试与 lint/typecheck 通过。
- [ ] 真实 Codex 交互界面不再出现 “Update Model Permissions”（需本机原生 CLI 人工确认）。
- [ ] 三种 CLI 跨供应商会话恢复可见（需实网人工验收）。

## Test Results

| 命令 | 结果 |
| --- | --- |
| `make check`（ruff format/check + mypy） | 通过 |
| `make test` / `uv run pytest tests` | 通过，`59 passed in 5.43s` |
| `git diff --cached --check` | 通过，无空白错误 |
| `uv run python -c "from ccs_plus.settings import load_settings; ..."` | 通过；本地加载得到 `never` / `danger-full-access` |

## Scope Differences

- 相对 2026-08-09 初版：默认策略从 `workspace-write` 改为配置驱动的 `danger-full-access`；配置载体改为语义化 YAML。
- 相对仅改 managed profile 硬编码 full-access 的提交：本次将默认源上收到 YAML，并让 launch 读供应商记录。
- 未包含协议转换、供应商编辑、会话迁移、删除 profile 文件等 non-goal。

## Risks

- 默认 `danger-full-access` 取消工作区文件边界，仅适用于可信目录。
- 数据库中既有 `workspace-write` 记录不会自动升级；launch 按其实际配置启动。
- 缺少 `approval_policy`/`sandbox_mode` 的旧记录会在 launch 时失败（有意失败，不静默回落硬编码）。

## Incomplete Items

1. 本机真实 Codex 启动的权限 UI 人工确认。
2. 三 CLI 跨供应商会话恢复人工验收。
3. 未对用户生产数据库执行 add/import（避免污染真实数据）。

## Conclusion

自动化验证通过，实现与已更新的 Requirement / Plan 对齐。用户于 2026-08-11 确认验证通过。剩余人工实网项不阻塞本轮交付，作为后续使用时的可选确认。

**Review status: Accepted。**
