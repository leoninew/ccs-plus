# 强类型配置与按 family 模块拆分 — 验证

最后修改时间: 2026-07-21 11:11:24

Review status: Draft

Flow mode: light / 轻量模式

## Requirement alignment

对照 [`docs/requirement/20260721-typed-settings-module-extract.md`](../requirement/20260721-typed-settings-module-extract.md)（Accepted）：

| 需求要点 | 结果 |
|----------|------|
| dynaconf + 分组 YAML；`Settings` 含 `log` / `cc_switch` / `claude` / `codex` / `grok` | 通过：仓库根 `cc-switch.yaml` 为分组形态；`get_settings()` 根字段含上述组 |
| 缺组/缺必填/非法字段 load-time `SettingsError` fail-closed | 通过：`settings.py` 集中校验；`test_settings.py` 覆盖 |
| 业务只读 typed 字段，不做配置兼容/隐式默认 | 通过：`store`/`launch`/`codex`/`grok`/`registry` 经 `get_settings()` 读字段；无二次 YAML 解析 |
| 按职责拆包（settings/errors/models/registry/store/launch/claude/codex/grok/cli） | 通过；额外抽出 `logging_util.py`、`util.py` 支撑模块 |
| `cli.py` 以编排为主 | 通过：约 380 行，仅 argparse / `run` / 日志摘要 / `main` |
| 对外行为不变 | 通过：子命令与 run 路径保留；测试覆盖 list/selector/backup/restore/run/alias 相关逻辑 |
| `ccs` entry = `cc_switch.cli:main` | 通过：`pyproject.toml` `[project.scripts]` |
| 测试全绿 + ruff | 通过：见 Commands |

**与 requirement 文档的有意偏离（用户后续明确要求）：**

- Requirement Decision 3 / Goal 测试句写「`cli` 可 re-export 符号以降低测试 churn」。
- 实现与验收按用户后续指令：**不保留 re-export 兼容层**；测试改为 import/patch 归属模块（`store`/`launch`/`codex`/`grok`/`registry`/`cli`）。
- 该偏离缩小了 facade 表面积，更符合 Goal「业务模块按职责拆分、cli 只编排」。

## Spec / Plan alignment

不适用（light 模式无独立 Spec/Plan；按 requirement 核对）。

## Actual diff summary

相对 `HEAD`（工作区 staged 变更，未提交）：

- **配置**：`cc-switch.yaml` 改为分组；`settings.py` 强类型 load/merge/`SettingsError`。
- **拆包**：从原单体 `cli.py` 抽出 `errors` / `models` / `logging_util` / `util` / `registry` / `store` / `launch` / `claude` / `codex` / `grok`；`cli.py` 仅编排。
- **测试**：`tests/test_settings.py` 对齐新配置契约；`tests/test_cc_switch.py` 按模块 import 与 patch。
- **过程文档**：新增 requirement；本 verification。

规模（`git diff --cached --stat`）：16 files, ~+2796 / ~-2449。

模块体量（非空行约）：

| 模块 | 约行数 | 角色 |
|------|--------|------|
| `cli.py` | 333 | 编排入口 |
| `settings.py` | 329 | 唯一配置出口 |
| `store.py` | 353 | DB / backup / selector |
| `launch.py` | 247 | launch home / hybrid / subprocess |
| `codex.py` / `grok.py` | 160 / 129 | family builders |
| 其余 | 小 | errors/models/registry/util/logging/claude |

## Expected vs actual changed files

| 预期（requirement） | 实际 | 说明 |
|---------------------|------|------|
| `cc-switch.yaml` | 有 | 分组配置 |
| `settings.py` | 有 | 重写为强类型 + dynaconf |
| `errors.py` `models.py` `registry.py` `store.py` `launch.py` `claude.py` `codex.py` `grok.py` | 有 | 新文件 |
| `cli.py` 变薄 | 有 | 删除 re-export 与实现正文 |
| `tests/test_*.py` | 有 | 适配配置与模块边界 |
| — | `logging_util.py` `util.py` | 额外支撑模块，未改对外 CLI 契约 |
| requirement 文档 | 有 | light 过程文档 |
| verification 文档 | 本文件 | |

未改：SQLite schema、console script 名 `ccs`、无新 family。

## Acceptance criteria checklist

- [x] 存在分组强类型 `Settings`；仓库根 `cc-switch.yaml` 为分组形态。
- [x] 业务代码中无「缺配置补默认 / 空 `home_env` 返回 None 继续跑」类逻辑（非法值在 `settings` load 失败）。
- [x] 源码按 Goal 模块拆分；`cli.py` 以编排为主。
- [x] `python -m pytest tests -q` 通过；`ruff check src/cc_switch tests` 通过。
- [x] `ccs` entry point 仍为 `cc_switch.cli:main`。
- [x] （用户追加）`cli` 无 re-export facade；测试 patch 打在归属模块。
- [x] 无业务模块 `import cc_switch.cli`（无回指环）。

## Commands

```text
python -m pytest tests -q
# OK: 76 passed, 3 subtests passed

python -m ruff check src/cc_switch tests
# OK: All checks passed!

python -c "from cc_switch.settings import get_settings; s=get_settings(); print(sorted(['log','cc_switch','claude','codex','grok']))"
# OK: Settings 根组可用（运行时已确认 groups 存在）

# pyproject.toml
# ccs = "cc_switch.cli:main"

# 确认 cli 无测试兼容 re-export 符号
python -c "import cc_switch.cli as c; print([a for a in ('DEFAULT_DB','PROVIDER_BACKUP_FORMAT','list_providers','build_codex_direct','safe_path_component') if hasattr(c,a)])"
# OK: []
```

## Missed or expanded scope

- **收紧**：去掉 requirement 允许的 `cli` re-export；测试改打归属模块（用户明确要求）。
- **小幅扩展**：`logging_util.py`、`util.py` 从原 cli 抽出，职责清晰，不扩大产品行为。
- **未做**：E2E 对真实 `ccs run` 启动外部 CLI 的手工冒烟（单测已 mock subprocess / builder 路径）。

## Risks

1. 模块级 `get_settings()` 缓存：测试与运行时必须 `get_settings.cache_clear()` + 正确 `CCS_*` / `CCS_LOCAL_CONFIG`；已有测试路径覆盖，生产侧需注意环境变更后进程内缓存。
2. 大搬迁后行为依赖单测代理，未在本机对真实 Claude/Codex/Grok 二进制做端到端联调。
3. 历史 requirement 仍写 re-export 策略；以用户后续指令与本 verification 为准。

## Incomplete items

无阻塞交付项。

可选后续（非本任务）：将 requirement Decision 3 改写为「测试按归属模块 patch」以消除文档与实现表述差；对真实 CLI 做一次 smoke。

## Conclusion

**通过验证。** light 模式下强类型配置边界与按 family/职责拆包已落地；`cli` 纯编排、无 re-export；测试与 ruff 全绿；entry point 与对外命令面保持。可交付（提交需用户授权）。
