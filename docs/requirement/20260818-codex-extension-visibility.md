# 受管启动的用户与项目扩展可见性
最后修改时间: 2026-08-25 15:45:20

Review status: Accepted

## Background

`ccs-plus launch <cli> --provider <provider>` 为 Claude、Codex 和 Grok 隔离 provider 的 endpoint、模型选择与 API Key。目标行为是：从项目目录启动时，受管会话继续发现真实 user Home 与当前项目目录中由原生 CLI 支持的 skills、MCP、plugins 及相关扩展设施。Claude/Grok 仍使用隔离 runtime Home；Codex 使用真实 user Home，因而不再按 provider 隔离 session、用户偏好或原生 plugin 状态。

实际检查发现，2026-08-11 生成的旧 managed profile 含 `best-practices@best-practices-local`、对应 marketplace 与多个 MCP；2026-08-18 重新生成的 Sub2API profile 只保留当前全局配置中仍可见的 MCP 和内建插件。 `~/.codex/plugins/cache/best-practices-local/best-practices/0.1.0` 存在完整缓存，但当前 `~/.codex/config.toml` 没有该插件的 marketplace 与 enabled 注册。 `best-practices` 仅是暴露问题的代表性回归样本，不是本需求的特殊处理目标；修复必须覆盖所有由对应原生 CLI 正式声明和启用的 MCP、plugin、skill 及项目级设施。

根因是 Codex managed profile 重建时仅保留旧 profile 的 `projects`，随后从 state home 和 user home 合并有限配置。MCP 会从 state/user config 合并，plugins 与 marketplaces 仅从当前 user-home config 复制。旧 profile 中已有效的扩展注册因此会在重建时丢失；仅有缓存的插件也无法被 Codex 当作已安装插件加载。

补充现场证据表明，plugin 仓库的 `sync.sh` 运行在 Git Bash 时可能继承 `CODEX_HOME`/`GROK_HOME` 的受管 runtime 值，并把 `/d/...` 的 POSIX 路径直接传给 Windows 原生 `codex`。前者会把 skill 或 registry 写进 Orca/ccs-plus runtime home，后者会使 `codex plugin marketplace add` 拒绝本地来源。因此真实 `~/.codex` 可能只留下 cache，缺少原生 plugin/marketplace 注册。该同步脚本边界也必须修复，不能由 launch 阶段把 cache 推断为已安装插件。

近期实现历史曾尝试将 Codex plugin cache 和其他用户设施投影到隔离 runtime Home。这会形成两个候选用户配置根，并让 cache、注册表和 profile 的优先级变得不可判定。2026-08-25 的单一真实 Home 决策废弃了该策略：cache 是否可用完全由真实 `~/.codex` 和原生 Codex 管理。

现场清理进一步确认，受管 Codex profile 文件名由 provider 数据库主键的哈希构成；同一 provider 记录的重复启动会复用同一 profile。问题不在 profile identity，而是每次 `ensure()` 覆盖配置前都会生成 `.ccs-plus.bak`，这不是 provider 隔离所需状态。

现有 `HomeVisibility` 为 Claude、Grok 与 OpenCode 建立目录和配置同步策略。旧实现曾在工作目录等于操作系统 user Home 时整体禁用 visibility；这会让 Claude/Grok 丢失用户 MCP、plugin、skill。当前约束是：只保留 OpenCode 的旧分支，Claude/Grok 无论工作目录为何都投影用户扩展，Codex 不进入 visibility。

## 2026-08-25 Codex 单一 Home 修正

现场从 `C:\Users\wangm25` 执行 `ccsp run x2` 时，Codex 报告：

```text
Ignored unsupported project-local config keys in C:\Users\wangm25\.codex\config.toml: notify
```

根因不是 `notify` 配置错误。启动器将 `CODEX_HOME` 设为隔离 runtime Home，但工作目录仍为 `C:\Users\wangm25`。真实 `~/.codex/config.toml` 因而在 project discovery 中被作为可信项目配置读取；`notify` 是 Codex 明确禁止的项目级键。旧受管 profile 还会持久化真实 user Home 的 `[projects]` trust，且后续 `ensure()` 原样保留该记录，使早先的“在 user Home 禁用 visibility”无法消除已写入的错误状态。

这说明 Codex 不能同时把隔离 runtime Home 和 `~/.codex` 当作两个用户配置根，再依靠 link 和 TOML 合并模拟原生行为。对 Codex，以下约束替代本文件中所有“隔离 Codex runtime home、复制/链接 Codex 用户扩展或在 user Home 禁用 Codex visibility”的旧表述；Claude 与 Grok 仍保持隔离 runtime Home，但无论工作目录是否为 OS user Home，都必须继续投影用户扩展：

- Codex 子进程的 `CODEX_HOME` 必须是配置的真实 Codex user Home（默认 `~/.codex`），且该目录是唯一的 Codex 配置、MCP、plugin、skill、session 与状态根。
- `ccs-plus` 受管 provider profile 写入这个真实 Home，并只持有 provider 所需的 `model_provider`、模型、权限与 `[model_providers]`；API Key 仍只通过子进程环境变量传递。profile 不复制 `mcp_servers`、`plugins`、`marketplaces`、shell policy 或 `[projects]`。
- 启动器不得对 Codex 执行 user-home visibility、目录链接、配置表合并或 project trust 投影；这些配置由原生 Codex 在同一个 Home 内按原生层级加载。
- 原生子进程工作目录始终为用户启动 `ccsp` 时的 `A`。不传 `--cd` 或 `--add-dir`；`A == Path.home()` 也不走特殊分支。

## Historical basis

本需求合并下列历史 SpecFlow 记录的有效约束。它们已在本实现中移除；本文件及对应 Plan/Verification 是后续修复的统一过程来源。

| 历史文档 | 已合并的约束或证据 | 本需求的处理 |
| --- | --- | --- |
| 20260811 link/merge requirement 与 plan（已移除） | 确立“能 link 就 link、需要 merge 就 merge、运行 Home 不全量 hybrid”；skills/plugins 逐条链接；Codex plugin 启用依赖 `[plugins]` 与 `[marketplaces]`，不只是 cache。 | Claude/Grok 保留条目级投影。Codex 不再链接 cache 或扩展目录，改由真实 Home 的原生注册和缓存直接决定。 |
| 20260814 MCP propagation requirement（已移除） | Codex state home 与 user home 的 MCP 应合并；同名 user MCP 覆盖 state 项。 | Codex 改为直接读取真实 Home，不再有 state/user 合并；Claude/Grok 保持各自的用户配置覆盖规则。 |
| 20260815 home visibility requirement 与 verification（已移除） | `HomeVisibility` 三端抽象已上线且验收通过；Claude、Codex、Grok 目录共享、配置合并、缓存隔离和 user-home 覆盖已具备实现与测试基础。 | 保留 Claude/Grok 的投影基础；移除 Codex visibility，并取消三端共用的 user-Home 禁用。 |
| 20260728 Codex MCP inheritance requirement（已移除） | 在不破坏 provider 隔离下继承用户 Codex MCP 的最初需求和风险边界。 | Codex 在真实 Home 原生加载 MCP；provider profile 只覆盖 provider 字段。 |
| `docs/archive/requirement/20260716-codex-hybrid-home-sessions.md`、`docs/archive/requirement/20260720-grok-hybrid-home-sessions.md` 及对应 verification | 早期临时 Home 的全量非私有条目共享、会话继承和 Windows 链接策略先例。 | 仅吸收“用户 Home 不作为认证/配置写入目标”和链接安全约束；明确不恢复全量 hybrid、临时 Home 清理或会话共享方案，当前稳定 `data/*` runtime home 保持不变。 |

历史约束的冲突已显式收口：20260811 的 Codex user-home 配置“整表覆盖”依赖 state/user 双 Home。当前不再合并 Codex profile、state 与 user 配置，所有 MCP、plugin、skill、cache 与注册状态由唯一真实 Home 的原生规则决定。

## Goal

- Claude、Codex 与 Grok 从任意目录 `A` 启动时，均按指定 provider 注入 endpoint、模型和 API Key。
- Claude/Grok 的隔离 runtime Home 始终可见真实 user Home 中用户主动配置的 MCP、plugins 和 skills；Codex 始终直接使用真实 `~/.codex`。
- 子进程工作目录始终为 `A`，不传 `--cd` 或 `--add-dir`，不复制、覆盖或替换项目级配置。由原生 CLI 支持的项目级扩展继续按原生规则发现。
- `A == Path.home()` 不关闭 Claude/Grok 的用户扩展投影；Codex 在相同真实 Home 中原生加载，不走 visibility、trust 或配置复制分支。
- Codex 受管 profile 只写 provider 所需字段，API Key 只经子进程环境变量传递；profile 更新保持锁与原子替换，不生成 `.ccs-plus.bak`。

## Non-goal

- 不改写用户基础 `config.toml`、plugin registry 或 marketplace 配置，也不根据 cache 自动启用 plugin。
- 不为 Codex 保持按 provider 分隔的会话数据库、用户偏好或 plugin runtime；这些状态属于唯一真实 `CODEX_HOME`。
- 不自定义或重实现各 CLI 的项目级扩展发现协议；只保证受管启动不破坏原生发现。
- 不新增工作目录重写、额外目录授权、project trust 写入或遗留运行目录兼容逻辑。

## User scenarios

1. 用户在项目目录通过指定 provider 启动 Codex，已安装的 user MCP、plugin、skill 和项目级原生设施继续可用。
2. 用户在项目目录通过任一受支持 provider 启动 Claude 或 Grok，仍可使用各自 user Home 中启用的 skills、plugins、MCP 和项目目录声明的原生设施。
3. 用户从操作系统 user Home 启动 Claude、Codex 或 Grok 时，仍可使用用户 Home 的 MCP、plugin、skill；provider 隔离和原生 `cwd` 不变。
4. 用户从任意目录 `A` 执行 `ccsp run x2` 时，Codex 以 `A` 为工作目录、使用 `x2` 对应 provider，并原生加载 `~/.codex` 中的 MCP、plugin 与 skill；不会把该文件再当成 project-local config 而警告 `notify`。
5. 用户从 `~` 执行同一命令时，不发生 cwd 重写、额外目录授权、trust 写入或配置复制；行为与原生 `codex --profile <managed-profile>` 一致。

## Acceptance

- Claude/Grok 的隔离 runtime Home 在普通目录和 `Path.home()` 启动时都可见 user Home 的 MCP、plugin、skill，且子进程 `cwd` 未改变。
- Codex launch 的 `CODEX_HOME` 等于真实 user Home；生成的受管 profile 位于同一目录，只含 provider 字段，不含扩展表或 `[projects]`，API Key 不落盘。
- 从普通目录和 `Path.home()` 分别构建 Codex launch spec，均断言 `cwd` 未改变、argv 不含 `--cd`/`--add-dir`、`CODEX_HOME` 是真实 user Home；后者不再出现 project-local `notify` 警告的配置前提。
- 从项目目录启动的测试证明三端的 `cwd` 未被 ccs-plus 改写；项目级 skills、MCP、plugins 仍由对应原生 CLI 在该目录决定是否发现。
- 同一 provider 的重复 profile 更新使用同一 ownership marker、文件锁和原子替换，且不生成 `.ccs-plus.bak`。
- 相关单元测试、项目 lint、类型检查和定向测试通过。

## Open questions

- 当前目录声明的“设施”在 Claude、Codex、Grok 中需要覆盖哪些原生机制？本需求默认覆盖各 CLI 当前版本原生支持的项目级 skills、MCP、plugins 与指令/配置发现，不新增 `ccs-plus` 私有格式；实现阶段需基于对应 CLI 的实际发现规则列出精确测试夹具。
- Codex 的共享 session 与用户偏好是否需要未来按 provider 分隔？当前结论是否定的：若需要该能力，应由原生 Codex 支持可组合的 user config/profile 机制后另立需求，不能恢复第二个 Home 投影。

## Decisions

- 当前工作目录始终原样传给原生 CLI；`ccs-plus` 不复制、覆盖或替换其项目级扩展配置。
- 工作目录等于操作系统 user Home 时，Claude/Grok 继续投影用户扩展；Codex 继续以真实 user Home 直接加载。三端均不重写 `cwd`、不复制项目配置、不写 project trust。
- Codex managed profile 不保留或同步 `[projects]`；历史 profile 中的 OS user-Home trust 必须在下一次该 profile `ensure()` 时移除，避免真实 user config 被误当作项目配置。
- Codex user configuration、plugin registry、marketplace、cache 与 session 是唯一真实 Home 的原生状态；ccs-plus 不投影、合并或从 cache 推断 enablement。
- Claude/Grok 的可见性合并键和目录 copy/skip 策略分别声明在 `apps.<cli>.visibility`；Codex 不再拥有 visibility 配置。
- provider 数据库主键继续同时作为受管 profile、环境变量键和 ownership marker 的身份；不按名称派生 identity，也不在 launch 业务逻辑中自动迁移或删除历史 profile。历史文件只在所有相关会话结束后离线清理。

## Risk

- Codex CLI 升级可能改变 profile 的覆盖语义；测试应基于 provider、cwd 与用户可见扩展行为，而非只断言内部目录。
- Claude 与 Grok 的项目级发现规则可能不同；错误地手动复制项目目录的配置会绕过原生信任与优先级模型，或将项目级配置错误带入 user Home 启动。
- 错误合并 `model_providers`、认证或权限配置会破坏 provider 隔离；Codex profile 只能写 ccs-plus 明确拥有的 provider 字段。
- Codex 的受管 profile 与用户原生 Codex 同时写入真实 Home；实现必须继续使用现有锁和原子替换，并将写入范围限于 ccs-plus ownership marker 对应的 profile 文件。
