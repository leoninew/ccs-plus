# ccs run Grok（Codex 供应商 + Grok 启动方式）

最后修改时间: 2026-07-20 18:38:38

Review status: Accepted

Flow mode: standard / 标准模式

## Background

`ccs run xN` / `ccs run codex <selector>` 已具备完整 Codex 路径：codex 分组选 provider、proxy 判定、会话级配置、不污染全局。

Grok 没有独立供应商分区，可用数据就是 **同一套 codex provider**。产品选择与编号因此与 Codex **相同**。

差异只有两层，且必须同时成立：

1. **启动的是 `grok` 二进制**（不是 `codex`）。
2. **必须用 Grok 自己的会话级注入方式启动**（不是复用 `CODEX_HOME` / `auth.json`+`config.toml` 那套 Codex 启动法）。

一句话：

> **选谁：跟 Codex 一样。怎么启：跟 Grok 的方式。**

## Goal

1. 注册 CLI：默认 `grok:g`（项目根 `cc-switch.yaml` / 可被 env 覆盖），可选 `CC_PROVIDER_LAUNCH_GROK_ARGS`。
2. 命令：
   - `ccs run g<n>`
   - `ccs run grok <selector>`（编号或 name，规则同 codex）
3. Provider / 编号 / name / `proxy_enabled` / `--mode`：**全部复用 codex 路径**（`app_type=codex`）。
4. 启动适配（Grok 方式）：
   - 从同一份 codex `settings_config`（`auth` + `config` TOML 字符串）或 proxy 当前态翻译。
   - **读** codex `config` 使用标准库 **`tomllib`**（禁止继续手写行扫描作为主路径）。
   - 生成临时 **`GROK_HOME`**（`config.toml` + 空 `auth.json`），进程注入 `GROK_HOME` + `XAI_API_KEY`。
   - 当 codex `wire_api = "responses"`（或等价）时，Grok config 写 `api_backend = "responses"`，**不要**仅靠 `GROK_MODELS_BASE_URL` 走 chat completions（第三方网关常只有 `/v1/responses`）。
   - `base_url` 规范化为带 `/v1` 的 OpenAI 兼容根（如 `https://host` → `https://host/v1`）。
   - **禁止**对 `grok` 注入 `CODEX_HOME`。
5. 模型沿用 Grok 既有能力；从 codex config 顶层 `model` 写入 Grok 临时 config 的 default model（非另造产品策略）。
6. `ccs alias` 展示 `g -> grok`；`ccs -v run` / `ccs run -v` 可打印最终命令与脱敏 env / Grok config。

## Non-goal

- 不新增 DB `grok` app_type / 独立编号。
- 不改 `ccs run xN` / Codex 行为（除共享的 TOML 读取若被抽公共函数外，Codex 写路径可仍简单）。
- 不重做 list 排序、argparse、backup/restore、proxy 协议。
- 不做“只列出 grok 相关 provider”的过滤。
- 不包装 `grok login` / 不改写用户全局 `~/.grok` 作为成功路径。
- 不为写 TOML 引入重型依赖；生成小文件可继续可控字符串拼接，或后续再加 `tomli-w`。

## User scenarios

- `ccs list codex` 后 `ccs run g3` 与 `ccs run x3` 选中同一 provider；前者启动 `grok`。
- 网关仅支持 `/v1/responses`（如 otokapi）时，`ccs run gN` 可会话级连通，而非卡在 chat completions 重试。
- proxy 开/关对 `gN` 与 `xN` 判定一致。
- `ccs run -v gN` 可见 `Command:`、`GROK_HOME`、生成的 config 摘要（密钥脱敏）。

## Acceptance

- 默认配置来自项目根 **`cc-switch.yaml`**（可 `CCS_CONFIG` / local / user yaml / dotenv 覆盖），含 `grok:g`。
- 同 selector 下，`g`/`grok` 与 `x`/`codex` 解析到同一 provider id。
- direct/proxy 与 Codex 共用 `proxy_enabled` / `--mode`。
- 子进程为 `grok`；注入含 `GROK_HOME`、`XAI_API_KEY`；**不**依赖 `CODEX_HOME`。
- codex config 中 `model` / `base_url` / `wire_api` 的读取经 **`tomllib.loads`**（无效 TOML fail-closed）。
- `wire_api=responses` → 临时 Grok config 含 `api_backend = "responses"` 且 `base_url` 含 `/v1`。
- 密钥不进普通日志明文。
- 单测覆盖：组合别名、同 selector、tomllib 嵌套 provider 解析、responses 后端生成、缺 base_url/model/wire_api fail-closed、歧义 nested 值失败、非法 wire_api 失败。

## Design notes

### 相同（复用）

| 能力 | 行为 |
|------|------|
| 列表与编号 | `app_type=codex` |
| name selector | 同 codex |
| proxy_config | `app_type=codex` |
| `--mode` | 同 codex |
| 配置数据形态 | codex `auth` + `config` |

### 不同（必须）

| 项 | Codex 路径 | Grok 路径 |
|----|------------|-----------|
| 二进制 | `codex`（`x`） | `grok`（`g`） |
| 会话注入 | 临时 `CODEX_HOME` | 临时 `GROK_HOME` + `XAI_API_KEY`；config 含 model/base_url/`api_backend` |
| 配置键 | `CC_PROVIDER_LAUNCH_CODEX_*` | `CC_PROVIDER_LAUNCH_GROK_*` / yaml `clis.grok` |

### TOML 读取

- 使用 **`tomllib`**（stdlib，Python ≥3.11）。
- 解析 codex `settings_config.config` 字符串 → 取：
  - 顶层 `model`（**必需**，direct；缺失则失败）
  - `base_url`：顶层优先，否则 `model_providers` 中唯一明确的 `base_url`（缺失或歧义则失败）
  - `wire_api`：顶层优先，否则 nested 唯一值；仅允许 `chat` / `responses`（缺失、歧义或未知值则失败，**不**默认 `chat`）
- 手写行扫描不再作为主路径；写 Codex proxy 临时文件的 `set_toml_scalar` 可暂留。

### Fail-closed

Grok/codex 配置读路径禁止软兜底：

| 场景 | 行为 |
|------|------|
| 缺 `base_url` / `model` / `wire_api` | `LaunchError` |
| 多个 nested provider 值不一致 | `LaunchError`（Ambiguous …） |
| `wire_api` 非 `chat`/`responses` | `LaunchError` |
| 模型 id 无法生成 slug | `LaunchError` |
| `launch_summary` codex 缺 base_url | 传播错误，不返回空 URL |

proxy 路径仍使用合成的 `model=default` + `wire_api=responses`（不读 provider TOML）。

## Open questions

暂无需要用户确认的未决事项（tomllib 读路径已确认采用）。

## Decisions

- 编号与供应商源 = codex。
- 产品选择逻辑 = 与 codex 相同；启动方式 = Grok 原生会话注入。
- 默认 alias：`g` → `grok`（`cc-switch.yaml`）。
- 配置根文件：`cc-switch.yaml`（非 package 内 default_settings）。
- Responses 网关：`api_backend = "responses"` + 规范化 `/v1` base_url。
- **读 TOML：标准库 `tomllib`。**
- 模型：写入 Grok 临时 config default，不另造 CLI 模型产品策略。
- **Fail-closed**：缺字段 / 歧义 nested / 非法 wire_api 直接失败，不默认 chat、不默认 model=default（direct）、不吞 summary 异常。


## Risk

- Grok 对 `api_backend = "responses"` 的支持依赖 CLI 版本；版本过旧可能仍失败。
- 无效或非标准 TOML 会 fail-closed（比错误上游更安全）。
- 用户可能混淆 `g2`/`x2` 会启同一程序 → 文档/`alias` 写清。

## User review notes

- 2026-07-20：`g<n>` 使用 codex 编号。
- 2026-07-20：除启动 grok 外与 codex 无产品差异；必须用 Grok 方式启动。
- 2026-07-20：默认配置基于根目录 `cc-switch.yaml`。
- 2026-07-20：otokapi 等网关仅 `/v1/responses` 可用；纯 `GROK_MODELS_BASE_URL` 会 chat completions 重试失败。
- 2026-07-20：确认应用 **tomllib** 读取 codex config，继续实现。
- 2026-07-20：软兜底改为 fail-closed（缺 model/wire_api/base_url、歧义 nested、非法 wire_api 均失败）。

