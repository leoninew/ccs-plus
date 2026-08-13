# Grok 混合 Home：共享会话状态

最后修改时间: 2026-07-20 21:37:50

Review status: Accepted

Flow mode: light / 轻量模式

## Background

`ccs run gN` / `ccs run grok <selector>` 为 Grok 创建临时 `GROK_HOME`，只写入 provider 翻译后的 `config.toml` 与空 `auth.json`，并注入 `GROK_HOME` + `XAI_API_KEY`，避免污染全局 `~/.grok`。

临时目录在进程结束后删除。Grok 会话落在 `$GROK_HOME/sessions/`（见 Grok 用户文档），整目录隔离导致：

1. 本次会话写入临时 home，退出后被删，无法 resume。
2. 真实 `~/.grok/sessions` 中的历史会话对子进程不可见。

Claude 可通过 `--settings` 只注入配置、不换 home；Grok **没有**对等单文件配置开关，只能用 `GROK_HOME` 覆盖整个 home。Codex 已采用混合 Home：临时目录承载 `auth.json`/`config.toml`，真实 home 其余状态通过链接共享。Grok 应对齐同一思路。

前置：`docs/requirement/20260720-ccs-run-grok.md`（Grok 启动路径）、`docs/requirement/20260716-codex-hybrid-home-sessions.md`（Codex hybrid 先例）。

## Goal

- Grok direct / proxy 启动时，临时 `GROK_HOME` 仍只写入隔离的 `config.toml` 与 `auth.json`，并继续注入 `GROK_HOME` + `XAI_API_KEY`；**不**注入 `CODEX_HOME`。
- 将真实 Grok 用户 Home（默认 `~/.grok`）中除私有条目外的已有项链接进临时 Home，使 `sessions` 等对子进程可见，且会话写入回落到真实 Home。
- 进程结束后拆除链接并删除临时目录；不得删除或改写真实 Home 中被链接目标的内容。
- 保持现有 CLI 用法（`gN` / `grok <selector>`、proxy/`--mode`、fail-closed 配置翻译）；不新增用户可见的 Home 模式开关。
- 实现形态对齐 Codex hybrid：复用或镜像 `share_*_user_state` / `detach_*` / private 名单 / Windows junction 策略。

## Non-goal

- 不引入 Grok 的「单配置文件路径」注入（Grok CLI 无 Claude 式 `--settings`）。
- 不把临时 `config.toml` / `auth.json` 写回真实 `~/.grok`。
- 不新增 DB `grok` app_type、独立编号、list 过滤。
- 不修改 provider 选择、proxy 语义、codex 配置 tomllib 解析与 fail-closed 规则。
- 不改写 Codex hybrid 行为（除非为抽取公共链接工具做无行为变更的小重构）。
- 不保证跨盘符/无权限环境下每个文件都能成功链接；目录链接失败应明确报错，文件链接失败可跳过（与 Codex 一致）。
- 不包装 `grok login` / 不把「改全局 `~/.grok` 为成功路径」作为方案。

## User scenarios

- 用户已有 `~/.grok/sessions` 与历史会话，执行 `ccs run g3` 或 `ccs run grok 3` 后，Grok 能看到既有会话并 `/resume` 或 `grok -c` / `-r` 可用。
- 用户在本次 `ccs run gN` 中产生的新会话经 `sessions` 目录链接写入真实 Home；临时目录清理后会话仍在，下次 `ccs run gN` 可 resume。
- 真实 Home 不存在时，行为退化为仅临时 Home（与改前隔离行为一致）。
- 清理临时目录或拆除链接后，真实 Home 中的 sessions 等内容保持不变。
- `ccs run -v gN` 可看到共享路径相关诊断（至少 verbose 下可见 Grok home；共享条目可与 Codex 对齐打印）。

## Acceptance

- `run` Grok 时子进程 `GROK_HOME` 仍指向临时目录，且该目录含启动器生成的 `config.toml` / `auth.json`；`XAI_API_KEY` 仍注入。
- 真实 Home 中已存在且名称不在私有名单内的目录通过 junction（Windows）或 symlink（POSIX）出现在临时 Home；文件优先 hardlink，失败则 symlink，再失败可跳过。
- 私有名单至少包含 `auth.json`、`config.toml`：不链接、不覆盖真实 Home 的这两项；临时侧保留 launcher 写入版本。
- 若 Codex 侧已对 SQLite 类运行时文件排除共享，Grok 应对同类后缀采取相同策略（避免 WAL DB 跨 home 硬链损坏）；当前 Grok home 未见同类文件时仍保留规则，防未来回归。
- 启动结束（成功或失败）后拆除共享链接；临时目录删除不得删除真实 Home 被链接目标内容。
- 无新 CLI 开关；`g`/`grok` 与 codex 同 selector、proxy、fail-closed 行为保持。
- 单元测试覆盖：共享链接创建（至少 `sessions`）、私有文件不共享、拆除后真实内容仍在、Grok direct/proxy 启动路径在 hybrid 后仍注入正确 env/config；现有 Grok/Codex 相关测试仍通过。
- `docs/README.md` 补充 Grok 混合 Home 与会话 resume 说明（与 Codex 段落对称，篇幅适中）。

## Open questions

暂无需要用户确认的未决事项。

## Decisions

- 流程模式：light / 轻量。
- 方案：Codex 同款 hybrid（临时 private config + 链接共享其余状态）；不做持久 per-provider home、不写全局 config 成功路径。
- 共享范围：真实 Grok Home 下除私有名单外的条目；私有名单固定为 `auth.json`、`config.toml`（及与 Codex 一致的 SQLite 后缀排除）。
- 真实用户 Home 来源：配置 `grok_user_home`（默认 `~/.grok`，见 `cc-switch.yaml`；可 dotenv/CCS 覆盖），可测试注入；不读取父进程已指向临时目录的 `GROK_HOME` 作为共享源。会话目录名配置 `grok_sessions_dir`（默认 `sessions`）。
- Windows 目录：`mklink /J` junction；文件 hardlink → symlink → 跳过。
- 链接失败策略：目录失败 → `LaunchError`；文件失败 → 跳过（与 Codex 一致）。
- 退出清理：`finally` 中 detach 链接后再让 `TemporaryDirectory` 回收（对齐 Codex `detach_shared_codex_state`）。
- **首次 sessions：B** — 真实 `~/.grok` 已存在时，若不存在 `sessions/` 则创建空目录再链接，保证首次 `ccs run gN` 会话写入真实 Home。真实 Home 整体不存在时仍退化为仅临时 Home。
- 配置翻译、responses 后端、fail-closed 读取逻辑保持不变，本需求只加 hybrid 共享层。

## Risk

- 杀毒/策略环境可能禁止 junction/symlink；目录失败会阻断启动。
- 并发多个 `ccs run grok` 与直接 `grok` 共享同一 `sessions`/`active_sessions*`，与原生多开同类风险，可接受。
- 若 Grok 未来把关键状态写入新的顶层私有文件名，可能被错误共享；需靠 private 名单扩展。
- 在真实 Home 存在但无 `sessions` 时会主动创建空目录（B）；若用户刻意删除 `sessions` 并希望完全无会话目录，下次 ccs run 会再创建。
- 共享 `bin/`、`docs/` 等只读目录无害但增加链接数；与 Codex「全量非 private」一致，不单独过滤除非实测有问题。

## User review notes

- 2026-07-20：用户确认 resume 失败因临时 `GROK_HOME`；要求按 Codex 同款 hybrid 实现。
- 2026-07-20：SpecFlow light 启动本任务；本轮仅需求草稿，待接受后实现。
- 2026-07-20：用户选择 **B**（预创建 `sessions`）并接受需求，进入实现。
- 2026-07-20：用户要求 hybrid 相关全局路径进 `cc-switch.yaml`（`codex_user_home` / `grok_user_home` / `grok_sessions_dir`）。
