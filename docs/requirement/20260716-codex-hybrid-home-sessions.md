# Codex 混合 Home：共享会话状态
最后修改时间: 2026-07-16 08:55:00

Review status: Accepted

## Mode

light / 轻量

## Background

`ccs run` 为 Codex 创建临时 `CODEX_HOME`，只写入 `auth.json` 与 `config.toml`，避免污染全局 `~/.codex`。临时目录退出后删除。整目录隔离导致看不到真实 Home 中的历史会话、history、skills 等。Claude 可通过 `--settings` 注入配置且不换 Home；Codex 无对等开关。用户要求在保持现有用法（不增加 `--codex-home` 等新参数）的前提下，采用混合 Home：临时目录继续承载认证与配置，真实用户 Home 的其余状态通过链接共享。

## Goal

- Codex direct / proxy 启动时，临时 `CODEX_HOME` 仍只写入隔离的 `auth.json` 与 `config.toml`。
- 将真实 Codex 用户 Home（默认 `~/.codex`）中除 `auth.json` / `config.toml` 外的已有条目链接进临时 Home，使会话、history、skills 等对子进程可见，且写入回落到真实 Home。
- 进程结束后拆除链接并删除临时目录；不得删除或改写真实 Home 中被链接目标的内容。
- 保持现有 CLI 用法与 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV` 契约，不新增用户可见的 Home 模式开关。

## Non-goal

- 不增加 `--codex-home` / `--mode isolated|shared` 等新 CLI 参数。
- 不使用 `codex --profile` 作为 provider 选择机制。
- 不把临时 `auth.json` / `config.toml` 写回真实 `~/.codex`。
- 不修改 cc-switch 数据库、provider 数据或 proxy 路由语义。
- 不保证跨盘符/无权限环境下每个文件都能成功链接；可跳过无法链接的文件，目录链接失败应明确报错。

## User scenarios

- 用户已有 `~/.codex/sessions` 与历史会话，执行 `ccs run codex 1` 或 `ccs run x2` 后，Codex 能看到既有会话并可 resume。
- 用户在本次 `ccs run` 中产生的新会话写入真实 Home 的 `sessions`（经目录链接），临时目录清理后会话仍在。
- 真实 Home 不存在时，行为退化为仅临时 Home（与改前隔离行为一致）。
- 清理临时目录或拆除链接后，真实 Home 中的 sessions/history 内容保持不变。

## Acceptance

- `run` Codex 时子进程 `CODEX_HOME` 仍指向临时目录，且该目录含启动器生成的 `auth.json` / `config.toml`。
- 真实 Home 中已存在且名称不是 `auth.json` / `config.toml` 的目录通过 junction（Windows）或 symlink（POSIX）出现在临时 Home；文件优先 hardlink，失败则 symlink，再失败可跳过。
- 不链接、不覆盖真实 Home 的 `auth.json` / `config.toml`。
- 启动结束（成功或失败）后拆除共享链接；临时目录删除不得删除真实 Home 被链接目标内容。
- 无新 CLI 开关；现有 env 选择器与 fail-closed 行为保持。
- 单元测试覆盖：共享链接创建、私有文件不共享、拆除后真实内容仍在；现有 Codex 启动测试仍通过。
- `docs/README.md` 说明混合 Home 行为与清理安全性。

## Open questions

暂无需要用户确认的未决事项。

## Decisions

- 流程模式：light / 轻量（范围明确，沿用现有 run 路径小改）。
- 共享范围：真实 Home 下除 `auth.json`、`config.toml` 外的条目；私有名单固定。
- 真实用户 Home 来源：`DEFAULT_CODEX_USER_HOME`（`~/.codex`），可测试注入；不读取父进程已指向临时目录的 `CODEX_HOME` 作为共享源。
- Windows 目录使用 `mklink /J` junction；文件 hardlink → symlink → 跳过。
- 不引入用户可见模式开关；混合共享为默认行为。

## Risk

- 部分杀毒/策略环境可能禁止 junction/symlink；目录失败会阻断启动，文件失败仅跳过可能导致 history 不可见。
- 若将来 Codex 将关键状态写入新的私有文件名，可能被错误共享；当前私有名单仅 auth/config。
- 并发多个 `ccs run codex` 共享同一真实 sessions 目录，与直接使用真实 Codex 多开风险同类，可接受。
