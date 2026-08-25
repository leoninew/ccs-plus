# 受管启动的用户与项目扩展可见性计划
最后修改时间: 2026-08-25 15:38:09

Review status: Accepted

## Requirement Basis

依据已接受的 [Requirement](../requirement/20260818-codex-extension-visibility.md)：

- 从任意目录 `A` 启动 Claude、Codex、Grok 时，provider 的 endpoint、模型与 API Key 保持隔离，同时继续发现各 CLI 原生支持的 user-home 与项目级 MCP、plugins、skills 和相关设施。
- Claude/Grok 无论从何处启动都投影 user Home 扩展；Codex 使用真实 user Home，不使用 visibility。
- `A == Path.home()` 不改变 cwd、不附加目录授权、不写 project trust，也不关闭用户扩展。
- Codex profile 仅写 provider 字段，且更新不触及基础 `config.toml`、plugin registry、marketplace、cache 或 session。

## Design

### 可见性与配置优先级

Claude 与 Grok 保持 stable isolated runtime home（`data/claude`、`data/grok`）与 provider/authentication 隔离，不将整个 user Home 挂载为运行 Home。

对于 Claude/Grok 的允许继承扩展配置，按各自 state 与真实 user Home 的既有策略合并，user Home 同名项优先。provider endpoint、API Key、模型、权限、认证与其他私有运行表绝不参与该合并。Codex 没有此合并层。

Codex managed profile 的旧“保留扩展表再合并”策略已由本次单一 Home 决策取代；profile 不再承担用户扩展配置。

目录策略按 CLI 语义区分：Claude/Grok 的 skills 与 plugin 条目继续逐条 link/copy/skip；Codex 不链接、复制或诊断 user Home cache，由原生 Codex 管理其 cache 与注册状态。

### 2026-08-25 Codex 单一真实 Home

Codex 不再使用隔离 runtime Home，也不再构造 HomeVisibility。每次 Codex launch 的 runtime Home 取 `settings.codex.user_home`（默认 `~/.codex`），并由 `CodexLauncher` 写入 `CODEX_HOME`。该目录同时承载用户基础配置、原生 MCP/plugin/skill、会话状态和 ccs-plus 受管 profile。

受管 profile 仍以 provider 数据库主键命名，仍通过环境变量提供 API Key，但重建时只写 provider 必需字段。它不复制或保留 `mcp_servers`、`plugins`、`marketplaces`、`shell_environment_policy` 和 `[projects]`。这会在 profile 下次 `ensure()` 时清除历史 OS user-Home trust，不影响用户 `config.toml` 中的项目 trust。

因此 Codex 不链接或合并 sessions、skills、plugins、cache 或 base `config.toml`；这些路径根本不进入 visibility 代码。启动子进程继续由 `subprocess.run(..., cwd=A)` 执行，不构造 `--cd` 或 `--add-dir`。`A == Path.home()` 没有特殊处理：原生 Codex 在其唯一 user Home 中处理用户配置与 project discovery。

### CLI 独立的 visibility 配置

`settings.yaml` 继续在 `apps.claude.visibility` 与 `apps.grok.visibility` 声明各自的 MCP/table 合并键与目录 copy/skip 策略。Codex visibility 配置已删除。共同且不可变的原生目录名称维持共用实现，其他策略不设共享默认值或跨端回退。

### 主键 Profile 与无备份写入

provider 数据库主键继续作为受管 profile 名、运行时 API Key 环境变量名和 ownership marker 的唯一身份；同一 provider 记录的重复启动直接覆盖该主键对应的同一 profile。不以 provider 名称重算 identity，不在 launch 业务逻辑中读取、迁移或删除历史 profile。历史文件仅在会话停止后通过离线维护清理。

受管配置更新只保留文件锁、写入 `fsync` 和 `os.replace` 的原子替换；移除每次覆盖前生成 `.ccs-plus.bak` 的逻辑。原子写入临时文件在替换完成或异常时被清除，不作为持久备份产物。

### 当前目录与 user-Home 启动

launcher 继续把用户选定的 `cwd` 原样传给原生 CLI。实现与测试不得将隔离 Home 覆盖到项目目录，也不得手动复制项目配置来模拟 CLI 发现；应验证 Codex、Claude、Grok 在其原生支持的项目级 skills/MCP/plugins/指令配置下仍以该 `cwd` 工作。

Claude 与 Grok 无论 `cwd` 是否为 `Path.home()`，均投影用户 Home 的 MCP、plugin 与 skill 到各自隔离 runtime Home。Codex 不使用 visibility，因为它没有第二个 runtime Home；无论 cwd 为何均使用唯一真实 user Home。OpenCode 保留既有的 user-Home 禁用路径，不属于本次三端目标。

## Implementation Steps

0. **统一 Codex 运行 Home**
- 将 Codex launch、session 查询与 managed-profile 清理使用的 Home 统一为 `settings.codex.user_home`；不保留第二个 Codex runtime-root 配置。
   - 删除 Codex visibility 与其配置；移除 profile 合并中对 extension tables 和 `[projects]` 的保留/投影，确保旧 profile 下次重建会清掉 OS user-Home trust。
   - 保持 `LaunchSpec.cwd=A` 和现有 provider/profile/API Key 注入；不得引入 `--cd`、`--add-dir`、trust 写入或真实 user `config.toml` 的改写。

1. **保留 Claude/Grok 用户扩展投影**
   - 保持 `apps.claude.visibility` 与 `apps.grok.visibility` 的合并键及 entry copy/skip 策略。
   - 当 `cwd == Path.home()` 时，Claude/Grok 继续创建并应用各自的 visibility；只有 OpenCode 保留旧的禁用分支。

2. **收敛 Codex profile 与扩展路径**
   - 修改 `CodexManagedConfig.ensure()`，只重建 ccs-plus 拥有的 provider 核心字段，不保留 extension tables 或 `projects`。
   - 删除 Codex 的 state/user TOML 合并与 skills/plugins/cache 链接职责；真实 Home 基础 `config.toml` 与目录由原生 Codex 正常加载。
   - 保留 Claude/Grok 的既有目录和配置投影策略，它们不从本次 Codex 收敛中获益或受影响。

3. **审计并补齐 Claude/Grok 同类重建路径**
   - Claude 保留 `skills`/`plugins` 的 link/copy/skip 语义，并将 `mcpServers` 的合并来源和目标状态文件纳入重复启动回归。
   - Grok 保留 skills/plugins/hooks/installed-plugin registry 的既有可见性和复制策略；验证其 state `config.toml` 重写后不丢失允许继承的 MCP、plugin 与 marketplace 配置。
   - 验证从 user Home 启动 Claude/Grok 时仍投影 MCP、plugin 与 skill；Codex 直接从真实 Home 加载，三端均保持原始 `cwd`。

4. **覆盖项目级原生发现**
   - 为每个 CLI 建立最小项目夹具，包含该 CLI 当前版本可识别的项目级 skill、MCP、 plugin 或指令配置。
   - 通过 `build_launch_spec` 和必要的 CLI 层测试断言受管启动仍保留项目 `cwd` 与相关 project trust/config，不将这些设施意外解析为 user-home visibility。

5. **取消受管配置旁路备份**
   - 保持 provider 数据库主键派生 profile、环境变量键和 ownership marker 的现有隔离语义，不增加自动迁移路径。
   - 去除 managed config 写入的 `.ccs-plus.bak`，为重复 ensure 补充不生成备份的单元测试；历史 profile 由会话停止后的离线维护处理。

## Files to Change

| 文件 | 计划变更 |
| --- | --- |
| `src/ccs_plus/home_visibility.py` | 保持 Claude/Grok 的可见性投影；删除 Codex extension/config/project-trust 合并路径。 |
| `src/ccs_plus/managed_config.py` | Codex profile 仅重建 provider 核心字段，清理历史 extension tables 与 `[projects]`。 |
| `src/ccs_plus/launcher.py` | 以真实 Codex user Home 构建 `CODEX_HOME`，保持 project cwd 原样传递且不追加 `--cd`/`--add-dir`。 |
| `src/ccs_plus/sessions.py`、`src/ccs_plus/cli.py` | 将 Codex 会话查询和受管 profile 清理切换到唯一真实 user Home。 |
| `tests/test_home_visibility.py` | Claude/Grok 的目录与配置投影回归；Codex 不再有 visibility 测试。 |
| `tests/test_managed_config.py` | Codex profile repeated-ensure、provider 隔离与不保留用户扩展表的测试。 |
| `tests/test_launcher.py` | 三端项目 cwd、project-level facility 与 user-Home 启动回归测试。 |
| `README.md` | 运行时隔离和扩展可见性行为说明。 |

## Verification Plan

- 单元：对 Codex managed profile 连续执行两次 ensure，确认 provider 核心字段稳定，历史 extension tables 与 `[projects]` 不会保留或重新写入，API Key 不落盘。
- 单元：Claude、Grok 的重复 launch/config 写入后，skills、plugins、MCP 及既有 registry/索引策略不回退；临时目录仍不共享。
- 单元：Codex launch 不链接或合并用户扩展；base config、MCP、plugin 与 skill 都只从 `CODEX_HOME=~/.codex` 的原生位置加载。
- 单元：项目目录和 `Path.home()` 启动都保留三端 `cwd`。Codex argv 不含 `--cd`/`--add-dir`，两者使用同一真实 Codex Home；Claude/Grok 在 user Home 启动时仍投影用户 MCP、plugin 与 skill。
- 单元：同一 provider 主键的重复 ensure 复用同一 profile/env key，且不生成 `.ccs-plus.bak`。
- 回归：运行现有 `pytest` 覆盖 launcher、managed config、home visibility、settings 与 TUI 关联用例。
- 工程：根据项目入口运行 lint、类型检查、格式和完整测试。

## Assumptions and Risks

- 本次明确不保留 Codex profile 的 extension tables 或 `[projects]`；这些值属于唯一真实 user Home 的 base config，而非 provider profile。Claude/Grok 仍遵循各自已接受的保留策略。
- 三个 CLI 的项目级发现协议会随版本改变；测试夹具必须使用已验证的原生机制，不能以 ccs-plus 私有目录约定替代。

## Rollback

- 回滚不恢复第二个 Codex runtime Home；不会自动删除真实 user Home 中已创建的 ccs-plus managed profile，需由既有 provider cleanup 命令显式处理。
- 若 Claude/Grok 的投影引入异常扩展加载，可仅恢复 OpenCode 的 user-Home 禁用分支；不得将 Codex 恢复为第二个 Home 投影方案。
