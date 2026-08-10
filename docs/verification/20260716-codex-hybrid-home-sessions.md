# Codex 混合 Home：共享会话状态
最后修改时间: 2026-07-16 08:58:30

Review status: Accepted

## Mode

light / 轻量

## Requirement alignment

对照 `docs/requirement/20260716-codex-hybrid-home-sessions.md`：

- 临时 `CODEX_HOME` 仍只写入隔离 `auth.json` / `config.toml`：满足。
- 真实用户 Home（默认 `~/.codex`）除私有名单外条目链接进临时 Home：满足（`share_codex_user_state`）。
- 启动结束拆除链接，不删除真实 Home 被链接内容：满足（`detach_shared_codex_state` + 测试断言）。
- 无新 CLI 开关，保留 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV` fail-closed：满足。
- README 说明混合 Home 与清理语义：满足。

## Spec alignment

不适用（light / 轻量模式未创建 spec）。

## Plan alignment

不适用（light / 轻量模式未创建 plan；按 requirement 直接实现）。

## Actual diff summary

功能改动（忽略整文件换行噪声后的语义 diff）：

- `src/cc_switch/cli.py`：新增混合 Home 链接/拆除逻辑；Codex `run` 路径在启动前后接入共享与 finally 清理。
- `tests/test_cc_switch.py`：新增共享链接、run 集成与清理安全测试。
- `docs/README.md`：更新 Codex 启动说明。
- `docs/requirement/20260716-codex-hybrid-home-sessions.md`：新增（untracked）需求文档。

## Expected vs actual changed files

| 预期 | 实际 | 结果 |
|---|---|---|
| `src/cc_switch/cli.py` | 已改 | 一致 |
| `tests/test_cc_switch.py` | 已改 | 一致 |
| `docs/README.md` | 已改 | 一致 |
| `docs/requirement/20260716-codex-hybrid-home-sessions.md` | 新增 | 一致（过程文档） |

无发现业务无关的逻辑改动。注意：若不加 `-w`，git 可能把 CRLF/LF 显示为整文件重写；功能 diff 约 +232 / -3 行。

## Acceptance criteria checklist

- [x] 子进程 `CODEX_HOME` 仍指向临时目录，且含启动器生成的 auth/config
- [x] 真实 Home 非私有条目可被链接进临时 Home（目录 junction/symlink，文件 hardlink/symlink）
- [x] 不链接/不覆盖真实 `auth.json` / `config.toml`
- [x] 结束后拆除链接；临时目录删除不破坏真实 sessions 内容
- [x] 无新 CLI 开关；既有 env 选择器与 fail-closed 保持
- [x] 单元测试覆盖共享、私有不共享、清理安全
- [x] README 更新混合 Home 行为

## Test results

```text
uv run ruff check --fix src tests  # All checks passed
uv run mypy src                     # Success: no issues found in 2 source files
uv run pytest -q                    # 38 passed, 3 subtests passed
```

## Missed or expanded scope

- 无需求外功能扩展。
- 实现上将共享范围定为「真实 Home 下除 auth/config 外全部条目」，与 requirement Decisions 一致，不限于 sessions 白名单。

## Risks

- 目录链接失败会阻断 Codex 启动；单文件链接失败仅跳过，可能导致 `history.jsonl` 等不可见。
- 多开 `ccs run codex` 共享同一真实 sessions，与直接多开 Codex 同类风险。
- 若 Codex 未来把敏感状态写入除 auth/config 外的新文件名，会被共享；当前私有名单固定。

## Incomplete items

无。未做真实交互式 `ccs run xN` 手工 smoke（依赖本机 provider/网络）；单元测试已覆盖链接与清理路径。

## Conclusion

验证通过。可按 requirement 交付混合 Home 行为；建议用户本地再跑一次 `ccs run xN -v` 确认 verbose 输出中的 Shared Codex paths 含 `sessions`。
