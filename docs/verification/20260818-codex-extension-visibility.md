# 受管启动的用户与项目扩展可见性验证
最后修改时间: 2026-08-18 18:24:41

Review status: Draft

## Requirement Alignment

- Claude、Codex、Grok 的 user-home extension visibility 保持 provider runtime home
  隔离；目录按条目 link/copy/skip，不挂载整个 user Home。
- Codex managed profile 重建保留配置允许的扩展表，并按 existing profile/state/user
  的优先级合并；user Home 同名项覆盖。
- Profile、API Key 环境变量键和 ownership marker 继续基于 provider 数据库主键；没有
  按名称复用，也没有在 launch 中自动迁移或删除旧 profile。
- 从 OS user Home 启动时，不应用 user-home visibility；但 Codex 仍携带配置声明的
  profile 保留表，避免 managed profile 重建丢失已有扩展。
- cache-only Codex plugin 只产生诊断，不会被隐式注册或启用。
- `best-practices` 与 `housekeeper` 的同步脚本均使用显式 `*_USER_HOME`，并把本地
  marketplace/plugin 路径转换为 native CLI 可识别的 Windows 路径。
- provider 的 `export`、`import`、`reset` 均支持可选 app 前置；省略 app 时分别在
  原有的 custom-provider / non-official-provider 过滤边界内同时处理 Claude、Codex、Grok。
- export 未给 output path 时，备份文件名以 `all` 或显式 app 标明实际数据范围。

## Plan Alignment

`settings.yaml` 已将 Claude MCP 键、Codex profile extension 表和 copy/skip 策略、Grok
extension 表及索引复制策略分别声明在 `apps.<cli>.visibility`。运行代码不再有
`CLAUDE_MCP_KEY`、`CODEX_PROFILE_EXTENSION_KEYS` 或 Claude plugin 策略字段。

三个 CLI 共同且不可变的原生目录名称（如 `skills`、`plugins`）保留在共享实现；它们不是
跨端可变策略。`.env.example` 记录 Claude MCP 键的标量覆盖方式，以及 Dynaconf 对列表型
visibility 配置执行追加合并的限制。

provider 数据维护统一以 app-first 方式限定单端，并保留既有路径调用：`export [app]
[output-path]`、`import [app] <input-path>`、`reset [app]`。限定导入先完整解密、解析并
验证备份，之后才过滤目标 app，因而不会忽略备份内非目标 app 的损坏记录。省略 output
path 的 export 分别生成 `providers-all-<timestamp>.json` 与
`providers-<app>-<timestamp>.json`。

## Actual Diff

| 范围 | 实际变更 |
| --- | --- |
| settings 与 runtime | 新增三套独立 visibility 设置模型，factory 将其注入 Claude、Codex、Grok visibility；Codex profile 保留表由实例配置读取。 |
| 可见性行为 | Claude MCP key、Codex skills/plugin 隔离规则、Grok extension/hook/registry 规则全部配置驱动。 |
| 配置写入与身份 | profile identity 继续由 provider 主键派生；受管配置使用锁和原子替换，不生成 `.ccs-plus.bak`。 |
| 同步脚本 | `best-practices/sync.sh`、`housekeeper/sync.sh` 不继承受管 Home；Grok 的 list/update/install 均通过 user-home 包装。 |
| 文档与测试 | 合并历史 SpecFlow 文档、补充 `.env.example`，并覆盖配置解析、三端 visibility、profile 重建、user-Home 禁用与 sync 调用边界。README 保持用户使用、开发、测试和贡献说明。 |
| Provider 数据命令 | export/import/reset 接受可选 `claude`、`codex`、`grok` 前置；默认统一操作三端，单端 import 在全量备份校验后过滤，自动 export 文件名包含 app scope。 |

实际变更与 Requirement/Plan 一致；未发现超出范围的生产行为变更。旧 SpecFlow 文档的删除
由新 Requirement、Plan 和本 Verification 统一承接，未发现指向被删除文档的 Markdown 链接。

## Acceptance Checklist

- [x] 项目目录启动保留 CLI 原生 `cwd` 与项目级发现边界。
- [x] 三端 user-home skills/plugins/MCP/扩展配置的隔离可见性有回归覆盖。
- [x] Codex repeated ensure 保留已有扩展并以 user 配置覆盖同名项。
- [x] cache-only plugin 有诊断且不自动启用。
- [x] user-Home 启动不执行 user-home link/merge，provider 隔离保持。
- [x] provider 主键 profile identity 和无 `.ccs-plus.bak` 有回归覆盖。
- [x] 同步脚本不再直接调用会继承受管 `GROK_HOME` 的 `grok plugin` 子命令。
- [x] provider export/import/reset 缺省时覆盖三端，显式 Codex 时只操作 Codex。
- [x] 限定 import 不会绕过完整备份校验，reset 的 Codex profile 清理仍只处理删除目标。
- [x] export 默认文件名在全端时包含 `all`，单端时包含显式 app。

## Test Results

| 检查 | 结果 |
| --- | --- |
| `uv run ruff format --check .` | 通过，87 files already formatted |
| `uv run ruff check src tests` | 通过 |
| `uv run mypy src` | 通过，14 source files 无问题 |
| `uv run pytest tests` | 通过，170 passed、1 skipped |
| `uv run ccs-plus providers {export,import,reset} --help` | 通过，三条命令均展示 app 可选语义 |
| `bash -n`（两个 `sync.sh`） | 通过 |
| 旧 SpecFlow 链接检查 | 通过，未发现指向已删除文档的 Markdown 链接 |

## Risks And Gaps

- 未执行 `sync.sh skills` 的真实 CLI 集成测试，因为它会修改 `~/.claude`、`~/.codex`、
  `~/.grok` 的 plugin/marketplace 状态。已使用 Bash 语法检查和静态调用路径检查覆盖
  user-home 包装与 native path 传递；首次实际执行仍应在可恢复的用户环境中观察 CLI 输出。
- 真实 user-home 中只有 cache、没有 plugin registration 的情况仍保持不自动恢复；这是
  已接受的安全边界。

## Conclusion

实现满足当前 Requirement 和 Plan，工程检查通过。建议将 ccs-plus 的暂存变更与两个 plugin
仓库中的 `sync.sh` 修改分别提交，避免跨仓库提交混合。
