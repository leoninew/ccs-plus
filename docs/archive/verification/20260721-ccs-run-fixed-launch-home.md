# ccs run 固定启动目录验证

最后修改时间: 2026-07-21 10:04:37

Review status: Draft

Flow mode: light / 轻量模式

## Requirement alignment

对照 `docs/requirement/20260721-ccs-run-fixed-launch-home.md`（Accepted，含 2026-07-21 修订）：

| 需求要点 | 结论 |
|---|---|
| 稳定启动根目录：`{tempdir}/{prefix}/{family}/{safe_provider}` | 已实现：`launch_temp_root` / `launch_temp_dir` / `ensure_launch_temp_dir` |
| 路径消毒（非法字符、空白、保留设备名） | 已实现：`safe_path_component` + 单测 |
| 同供应商复用目录，覆盖 private 配置，退出不 rmtree | 已实现；`run()` 不再 `TemporaryDirectory` / detach 清理 |
| Codex/Grok hybrid share 写入固定 home，退出不 detach | 已实现；`run()` 仅 `share_*`，不调用 `detach_shared_*` |
| `Popen` 后 **wait** 回传子进程退出码 | 已实现（相对初版 non-blocking 的修订）：`process.wait()` |
| direct/proxy、CLI args、env、Codex fail-closed 不变 | 既有路径保留；单测仍覆盖 |
| YAML `paths` / `homes` / `proxy` 与去掉 dotenv | 已实现（`settings.py` + `cc-switch.yaml` + 去 `python-dotenv`） |

标题仍为「固定启动目录并**立即退出**」，与修订后 Goal/Acceptance 不一致，属文档债（见 Incomplete items）。

## Spec alignment

不适用（light / 轻量模式无 `docs/spec/20260721-ccs-run-fixed-launch-home.md`）。按 requirement / 需求核对。

## Plan alignment

不适用（light / 轻量模式无 `docs/plan/20260721-ccs-run-fixed-launch-home.md`）。按 requirement / 需求核对。

## Actual diff summary

功能主体已提交：

- `e7c22a2 feat(run): use fixed per-provider launch homes and non-blocking launch`
  - 固定 launch home、settings 路径/homes/proxy、去掉 dotenv
  - 初版为 `Popen` 后立即返回 `0`（后续修订已否定）

工作区已暂存、待提交（验证时点）：

- `src/cc_switch/cli.py`：`launch_subprocess` 改为 `wait` 并回传退出码；注释同步
- `tests/test_cc_switch.py`：`test_launch_subprocess_waits_for_process_exit`
- `docs/requirement/20260721-ccs-run-fixed-launch-home.md`：放弃立即返回，记录交互修复决策
- `docs/verification/20260721-ccs-run-fixed-launch-home.md`：本文件（验证阶段新增，当前未暂存）

## Expected vs actual changed files

| 预期范围 | 实际 |
|---|---|
| `src/cc_switch/cli.py`（固定 home + launch wait） | 是 |
| `src/cc_switch/settings.py`（paths/homes/proxy、去 dotenv） | 是（已提交） |
| `cc-switch.yaml` | 是（已提交） |
| `pyproject.toml` / `uv.lock`（去 python-dotenv） | 是（已提交） |
| `tests/test_cc_switch.py` / `tests/test_settings.py` | 是 |
| `docs/requirement/20260721-ccs-run-fixed-launch-home.md` | 是 |
| `docs/verification/20260721-ccs-run-fixed-launch-home.md` | 是（本文件） |
| 后台守护 / PID 文件 / `os.exec*` | 无（符合 non-goal） |
| 自动清理历史固定目录 | 无（符合 non-goal） |
| 写回用户全局 Claude/Codex/Grok 配置作为成功路径 | 无；单测断言 real home 无 auth/config 写回 |

范围说明：settings 层去掉 dotenv、路径配置化与固定 launch home 同批交付，属支持本需求的配置面；未发现无关业务改动。

## Acceptance checklist

- [x] 启动目录由 family + 安全化 provider name 决定，同名同 family 路径稳定可复现（单测 `test_launch_temp_dir_is_stable_for_provider_name`）
- [x] 路径消毒覆盖非法字符 / 空名 / Windows 保留名（`test_safe_path_component_sanitizes_provider_names`）
- [x] `ccs run` 前台 wait，不在成功启动后立即交回 shell（`process.wait()` + `test_launch_subprocess_waits_for_process_exit` 回传退出码 7）
- [x] 目标 CLI 退出后固定目录仍存在（codex/grok run 路径单测 `assertTrue(...home.exists())`）
- [x] hybrid sessions 共享仍可用，且不写回 real home private 配置
- [x] 不因退出 rmtree / detach 共享链接（`run()` 路径无 detach）
- [x] 可执行文件缺失仍 `LaunchError`（`test_launch_subprocess_reports_missing_executable`）
- [x] Windows 清空 env 下 junction 创建（既有 hybrid/share 相关测试在本机通过）
- [x] 全量 `tests` 通过
- [ ] **人工交互验收（建议用户本地再确认）**：真实 `ccs run <cli> <selector>` 会话中 Ctrl+C 可退出、stdin 无莫名回显（此前 non-blocking 回归点）

## Test / command results

项目约定：Python + uv + ruff / mypy / pytest（`pyproject.toml` dependency-groups.dev）。

```text
uv run ruff check src tests
# All checks passed!

uv run ruff format --check src tests
# 5 files already formatted

uv run mypy src
# Success: no issues found in 3 source files

uv run pytest tests -q
# 73 passed, 3 subtests passed in 6.28s
```

未做真实交互 CLI 冒烟（会阻塞终端且依赖本机 claude/codex/grok 与 DB provider）；交互 Ctrl+C / stdin 项依赖人工验收。

## Missed or expanded scope

- **修订范围**：相对初版 requirement「立即退出」，验证时点以修订后 Acceptance 为准（wait 前台）。初版 commit message 仍写 non-blocking，属历史提交文案，不作为当前验收目标。
- **扩展但合理**：`paths` / `homes` / `proxy` 配置化与移除 `python-dotenv` 一并合入，支撑固定 home 与默认路径；未超出 launcher 配置边界。
- **未做**：自动清理固定目录、进程替换、后台 job control 改进（non-goal）。

## Risks

1. **磁盘残留**：固定目录可能含密钥配置，长期留在系统 temp；依赖 OS temp ACL。
2. **同名 provider 共用目录**：同 family 下 name 相同会覆盖 private 配置。
3. **交互未人工复测**：自动化无法证明 Ctrl+C / 无莫名输入；需用户在修复后本地再跑一次 `ccs run`。
4. **requirement 标题滞后**：仍含「立即退出」，易误导后续读者。

## Incomplete items

1. 建议将 requirement 标题改为「固定启动目录」或「固定启动目录与前台等待」，去掉「立即退出」。
2. 建议用户本地执行一次真实 `ccs run` 确认交互体验后，再将本 verification `Review status` 标为 `Accepted`。
3. 工作区 wait 修复与 verification 文档尚未提交；`e7c22a2` 已推送前本地领先 origin 1 commit。

## Conclusion

固定 per-provider launch home、不清理目录、hybrid share 保留、settings 路径配置化等主线已落地；交互回归已通过恢复 `process.wait()` 对齐修订后需求。自动化检查（ruff / mypy / pytest）全部通过。

**结论：有条件通过（Conditionally pass）** — 代码与单测满足修订后 Acceptance；待用户完成一次真实交互确认，并建议修正 requirement 标题后可将 verification 标为 Accepted。
