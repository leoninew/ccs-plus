# Codex 临时配置隔离修复验证
最后修改时间: 2026-07-14 10:19:07

Review status: Accepted

Flow mode: light / 轻量模式

## Requirement alignment

对照 `docs/requirement/20260714-codex-home-isolation.md`：

- 已从父进程环境与选定 env 文件解析 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV`，父进程优先。
- 已按 `CC_SWITCH_ENV_FILE` → 源码 checkout `.env`（需同目录 `pyproject.toml`）→ `~/.cc-switch/.env` 解析配置，不扫描 CWD。
- Codex direct / proxy 启动均仅向子进程注入临时 Home；缺失/空白/非法选择器 fail-closed。
- 未引入 `--profile`，未读写全局 `~/.codex`，未改 provider DB / proxy 路由语义。
- 文档与 `.env.sample` 已同步说明变量名语义、优先级与安全默认参数。

## Spec alignment

不适用（light / 轻量模式，无独立 spec 文档）。

## Plan alignment

不适用（light / 轻量模式，无独立 plan 文档；按 requirement 实现）。

## Actual diff summary

- `src/cc_switch/cli.py`
  - 新增 `env_value` / `is_source_checkout_env_file` / `env_file_path`。
  - `codex_launch_env` 支持从 env 文件读取选择器，校验合法环境变量名。
  - 缺失选择器错误提示包含配置键与选定 env 文件路径。
  - `env_csv` / `env_args` / `backup_dir_from_env` / `run` 统一走 `env_value` / `env_file_path`。
- `tests/test_cc_switch.py`
  - 覆盖路径优先级、pyproject 标记、父进程优先、非法/空白拦截、direct/proxy 注入、user/explicit env 全链路。
- `docs/README.md`、`docs/requirement/20260714-codex-home-isolation.md`、`docs/verification/20260714-codex-home-isolation.md`
- `.env.sample`：默认 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV=CODEX_HOME`，危险 CLI args 注释，补末尾换行。
- `uv.lock`：同步本地 package 版本 `0.1.0` 到 `0.1.1`（与已有 `pyproject.toml` 对齐）。

## Expected vs actual changed files

| 预期（按 requirement） | 实际 |
| --- | --- |
| launcher 逻辑（cli） | `src/cc_switch/cli.py` |
| 单元测试 | `tests/test_cc_switch.py` |
| 文档与示例 | `docs/README.md`、`.env.sample`、requirement/verification |
| 不改 provider DB / proxy 语义 | 无相关代码改动 |
| 过程文档 | requirement + verification（light） |

额外改动：

- `uv.lock` 版本字段同步到 `0.1.1`（与已提交的 `pyproject.toml` 对齐，属交付一致性，非功能行为变更）。

## Acceptance criteria checklist

- [x] 成功的 Codex direct 和 proxy 启动都仅将临时 `<temp>/codex` 注入到子进程 Home 环境变量。
- [x] 父进程配置优先，其次为选定 env 文件；不得扫描当前工作目录 `.env`。
- [x] 安装制品可通过 `CC_SWITCH_ENV_FILE` 或 `~/.cc-switch/.env` 获取配置。
- [x] 源码 checkout `.env` 仅在同目录存在 `pyproject.toml` 时视为有效。
- [x] 缺失、空白或非法选择器 fail-closed，且不调用子进程。
- [x] 示例与文档准确说明 `CODEX_HOME` 及配置文件优先级。

## Test / command results

项目入口：`Makefile`（`make check` / `make test`）。

```text
make check
uv run ruff check --fix src tests
# All checks passed!
uv run ruff format src tests
# 3 files left unchanged
uv run mypy src
# Success: no issues found in 2 source files

make test
uv run pytest
# 36 passed in 0.16s
```

## Missed or expanded scope

- 扩展：配置文件解析从“仅 Codex Home”扩展为所有命令共用的 `env_file_path()`（alias / backup / restore / run）。requirement Risk 已预告 `CC_SWITCH_ENV_FILE` 契约变化，行为与文档一致，属合理实现展开。
- 扩展：`uv.lock` 版本号同步；不影响运行时行为。
- 未遗漏 requirement 中的 Non-goal 与 fail-closed 约束。

## Risks

- 已安装用户若未设置 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV`，Codex 启动仍会 fail-closed；错误信息已指向配置键与 env 文件路径。
- 源码 `.env` 依赖同目录 `pyproject.toml` 判定；对本仓库布局正确，若未来 monorepo 改布局需同步调整。
- 未做真实 Codex CLI 二进制端到端联调（依赖本机是否安装 codex）；隔离与注入行为由 unit test 覆盖。

## Incomplete items

无。

## Conclusion

验证通过。实现与 light / 轻量模式 requirement 对齐，项目 `make check` / `make test` 通过，可交付。
