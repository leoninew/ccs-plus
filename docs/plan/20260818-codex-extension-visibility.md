# 受管启动的用户与项目扩展可见性计划
最后修改时间: 2026-08-18 18:58:47

Review status: Accepted

## Requirement Basis

依据已接受的 [Requirement](../requirement/20260818-codex-extension-visibility.md)：

- 从项目目录启动 Claude、Codex、Grok 时，provider 隔离保持不变，同时继续发现各
  CLI 原生支持的 user-home 与项目级 MCP、plugins、skills 和相关设施。
- 从操作系统 user Home 启动时，不执行 user-home visibility 与项目级继承。
- user Home 的显式配置覆盖同名的 state/profile 配置；未声明的有效扩展配置不能因
  managed profile 重建而被无条件清空。
- 插件 cache 不是 enablement 的充分证据，不自动重新启用未注册插件。
- plugin `sync.sh` 必须把用户主动安装写入真实 CLI home；不能继承 Orca/ccs-plus 的
  `CODEX_HOME` 或 `GROK_HOME`，并且在 Windows Git Bash 中必须把本地 plugin 路径转换为
  原生 CLI 可识别的路径。
- 当前 requirement 统一替代 20260811、20260814、20260815 与 20260728 中关于
  extension visibility 的需求/计划/验证记录；旧文档在实现中删除。

## Design

### 可见性与配置优先级

保持 stable isolated runtime home（`data/claude`、`data/codex`、`data/grok`）与
provider/authentication 隔离，不将整个 user Home 挂载为运行 Home。

对于允许继承的扩展配置，按“已有 managed profile/state → state-home base config →
真实 user-home config”的顺序合并；后者只覆盖同名条目。该规则适用于 `mcp_servers`、
Codex `plugins`/`marketplaces`、Grok 对应 plugin/marketplace/hook 配置，以及必要的
shell policy。provider endpoint、API Key、模型、权限、认证与其他私有运行表绝不参与
该合并。

Codex managed profile 重建须先恢复既有允许继承表，再覆盖 provider 核心字段，最后由
`CodexHomeVisibility` 按上述优先级合并。不能继续只保留 `projects` 后从空文档构造。

目录策略保持逐条 link/copy/skip：skills 与已注册 plugin 的必要缓存/索引目录可见；
插件 appserver、安装 staging 和其他运行时临时目录保持隔离。对于仅发现 cache、未在
user config 或既有 profile/state 注册的插件，记录可操作诊断但不设置 `enabled = true`。

### CLI 独立的 visibility 配置

`settings.yaml` 在 `apps.claude.visibility`、`apps.codex.visibility`、
`apps.grok.visibility` 中分别声明 MCP/table 合并键与目录 copy/skip 策略。Codex 的
`profile_extension_keys` 同时用于重建既有 managed profile 和合并 state/user config；
即使从 user Home 启动而禁用条目同步，仍须把该配置传给 `DisabledHomeVisibility`，避免
profile 重建丢失允许保留的表。三端共同且不可变的原生目录名称维持共用实现，其他策略
不设共享默认值或跨端回退。

### 主键 Profile 与无备份写入

provider 数据库主键继续作为受管 profile 名、运行时 API Key 环境变量名和 ownership
marker 的唯一身份；同一 provider 记录的重复启动直接覆盖该主键对应的同一 profile。
不以 provider 名称重算 identity，不在 launch 业务逻辑中读取、迁移或删除历史 profile。
历史文件仅在会话停止后通过离线维护清理。

受管配置更新只保留文件锁、写入 `fsync` 和 `os.replace` 的原子替换；移除每次覆盖前
生成 `.ccs-plus.bak` 的逻辑。原子写入临时文件在替换完成或异常时被清除，不作为持久
备份产物。

### 当前目录与 user-Home 启动

launcher 继续把用户选定的 `cwd` 原样传给原生 CLI。实现与测试不得将隔离 Home 覆盖到
项目目录，也不得手动复制项目配置来模拟 CLI 发现；应验证 Codex、Claude、Grok 在其
原生支持的项目级 skills/MCP/plugins/指令配置下仍以该 `cwd` 工作。

复用 `_is_user_home_directory` 的已有总开关：`cwd == Path.home()` 时构造
`DisabledHomeVisibility`，不链接 user-home 条目、不合并 user 扩展配置；启动仍使用
provider 隔离 runtime home。

### 原生插件同步入口

`best-practices` 与 `housekeeper` 的 `sync.sh` 将真实 Home 与 runtime Home 分开：
`CLAUDE_USER_HOME`、`CODEX_USER_HOME`、`GROK_USER_HOME` 仅用于用户明确的同步目标，
默认分别为 `~/.claude`、`~/.codex`、`~/.grok`。调用 `codex plugin ...` 与
`grok plugin ...` 时显式设置该真实 Home；不可把运行环境中的 `CODEX_HOME`/`GROK_HOME`
作为默认值。Git Bash 下通过 `cygpath -aw` 将 marketplace/plugin source 转为 Windows
路径，避免 native CLI 把 `/d/...` 视为无效 registry source。

### Provider 数据维护范围

`provider export`、`provider import` 与 `provider reset` 共享可选 app 前置，app
集合为 `claude`、`codex`、`grok`；省略时统一传入 `list(AppKind)`，使三条命令都在其
既有业务边界内操作全部 app。export 保持已有的 `export <output-path>` 兼容形式，并增加
`export <app> [output-path]`；import 使用 `import <app> <input-path>`。限定 import 必须
先通过 `parse_backup_document()` 验证整份备份，再按 app 过滤记录并检查该 app 的名称冲突。
reset 的 dry-run 与经 `--yes` 确认的实际删除均使用同一 app 集合，仍只删除非官方 provider；仅其中的
Codex 目标继续清理对应的 managed profile。未提供 output path 的 export 按 scope 生成
`providers-all-<timestamp>.json` 或 `providers-<app>-<timestamp>.json`，避免三端和单端
备份在 `data/` 中语义不明。

Click 命令组使用单数 `provider`，所有子命令、usage 文本、README 和测试随之统一；不提供
`providers` 兼容别名，避免两种命令面并存。

顶层 `launch`、`provider`、`run` 同时注册 `l`、`p`、`r` 作为指向同一 Click 命令对象的
短用法，确保参数、帮助和执行逻辑不会分叉。

### CLI 别名

保留 `ccs-plus` 为主 console script，并在项目发行元数据中将 `ccsp` 映射到相同的
`ccs_plus.cli:main`。README 仅说明二者等价；不改写生成的 provider shortcut 或 TUI 品牌。

## Implementation Steps

1. **梳理与固化跨端扩展表**
   - 将 Claude、Codex、Grok 的合并键及 entry copy/skip 策略迁入各自的
     `apps.<cli>.visibility` 配置模型，校验必填表列表与条目列表类型。
   - 在 `home_visibility.py` 提取或扩展表合并辅助函数，支持“已有 profile/state
     保留 + state 覆盖 + user 覆盖”的命名条目合并。
   - 明确 Claude、Codex、Grok 每种可继承表与应隔离的运行时目录；不扩大到认证、
     provider 或会话私有状态。

2. **修复 Codex profile 重建**
   - 修改 `CodexManagedConfig.ensure()`，从已有受管 profile 保留允许继承的扩展表，
     而非只恢复 `projects`。
   - 修改 `CodexHomeVisibility.merge_into()`，按统一优先级合并 MCP、plugins、
     marketplaces 与 shell policy；user Home 同名配置必须覆盖。
   - 保持 skills 与 plugins cache 的逐条链接，并为 cache-only、未注册插件增加安全
     诊断路径。

3. **审计并补齐 Claude/Grok 同类重建路径**
   - Claude 保留 `skills`/`plugins` 的 link/copy/skip 语义，并将 `mcpServers` 的
     合并来源和目标状态文件纳入重复启动回归。
   - Grok 保留 skills/plugins/hooks/installed-plugin registry 的既有可见性和复制策略；
     验证其 state `config.toml` 重写后不丢失允许继承的 MCP、plugin 与 marketplace
     配置。
   - 三端共同验证从 user Home 启动时 `DisabledHomeVisibility` 不产生链接或配置合并。

4. **覆盖项目级原生发现**
   - 为每个 CLI 建立最小项目夹具，包含该 CLI 当前版本可识别的项目级 skill、MCP、
     plugin 或指令配置。
   - 通过 `build_launch_spec` 和必要的 CLI 层测试断言受管启动仍保留项目 `cwd` 与相关
     project trust/config，不将这些设施意外解析为 user-home visibility。

5. **更新说明与移除旧过程文档**
   - 更新 README，使隔离边界、user-home 可见性、项目级原生发现、user-Home 启动禁用
     和 cache-only 插件的限制清晰可见。
   - 已删除以下被本需求统一取代的过程文档：20260811 link/merge requirement 与 plan、
     20260728 Codex MCP inheritance requirement、20260814 MCP propagation requirement、
     20260815 home visibility requirement 与 verification。
   - 保留 20260716/20260720 的 archive，因为它们记录已移除的临时 Home 会话共享机制，
     不与当前稳定 runtime-home extension visibility 完全等价。

6. **修复用户插件同步入口**
   - 更新 `best-practices/sync.sh` 与 `housekeeper/sync.sh`：实际文件同步和 Codex/Grok
     原生注册均强制使用真实 user home。
   - 使用独立的 `*_USER_HOME` 覆盖变量，避免用户在 Orca 或 ccs-plus terminal 中运行
     同步脚本时污染隔离 runtime home。
   - 在 Windows Git Bash 中将本地 plugin path 转为 native CLI 接受的格式；不以 cache
     补偿 marketplace/plugin 注册失败。

7. **取消受管配置旁路备份**
   - 保持 provider 数据库主键派生 profile、环境变量键和 ownership marker 的现有隔离
     语义，不增加自动迁移路径。
   - 去除 managed config 写入的 `.ccs-plus.bak`，为重复 ensure 补充不生成备份的单元
     测试；历史 profile 由会话停止后的离线维护处理。

8. **统一 provider 数据维护的 app 选择**
   - 为 export/import 的可变位置参数保留旧路径形式，同时识别 app-first 形式；reset 将
     app 参数改为可选。
   - app 缺省时将 Claude、Codex、Grok 一次传入 repository；限定 import 在全量解析后
     再过滤，限定 reset 的 Codex profile 清理只处理真实删除目标。
   - 添加默认三端、限定单端、导入全量校验顺序的 CLI 回归测试，并在 README 使用区展示
     全端和 Codex 限定示例，以及对应的自动文件名。

9. **提供短命令别名**
   - 在 `[project.scripts]` 为 `ccsp` 注册与 `ccs-plus` 相同的 CLI 入口。
   - 验证两者的 `--help` 命令面一致，并更新 README 安装说明。

10. **统一 provider 管理命令组名称**
   - 将 Click 分组和所有使用示例从 `providers` 改为 `provider`。
   - 保留备份格式与自动文件名的 `providers` 复数语义，并回归验证旧命令不可用。

11. **提供顶层命令短用法**
   - 为 `launch`、`provider`、`run` 分别注册 `l`、`p`、`r`。
   - 通过同一 Click 命令对象实现别名，并覆盖帮助与对象映射回归。

## Files to Change

| 文件 | 计划变更 |
| --- | --- |
| `src/ccs_plus/home_visibility.py` | 跨端扩展表的保留与优先级合并；Codex cache-only 诊断；保持目录隔离规则。 |
| `src/ccs_plus/managed_config.py` | Codex profile 重建时保留允许继承的既有扩展表。 |
| `src/ccs_plus/launcher.py` | 确保 project cwd 原样传递、user-Home 禁用路径和 visibility 调用契约覆盖。 |
| `tests/test_home_visibility.py` | 三端目录、配置优先级、cache-only、user-Home 禁用测试。 |
| `tests/test_managed_config.py` | Codex profile repeated-ensure、profile/state/user 覆盖与 provider 隔离测试。 |
| `tests/test_launcher.py` | 三端项目 cwd、project-level facility 与 user-Home 启动回归测试。 |
| `README.md` | 运行时隔离和扩展可见性行为说明。 |
| `pyproject.toml` | 注册 `ccsp` console-script 别名。 |
| `src/ccs_plus/cli.py` | provider export/import/reset 的可选 app 前置与全端默认选择。 |
| `tests/test_cli.py` | provider 数据维护的全端默认、单端限定和完整备份校验回归。 |
| `../best-practices/sync.sh` | 向真实 user home 同步，并以 native Windows 路径注册 Codex/Grok 本地插件。 |
| `../housekeeper/sync.sh` | 向真实 user home 同步，并以 native Windows 路径注册 Codex/Grok 本地插件。 |
| 上述六份旧过程文档 | 在实现阶段删除。 |
| `docs/verification/20260818-codex-extension-visibility.md` | 验证阶段新增，不在实现阶段提前创建。 |

## Verification Plan

- 单元：对 Codex managed profile 连续执行两次 ensure，确认既有不同名 MCP/plugin/
  marketplace/shell policy 保留，user Home 同名项覆盖，provider 核心字段不受影响。
- 单元：Claude、Grok 的重复 launch/config 写入后，skills、plugins、MCP 及既有
  registry/索引策略不回退；临时目录仍不共享。
- 单元：cache-only plugin 产生诊断且未自动 enable；已注册的 `best-practices` 可在
  Codex profile 保留任一正式注册 plugin 及其 skill 所需的 config 与目录状态；
  `best-practices` 仅作为代表性回归夹具，不允许为其加入特殊逻辑。
- 单元：项目目录启动保留 `cwd` 和原生项目级扩展发现；`cwd == Path.home()` 时三个
  runtime 都不产生 user-home link/merge。
- 单元：同一 provider 主键的重复 ensure 复用同一 profile/env key，且不生成
  `.ccs-plus.bak`。
- 回归：运行现有 `pytest` 覆盖 launcher、managed config、home visibility、settings 与
  TUI 关联用例。
- CLI：验证 `export`、`import`、`reset` 省略 app 时选中三端，显式 Codex 时只操作 Codex；
  验证带无效非目标记录的备份不会因限定导入而绕过完整性校验；验证 export 默认文件名
  包含 `all` 或目标 app。
- 打包：验证 `ccs-plus --help` 与 `ccsp --help` 均可运行并暴露同一命令面。
- 工程：根据项目入口运行 lint、类型检查、格式和完整测试；检查 README 与删除文档的
  链接不存在悬挂引用。

## Assumptions and Risks

- 任一 plugin 在真实 user Home 缺少正式注册时，ccs-plus 不应从 cache 自动激活它；
  恢复正式注册仍须通过原生 CLI 的 plugin 安装流程完成。`best-practices` 仅用于覆盖
  该通用约束。
- 仅以“未在当前 user config 出现”判断删除会误删有效旧 profile 配置；本次默认保留。
  若未来需要显式移除同步，必须设计可区分用户卸载和配置暂时不可读的证据。
- 三个 CLI 的项目级发现协议会随版本改变；测试夹具必须使用已验证的原生机制，不能
  以 ccs-plus 私有目录约定替代。
- 旧过程文档删除后，新的 requirement、plan 和后续 verification 是此行为的唯一过程
  入口；需在同一实现变更中完成，避免文档链断裂。

## Rollback

- 回滚实现会恢复当前 visibility 合并行为；不会修改真实 user-home 的认证或配置文件。
- 若保留策略引入异常扩展加载，可回滚到仅 user-home 配置合并，并保留测试夹具用于
  后续定位。
- 文档删除将在同一变更中进行；回滚该变更即可恢复旧过程文档。
