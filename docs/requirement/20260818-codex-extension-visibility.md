# 受管启动的用户与项目扩展可见性
最后修改时间: 2026-08-24 16:56:32

Review status: Accepted

## Background

`ccs-plus launch <cli> --provider <provider>` 为 Claude、Codex 和 Grok 启动
provider 隔离的 runtime home。目标行为是：从项目目录启动时，受管会话继续发现
真实 user home 与当前项目目录中由原生 CLI 支持的 skills、MCP、plugins 及相关
扩展设施；认证、provider endpoint、API Key、模型和运行时状态仍保持隔离。

实际检查发现，2026-08-11 生成的旧 managed profile 含
`best-practices@best-practices-local`、对应 marketplace 与多个 MCP；2026-08-18
重新生成的 Sub2API profile 只保留当前全局配置中仍可见的 MCP 和内建插件。
`~/.codex/plugins/cache/best-practices-local/best-practices/0.1.0` 存在完整缓存，
但当前 `~/.codex/config.toml` 没有该插件的 marketplace 与 enabled 注册。
`best-practices` 仅是暴露问题的代表性回归样本，不是本需求的特殊处理目标；修复必须
覆盖所有由对应原生 CLI 正式声明和启用的 MCP、plugin、skill 及项目级设施。

根因是 Codex managed profile 重建时仅保留旧 profile 的 `projects`，随后从
state home 和 user home 合并有限配置。MCP 会从 state/user config 合并，plugins
与 marketplaces 仅从当前 user-home config 复制。旧 profile 中已有效的扩展注册
因此会在重建时丢失；仅有缓存的插件也无法被 Codex 当作已安装插件加载。

补充现场证据表明，plugin 仓库的 `sync.sh` 运行在 Git Bash 时可能继承
`CODEX_HOME`/`GROK_HOME` 的受管 runtime 值，并把 `/d/...` 的 POSIX 路径直接传给
Windows 原生 `codex`。前者会把 skill 或 registry 写进 Orca/ccs-plus runtime home，
后者会使 `codex plugin marketplace add` 拒绝本地来源。因此真实 `~/.codex` 可能只留下
cache，缺少原生 plugin/marketplace 注册。该同步脚本边界也必须修复，不能由 launch
阶段把 cache 推断为已安装插件。

近期实现历史进一步确认，`03e063e` 曾将 Codex plugin cache 隔离为 state 侧实体目录，
`76fecae` 又恢复为共享 user cache；后者沿用了通用的“目标端已有实体条目则保持不动”
规则。因此历史实体 `data/codex/plugins/cache` 会遮蔽完整的
`~/.codex/plugins/cache`，无法随下一次启动恢复。Codex plugin cache 不应遵循该通用
条目保留规则，而应以真实 user Home 的 cache 根目录为权威来源。

现场清理进一步确认，受管 Codex profile 文件名由 provider 数据库主键的哈希构成；
同一 provider 记录的重复启动会复用同一 profile。问题不在 profile identity，而是每次
`ensure()` 覆盖配置前都会生成 `.ccs-plus.bak`，这不是 provider 隔离所需状态。

现有 `HomeVisibility` 已为三个 CLI 建立目录和配置同步策略，也已在工作目录等于
操作系统 user Home 时整体禁用 visibility。但该策略尚未以以下跨端保证约束：
受管 profile 的重复生成不能丢失可见扩展状态；当前工作目录的原生项目级发现不能
因隔离 Home 或 profile 合并被遮蔽；Claude 与 Grok 也需要纳入同一回归面。

## Historical basis

本需求合并下列历史 SpecFlow 记录的有效约束。它们已在本实现中移除；本文件及对应
Plan/Verification 是后续修复的统一过程来源。

| 历史文档 | 已合并的约束或证据 | 本需求的处理 |
| --- | --- | --- |
| 20260811 link/merge requirement 与 plan（已移除） | 确立“能 link 就 link、需要 merge 就 merge、运行 Home 不全量 hybrid”；skills/plugins 逐条链接；Codex plugin 启用依赖 `[plugins]` 与 `[marketplaces]`，不只是 cache。 | 保留隔离边界；skills 与普通 plugin 条目继续逐条 link，但 Codex `plugins/cache` 作为整体链接并由 user Home 权威覆盖已有 state 实体目录；同时保留 profile 重建策略。 |
| 20260814 MCP propagation requirement（已移除） | Codex state home 与 user home 的 MCP 应合并；同名 user MCP 覆盖 state 项。 | 沿用该优先级，并扩展到 profile/state 重建时不丢失不同名的既有允许继承项。 |
| 20260815 home visibility requirement 与 verification（已移除） | `HomeVisibility` 三端抽象已上线且验收通过；Claude、Codex、Grok 目录共享、配置合并、缓存隔离和 user-home 覆盖已具备实现与测试基础。 | 作为本次修复的直接基线；新增跨端重复重建、项目级发现和 user-Home 启动禁用的回归验收。 |
| 20260728 Codex MCP inheritance requirement（已移除） | 在不破坏 provider 隔离下继承用户 Codex MCP 的最初需求和风险边界。 | 保留 provider 核心配置隔离与 user MCP 优先级。 |
| `docs/archive/requirement/20260716-codex-hybrid-home-sessions.md`、`docs/archive/requirement/20260720-grok-hybrid-home-sessions.md` 及对应 verification | 早期临时 Home 的全量非私有条目共享、会话继承和 Windows 链接策略先例。 | 仅吸收“用户 Home 不作为认证/配置写入目标”和链接安全约束；明确不恢复全量 hybrid、临时 Home 清理或会话共享方案，当前稳定 `data/*` runtime home 保持不变。 |

历史约束的冲突已显式收口：20260811 的 Codex user-home 配置“整表覆盖”在当时用于
保证用户更新立即生效；本次保留该同名优先级，但增加对 user-home 未声明、既有
profile/state 仍有效扩展项的保留规则。缓存仍不是 enablement 的充分证据。

## Goal

- Claude、Codex 与 Grok 从项目目录启动时，继续发现各自真实 user home 中用户主动
  配置的 MCP、plugins 和 skills。
- 三端的受管配置/profile 重建不得丢失已启用的用户扩展状态，包括 MCP、plugin
  enablement、marketplace registration、skills 相关配置与必要的 shell policy。
- 真实 user home 的显式配置为权威来源，并能覆盖同名的旧 profile/state 配置。
- 受管会话保留当前工作目录中由原生 CLI 支持的项目级扩展发现；`ccs-plus` 不以
  隔离 Home 替换或遮蔽当前项目目录。
- 从操作系统 user Home 作为工作目录启动时，不应用 user-home visibility 和项目级
  扩展继承，避免自引用、重复加载和将个人 Home 误作项目。
- 对“缓存存在但未注册”的插件给出可预测、安全的行为与诊断，避免再次出现缓存存在
  而运行时不可发现的状态。
- Codex `plugins/cache` 以真实 user Home 为唯一内容来源；state Home 的同名实体目录或
  旧链接不能遮蔽该来源，启动后必须指向 user cache。
- 受管配置写入保持锁与原子替换，但不生成旁路 `.ccs-plus.bak` 文件。
- provider 的导出、导入与重置均支持 `claude`、`codex`、`grok` 作为可选前置；未指定
  app 时在各操作原有的过滤边界内同时处理三端数据。
- 安装包保留 `ccs-plus` 主命令，同时提供等价的 `ccsp` 短别名。

## Non-goal

- 不修改 `~/.claude`、`~/.codex`、`~/.grok` 或用户 plugin registry、marketplace
  配置；user home 仍由对应的原生 CLI 管理。
- 不共享 user-home 的认证、provider endpoint、API Key、会话数据库或临时运行目录。
- 不自动启用仅从 cache 推断出的未知插件，除非需求阶段明确接受该恢复策略。
- 不改变 provider 选择、模型、审批策略或 sandbox 行为。
- 不自定义或重实现各 CLI 的项目级扩展发现协议；只保证受管启动不破坏原生发现。

## User scenarios

1. 用户在项目目录通过 Sub2API 启动 Codex，任一已安装 plugin 及其 skill 均可继续
   使用，并加载 user-home MCP 与项目级 skills/MCP 等原生设施；
   `best-practices@best-practices-local` 是其中一个回归样本。
2. 用户在项目目录通过任一受支持 provider 启动 Claude 或 Grok，仍可使用各自 user
   home 中启用的 skills、plugins、MCP 和项目目录声明的原生设施。
3. 同一 provider profile/state 被多次重建后，已存在的 user MCP、marketplace 与
   enabled plugin 不会消失。
4. 用户在真实 user-home 配置中更新同名 MCP、plugin 或 marketplace 后，下一次受管
   启动使用用户配置，而不是旧 profile/state 的值。
5. 用户从操作系统 user Home 启动任一 CLI 时，不发生 user-home 或项目级扩展继承，
   但 provider 隔离和正常启动保持可用。
6. 若 cache 中存在插件但 user Home 没有其安装注册，启动结果可诊断，且不会在未授权
   情况下自动将缓存视为启用插件。
7. 用户可执行 `provider export codex`、`provider import codex <file>` 或
   `provider reset codex --yes` 仅维护一个 app；省略 app 时三条命令均处理三端。

## Acceptance

- Claude、Codex 与 Grok 的受管配置/profile/state 重建会保留允许继承的既有扩展项，
  再合并 state home 和 user home 的允许配置。
- 配置优先级明确且有测试：同名项由真实 user home 覆盖；user home 未声明的既有
  profile/state 扩展项按已接受的保留策略保持可用。
- `~/.claude`、`~/.codex`、`~/.grok` 的 skills 与各自已注册 plugins 的必要目录、索引
  与配置在隔离 runtime home 中可见，且临时运行目录仍隔离。
- 使用 Sub2API 的新 profile 与已有 profile 都覆盖 MCP、已注册 plugin、marketplace
  和 skill 发现；Claude/Grok 也有等价的回归测试。
- Codex state Home 的 `plugins/cache` 在目标缺失、目标为实体目录或目标链接错误时，均
  能恢复为指向 user Home cache 的链接；appserver 与 remote install staging 仍保持隔离。
- 从项目目录启动的测试证明原生项目级 skills、MCP、plugins 或等价扩展设施仍可发现；
  从 user Home 启动的测试证明这些 visibility 行为不执行。
- 当插件仅存 cache、未在 user Home 注册时，行为与诊断有测试覆盖；不隐式改变用户
  配置。
- `provider export`、`provider import`、`provider reset` 可选接受 app 前置；缺省与
  显式 `claude`、`codex`、`grok` 的三端并集等效。限定导入仍须完整验证备份后才过滤目标
  app，限定 reset 继续只删除非官方 provider。
- CLI 的 provider 管理命令组固定为单数 `provider`，不保留 `providers` 子命令别名；备份
  文件名和备份 JSON 的 `providers` 数据字段不受此命令命名约束影响。
- 顶层 `launch`、`provider`、`run` 分别提供 `l`、`p`、`r` 短用法，且每一对共用同一
  命令参数和执行逻辑。
- `ccs-plus` 与 `ccsp` 安装后指向同一个 CLI 入口，并保留相同的命令语义。
- 相关单元测试、项目 lint、类型检查和定向测试通过。

## Open questions

- 当前目录声明的“设施”在 Claude、Codex、Grok 中需要覆盖哪些原生机制？本需求默认
  覆盖各 CLI 当前版本原生支持的项目级 skills、MCP、plugins 与指令/配置发现，不新增
  `ccs-plus` 私有格式；实现阶段需基于对应 CLI 的实际发现规则列出精确测试夹具。
- 当插件仅存在于 `~/.codex/plugins/cache`，且不在真实 user-home config 或既有
  managed profile 注册时，是否应由 `ccs-plus` 仅报告该状态，还是提供显式的恢复动作？
  当前建议为仅报告，避免把用户已卸载的插件重新启用。

## Decisions

- 本需求新建记录，不修改已 Accepted 的 home visibility 与 MCP propagation 文档。
- 真实 user home 的显式配置为同名项的最高优先级。
- 已有 managed profile/state 的允许继承扩展配置是重建时的保留来源，但不能覆盖 user
  home 的更新。
- 当前工作目录始终原样传给原生 CLI；`ccs-plus` 不复制、覆盖或替换其项目级扩展配置。
- 工作目录等于操作系统 user Home 时禁用 visibility，保持现有隔离语义。
- 缓存本身不是插件已启用的证据；默认不由 `ccs-plus` 自动恢复为 enabled。
- Codex plugin package cache 与 plugin enablement 是两个独立问题：cache 根目录由 user
  Home 权威链接提供，是否启用仍只由 `[plugins]`/`[marketplaces]` 注册决定；不得从 cache
  反推 enablement。
- plugin 的同步脚本必须忽略继承的 runtime Home 变量，显式写入真实 user home，并向
  Windows 原生 CLI 传递其可识别的本地路径。
- Claude、Codex、Grok 的可见性合并键和目录 copy/skip 策略必须分别声明在
  `apps.<cli>.visibility`；不得在运行代码中以跨 CLI 常量固化。只有三端含义和值都相同
  的原生目录契约可以共用实现。
- provider 数据库主键继续同时作为受管 profile、环境变量键和 ownership marker 的身份；
  不按名称派生 identity，也不在 launch 业务逻辑中自动迁移或删除历史 profile。历史文件
  只在所有相关会话结束后离线清理。
- provider 数据维护命令使用可选 app 前置：`export [app] [output-path]`、
  `import [app] <input-path>`、`reset [app]`。保留既有 `export <output-path>` 与
  `import <input-path>` 形式；首个参数是 app 名称时按 app 处理。自动生成的 export
  文件名必须包含 app scope：未给 app 时为 `providers-all-<timestamp>.json`，给 app 时为
  `providers-<app>-<timestamp>.json`。
- 发行元数据将 `ccsp` 映射到与 `ccs-plus` 相同的 `ccs_plus.cli:main` 入口，不引入
  第二个 CLI 实现或改变输出中的主产品名称。

## Risk

- 保留 profile/state 扩展项可能继续暴露用户后来从全局配置移除的插件或 MCP；需在
  实现中明确保留、显式覆盖和显式移除的边界。
- Codex CLI 升级可能继续改变插件注册文件、缓存或 profile 合并语义，测试应基于
  配置结果与用户可见行为，而非只断言内部目录。
- Claude 与 Grok 的项目级发现规则可能不同；错误地手动复制项目目录的配置会绕过原生
  信任与优先级模型，或将项目级配置错误带入 user Home 启动。
- 错误合并 `model_providers`、认证或权限配置会破坏 provider 隔离，修复只能扩展
  允许继承的用户扩展表。
- 自动生成备份不再可用于恢复受管 profile 的历史版本；用户需要历史恢复时应使用显式
  provider 导出或操作系统备份，而不是依赖 launch 副作用。
- `export` 的 app-first 语法与输出路径恰好为 `claude`、`codex` 或 `grok` 存在位置歧义；
  该罕见路径应使用其他文件名或显式目录，避免被解析为 app。
- 同步脚本若继续接受 `CODEX_HOME` 作为默认目标，会在 Orca 或受管会话内再次把用户
  安装写入隔离 Home；需使用独立的显式 user-home 覆盖变量。
