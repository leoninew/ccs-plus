# 强类型配置与按 family 模块拆分

最后修改时间: 2026-07-21 10:37:36

Review status: Accepted

Flow mode: light / 轻量模式

## Background

`ccs` 启动器长期落在单体 [`src/cc_switch/cli.py`](../../src/cc_switch/cli.py)（约 1600 行）：配置读取、DB、backup、Claude/Codex/Grok 构建、hybrid home、进程启动混在一起。

上一轮已引入 dynaconf + 分组 YAML，目标形态为：

- 配置只经 [`settings.py`](../../src/cc_switch/settings.py) 强类型出口
- 分组：`log` / `cc_switch` / `claude` / `codex` / `grok`
- 业务不解析配置、不做兼容/fallback/隐式默认

配置层主体已在工作区落地；本任务在 light 流程下**记录约束**并**完成模块提取**，使后续实现可按 group 独立演进。

## Goal

1. **配置契约（已部分完成，本任务验收须保持）**
   - dynaconf 加载项目/local/user YAML + `CCS_*`（嵌套 `CCS_GROUP__KEY`）
   - `Settings` 根对象含 `log` / `cc_switch` / `claude` / `codex` / `grok`
   - 缺组、缺必填、非法 `home_env` / `sessions_dir` / `args` 等在 load 时 `SettingsError` fail-closed
   - 业务只读 typed 字段；`clis`→`CliEntry`、`args`→`tuple[str, ...]`、路径已 expand

2. **按职责拆包（本任务实现重点）**，包布局建议：

   | 模块 | 职责 |
   |------|------|
   | `settings.py` | 唯一配置加载与强类型 |
   | `errors.py` | `LaunchError` 等公共异常 |
   | `models.py` | `Provider` / `ProxyConfig` |
   | `registry.py` | CLI 名/别名注册、family 解析（读 settings） |
   | `store.py` | DB 读写、list/selector、backup/restore、visibleApps |
   | `launch.py` | 固定 launch home、hybrid share、subprocess |
   | `claude.py` | Claude direct/proxy 临时配置 |
   | `codex.py` | Codex 配置提取/构建、`CODEX_HOME` 注入 |
   | `grok.py` | Grok 配置翻译、`GROK_HOME` 注入 |
   | `cli.py` | argparse、`run` 编排、`main` 入口 |

3. **对外行为不变**：`ccs list|alias|backup|restore|run`、direct/proxy、组合别名、固定 launch home + wait、Grok 复用 codex provider 编号。
4. **测试**：现有 `tests/test_settings.py` + `tests/test_cc_switch.py` 全绿；`cli` 可 re-export 符号以降低测试 churn。

## Non-goal

1. 不改 cc-switch SQLite schema、不新增 grok app_type。
2. 不引入 pydantic / 新配置格式（仍 YAML + dynaconf）。
3. 不重做 CLI UX、不改 console script 名。
4. 不实现新 family（Gemini 等）。
5. 不在本任务做大规模行为重构（仅结构拆分 + 配置边界硬化）。

## User scenarios

1. 开发者改 `codex` 启动逻辑时只动 `codex.py`（及测试），不扫整份 `cli.py`。
2. 运维/用户在 `cc-switch.yaml` 改 `codex.home_env` / `grok.sessions_dir`；非法值启动即失败，无静默回落。
3. 用户日常 `ccs run x1` / `ccs run g1` 行为与拆分前一致。

## Acceptance

1. 存在分组强类型 `Settings`；仓库根 `cc-switch.yaml` 为分组形态。
2. 业务代码中无「缺配置补默认 / 空 `home_env` 返回 None 继续跑」类逻辑。
3. 源码按 Goal 中模块拆分；`cli.py` 以编排为主，不再承载全部实现正文。
4. `uv run python -m pytest tests -q` 通过；`ruff check src/cc_switch tests` 通过。
5. `ccs` entry point 仍为 `cc_switch.cli:main`。

## Open questions

无。用户已确认配置原则并要求 light 记录后直接实现。

## Decisions

1. light 模式：Requirement → Implementation →（用户验收后）Verification。
2. 配置缺失一律 load-time fail-closed；实现层不二次解析 YAML。
3. 拆分后 `tests` 可继续 `import cc_switch.cli as launcher`，由 `cli` re-export 公共符号。
4. 共享 hybrid home 策略字段留在 `settings.cc_switch`（`private_home_names` / `sqlite_home_suffixes`）。

## Risk

1. **大文件搬迁**易漏 re-export 导致测试 AttributeError — 以全量测试兜底。
2. **import 环**：`launch`/`codex`/`grok` 依赖 `settings`/`models`/`errors`，禁止回指 `cli`。
3. **模块级 bootstrap 常量**（`DEFAULT_DB` 等）仍在 import 时读配置；测试依赖 `get_settings.cache_clear()` 与 `CCS_LOCAL_CONFIG`。
