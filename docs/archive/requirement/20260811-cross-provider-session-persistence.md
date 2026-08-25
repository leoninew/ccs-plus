# 跨供应商 Codex 会话复用
最后修改时间: 2026-08-12 17:34:51

流程模式: strict

当前阶段: Requirement / 需求

Review status: Accepted

## Background

用户不切换工作目录，在不同终端依次通过 `ccs-plus launch codex --provider A`、 `ccs-plus launch codex --provider B` 使用同一个应用。会话进入后调用交互式 `/resume`，而不是显式 `resume <id>` 命令，必须能看到相同工作目录的历史会话。

`data/codex/sessions` 已删除后重新测试，ccs-plus 创建的会话 rollout 已正确写入 `~/.codex/sessions`，且 `data/codex/sessions` 是指向该目录的 junction。问题不在旧目录遗留： Codex 的 `/resume` 还从 SQLite 按 `model_provider` 筛选。若 provider profile 各自使用不同 identity， 同一 rollout 会在另一个供应商的列表中被隐藏。

## Goal

1. 同一工作目录中，Codex provider A 和 provider B 创建的新会话互相出现在交互式 `/resume` 列表中。
2. `CODEX_HOME` 继续使用项目的 `data/codex`，仅将其 `sessions` 定向链接到 `~/.codex/sessions`。
3. provider 的 endpoint、API Key、模型和权限配置继续由各自命名的 managed profile 隔离。

## Non-goal

- 不把整个 `~/.codex` 链接到 `data/codex`，也不让 ccs-plus 直接以 `~/.codex` 作为 `CODEX_HOME`。
- 不在启动业务逻辑中检测、迁移、复制、合并或阻断旧 `data/codex/sessions`、SQLite/WAL 或历史会话。
- 不让直接 `codex` 的内置 `openai` provider 列表与 ccs-plus custom provider 列表合并；`openai` 是 Codex 保留 provider ID，不能在 `[model_providers]` 覆写。

## User Scenarios

1. 用户经 provider A 建立新会话，退出后经 provider B 进入交互式 `/resume`，能看到并恢复该会话。
2. 用户经 provider B 建立新会话，退出后经 provider A 进入交互式 `/resume`，能看到并恢复该会话。

## Acceptance

1. Codex custom profile 的 `model_provider` 与 provider table key 都为 `apps.codex.session_model_provider` 配置的稳定非保留 custom ID。
2. provider A/B 的 profile 文件名、endpoint 与 API Key 环境变量仍各自独立。
3. `CODEX_HOME=data/codex`，不设置 `CODEX_SQLITE_HOME`；`data/codex/sessions` 不存在时才创建指向 `~/.codex/sessions` 的 directory link。
4. 没有迁移、目录阻断或旧数据处理代码。
5. 新建会话后，交互式 `/resume` 的 ccs-plus A/B 双向人工烟测通过。

## Open Questions

暂无需要用户确认的未决事项。直接 `codex` 使用内置 `openai` identity 与 custom provider 不能合并是已确认的 Codex 约束。

## Decisions

- ccs-plus providers 共享 `apps.codex.session_model_provider` 指定的 custom thread identity，而不是覆写 保留的 `openai` provider；默认配置为 `ccs-plus-managed`。
- 会话 rollout 通过单独的 `sessions` junction 与真实 `~/.codex/sessions` 共享；SQLite 和 managed profile 保持在 `data/codex`。

## Risk

原生直接 `codex` 的 `/resume` 默认筛选与 ccs-plus custom provider 的 `/resume` 筛选不同；本次仅保证 ccs-plus 内部 A/B 切换的核心场景。

## User Review Notes

- 2026-08-12：用户明确核心目标是同一应用切换供应商后交互式 `/resume` 会话可复用，且不切换目录。
- 2026-08-12：用户明确不能把整个 `~/.codex` 链接或作为工作 home；遗留数据能离线处理才处理，但不得写入业务逻辑。
- 2026-08-12：实测 Codex 拒绝 custom profile 覆写保留 `openai` ID，范围收敛为 ccs-plus provider A/B。
