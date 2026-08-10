# ccs run Grok 验证

最后修改时间: 2026-07-20 19:06:31

Review status: Accepted

Flow mode: standard / 标准模式

## Requirement alignment

对照 `docs/requirement/20260720-ccs-run-grok.md`（Accepted）：

- CLI 注册默认 `grok:g`（`cc-switch.yaml`）— 已实现；`ccs alias` 展示 `g -> grok`。
- 命令 `ccs run gN` / `ccs run grok <selector>` — 已实现；同 selector 复用 `app_type=codex` 编号与 proxy。
- 启动为 `grok` 二进制；会话注入临时 `GROK_HOME` + `XAI_API_KEY`；**不**注入 `CODEX_HOME` — 已实现。
- codex config 经 **`tomllib`** 读取；`wire_api=responses` → Grok `api_backend = "responses"`，`base_url` 规范化含 `/v1` — 已实现。
- fail-closed：缺 `model` / `base_url` / `wire_api`、歧义 nested、非法 `wire_api` 失败 — 已实现并有单测。
- `ccs -v run` / `ccs run -v` 打印命令与脱敏 env / Grok config — 已实现。
- 配置根：`cc-switch.yaml` + dynaconf 合并 — 已实现（`src/cc_switch/settings.py`）。

## Spec alignment

不适用（standard / 标准模式无独立 `docs/spec/20260720-ccs-run-grok.md`）。

## Plan alignment

无独立 `docs/plan/20260720-ccs-run-grok.md`（本需求在标准流程中跳过了显式 Plan 文档，直接按 Accepted requirement 实现）。按 requirement 核对，不另做 plan 偏差判定。

## Actual diff summary

功能主体已提交：

- `539f7bf feat(run): add Grok launch path and dynaconf settings defaults`
  - 新增 `cc-switch.yaml`、`src/cc_switch/settings.py`
  - `cli.py`：grok 路径、`GROK_HOME` 注入、responses 后端、verbose
  - 测试：`tests/test_cc_switch.py`、`tests/test_settings.py`
  - 文档：`docs/README.md`、requirement、`.env.sample`、`pyproject.toml`（dynaconf）

工作区待提交（验证时点）：

- `src/cc_switch/cli.py`：fail-closed 配置提取；`ruff format`
- `tests/test_cc_switch.py`：缺字段/歧义/非法 wire_api 等用例；format
- `docs/requirement/20260720-ccs-run-grok.md`：fail-closed / tomllib / cc-switch.yaml 约定
- `src/cc_switch/settings.py`：format only

## Expected vs actual changed files

| 预期范围 | 实际 |
|---|---|
| `src/cc_switch/cli.py` | 是 |
| `src/cc_switch/settings.py` | 是（dynaconf） |
| `cc-switch.yaml` | 是 |
| `tests/test_cc_switch.py` / `tests/test_settings.py` | 是 |
| `docs/requirement/20260720-ccs-run-grok.md` | 是 |
| `docs/README.md` / `.env.sample` / `pyproject.toml` / `uv.lock` | 是（已提交） |
| 新增 DB `grok` app_type | 无（符合 non-goal） |
| 改写用户全局 `~/.grok` 作为成功路径 | 无 |

未发现超出 Grok 启动 + 配置合并 + fail-closed  hardening 的无关业务改动。

## Acceptance checklist

- [x] 默认配置 `cc-switch.yaml` 含 `grok:g`
- [x] `g`/`grok` 与 `x`/`codex` 同 selector 解析到同一 codex provider
- [x] direct/proxy 共用 codex `proxy_enabled` / `--mode`
- [x] 子进程 `grok`；注入 `GROK_HOME`、`XAI_API_KEY`；无 `CODEX_HOME`
- [x] tomllib 读取；无效 TOML fail-closed
- [x] `wire_api=responses` → `api_backend = "responses"` 且 base 含 `/v1`
- [x] 缺 model/base_url/wire_api、歧义 nested、非法 wire_api fail-closed
- [x] 密钥不在 verbose 日志明文（仅尾号/脱敏）
- [x] 单测覆盖组合别名、同 selector、嵌套解析、responses、fail-closed
- [x] 本地 smoke：`g3` → `otokapi.com/grok`，`API URL: https://otokapi.com/v1`，生成 config 含 `api_backend = "responses"`

## Test / command results

项目约定（Python + uv + Makefile / ruff / mypy / pytest）：

```text
uv run ruff check src tests
# All checks passed!

uv run ruff format --check src tests
# 5 files already formatted

uv run mypy src
# Success: no issues found in 3 source files

uv run pytest tests -q
# 68 passed, 3 subtests passed
```

Live / dry smoke（本机 DB `~/.cc-switch/cc-switch.db`）：

```text
uv run ccs alias
# 含 grok / g

uv run ccs list codex
# 3. otokapi.com/grok

# dry-run（mock launch_subprocess）ccs -v run g3：
# Resolved CLI: g -> grok
# Provider: otokapi.com/grok
# API URL: https://otokapi.com/v1
# Command: grok
# Extra env: GROK_HOME=... XAI_API_KEY=****1a9b
# Grok config:
#   model = "grok-4.5"
#   base_url = "https://otokapi.com/v1"
#   api_backend = "responses"
# auth.json = {}

# 真实启动：PATH 含 C:\Users\wangm25\.grok\bin 时 ccs run g3
# 能打印 Provider/API URL 并拉起 grok 进程（交互会话，验证时主动中断）
```

说明：

- 默认 shell PATH 可能不含 `~/.grok\bin`；未加入 PATH 时会 `Executable not found: grok`（环境前提，非代码逻辑错误）。
- `ccs run g3 -- --help` 在 argparse 下可能把 `--help` 当成 `provider`，从而跳过组合别名拆分；应使用 `ccs run g3` 或 `ccs run grok 3`，passthrough 需确认 argparse 边界。

## Missed or expanded scope

- 相对初版：增加 dynaconf / 根目录 `cc-switch.yaml`、verbose、tomllib、fail-closed、responses 后端 — 均为需求澄清过程中用户明确要求，已写入 requirement。
- 标准模式未单独写 plan 文档 — 流程文档缺口，不阻塞功能交付。
- 未对真实 otokapi 做端到端对话成功断言（仅验证注入与进程启动路径）；curl `/v1/responses` 在需求阶段已由用户确认可通。

## Risks

- Grok CLI 版本若不支持 `api_backend = "responses"`，仍可能失败。
- Provider TOML 缺 `model`/`wire_api` 会直接失败（fail-closed 预期）；需在 cc-switch 供应商配置中补齐。
- `grok` 需在 PATH 中（或改为绝对路径配置）才能真实启动。
- `gN` 与 `xN` 共用编号，用户可能误以为不同供应商池。

## Incomplete items

- 无独立 plan 文档（流程项）。
- 未自动化“真实 grok 交互一轮并拿到模型回复”的 E2E。
- 工作区 fail-closed / format 改动尚未 commit（与 `539f7bf` 分离）。

## Conclusion

验证通过。实现满足 Accepted requirement 的验收标准：Grok 复用 codex 编号、以 `GROK_HOME` 会话注入启动、responses 网关配置正确、配置 fail-closed，自动化检查与本地 dry smoke 均通过。交付前建议提交工作区 fail-closed 变更，并将 `~/.grok\bin` 加入 PATH 以便真实 `ccs run gN`。
