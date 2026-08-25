# 受管启动的用户与项目扩展可见性验证
最后修改时间: 2026-08-25 16:10:06

Review status: Draft

## Requirement Alignment

- 指定 provider 时，Claude、Codex、Grok 的 endpoint、模型与 API Key 隔离；profile、API Key 环境变量键和 ownership marker 继续基于 provider 数据库主键。
- Claude/Grok 保持隔离 runtime Home，并按条目投影真实 user Home 的 MCP、plugin 与 skill。
- Codex 使用唯一真实 `CODEX_HOME`；profile 不保留或合并用户扩展表、session 或 cache，并保留自身已有的项目 trust。
- 从 OS user Home 启动不会改变三端的 cwd。Claude/Grok 仍投影用户扩展；Codex 与普通目录启动完全相同，不产生 visibility、trust 或配置复制的特殊写入。
- 当前工作目录中的扩展仍由原生 CLI 发现；ccs-plus 不传 `--cd` 或 `--add-dir`，也不复制项目配置。

## Plan Alignment

`settings.yaml` 在 `apps.claude.visibility` 与 `apps.grok.visibility` 分别声明 MCP、扩展表和 copy/skip 策略。Codex visibility 设置和对应运行代码均已删除。

三个 CLI 共同且不可变的原生目录名称（如 `skills`、`plugins`）保留在共享实现；它们不是跨端可变策略。`.env.example` 记录 Claude MCP 键的标量覆盖方式，以及 Dynaconf 对列表型 visibility 配置执行追加合并的限制。

### 2026-08-25 待实现范围

实现已基于现场 `notify` 警告改为：Codex 不再使用隔离 runtime Home 加 visibility 投影，而是以真实 `~/.codex` 作为唯一 `CODEX_HOME`。受管 profile 与原生用户配置处于同一 Home；profile 只包含 provider 核心字段，不复制 extension tables，但保留自身已有的 `[projects]`，并对第三方 provider 关闭 ChatGPT 会话认证的内置 Codex Apps MCP。本轮 Verification 需核对这一实现是否同时保留 provider 路由隔离、用户扩展可见性与原生 cwd。

## Actual Diff

| 范围 | 实际变更 |
| --- | --- |
| Codex runtime | launch、session 查询与受管 profile 清理均使用真实 `apps.codex.user_home`；不保留第二个 Codex runtime-root 配置。 |
| Codex profile | profile 仅重建 provider 核心字段，不再保留或合并 MCP、plugins、marketplaces、shell policy；已有 `[projects]` trust 保持。 |
| Codex Apps MCP | 第三方 managed provider 通过 `--disable apps` 避免启动 ChatGPT 会话认证的内置 MCP；官方 provider 保留原生行为。 |
| 用户扩展 | Claude/Grok 保留隔离 Home 的条目投影与用户配置合并；Codex 不进入 `HomeVisibility`。 |
| user Home 工作目录 | Claude/Grok 在 `cwd == Path.home()` 时仍投影 MCP、plugin、skill；Codex 直接使用真实 Home。三端都保留传入 cwd。 |
| 文档与测试 | RSPV 以单一真实 Codex Home 为准，不再把 cache 投影、同步脚本或 CLI 别名作为本场景验收。 |

当前实际变更与已收口的 Requirement/Plan 对齐。Verification 保持 Draft，待用户审阅验收结论。

## Acceptance Checklist

- [x] Claude/Grok 从 user Home 启动时仍投影用户 MCP、plugin 与 skill，provider 隔离和 `cwd` 保持不变。
- [x] Codex 从任意 `cwd=A` 启动时，`CODEX_HOME` 是唯一真实 user Home，`cwd=A` 不变，argv 不含 `--cd`/`--add-dir`，并使用指定的 managed provider profile。
- [x] Codex managed profile 不保留 `mcp_servers`、plugins、marketplaces 或 shell policy；旧 profile 中已有的 `[projects]` trust 在下一次 ensure 后保留。
- [x] Codex managed provider 启动参数包含 `--disable apps`，官方 provider 不添加该覆盖。
- [x] `cwd == Path.home()` 的 Codex launch 没有 visibility/trust/config 特殊写入，且真实 user `config.toml` 不再触发 project-local `notify` 警告。
- [x] 项目目录启动保留 CLI 原生 `cwd` 与项目级发现边界。
- [x] Codex profile identity 和无 `.ccs-plus.bak` 有回归覆盖。

## Test Results

| 检查 | 结果 |
| --- | --- |
| 单元与集成回归 | `uv run pytest tests`：194 passed, 1 skipped。 |
| 静态检查 | `ruff check .`：通过；`mypy src`：无问题。 |
| user Home 原生探针 | Claude `c2`、Codex `x2`、Grok `g3` 的 MCP 与 plugin list 均成功；三端 launch spec 均保留传入 cwd。 |
| 最小真实推理 | Claude `c2`、Codex `x2`、Grok `g3` 均从 `C:\Users\wangm25` 返回 `READY`。Grok `g3` 启动约 43 秒、实际推理约 7.5 秒，300 秒上限未触发。 |
| 项目目录原生探针 | 从 `D:\SourceCodes\mywork\ccs-plus` 重新执行 Claude MCP、Codex `debug prompt-input` 与 Grok MCP 均成功，cwd 未被 ccs-plus 改写。 |

## Risks And Gaps

- Codex 与原生 Codex 共同写入真实 Home 的风险仍存在；受管 profile 必须继续按 ownership marker、文件锁和原子替换受限写入。
- Claude/Grok 的项目级发现协议由 CLI 版本决定；验收只能证明 ccs-plus 保持 cwd，不能代替各原生 CLI 的兼容性测试。
- Grok `g2` 的 provider 在真实请求中被服务端以 401 拒绝（API Key 无效）；`g3` 已成功，因此这是该 provider credential 的运行问题，不是 Grok adapter、Home 投影或超时问题。

## Conclusion

单一真实 Codex Home 方案在 user Home 与项目目录的三端原生探针、三条最小真实推理和全量工程检查中均符合本需求。`g2` 的失效 credential 不影响实现结论，但该 provider 本身不能投入使用。Verification 保持 Draft，等待用户审阅。
