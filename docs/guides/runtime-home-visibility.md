# Runtime Home 可见性与权威来源

最后修改时间: 2026-08-24 18:01:47

`ccsp launch` 同时使用真实用户 Home 与隔离的 state Home。用户 Home 保存用户主动安装、
启用和维护的扩展；state Home 只保存 ccs-plus 的 provider runtime 状态。两者不能互为
备份或平级来源。

本文以 `~/.codex` 等默认路径说明；实际 source 是 `settings.yaml` 中配置的对应 app
`user_home`。

## 不变量

对由真实用户 Home 提供的可见性条目，用户 Home 是唯一权威来源。每次受管启动同步时，
source 中存在的目录或文件必须覆盖同名 state target，不得因 target 已是实体目录、实体
文件、悬挂链接或指向其他来源的链接而保留旧内容。

这条规则适用于 `link_user_entries()` 管理的 user-owned entries，以及 Codex 的
`sessions` 链接。它不表示整个 state Home 都可以被用户 Home 覆盖。

## 权威来源表

| 内容 | 权威来源 | state Home 行为 |
| --- | --- | --- |
| 用户 skills、plugins、hooks、OpenCode 用户配置条目 | 对应 `~` 下 app Home | 同名 target 覆盖后链接；声明为 copy 的文件覆盖复制。 |
| Codex `plugins/cache` | `~/.codex/plugins/cache` | 作为一个整体链接；已有 state 实体 cache 或错误链接必须替换。 |
| Codex `sessions` | `~/.codex/sessions` | 作为一个整体链接；不保留 state 的第二份 sessions 目录。 |
| MCP、plugin enablement、marketplace 等允许继承的配置表 | 真实 user Home `config.toml` | 按既有 profile/state 再到 user Home 的顺序合并；同名 user 配置最终覆盖。 |
| Codex plugin appserver、remote install staging | state Home | 明确 `skip`，不链接、不复制、不可被 user Home 覆盖。 |
| provider profile、认证、SQLite state、临时运行文件 | state Home | 不参与 user-home visibility。 |

`plugins/cache` 的内容可见不等于插件已启用。启用仍取决于 `[plugins]` 与
`[marketplaces]` 注册；不得从缓存目录反推或自动写入 enablement。

## 同步规则

`src/ccs_plus/home_visibility.py` 的 `link_user_entries()` 实现以下契约：

1. source 目录不存在时不创建 target，也不清理 state 内容。
2. source 与 target 是同一路径时不操作，避免自引用。
3. target 根是文件或错误链接时，先移除后创建隔离容器；根目录本身仍由 state Home 管理，
   以容纳该 app 的隔离 `skip` 条目。
4. source 子条目与 target 同名时，正确指向 source 的链接保持不变；其他 target 文件、
   目录和链接均先移除，再创建链接或复制。
5. `copy_names` 中的普通文件每次覆盖复制；其他文件优先硬链接，无法硬链接时创建符号链接。
6. `skip_names` 是 state-owned 例外：source 中同名条目不会触碰 target。

Windows 原生插件缓存可包含只读 Git object。删除 state target 时必须递归清除只读属性并
重试，不能因 `WinError 5` 保留陈旧 cache。每个 target projection 使用 state 侧锁，避免
多个 `ccsp launch` 并发删除和重建同一目录。若仍因文件锁而失败，启动器会记录链接或复制
失败，且不会改写用户 Home；关闭占用该 state Home 的 CLI 进程后重新执行相同的
`ccsp launch`，让同步重新建立权威投影。

## Codex Cache 的历史与结论

曾经有两种相互冲突的实现：先为避免陈旧 cache 建立 state 侧实体 cache，后又恢复共享
`~/.codex/plugins/cache`。恢复共享时复用了“已有实体 target 保持不动”的通用逻辑，导致
早期实体 cache 永久遮蔽 user cache，出现插件 manifest 丢失而 skill 无法发现的状态。

结论不是在“隔离 cache”与“共享 cache”间折返，而是固定以下边界：

- 插件包 cache 是用户安装状态，必须从 user Home 投影到 state Home。
- provider 与 plugin runtime 临时目录是受管状态，必须继续隔离。
- plugin 注册是用户配置，user Home 对同名注册有最高优先级。

不要为某个 marketplace、plugin 或 skill 增加例外。`best-practices`、`dev-commit` 只能
作为回归样本，不能成为实现分支。

## 修改守则

修改 visibility 代码或 `settings.yaml` 的 copy/skip 配置前，先为每个条目确定权威来源。
不要以“state 里已有内容”为保留理由；只有本表明确列为 state-owned 的条目才可保留。

变更必须至少覆盖以下测试状态：

- target 不存在；
- target 是同名实体目录；
- target 是同名实体文件；
- target 是悬挂链接或指向错误 source 的链接；
- `skip` 的 state-owned target 保持不变；
- Codex `plugins/cache` 的完整 manifest 与 skill 能通过 target 链接可见；
- user 配置覆盖同名 state/profile 配置，但 cache 不自动创建 enablement。

实现完成后运行：

```powershell
uv run pytest tests/test_home_visibility.py tests/test_launcher.py tests/test_managed_config.py -q
uv run ruff format --check src/ccs_plus/home_visibility.py tests/test_home_visibility.py
uv run ruff check src/ccs_plus/home_visibility.py tests/test_home_visibility.py
uv run mypy src
```

相关实现位于 `src/ccs_plus/home_visibility.py`，回归夹具位于
`tests/test_home_visibility.py`。受管启动的更完整背景与验收状态见
[`20260818-codex-extension-visibility`](../requirement/20260818-codex-extension-visibility.md)。
