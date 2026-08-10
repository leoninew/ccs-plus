# Grok 混合 Home：共享会话状态 — 验证

最后修改时间: 2026-07-20 22:35:42

Review status: Accepted

Flow mode: light / 轻量模式

## Requirement alignment

对照 `docs/requirement/20260720-grok-hybrid-home-sessions.md`（Accepted）：

- 临时 `GROK_HOME` 仍只写入隔离 `config.toml` / `auth.json`，注入 `GROK_HOME` + `XAI_API_KEY`，不注入 `CODEX_HOME`：满足。
- 真实 Grok 用户 Home 非私有条目链接进临时 Home；`sessions` 写入回落真实 Home：满足（`share_grok_user_state` + run 路径）。
- 决策 **B**：真实 home 存在时若不存在 sessions 目录则创建再链接：满足。
- 启动结束 detach 链接，不删除真实 Home 被链接内容：满足（`detach_shared_home_state` + 单测）。
- 私有名单 `auth.json` / `config.toml` + SQLite 后缀排除：满足（`is_cli_private_home_entry`）。
- 无新 CLI 开关；provider/proxy/fail-closed 保持：满足。
- hybrid 路径可配置：`codex_user_home` / `grok_user_home` / `grok_sessions_dir` 进 `cc-switch.yaml` 与 settings 层：满足（实现期用户追加，已写入 requirement Decisions / review notes）。
- `docs/README.md` 补充 Grok 混合 Home / resume：满足。

## Spec alignment

不适用（light / 轻量模式未创建 spec）。

## Plan alignment

不适用（light / 轻量模式未创建 plan；按 requirement 直接实现）。

## Actual diff summary

当前 staged 工作区（相对 `origin/develop` / `0d72446`）：

| 路径 | 变更要点 |
|------|----------|
| `src/cc_switch/cli.py` | 抽取 `share_user_home_state`；新增 `share_grok_user_state`（ensure sessions）；run Grok 接入 hybrid；verbose 打印 shared paths；user home 从 settings 解析 |
| `src/cc_switch/settings.py` | `LaunchSettings` 增加 `codex_user_home` / `grok_user_home` / `grok_sessions_dir`；legacy dotenv 键；`expand_user_home_path` / `sessions_dir_name` |
| `cc-switch.yaml` | 默认写入上述 home/sessions 配置项 |
| `tests/test_cc_switch.py` | Grok share/create sessions、run hybrid 集成、private 名单 |
| `tests/test_settings.py` | 默认值与 yaml/dotenv 覆盖 |
| `docs/README.md` | Grok 启动 + 混合 Home 说明 |
| `docs/requirement/20260720-grok-hybrid-home-sessions.md` | 需求（Accepted） |
| `.env.sample` | 可选覆盖键注释 |

## Expected vs actual changed files

| 预期（按 requirement） | 实际 | 结果 |
|------------------------|------|------|
| `src/cc_switch/cli.py` | 已改 | 一致 |
| `tests/test_cc_switch.py` | 已改 | 一致 |
| `docs/README.md` | 已改 | 一致 |
| `docs/requirement/20260720-grok-hybrid-home-sessions.md` | 新增 | 一致（过程文档） |
| （用户追加）settings / yaml 可配置 user home | `settings.py`、`cc-switch.yaml`、`test_settings.py`、`.env.sample` | 一致（已记录在 requirement） |
| 本验证文档 | `docs/verification/20260720-grok-hybrid-home-sessions.md` | 本阶段新增 |

未发现无关业务模块（backup/restore/list/claude 路径）被改写。Codex hybrid 经公共 `share_user_home_state` 重构，行为保持：`ensure_sessions` 仅 Grok 开启；Codex 单测仍通过。

## Acceptance criteria checklist

- [x] `run` Grok 时 `GROK_HOME` 指向临时目录，含 launcher 生成的 `config.toml` / `auth.json`；`XAI_API_KEY` 注入
- [x] 真实 Home 非私有目录/文件可链接进临时 Home（目录 junction/symlink，文件 hardlink/symlink）
- [x] 不链接/不覆盖真实 `auth.json` / `config.toml`；临时侧保留 launcher 版本
- [x] SQLite 后缀排除共享
- [x] 结束后拆除链接；临时目录删除不破坏真实 sessions 内容
- [x] 真实 home 存在时自动创建缺失的 sessions 目录（B）
- [x] 真实 home 不存在时退化为仅临时 Home
- [x] 无新 CLI 开关；同 selector / proxy / fail-closed 保持
- [x] 单元测试覆盖 share、private、detach、run hybrid、settings 默认与覆盖
- [x] README 说明 Grok 混合 Home 与 resume
- [x] 路径配置进入 `cc-switch.yaml` 配置机制

## Test results

```text
uv run ruff check src tests     # All checks passed!
uv run ruff format --check src tests  # 5 files already formatted
uv run mypy src                 # Success: no issues found in 3 source files
uv run pytest -q                # 73 passed, 3 subtests passed
```

工具链：Python 包 `cc-switch`，入口 `Makefile` 的 `check` / `test`（uv + ruff + mypy + pytest）。

## Missed or expanded scope

- **范围扩展（用户明确要求）**：hybrid 相关全局路径进入 `cc-switch.yaml`（及 dotenv/CCS 覆盖），不仅硬编码 `~/.grok`。已写入 requirement Decisions 与 review notes。
- **小重构**：Codex/Grok 共享链接逻辑合并为 `share_user_home_state`；Codex 行为无产品变化（不 ensure sessions）。
- 无 DB / app_type / 新 CLI 参数 / 写回真实 config 等 non-goal 违规。

## Risks

- 目录 junction/symlink 失败会阻断 Grok 启动（与 Codex 同策略）。
- 并发 `ccs run gN` 与原生 `grok` 共享同一 sessions / active_sessions，与原生多开同类风险。
- 未做真实交互式 `ccs run gN` → `/resume` 手工 E2E（依赖本机 `grok` PATH、provider 与 `~/.grok`）。
- `expand_user_home_path` 在 HOME 不可用时回落到不可达路径以使 hybrid no-op；生产环境正常具备 USERPROFILE/HOME。

## Incomplete items

- 无代码 incomplete 项。
- 建议用户本地 smoke：`ccs run -v gN` 确认 `Shared Grok paths` 含 `sessions`，退出后再 `ccs run gN` / `/resume`。

## Conclusion

验证通过。实现满足 Accepted requirement：Grok hybrid home 共享会话、决策 B 预创建 sessions、配置进 `cc-switch.yaml`、自动化检查与单测全绿。交付前可按建议 commit message 提交当前 staged 变更；verification 文档若尚未 stage 可一并加入。
