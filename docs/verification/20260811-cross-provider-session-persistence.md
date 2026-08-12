# 跨供应商 Codex 会话复用验证记录
最后修改时间: 2026-08-12 17:43:16

流程模式: strict

当前阶段: Verification / 验证

Review status: Accepted

## Requirement Alignment

| 需求点 | 当前结论 |
| --- | --- |
| `data/codex` 保持 `CODEX_HOME` | 通过；本次不改 home 选择。 |
| 仅共享 sessions 目录 | 通过；现有 `data/codex/sessions` 已是到 `~/.codex/sessions` 的 junction。 |
| ccs-plus A/B `/resume` 双向可见 | 通过；用户已确认新会话在同一 cwd 的 provider A/B 交互式列表中双向可见。 |
| provider 配置隔离 | 通过；profile 名称和配置内容仍按 provider 分别生成。 |
| 无迁移、阻断逻辑 | 通过；本次不加入任何旧数据处理。 |

## Spec Alignment

- `apps.codex.session_model_provider` 默认是 `ccs-plus-managed`；managed profile 的顶层
  `model_provider` 与 `model_providers` table key 同步使用该配置值。
- Codex 明确拒绝 custom profile 覆写 `[model_providers.openai]`：`openai` 是保留内置 provider ID。
- 仅有 `sessions` 指向真实用户会话目录；SQLite、profile 与其余 runtime state 留在 `data/codex`。
- 本次不修改、迁移或识别任何旧会话记录。

## Plan Alignment

| 计划项 | 结果 |
| --- | --- |
| 使用可配置的 custom profile identity | 已完成；`apps.codex.session_model_provider` 默认 `ccs-plus-managed`，可由环境变量覆盖。 |
| 保留 provider profile 隔离 | 已完成。 |
| 增加测试断言 | 已完成。 |
| 记录 `openai` 保留 ID 约束 | 已完成。 |
| 自动化和 A/B 交互式验证 | 已完成。 |

## Actual Diff Summary

- ccs-plus Codex provider 共享 `apps.codex.session_model_provider` 的 non-reserved `model_provider`，使 A/B
  `/resume` 使用同一筛选集合。
- 未改变 `CODEX_HOME=data/codex` 与其 `sessions` directory link 行为。
- 未加入迁移、目录存在性断言、复制或 SQLite 写入逻辑。

## Expected vs Actual Changed Files

| 预期文件 | 实际文件 | 结论 |
| --- | --- | --- |
| `src/ccs_plus/managed_config.py` | `src/ccs_plus/managed_config.py` | 通过。 |
| `tests/test_managed_config.py` | `tests/test_managed_config.py` | 通过。 |
| `README.md` | `README.md` | 通过。 |
| feature process docs | Requirement / Spec / Plan / Verification | 通过。 |

## Acceptance Criteria

- [x] custom Codex profile 使用配置中的 non-reserved `model_provider`。
- [x] provider profile 仍有独立名称和 endpoint/API Key 配置。
- [x] 没有变更整个 `~/.codex` 链接或 `CODEX_HOME`。
- [x] 没有引入遗留数据处理。
- [x] 自动化检查再次通过。
- [x] `deepseek.com` 的实际 managed profile 可由 Codex 解析。
- [x] 用户完成新会话的 A/B 交互式 `/resume` 双向烟测。

## Test Results

| 命令或检查 | 结果 |
| --- | --- |
| `openai` override 启动 | 失败，Codex 报 `model_providers contains reserved built-in provider IDs: openai`；已撤回该无效配置。 |
| `uv run pytest tests` | 通过，`87 passed in 0.85s`。 |
| `uv run ruff check .` | 通过，`All checks passed!`。 |
| `uv run ruff format --check .` | 通过，`75 files already formatted`。 |
| `uv run mypy src` | 通过，`Success: no issues found in 11 source files`。 |
| `deepseek.com` profile 解析 | 通过。由 `build_launch_spec()` 生成 profile 后执行 `codex --profile <name> --help` 返回 0，且没有保留 `openai` provider ID 错误。 |
| 交互式 `/resume` A/B 烟测 | 通过；用户确认同一 cwd 下新会话可在 provider A/B 之间双向出现在交互式列表并恢复。 |

## Scope Differences

无。直接 `codex` 与 custom provider 的 `/resume` identity 无法通过 `[model_providers]` 合并，已从验收条件
剔除；核心范围保留为 ccs-plus 的 provider A/B 切换。

## Risks

直接 `codex` 的内置 `openai` 线程不会显示在 ccs-plus custom `/resume` 过滤结果中，反之亦然。

## Conclusion

Codex 的保留 ID 约束排除了 direct/custom 三向合并；实现聚焦并满足 ccs-plus A/B 核心场景。自动化、实际
profile 解析和用户交互式验收均已通过。
