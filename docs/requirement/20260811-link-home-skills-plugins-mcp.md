# Codex / Claude 启动时选择性链接 Home Skills、Plugins 并合并 MCP（非 hybrid 全量共享）

最后修改时间: 2026-08-11 14:30:00

Review status: Accepted

Flow mode: standard / 标准模式

## Strategy

本需求的启动时可见性策略，一句话概括：**能 link 就 link，需要 merge 就 merge，运行 home 不 hybrid 全量共享。**

- **能 link 就 link**：`skills`、`plugins` 这类「目录树下的条目」用链接（Windows junction / POSIX symlink；文件 hardlink → symlink → 跳过）**逐条**带进隔离 home，实时可见、零拷贝。
- **范围内逐条全链，范围外一个不链**：绝不把真实 home（`~/.claude`、`~/.codex`）或某个子目录整体（整个 `skills/`、整个 `plugins/`）作为**单一链接单元**挂载；只对约定范围内的子条目逐条建立链接。当前范围内**无名称过滤名单**（Codex skills 仅额外跳过 `.system`）；后续若需收敛可再加白名单，不影响链接机制。
- **需要 merge 就 merge**：MCP server 与配置表这类「非目录实体」无法链接，采取配置合并；用户级相关表/键在每次启动时重同步进隔离 home 的对应配置。
- **运行 home 不 hybrid 全量共享**：隔离 home（`data/*`）仍是各 app 的稳定运行目录；不以用户真实 home 作为 `CODEX_HOME` / `CLAUDE_CONFIG_DIR`；不把用户 home 整盘挂入。  
  **注意**：被链接的单条目与真实 home 在文件系统上是**同一目标**——对该路径的读写会落到真实 home。所谓「不写回」仅指启动器**不主动改写**真实侧 `auth.json` / `config.toml` / `settings.json` / `~/.claude.json` 等本体，以及不把隔离 home 的私有状态同步回用户 home。

## Background

`ccs-plus launch` 为各 app 使用项目本地稳定 home（`settings.yaml` 的 `apps.*.home`）：Codex 固定 `CODEX_HOME=data/codex`，Claude 固定 `CLAUDE_CONFIG_DIR=data/claude`，均不读回用户真实 home。当前隔离导致两个 app 各自存在可见性缺口。

### Codex（`CODEX_HOME=data/codex`）

- Skills：Codex 从 `$CODEX_HOME/skills` 加载全局 skill，`data/codex/skills` 只有 `.system` 系统内置项；用户真实 `~/.codex/skills` 中的个人 skill（如 `compound-engineering`、`dev-*`、`playwright-cli`、`pomelo-*`、`specflow`）在 ccs-plus 启动的会话中不可见。
- Plugins：**启用关键路径是配置表**，不是仅依赖 `plugins/` 目录。`~/.codex/config.toml` 的 `[plugins]` / `[marketplaces]` 决定启用的插件及其来源；这些表未进入 managed profile，故 ccs-plus 启动的会话中插件未启用。`~/.codex/plugins` 下的条目（缓存、本地产物等）可作为补充链接，**单独链接目录不足以启用插件**。
- MCP：managed profile（`data/codex/ccs-plus-codex-<digest>.config.toml`）不包含用户 `~/.codex/config.toml` 的 `[mcp_servers]`（如 `mks-ttyd`、`node_repl`、`pomelo-orbit-ssh`、`outlook`），因此 ccs-plus 启动的会话无法发现这些 MCP。本机用户配置还存在 `[shell_environment_policy]`，影响子进程/MCP 环境，一并纳入白名单合并。

### Claude（`CLAUDE_CONFIG_DIR=data/claude`）

- Skills：Claude Code 从 config dir 的 `skills/` 读取个人 skill；用户全局 `~/.claude/skills/` 中的 skill 在 ccs-plus 启动的会话中不可见。
- Plugins：Claude Code 从 config dir 的 `plugins/`（含文件如 `installed_plugins.json`、`known_marketplaces.json`，以及目录如 `marketplaces/`、`repos/`）读取已安装插件；用户全局 `~/.claude/plugins/` 中的条目在隔离会话中不可见。
- MCP：Claude Code 的用户级 `mcpServers` 存在全局状态文件 `~/.claude.json`（位于 **OS 用户主目录**，不是 `~/.claude/.claude.json`）；实测隔离会话的有效状态文件落在 `data/claude/.claude.json`，因此 `~/.claude.json` 的用户级 MCP 不会出现在 ccs-plus 启动的会话中。
- 现状说明：本机 `~/.claude` 含 `skills/` 与 `plugins/`（有实际内容可链接）；`~/.claude.json` 存在但 `mcpServers` 可能为空对象 `{}`。本需求补齐通用机制，使 `mcpServers` 一旦被填充即自动合并。`data/claude/plugins` 可能已有同名真实条目（非链接）；按「同名真实条目不覆盖」策略，这些条目不会自动改成链接，用户需自行清理隔离侧同名真实项才能切到链接形态。

旧 `cc-switch` 已有相关先例：`20260716-codex-hybrid-home-sessions`（临时 home 全量链接用户状态）与 `20260728-codex-mcp-config-inheritance`（合并 `[mcp_servers]`）。本需求恢复可见性能力，但采取**逐条链接 + 白名单配置合并 + 稳定隔离运行 home**，区别于旧的「临时 home 全量链接共享并结束拆除」形态。相对旧 hybrid 合并「真实侧优先」的表述，本需求对**白名单表/键**改为**每次启动以用户源为真相源重同步**（见 Decisions）。

## Goal

### 路径矩阵

| 路径 | skills / plugins 逐条链接 | 配置表 / MCP 合并 |
| --- | --- | --- |
| Codex custom（有 endpoint → managed profile） | 是 | 是：合并进 `ccs-plus-codex-<digest>.config.toml` |
| Codex direct（无 endpoint，无 managed profile） | 是 | 否（见 Decisions Q2） |
| Claude | 是 | 是：仅同步 `mcpServers` 到 `data/claude/.claude.json` |
| Grok | 否 | 否 |

### Codex

启动（`build_launch_spec`）时检查真实用户 home（默认 `~/.codex`，可配置 `apps.codex.user_home`）：

- Skills：把 `user_home/skills` 下条目**逐条**链接到 `data/codex/skills`（跳过 `.system`）。
- Plugins：把 `user_home/plugins` 下条目**逐条**链接到 `data/codex/plugins`（目录与文件统一策略，见 Decisions）。
- 配置合并（**仅 custom / managed profile**）：每次启动在生成 managed profile 核心字段之后，将 `user_home/config.toml` 的白名单顶层表**整表**写入该 profile：`mcp_servers`、`plugins`、`marketplaces`、`shell_environment_policy`。用户源为这些表的真相源。

### Claude

启动时检查真实用户 home（默认 `~/.claude`，可配置 `apps.claude.user_home`）：

- Skills：把 `user_home/skills` 下条目**逐条**链接到 `data/claude/skills`。
- Plugins：把 `user_home/plugins` 下条目**逐条**链接到 `data/claude/plugins`（含其内部的 `marketplaces/` 等子条目；**不是**链接用户 home 顶层的无关目录）。
- MCP：每次启动读取 **OS 主目录**下的 `~/.claude.json` 的 `mcpServers`（路径固定，不随 `apps.claude.user_home` 变化），将其中**全部**服务同步进 `data/claude/.claude.json` 的同名键；不改写源文件其他键，也不改写目标文件除 `mcpServers` 外的其他状态字段。

### 共通

- 只逐条链接约定范围内的个人条目，**绝不**把整个 home 或整个 `skills/`、`plugins/` 做成单一链接单元。
- 保持 `data/*` 稳定 state home；启动器不主动写回真实侧认证/配置本体。
- 不新增用户可见 CLI 开关，默认启用。

## Non-goal

- 不把真实 home 或整个 `skills/`、`plugins/` 子目录作为**单一链接单元**挂载进隔离 home。
- 不链接、不覆盖真实侧 `auth.json`、`config.toml`、`settings.json`、`~/.claude.json` 本体。
- 不链接用户 home **顶层**的 `agents`、`rules`、`memories` 等目录；不共享其目录内容。  
  **例外说明**：Claude/Codex 的 `plugins/` **内部**条目（例如 `plugins/marketplaces`）属于 plugins 范围内的逐条链接对象，与「不链接用户 home 顶层 marketplaces」不矛盾。Codex 的 marketplace **源/启用**主要靠 `config.toml` 表合并，不依赖顶层 marketplaces 目录。
- 不合并 `~/.claude.json` 的 `projects`、会话、缓存、遥测等其他键；不合并 Codex `notify`、`[features]`、`[desktop]` 等非白名单顶层配置表。
- 不合并 Claude `settings.json`（见 Decisions Q1）。
- 不做 hybrid-home 全量共享：不把用户状态目录整体作为运行 home。
- 不改 Grok 启动路径。
- 不改变 provider 模型、网关、认证、approval/sandbox 策略与 fail-closed 规则。
- 不自动删除或替换隔离 home 中已存在的同名**真实**目录/文件；不提供迁移/清理子命令。
- 不保证跨盘符/无权限环境下每个链接必然成功；链接失败不阻断启动。

## User scenarios

- 用户在 `~/.codex/skills` 安装个人 skill（如 `pomelo-db`、`specflow`），执行 `ccs-plus launch codex --provider <name>` 后，新会话可看到并调用这些 skill。
- 用户在 `~/.codex/config.toml` 配置了 `[plugins]` / `[marketplaces]`（并可选地在 `plugins/` 下有本地条目），custom 路径启动后 Codex 会话可发现并启用这些插件；**仅有目录链接、无配置表合并时不足以保证启用**。
- 用户在 `~/.codex/config.toml` 注册了 MCP（如 `mks-ttyd`、`node_repl`），custom 路径启动后 Codex 会话可发现并连接。
- 用户在 `~/.claude/skills` 安装个人 skill、在 `~/.claude/plugins` 安装插件，或在 `~/.claude.json` 注册用户级 MCP，ccs-plus 启动的 Claude 会话可看到 skill、启用插件、发现并连接 MCP。
- 用户更新真实 home 中 skill/plugin **内容**，因链接指向同一目标，会话中实时可见；**新增/删除**条目或更新 MCP/白名单配置表后，**下次启动**重查/重同步后反映。
- 用户删除真实 home 中某 skill/plugin，下次启动清理指向已消失目标的孤立链接，CLI 不因 dangling 链接报错。
- 真实 home 不存在时，行为与改前一致（仅隔离 home）。
- 隔离 home 中已存在与源同名的**真实**目录/文件时，不覆盖，以隔离 home 该条目为准（可能不是最新用户内容；需用户自行清理后才会建立链接）。

## Acceptance

- Codex `build_launch_spec`（**custom 与 direct**）后，`data/codex/skills` 与 `data/codex/plugins` 下分别出现指向 `user_home` 对应条目的链接（skills 的 `.system` 除外）；**不存在**指向整个 `user_home` 或整个 `skills/`、`plugins/` 的单一链接；已存在的同名真实条目不被覆盖。
- Codex **custom** 路径下 managed profile `ccs-plus-codex-<digest>.config.toml` 在每次启动后包含用户白名单表 `mcp_servers`、`plugins`、`marketplaces`、`shell_environment_policy` 的当前内容；用户侧更新这些表后，下次启动 profile 中对应表随之更新。provider 核心字段（`model_provider`、`model`、`approval_policy`、`default_permissions`、`model_providers` 等）仍由 managed 生成逻辑决定，且 `[projects]` 仍按现有规则保留。
- Codex **direct** 路径：完成 skills/plugins 链接；**不**创建或改写 `data/codex/config.toml` 以合并白名单表。
- Claude `build_launch_spec` 后，`data/claude/skills` 与 `data/claude/plugins` 下出现指向 `user_home` 对应条目的链接；目录为 junction/symlink，文件为 hardlink → symlink（均失败则跳过并 warning）；同名真实条目不被覆盖；无整目录单一链接。
- Claude 启动后 `data/claude/.claude.json` 的 `mcpServers` 包含 `~/.claude.json` 中的**全部**用户级服务（用户源为该键下服务名的真相源：同名以用户为准覆盖，隔离侧仅有的服务名保留）；`~/.claude.json` 不被改写；目标文件其他键不被删除或替换。
- 真实 home、对应子目录或配置文件缺失时静默跳过（no-op）。
- 链接创建失败、配置文件非法（TOML/JSON）时记录 warning，不阻断启动。
- 新增 `apps.codex.user_home`（默认 `~/.codex`）与 `apps.claude.user_home`（默认 `~/.claude`）配置；Claude MCP 源固定为 OS 主目录下的 `.claude.json`，不随 `apps.claude.user_home` 变化。settings 测试覆盖默认值与覆盖。
- 单元测试覆盖：逐条链接创建、`.system` 跳过、同名真实条目跳过、孤立链接清理、Codex 白名单表每次重同步、Claude `mcpServers` 用户源覆盖同名且保留隔离独有服务、home 缺失 no-op、无整目录单一链接、direct 不做配置合并；现有 launch / managed_config / settings 测试仍通过。
- README 补充说明本行为（含「链接条目写穿真实 home」与「插件启用依赖配置合并」）。

## Open questions

无未决项。原 Q1/Q2 已收口，见 Decisions。

## Decisions

- 流程模式：standard / 标准（需求 → 计划 → 实现 → 验证）。
- 可见性策略：能 link 就 link、需要 merge 就 merge、运行 home 不 hybrid 全量共享（见 Strategy）。
- **Q1（Claude `settings.json`）**：不合并，保持行为配置纯隔离；若实测依赖全局 hooks/permissions，另开需求评估白名单键。
- **Q2（Codex direct 配置合并）**：本次仅 managed profile（custom）路径合并白名单表；direct 只做 skills/plugins 链接，不写 `data/codex/config.toml`。
- 真实用户 home 来源：`apps.codex.user_home`（默认 `~/.codex`）与 `apps.claude.user_home`（默认 `~/.claude`），进 `settings.yaml` 与 settings 层；测试可注入；**不**读取父进程已指向隔离 home 的 `CODEX_HOME` / `CLAUDE_CONFIG_DIR` 作为共享源。
- Claude MCP 源路径：固定 `Path.home() / ".claude.json"`（OS 用户主目录），**不**随 `apps.claude.user_home` 变化；与 Claude Code 在未设置 `CLAUDE_CONFIG_DIR` 时的默认一致。
- 链接方式与范围：
  - Windows 目录：`_winapi.CreateJunction`（免管理员）；POSIX 目录：symlink。
  - **Codex 与 Claude 文件策略统一**：hardlink → symlink → 跳过并 warning。
  - **逐条**建立；范围内无名称过滤（Codex skills 跳过 `.system`）；链接持久保留在稳定 home，不随启动拆除。
  - 同名**真实**条目不覆盖；已存在且目标仍有效的链接可保留或按实现选择重建；目标已消失的孤立链接启动时清理并视情况重建。
  - `FileExistsError` 视为竞态下已存在，可接受。
- **合并算法（写死）**：
  1. **挂钩点**：在 `build_launch_spec` 路径内执行；Codex 配置合并必须发生在 `ensure_managed_config` **生成/重写** managed profile **之后**（或作为该函数内写盘前的一步），保证与「每次整表重写核心字段、仅保留 `projects`」兼容，避免合并结果被下次启动擦掉却不再灌入。
  2. **Codex 白名单表**（仅 custom）：每次从 `user_home/config.toml` 读取；对 `mcp_servers`、`plugins`、`marketplaces`、`shell_environment_policy` 四个顶层键，**以用户源整表覆盖写入** managed 文档（用户为真相源）。managed 生成逻辑负责的 provider 核心键与 `[projects]` 不在此列、不被用户表覆盖。纳入 `shell_environment_policy` 的理由：用户配置用其控制子进程/MCP 可见环境，与 MCP 可用性直接相关。
  3. **Claude `mcpServers`**：每次读取源 `~/.claude.json`；  
     `result = {**existing_target_mcpServers, **user_mcpServers}`  
     即：**同名服务以用户为准**（用户更新下次生效），**隔离侧独有服务名保留**；只写回目标文件的 `mcpServers` 键。
  4. 非法 TOML/JSON、缺文件：warning + 跳过该合并，不阻断启动。
- `.claude.json` 生效位置（已确认）：Claude Code 2.1.220 源码为 `join(process.env.CLAUDE_CONFIG_DIR || homedir(), ".claude.json")`；ccs-plus 设 `CLAUDE_CONFIG_DIR=data/claude`，故生效状态文件是 `data/claude/.claude.json`。
- 失败策略：链接创建失败、配置合并失败均 warning，不阻断启动；home 缺失时静默跳过。
- 不新增 CLI 开关，默认启用。
- 不提供隔离 home 脏数据清理命令；文档说明同名真实条目会阻止链接。

## Risk

- 杀毒/策略环境可能禁止 junction/symlink：该 skill/plugin 不可见，但启动正常（warning）。
- 被链接条目写穿真实 home：CLI 在链接路径下的安装/编辑/删除会影响用户真实 home；与「运行 home 隔离」并存，需在 README 说明。
- 白名单配置表原样进入 managed profile：含内联 `env`（如某 MCP 的 `CODEX_HOME` 指向真实 home）或绝对路径的表项可能与隔离 home 语义不完全一致，需验证阶段实测。
- 合并 `[marketplaces]` / `[plugins]` 后，marketplace 本地源路径仍按原样引用；源不可达时插件可能无法解析。
- `data/claude/.claude.json` 是运行状态文件：启动前写入 `mcpServers` 可能与 Claude Code 自身写入竞争；只触碰单键以降低风险。
- 隔离 home 已有同名真实 `skills`/`plugins` 条目时跳过链接，用户可能看到过期或空内容；需人工清理 `data/*` 侧对应真实项。
- 并发多次启动同时建链接：`FileExistsError` 可接受。
