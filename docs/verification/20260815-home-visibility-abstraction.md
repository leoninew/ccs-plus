# Home Visibility 抽象与三端策略统一验证
最后修改时间: 2026-08-15 23:48:38

Review status: Accepted

## Requirement alignment

- 已建立 `HomeVisibility` 基类、Claude/Codex/Grok 三个具体实现和统一工厂。
- launcher 统一执行 visibility；Codex managed profile 通过 `HomeVisibility.merge_into()`
  抽象钩子接收可见配置。
- Claude、Codex、Grok 的目录共享、文件复制、缓存隔离和配置合并策略均位于具体实现。
- 产品代码中已不存在需求列出的 app-specific 顶层同步入口。
- Grok 默认 user home、README 和测试已同步更新。
- 未实现历史数据迁移，符合 Non-goal。

## Spec alignment

不适用。轻量模式 / light 未创建 Spec。

## Plan alignment

不适用。轻量模式 / light 按已接受的 Requirement 实现。

## Actual diff summary

- `home_visibility.py`：新增多态 visibility 体系、三端策略、通用 JSON/TOML 合并及原子写入。
- `launcher.py`：统一构造和调用 visibility，并将抽象传入 Codex managed profile 生成。
- `managed_config.py`：删除 Codex/Grok 用户配置同步实现，只保留 provider 配置生成并调用抽象钩子。
- `settings.py`：Grok user home 默认解析为 `~/.grok`。
- `tui.py`：通过 `CodexHomeVisibility` 暴露 session，而非调用独立过程函数。
- README、Requirement 和相关测试同步更新。
- 后续补丁：`GrokHomeVisibility` 将 `hooks/orca-status.json` 改为复制，避免 Windows
  跨卷硬链接失败后再走文件 symlink 触发 `WinError 1314`。

## Expected vs actual changed files

预期涉及 visibility、launcher、managed config、settings、TUI、README、Requirement 和测试。
实际 staged diff 共 11 个文件，均属于上述范围：

- `README.md`
- `docs/requirement/20260815-home-visibility-abstraction.md`
- `src/ccs_plus/home_visibility.py`
- `src/ccs_plus/launcher.py`
- `src/ccs_plus/managed_config.py`
- `src/ccs_plus/settings.py`
- `src/ccs_plus/tui.py`
- `tests/test_home_visibility.py`
- `tests/test_launcher.py`
- `tests/test_managed_config.py`
- `tests/test_settings.py`

本 verification 文档为验证阶段新增，当前未加入 staged diff。

后续补丁改动：

- `src/ccs_plus/home_visibility.py`：Grok `hooks` 增加 `copy_names={"orca-status.json"}`。
- `tests/test_home_visibility.py`：断言 hook 目录仍链接，`orca-status.json` 为普通文件副本。
- `docs/requirement/20260815-home-visibility-abstraction.md`：验收与决策补充 hook 状态文件复制。

## Acceptance checklist

- [x] 存在统一基类、三个实现类和构造入口。
- [x] launcher 与 managed profile 生成依赖 visibility 抽象。
- [x] 删除 app-specific 顶层同步入口。
- [x] Claude plugin metadata、cache 和 MCP 行为被实现类覆盖。
- [x] Codex sessions、skills、plugins、配置表与 project trust 被实现类覆盖。
- [x] Codex plugin 进程目录和安装 staging 保持隔离。
- [x] Grok skills、plugins、hooks、installed plugins、MCP 和 marketplace 被实现类覆盖。
- [x] Grok registry 与 `hooks/orca-status.json` 使用复制，marketplace cache 不共享。
- [x] MCP 合并保留不同名 state 条目，同名 user 条目优先。
- [x] README 与 Grok 默认 user home 已更新。
- [x] 测试、lint、类型检查和 whitespace 检查通过。

## Command results

- `uv run pytest -q`：通过，153 passed，1 skipped。
- `uv run ruff check src tests`：通过。
- `uv run mypy src`：通过，14 个 source files 无问题。
- `git diff --cached --check`：通过。
- app-specific 同步入口 `rg` 检索：无匹配。

## Missed or expanded scope

- 未发现遗漏的验收项。
- Grok visibility 从历史需求的 MCP-only 扩展到 skills/plugins/hooks/marketplace；该变化已在本次
  Accepted Requirement 中明确取代旧约束，不属于未记录的范围扩张。
- 首次验证后，Windows 实测 `hooks/orca-status.json` 跨卷链接失败。已按同一“索引/状态
  文件复制”策略补进 Requirement 与实现，属于已记录的策略细化，不是未登记的范围扩张。

## Risks

- 三套 CLI 的内部扩展目录未来可能变化，常量名单需要随上游版本维护。
- junction/symlink 使受管运行能够修改用户扩展目录；临时目录排除规则需持续保持准确。
- 本任务明确不处理旧隔离 home 的历史链接迁移。

## Incomplete items

无。

## Conclusion

实现与已接受 Requirement 一致，自动化验证全部通过，可以进入提交前人工 review。

