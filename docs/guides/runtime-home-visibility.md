# Runtime Home 可见性与权威来源

最后修改时间: 2026-08-25 17:19:02

`ccsp launch` 对 Claude、Grok、OpenCode 同时使用真实用户 Home 与隔离的 state Home。用户 Home 保存用户主动安装、启用和维护的扩展；state Home 只保存 ccs-plus 的 provider runtime 状态。两者不能互为备份或平级来源。Codex 是例外：它使用配置的真实 `apps.codex.user_home` 作为唯一 `CODEX_HOME`，不再投影用户配置。

本文以 `~/.codex` 等默认路径说明；实际 source 是 `settings.yaml` 中配置的对应 app `user_home`。

## 不变量

对由真实用户 Home 提供的可见性条目，用户 Home 是唯一权威来源。每次受管启动同步时，source 中存在的目录或文件必须覆盖同名 state target，不得因 target 已是实体目录、实体文件、悬挂链接或指向其他来源的链接而保留旧内容。

这条规则适用于 `link_user_entries()` 管理的 Claude、Grok 与 OpenCode user-owned entries。它不表示整个 state Home 都可以被用户 Home 覆盖。

## 权威来源表

| 内容 | 权威来源 | ccs-plus 行为 |
| --- | --- | --- |
| 选中 provider 的 endpoint、模型、API Key、权限策略 | cc-switch SQLite 中由 `cN`、`xN`、`gN` 选中的记录 | 每次启动从该记录构造环境变量或受管 profile；API Key 不写入用户基础配置。 |
| 当前工作目录 `A` 的 MCP、plugin、skill 与项目配置 | 用户启动 `ccsp` 时所在目录 | 原样作为子进程 cwd 传递，由原生 CLI 发现；不复制、合并、授权或重写，`A == Path.home()` 也相同。 |
| 用户 skills、plugins、hooks、OpenCode 用户配置条目 | 对应 `~` 下 app Home | 同名 target 覆盖后链接；声明为 copy 的文件覆盖复制。 |
| Claude `settings.json` 的 `apps.claude.visibility.settings_keys` 声明键（`settings.yaml` 必填声明为 `enabledPlugins`、`extraKnownMarketplaces`） | `~/.claude/settings.json` | 按键并集合并到 state `settings.json`，同名条目以 user Home 为准；state 独有键（如 `theme`）保留。 |
| Codex 的 MCP、plugin、skill、session、基础 `config.toml` | `apps.codex.user_home`（默认 `~/.codex`） | 子进程直接使用该目录作为 `CODEX_HOME`；不链接、不复制、不合并。 |
| Codex ccs-plus managed profile | 同一个真实 Codex user Home | 仅写 provider 所需字段；不包含 `mcp_servers`、plugins、marketplaces、shell policy 或 `[projects]`。 |
| Claude/Grok/OpenCode provider profile、认证、SQLite state、临时运行文件 | 对应 state Home | 不参与 user-home visibility。 |

`plugins/cache` 的内容可见不等于插件已启用。启用仍取决于 `[plugins]` 与 `[marketplaces]` 注册；不得从缓存目录反推或自动写入 enablement。

Claude 侧同理：缓存可见不等于已启用，启用取决于 `settings.json` 的 `enabledPlugins`。由于 `plugins/cache` 通过 junction 与 user Home 共享，隔离会话的 cache 清扫会以自己可见的启用清单判定"在用"条目；若隔离 `settings.json` 缺少 user Home 刚启用的插件，共享缓存会被标记 `.orphaned_at` 并在宽限期后删除，两个 Home 同时失去该插件。因此 `enabledPlugins` 与 `extraKnownMarketplaces` 必须随每次启动合并进 state `settings.json`（2026-08-24 specflow 缓存被误孤立即为此类事故）。

## Codex 单一 Home

Codex 的用户配置只能有一个用户层根。若子进程使用隔离 runtime Home，同时又从 `~` 作为工作目录发现可信的 `~/.codex/config.toml`，后者会被当作 project-local config 读取；例如 `notify` 这样的用户级键会被原生 Codex 拒绝并警告。因此 Codex 不使用 state Home 投影，也不需要在 `cwd == Path.home()` 时执行特殊清理或目录授权。

从任意目录 `A` 启动时，ccs-plus 将子进程 `cwd` 保持为 `A`、`CODEX_HOME` 设为 `apps.codex.user_home`，再通过 `--profile ccs-plus-codex-...` 选择 provider。profile 仅包含 ccs-plus 所有的 provider 字段，API Key 仍通过子进程环境变量传递。

## User Home 作为工作目录

工作目录等于操作系统 user Home 不是关闭 Claude、Codex、Grok 用户扩展的条件。Claude 与 Grok 仍将真实 Home 的 MCP、plugin 与 skill 投影到各自隔离的 state Home；Codex 仍直接使用真实 `CODEX_HOME`。三端的子进程 `cwd` 都保持为用户传入的目录，ccs-plus 不复制或改写该目录的项目配置。

## 同步规则

`src/ccs_plus/home_visibility.py` 的 `link_user_entries()` 为 Claude、Grok 与 OpenCode 实现以下契约：

1. source 目录不存在时不创建 target，也不清理 state 内容。
2. source 与 target 是同一路径时不操作，避免自引用。
3. target 根是文件或错误链接时，先移除后创建隔离容器；根目录本身仍由 state Home 管理，以容纳该 app 的隔离 `skip` 条目。
4. source 子条目与 target 同名时，正确指向 source 的链接保持不变；其他 target 文件、目录和链接均先移除，再创建链接或复制。
5. `copy_names` 中的普通文件每次覆盖复制；其他文件优先硬链接，无法硬链接时创建符号链接。
6. `skip_names` 是 state-owned 例外：source 中同名条目不会触碰 target。

Windows 原生插件缓存可包含只读 Git object。删除 state target 时必须递归清除只读属性并重试，不能因 `WinError 5` 保留陈旧 cache。每个 target projection 使用 state 侧锁，避免多个 `ccsp launch` 并发删除和重建同一目录。若仍因文件锁而失败，启动器会记录链接或复制失败，且不会改写用户 Home；关闭占用该 state Home 的 CLI 进程后重新执行相同的 `ccsp launch`，让同步重新建立权威投影。

## 修改守则

修改 visibility 代码或 `settings.yaml` 的 copy/skip 配置前，先为每个条目确定权威来源。不要以“state 里已有内容”为保留理由；只有本表明确列为 state-owned 的条目才可保留。

变更必须至少覆盖以下测试状态：

- target 不存在；
- target 是同名实体目录；
- target 是同名实体文件；
- target 是悬挂链接或指向错误 source 的链接；
- `skip` 的 state-owned target 保持不变；
- Codex 从普通目录和 `Path.home()` 启动时都保持 cwd，不传 `--cd`/`--add-dir`，且使用同一真实 user Home；
- Claude/Grok 从 `Path.home()` 启动时仍投影用户 MCP、plugin 与 skill，且保持 cwd；
- Codex managed profile 不包含用户扩展表或 `[projects]`，且 cache 不自动创建 enablement。

实现完成后运行：

```powershell
uv run pytest tests/test_home_visibility.py tests/test_launcher.py tests/test_managed_config.py -q
uv run ruff format --check src/ccs_plus/home_visibility.py tests/test_home_visibility.py
uv run ruff check src/ccs_plus/home_visibility.py tests/test_home_visibility.py
uv run mypy src
```

相关实现位于 `src/ccs_plus/launcher.py`、`src/ccs_plus/managed_config.py` 和 `src/ccs_plus/home_visibility.py`，回归夹具位于 `tests/test_launcher.py`、`tests/test_managed_config.py` 与 `tests/test_home_visibility.py`。受管启动的更完整背景与验收状态见 [`20260818-codex-extension-visibility`](../requirement/20260818-codex-extension-visibility.md)。
