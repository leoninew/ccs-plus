# 跨供应商 Codex 会话复用规格
最后修改时间: 2026-08-12 17:34:51

流程模式: strict

当前阶段: Spec / 规格

Review status: Accepted

## Requirement Basis

共享目标是 ccs-plus 同一 app、同一 cwd 下的交互式 `/resume` 列表。不能以 `sessions` 文件目录是否共享作为唯一判断， 因为 Codex 的 thread SQLite 索引按 `model_provider` 过滤。

## Overview

```text
ccs-plus provider A profile - model_provider=ccs-plus-managed --+
ccs-plus provider B profile - model_provider=ccs-plus-managed --+--> data/codex/state_5.sqlite

data/codex/sessions -----------------------------------------------> ~/.codex/sessions
```

`CODEX_HOME` 始终为 `data/codex`。启动时仅在 `data/codex/sessions` 缺失时创建到 `~/.codex/sessions` 的 directory junction/symlink。每个 provider 仍生成独立命名的 profile 文件， 但 profile 内的 `model_provider` 和 `[model_providers.<key>]` 使用 `apps.codex.session_model_provider`；默认值是 `ccs-plus-managed`。各 profile 中该 table 的 endpoint、模型、 权限和 API Key env key 仍与该 provider 对应。

## Design Decisions

1. `apps.codex.session_model_provider` 是所有 ccs-plus custom profile 的 `/resume` thread identity；默认 配置为 `ccs-plus-managed`，可由 YAML 或 `CCS_PLUS_APPS__CODEX__SESSION_MODEL_PROVIDER` 覆盖。
2. `openai` 是 Codex 内置保留 provider ID，custom profile 不能在 `[model_providers.openai]` 覆写它；尝试 这样做会导致 `Error loading config.toml`，所以不用于共享 identity。
3. profile 名称不是 thread identity；它只选择本次启动应使用的 endpoint、模型、权限与 API Key。
4. 不设置 `CODEX_SQLITE_HOME`。SQLite 保持在项目 `data/codex`，不与整个用户 home 共享。
5. 不识别或处理已存在的非链接 `data/codex/sessions`，也不迁移旧 SQLite 记录。

## Affected Components

| Component | Change |
| --- | --- |
| `src/ccs_plus/settings.py` | 读取并校验 session model provider 配置。 |
| `src/ccs_plus/managed_config.py` | 从配置写入 managed Codex profile 的 custom thread identity。 |
| `tests/test_managed_config.py` | 断言 A/B profile 使用同一配置 identity。 |
| `README.md` | 说明 sessions link、SQLite 位置和 direct Codex 的保留 ID 边界。 |
| process docs | 对齐“仅 sessions link + custom thread identity”的设计。 |

## Interfaces

```python
profile.name != other_profile.name
profile_document["model_provider"] == settings.codex.session_model_provider
list(profile_document["model_providers"]) == [settings.codex.session_model_provider]
```

## Risks

- 直接 `codex` 的 `openai` 线程与 ccs-plus custom threads 属于不同 `/resume` 筛选集合，不能通过 custom profile 配置统一。
- 直接 `codex` 与 ccs-plus 同时写同一 `data/codex` SQLite 的风险等同于同时运行使用相同 `CODEX_HOME` 的原生 Codex。

## Alternatives

- 将整个 `~/.codex` 设为 `CODEX_HOME`：拒绝，会混入不属于 provider runtime 的完整用户状态，偏离隔离要求。
- 仅共享 sessions：拒绝，已证实 `/resume` 还会按 SQLite `model_provider` 筛选。
- 覆写 `[model_providers.openai]`：拒绝，Codex 将其视为保留内置 ID 并拒绝加载。
- 运行时迁移或修改旧 SQLite：拒绝，偏离核心目标且引入遗留数据处理。

## User Review Notes

- 2026-08-12：用户删除 `data/codex/sessions` 后重测仍复现，确认必须修复新会话 identity 而不是处理旧目录。
