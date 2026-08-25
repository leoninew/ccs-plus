# 跨供应商 Codex 会话复用计划
最后修改时间: 2026-08-12 17:34:51

流程模式: strict

当前阶段: Plan / 计划

Review status: Accepted

## Implementation Steps

1. 在 `apps.codex.session_model_provider` 配置一个稳定的非保留 custom `model_provider`，作为所有 managed Codex profile 的 thread identity。
2. 保留 provider profile 的独立命名及其 endpoint、模型、权限和 API Key 环境变量写入方式。
3. 增强配置测试，明确断言 A/B profile 使用相同 custom identity，且 profile 本身仍独立。
4. 修正文档，记录仅 sessions link 共享、`openai` 保留 ID 不能覆写，以及 direct Codex 不属于验收范围。
5. 运行自动化检查；用户按 provider A/B 的交互式 `/resume` 场景人工验收。

## Files To Change

| File | Intended change |
| --- | --- |
| `settings.yaml` / `src/ccs_plus/settings.py` | 声明、读取和校验 session model provider。 |
| `src/ccs_plus/managed_config.py` | 使用配置中的 custom thread identity。 |
| `tests/test_managed_config.py` | 覆盖 profile identity 与隔离边界。 |
| `README.md` | 对齐单 sessions link 设计与 direct Codex 边界。 |
| process docs | 对齐实际架构、边界和验收方式。 |

## Verification Plan

- `uv run pytest tests`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`
- `git diff --cached --check`
- 人工：在同一 cwd 新建会话后，使用另一个 ccs-plus provider 打开交互式 `/resume`。

## Assumptions

Codex 对同一 non-reserved `model_provider` identity 的 thread 进行同一列表筛选；本机此前使用 `ccs-plus-managed` 的 A/B 测试已支持此假设。

## Risks

直接 `codex` 的内置 `openai` identity 保持独立，不进入本次 A/B 验收。

## Rollback

无新的行为分支；恢复原先每 profile identity 会重新造成 A/B 列表分裂，因此不作为建议操作。

## User Review Notes

- 2026-08-12：用户要求遗留数据如需处理只能离线处理，业务逻辑只解决新的正常启动路径。
- 2026-08-12：Codex 明确拒绝覆写保留 `openai` provider，因此验收聚焦 ccs-plus provider A/B。
