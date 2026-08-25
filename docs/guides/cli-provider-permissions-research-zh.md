# Claude、Codex 与 Grok CLI 服务商及权限配置调研

最后修改时间：2026-08-09 13:47:58 调研日期：2026-08-09 cc-switch 版本：3.19.2

## 目标与范围

本文记录 Claude Code、Codex CLI 和 Grok CLI 的以下配置方式：

- 常规 API base URL、协议和模型选择；
- 推理强度（effort）设置；
- 在工作目录内修改文件、执行命令和访问网络时不再逐项请求确认；
- 本机 cc-switch 数据库记录与各 CLI 实际运行时配置的差异。

本文没有读取、记录或修改任何 API Key、令牌、供应商记录或 CLI 配置文件。

## 调研方法

- 使用 `pomelo-db` 只读查询 `C:\\Users\\leon\\.cc-switch\\cc-switch.db` 中的 `providers` 和 `provider_endpoints`。
- 检查已安装 CLI 的 `--version`、`--help`、`codex doctor`、`grok inspect --json`。
- 阅读 cc-switch 源码中 Claude、Codex、Grok Build 的配置转换逻辑。
- 对照 Claude、OpenAI、xAI 的当前官方文档。

## 本机现状

| 项目 | 实测结果 |
| --- | --- |
| Claude Code | `2.1.226` |
| Codex CLI | `0.147.0` |
| Grok CLI | `1.0.0` |
| Claude 供应商记录数 / 当前记录数 | 9 / 1 |
| Codex 供应商记录数 / 当前记录数 | 9 / 1 |
| Grok Build 供应商记录数 / 当前记录数 | 5 / 1 |

数据库中当前选中的记录如下：

| CLI | 数据库当前记录 | 模型或端点摘要 |
| --- | --- | --- |
| Claude | `airoute.mycyjg.net/terra` | `https://airoute.mycyjg.net/`，所有 Claude 模型槽位均为 `gpt-5.6-terra` |
| Codex | `OpenAI Official` | 官方记录本身不写 API-key provider 配置 |
| Grok Build | `otokapi.com/grok` | 自定义 Grok provider 记录 |

### 数据库记录不等于当前进程配置

当前 PowerShell 进程的 `CODEX_HOME` 是 cc-switch 临时目录：

```text
D:\\ProgramFiles\\Cygwin64\\tmp\\cc-provider-launch\\codex\\airoute.mycyjg.net_terra\\codex
```

因此，实际运行的 Codex 并未使用数据库中标记为 `OpenAI Official` 的记录，而是使用该临时目录中的 `cch` provider：

```toml
model_provider = "cch"
model = "gpt-5.6-terra"
model_reasoning_effort = "xhigh"
web_search = "live"
sandbox_mode = "workspace-write"

[model_providers.cch]
base_url = "https://airoute.mycyjg.net/v1"
wire_api = "responses"

[sandbox_workspace_write]
network_access = true
```

同理，直接在当前终端执行 `grok models` 使用的是本机 Grok 登录态，显示默认模型 `grok-4.5`；它不能证明 cc-switch 在其启动器中是否已应用数据库的 `otokapi.com/grok` 记录。

**结论：切换后应使用目标 CLI 的运行时诊断确认，而不能只看数据库的 `is_current`。** 对 Codex 使用 `codex doctor`，对 Grok 使用 `grok inspect --json`。

## 常规服务商配置

### Claude Code

官方 API 的 base URL 是 `https://api.anthropic.com`，Messages API 的资源路径为 `/v1/messages`。第三方服务商必须提供 Anthropic Messages 兼容协议；单纯支持 OpenAI Chat Completions 的地址不能直接当作 Claude Code 上游。

cc-switch 的 Claude 供应商配置写在 JSON 的 `env` 中，主要字段为：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
    "ANTHROPIC_AUTH_TOKEN": "<token>",
    "ANTHROPIC_MODEL": "<主模型>",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "<轻量模型>",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "<常用模型>",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "<高能力模型>"
  }
}
```

- CLI 单次选择模型：`claude --model <模型或别名>`。本机帮助中列出 `fable`、`opus`、`sonnet` 等别名，也接受完整模型 ID。
- CLI 单次设置推理强度：`claude --effort low|medium|high|xhigh|max`。
- 持久默认 effort 使用 Claude 设置中的 `effortLevel`；`--effort` 和 `CLAUDE_CODE_EFFORT_LEVEL` 对当前会话优先。

### Codex CLI

使用 API Key 的官方 OpenAI provider 通常以 `https://api.openai.com/v1` 为 base URL，并通过 Responses API 请求 `/responses`。cc-switch 的 Codex 配置使用 TOML：

```toml
model_provider = "custom"
model = "<模型 ID>"
model_reasoning_effort = "high"

[model_providers.custom]
name = "<供应商名称>"
base_url = "https://api.openai.com/v1"
wire_api = "responses"
```

- `model` 选择模型。
- `model_reasoning_effort` 选择推理强度；本机现有配置使用 `xhigh`。
- `wire_api = "responses"` 是协议约束，要求上游实现 Responses API，而不是只实现 Chat Completions。
- `base_url` 是 base URL，不能重复附加 `/responses`，除非供应商文档明确给出了完整资源 URL 的特殊约定。

### Grok CLI / Grok Build

xAI API 的标准 base URL 是 `https://api.x.ai/v1`，Responses API 为 `/v1/responses`。当前本机账户的 `grok models` 只显示 `grok-4.5`；该模型支持 `low`、`medium`、`high`、`xhigh`，默认 `high`。

cc-switch 不会把 Grok Build 的预设 TOML 原样交给 Grok CLI。它会转换为 Grok 的原生配置结构：

```toml
[models]
default = "grok-4.5"

[model.grok-4.5]
model = "grok-4.5"
base_url = "https://api.x.ai/v1"
name = "xAI (Grok)"
env_key = "XAI_API_KEY"
api_backend = "responses"
context_window = 500000
```

其中 `api_key` 与 `env_key` 二选一。Grok Build 表单默认模型为 `grok-4.5`、后端为 `responses`、上下文窗口为 `500000`。单次调整推理强度使用：

```powershell
grok --reasoning-effort xhigh
```

供应商级默认推理强度写在同一 TOML 的 `[models].default_reasoning_effort`；命令行 `--reasoning-effort` 会覆盖该默认值。启动器应从供应商记录读取该字段，但不应修改共享 state home 中的 `[models]` 默认项。

Grok 也支持以 `GROK_MODELS_BASE_URL` 指向 OpenAI 兼容的自定义模型服务；它从 `{base_url}/models` 拉取模型列表，可用 `GROK_MODELS_LIST_URL` 覆盖该列表地址。

## 免确认且保留工作目录边界

目标是：在 `D:\\SourceCodes\\mywork\\cc-switch2\\cc-switch` 工作目录内可修改文件、执行命令、访问网络，且不再逐项批准。三者的实现方式不同。

### Claude Code

单次会话可直接使用：

```powershell
claude --dangerously-skip-permissions
```

持久设置应放在用户级 `C:\\Users\\leon\\.claude\\settings.json`：

```json
{
  "permissions": {
    "defaultMode": "bypassPermissions",
    "skipDangerousModePermissionPrompt": true
  }
}
```

注意事项：

- `skipDangerousModePermissionPrompt` 在项目级 `.claude/settings.json` 中会被忽略，必须放在用户级设置或受管设置。
- `dontAsk` 不是自动批准；它会自动拒绝需要权限的操作，因此不符合本目标。
- `bypassPermissions` 是跳过权限检查，不是操作系统级的目录隔离。以工作目录启动可以满足日常目录内编辑，但 Bash/PowerShell 命令仍可能访问工作目录外内容。需要强制目录边界时，应在外层使用容器、受限账户或其他操作系统级沙箱。
- 网络不需要额外的 Claude permission allow 规则；但不能被受管的网络限制策略阻止。

### Codex CLI

推荐使用 `workspace-write`，以保留工作区写入边界并显式允许网络。以下键必须放在 `config.toml` 的**顶层**，即任何 `[table]` 之前：

```toml
sandbox_mode = "workspace-write"
approval_policy = "never"

[sandbox_workspace_write]
network_access = true
```

单次非交互执行可写为：

```powershell
codex exec -C "D:\\SourceCodes\\mywork\\cc-switch2\\cc-switch" -s workspace-write -c 'approval_policy="never"' -c 'sandbox_workspace_write.network_access=true' "<任务>"
```

不要将以下两个模式混淆：

- `--full-auto` 的语义是 `workspace-write` 加自动审查，仍可能在失败时请求批准，不能保证免确认。
- `--dangerously-bypass-approvals-and-sandbox` 会跳过批准和沙箱，文件范围也不再限制到工作区；只应在已经由外部环境隔离时使用。

#### 当前 Codex 配置缺陷

当前 cc-switch 临时配置中存在：

```toml
[marketplaces.best-practices-local]
sandbox_mode = "danger-full-access"
approval_policy = "never"
```

这两个键位于 `marketplaces.best-practices-local` 表内，不是顶层 Codex 配置。`codex doctor` 的有效诊断为：

```text
sandbox: restricted fs + enabled network · approval OnRequest
```

因此当前 Codex **尚未达到免确认目标**。修复时应将 `approval_policy = "never"` 移到顶层；不应将它作为 marketplace 字段保存。还需注意当前进程设置了 `CODEX_HOME`，所以修改 `C:\\Users\\leon\\.codex\\config.toml` 不会影响这个 cc-switch 启动器进程。

### Grok CLI

单次会话推荐：

```powershell
grok --sandbox workspace --always-approve --reasoning-effort xhigh
```

- `--always-approve` 自动批准工具执行。
- `--sandbox workspace` 允许当前工作目录和 Grok 自身目录写入，并允许子进程联网。
- 本机 `C:\\Users\\leon\\.grok\\config.toml` 已设置 `ui.permission_mode = "always-approve"`。
- `grok inspect --json` 已将当前项目报告为 `projectTrusted: true`。

Grok 的 `sandbox = off` 虽也是默认且不会限制网络，但会移除工作目录写入边界，不适合本目标。

## 新应用的启动策略

本调研后续对应的新 Python 启动器。它适配原生 CLI，不修改 cc-switch 当前临时目录中的配置，也不迁移其既有会话。

1. Claude 每次启动将 `CLAUDE_CONFIG_DIR` 显式设为 Dynaconf 配置的稳定 state home，再注入供应商环境变量并加 `--dangerously-skip-permissions`；该目录不得随供应商变化。
2. Codex 在稳定 `CODEX_HOME` 创建不含 API Key 的命名 profile，把 `approval_policy` 与 sandbox 键放在 profile 顶层；使用 `--profile` 启动，不继承 cc-switch 临时 `CODEX_HOME`。
3. Grok 在稳定 `GROK_HOME/config.toml` 增加命名 `[model.<profile>]`，启动时使用 `--model <profile> --sandbox workspace --always-approve`，不变更 `[models].default`。
4. 每次新应用启动前验证 CLI 可执行文件、profile/TOML 语法、数据库记录和稳定状态目录；启动后可用 `codex doctor`、`grok inspect` 或原生 resume/历史入口人工确认实际生效配置。
5. 供应商切换只改变 API 路由、认证和模型配置；权限策略不得误写入供应商 TOML 的嵌套表，也不得以无沙箱模式替代工作区边界。

## 证据与参考

### 本地来源

- `package.json`：cc-switch 版本 `3.19.2`。
- `C:\\Users\\leon\\.cc-switch\\cc-switch.db`：供应商和 endpoint 记录，通过 `pomelo-db` 只读查询。
- `src/utils/grokBuildConfig.ts`：Grok Build 的原生 TOML 生成、默认模型、Responses backend 和 context window。
- `src/config/claudeProviderPresets.ts`：Claude provider 的 `ANTHROPIC_*` 环境变量配置形式。
- `src/config/codexProviderPresets.ts`：Codex 的 `model`、`model_reasoning_effort`、`model_providers.*.base_url`、`wire_api` 形式。
- `codex doctor`：确认当前临时 `CODEX_HOME`、provider、网络、沙箱和 approval 的有效值。

### 官方文档

- Claude Code Settings: <https://code.claude.com/docs/en/settings>
- OpenAI Codex configuration: <https://learn.chatgpt.com/docs/configuration>
- xAI model catalog: <https://docs.x.ai/developers/models>
- xAI API reference: <https://docs.x.ai/developers/api-reference>

## 会话历史与启动方式复核

复核日期：2026-08-09。以下结论基于本机 Claude Code `2.1.226`、Codex CLI `0.147.0`、Grok `1.0.0` 的帮助、诊断、安装附带文档，以及 Codex 官方配置参考；没有发送模型请求或读取 API Key。

### 结论

供应商切换不能依赖供应商专属的临时 home。临时配置文件本身不是问题；将 `CLAUDE_CONFIG_DIR`、`CODEX_HOME` 或 `GROK_HOME` 指向另一个目录才会把会话状态分到另一处。

| CLI | 正确的稳定状态策略 | 供应商配置策略 |
| --- | --- | --- |
| Claude | 使用一个固定的配置式 Claude home，项目会话位于 `<claude_home>/projects/`；如需复用既有历史，可将该配置设为 `~/.claude` | 对子进程设置稳定 `CLAUDE_CONFIG_DIR`，再注入 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN` 和模型环境变量；可选 `--settings` 只能追加设置，不能使用供应商专属目录 |
| Codex | 使用同一个配置式 `CODEX_HOME`，其中含 `sessions` 与 SQLite state；如需复用既有历史，可将该配置设为原有目录 | 在该 home 旁创建 `<profile>.config.toml`，以 `--profile <profile>` 叠加 custom Responses provider；API Key 用 `env_key` 和子进程环境传递 |
| Grok | 使用同一个配置式 Grok home，会话位于 `<grok_home>/sessions/<encoded-cwd>/`；如需复用既有历史，可将该配置设为 `~/.grok` | 在同一个 `config.toml` 增加命名 `[model.<profile>]`，以 `--model <profile>` 选择；不改变 `[models].default`，也不按供应商改变 `GROK_HOME` |

本机启动环境当前带有 cc-switch 临时 `CODEX_HOME`：

```text
D:\\ProgramFiles\\Cygwin64\\tmp\\cc-provider-launch\\codex\\airoute.mycyjg.net_terra\\codex
```

这说明新的启动器必须显式选择配置的稳定 state home，且不能盲目继承父进程的 `CODEX_HOME` 或 `CODEX_SQLITE_HOME`。同理，应将 `CLAUDE_CONFIG_DIR`、`GROK_HOME` 覆盖为配置的稳定目录，而非继承供应商专属值。

### 当前 Codex profile 方式

Codex 官方配置参考确认：profile 是 `$CODEX_HOME/<name>.config.toml`，而 provider 相关键不能依靠项目 `.codex/config.toml`。因此可在稳定 home 中维护不含密钥的 profile：

```toml
model_provider = "cc-provider-example"
model = "provider-model-id"
model_reasoning_effort = "high"
approval_policy = "never"
sandbox_mode = "workspace-write"

[model_providers.cc-provider-example]
name = "Example"
base_url = "https://api.example.com/v1"
wire_api = "responses"
env_key = "CC_PROVIDER_CODEX_EXAMPLE_KEY"

[sandbox_workspace_write]
network_access = true
```

启动时再在子进程环境中设置 `CC_PROVIDER_CODEX_EXAMPLE_KEY`，并传入 `--profile cc-provider-example --ask-for-approval never --sandbox workspace-write`。这既不改变全局 `config.toml` 的其他内容，也不把 API Key 写到 profile 中。

已在稳定 `C:\\Users\\leon\\.codex` 上用 `codex --strict-config ... doctor` 解析顶层权限键，结果为：

```text
approval policy          Never
filesystem sandbox       restricted
network sandbox          enabled
```

### 当前 Grok profile 方式

Grok 安装附带 README 确认 TOML 头名是模型选择器显示的 profile 名，而 `model` 是实际发送给 API 的模型 ID。可使用：

```toml
[model.cc-provider-example]
model = "provider-model-id"
base_url = "https://api.example.com/v1"
env_key = "CC_PROVIDER_GROK_EXAMPLE_KEY"
api_backend = "responses"
```

然后以如下方式启动：

```powershell
grok --model cc-provider-example --sandbox workspace --always-approve
```

`workspace` 允许读取文件系统、写入当前目录与 Grok 自身目录，并允许子进程联网；`--always-approve` 自动同意工具调用。Grok 的推理参数是 `--reasoning-effort`（别名 `--effort`），支持 `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`，以及模型定义的专有菜单值。

### 未执行的实网验证

本次未用真实供应商发起会话，因而没有实测某一第三方 endpoint 的 API 兼容性，也没有实际创建再恢复会话。状态目录和配置加载结论已经由本机 CLI 文档与配置解析验证；后续应用验收仍应针对每种 CLI 实测“供应商 A 创建会话，供应商 B 启动后原生恢复入口仍可见 A”的场景。
