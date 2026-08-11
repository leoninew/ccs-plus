# Codex / Claude 选择性链接 Skills、Plugins 并合并 MCP 计划

最后修改时间: 2026-08-11 14:30:00

Review status: Accepted

Flow mode: standard / 标准模式

## Requirement Basis

依据已接受的 [Requirement](../requirement/20260811-link-home-skills-plugins-mcp.md)：

- 稳定隔离 home（`data/*`）不变；**不**做 hybrid 全量共享。
- Codex / Claude 启动时对 `user_home/skills` 与 `user_home/plugins` **逐条**链接进隔离 home。
- Codex **custom**（managed profile）路径每次启动将用户 `config.toml` 白名单表写入 profile；**direct** 只链接不合并。
- Claude 每次启动将 OS 主目录 `~/.claude.json` 的 `mcpServers` 同步进 `data/claude/.claude.json`。
- 不改 Grok；无新 CLI 开关；失败 warning 不阻断启动。

## Proposed Design

### 配置

在 `settings.yaml` / `AppSettings` 增加：

```yaml
apps:
  claude:
    home: data/claude
    user_home: "~/.claude"
  codex:
    home: data/codex
    user_home: "~/.codex"
    approval_policy: never
    sandbox_mode: danger-full-access
```

- `AppHomeSettings`（Claude）与 `CodexSettings` 均增加 `user_home: Path`。
- 解析规则与现有 `home` 相同：`expanduser`，相对路径相对项目根。
- 环境覆盖：`CCS_PLUS_APPS__CLAUDE__USER_HOME`、`CCS_PLUS_APPS__CODEX__USER_HOME`。
- Claude MCP 源**不**走 `user_home`：固定 `Path.home() / ".claude.json"`。

### 模块边界

```text
src/ccs_plus/
  home_visibility.py   # 新建：逐条链接 + 孤立链接清理 + Claude mcpServers 同步
  managed_config.py    # 扩展：Codex profile 写盘前注入白名单表
  launcher.py          # 在 build_launch_spec 中调用链接；Claude 调 MCP 同步
  settings.py          # user_home 字段
```

`home_visibility.py` 保持无 Click / 无 DB 依赖，便于单测。

### 链接算法（`link_user_entries`）

输入：`source_dir`、`target_dir`、可选 `skip_names`（如 `{".system"}`）。

1. `source_dir` 不存在 → 静默 return。
2. `target_dir.mkdir(parents=True, exist_ok=True)`。
3. 扫描 `target_dir` 下已有链接：若是 junction/symlink 且目标不存在 → unlink 清理（warning 可选）。
4. 遍历 `source_dir` 子条目（非递归「整目录单链」）：
   - 名称在 `skip_names` → skip。
   - `target` 已存在：
     - 已是指向正确目标的链接 → keep。
     - 是真实文件/目录或指向其他目标的链接 → **不覆盖**（真实优先 / 隔离侧为准）。
   - 否则创建链接：
     - 目录：Windows `_winapi.CreateJunction`，POSIX `Path.symlink_to(..., target_is_directory=True)`。
     - 文件：`os.link` hardlink → 失败则 symlink → 再失败 warning 跳过。
5. 任何单条失败：logger.warning，继续其余条目；不抛到 launch。

**禁止**：对 `source_dir` 本身或 `user_home` 做单一 junction/symlink 到隔离 home。

调用点（均在 `build_launch_spec` 内，设置好 `state_home` 之后）：

| App | 调用 |
| --- | --- |
| Codex | `link_user_entries(user_home/skills, state/skills, skip={.system})`；`link_user_entries(user_home/plugins, state/plugins)` |
| Claude | 同上（skills 无 `.system` 跳过，除非源侧出现同名再按通用 skip 扩展）；plugins 全量逐条 |
| Grok | 不调用 |

### Codex 白名单合并（`managed_config`）

白名单顶层键：

```text
mcp_servers
plugins
marketplaces
shell_environment_policy
```

流程（仅 custom 路径，`ensure_managed_config` → `_ensure_codex_profile`）：

1. 现有逻辑构建 document：marker、provider 核心字段、`model_providers`、保留 `projects`。
2. 若调用方传入 `user_home`（或可选的已解析 `user_tables`）：
   - 读 `user_home / "config.toml"`；缺失/非法 TOML → warning，跳过合并。
   - 对每个白名单键：若用户文档中存在该顶层表，则 **整表写入** managed document（覆盖 document 中同名顶层键；用户为真相源）。
3. 原子写盘（现有 `_write_atomic` + lock + backup）。

API 调整建议（保持向后兼容测试友好）：

```python
def ensure_managed_config(
    runtime, state_home, model, effort, *, user_home: Path | None = None
) -> ManagedProfile
```

- `launcher._codex_spec` 在 custom 分支传入 `settings.codex.user_home`。
- direct 分支不调用 `ensure_managed_config`，故自然不合并。

### Claude `mcpServers` 同步

函数：`sync_claude_mcp_servers(state_home: Path, source_path: Path | None = None) -> None`

- `source_path` 默认 `Path.home() / ".claude.json"`。
- 源缺失/非法 → warning 或静默（缺文件静默，非法 warning），return。
- 读源 `mcpServers`（非 dict 则 warning skip）。
- 目标 `state_home / ".claude.json"`：
  - 不存在 → 写 `{"mcpServers": user_servers}`（或 `{}` 再合并）。
  - 存在 → 解析 JSON；非法则 warning skip（不阻断启动，避免毁掉状态文件——若选择更激进策略需在实现时与测试对齐；**默认：非法目标不覆盖整文件**）。
  - `merged = {**existing_mcp, **user_mcp}`。
  - 仅当 `merged != existing_mcp` 时写回：保留目标其他顶层键，只替换 `mcpServers`。
- 写盘：与 managed_config 类似可用临时文件 + `os.replace`；对 `.claude.json` 使用短锁（portalocker）降低并发损坏概率。

调用点：`launcher._claude_spec` 在设置 `CLAUDE_CONFIG_DIR` 后、返回 argv 前。

### 启动时序

```text
build_launch_spec
  resolve state_home, user_home
  if claude:
    link skills/plugins
    sync mcpServers
    build claude argv/env
  if codex:
    link skills/plugins
    if custom:
      ensure_managed_config(..., user_home=codex.user_home)  # 内含白名单 merge
    build codex argv/env
  if grok:
    现有逻辑不变
```

## Implementation Steps

1. **Settings**：`AppHomeSettings` / `CodexSettings` 增加 `user_home`；`load_settings` 解析；`settings.yaml` 与 `.env.example` 补充注释键；`make_app_settings` / settings 测试更新。
2. **新建 `home_visibility.py`**：实现 `link_user_entries`、孤立链接清理、跨平台目录/文件链接、`sync_claude_mcp_servers`；纯函数 + logging。
3. **`managed_config.py`**：`ensure_managed_config` / `_ensure_codex_profile` 接受可选 `user_home`，写盘前合并四张白名单表；非法 TOML warning 不抛 `ProviderError`（与 provider 核心校验 fail-closed 区分）。
4. **`launcher.py`**：Codex/Claude 分支调用链接；Claude 调用 MCP 同步；Codex custom 传 `user_home` 进 managed config。
5. **测试**：
   - `tests/test_home_visibility.py`（新建）：逐条链接、`.system` 跳过、真实同名不覆盖、孤立链接清理、文件 hardlink/symlink 降级（可用 monkeypatch）、整目录不被单链、mcpServers 合并语义。
   - `tests/test_managed_config.py`：白名单表写入、用户更新后再次 ensure 反映新值、`projects` 仍保留、缺 config.toml 不破坏 profile。
   - `tests/test_launcher.py`：build_launch_spec 触发链接；Codex direct 有链接无 merge；custom 有 merge；Grok 无链接副作用。
   - `tests/test_settings.py`：`user_home` 默认与 env 覆盖。
6. **README**：说明默认启用、配置键、链接写穿语义、Codex 插件依赖配置合并、direct 不合并表、Claude MCP 源固定 `~/.claude.json`。
7. **质量门**：`make check`、`make test`。

## Files to Change

| 文件 | 变更 |
| --- | --- |
| `settings.yaml` | `apps.claude.user_home` / `apps.codex.user_home` |
| `.env.example` | 对应 `CCS_PLUS_*` 注释 |
| `README.md` | 行为说明 |
| `src/ccs_plus/settings.py` | 字段与加载 |
| `src/ccs_plus/home_visibility.py` | **新建** |
| `src/ccs_plus/managed_config.py` | 白名单表合并 |
| `src/ccs_plus/launcher.py` | 挂钩链接与同步 |
| `tests/conftest.py` | `make_app_settings` 支持 `user_home` |
| `tests/test_settings.py` | 默认/覆盖 |
| `tests/test_home_visibility.py` | **新建** |
| `tests/test_managed_config.py` | 合并用例 |
| `tests/test_launcher.py` | 启动挂钩用例 |

## Verification Plan

| 层级 | 验证 |
| --- | --- |
| 单元：链接 | 源 skills 多条目 → 目标逐条链接；`.system` 跳过；真实同名跳过；删除源后下次清理孤立链接；不出现「目标 skills 本身是指向源 skills 的单链接」。 |
| 单元：文件 | 源 plugins 下 json 文件按 hardlink/symlink 策略进入目标。 |
| 单元：Codex merge | custom profile 含四张用户表；修改用户 `config.toml` 后再次 ensure 表内容更新；`projects` 保留；provider 核心字段不被用户表覆盖。 |
| 单元：Codex direct | 无 endpoint 时不写 managed profile、不写 `config.toml`，仍创建 skills/plugins 链接。 |
| 单元：Claude MCP | 源服务进入目标；同名以源为准；目标独有服务保留；源文件不被改写；目标其他顶层键保留。 |
| 单元：缺失 | user_home / 子目录 / 配置文件缺失 → 启动仍成功。 |
| 回归 | 既有 launcher / managed_config / settings / cli 测试通过。 |
| 本地手测（可选） | `ccs-plus launch codex --provider <custom>` 后检查 `data/codex/skills` 链接与 profile 中 `mcp_servers`；Claude 同理检查 `data/claude/skills` 与 `.claude.json`。 |
| 工程 | `make check`、`make test`。 |

## Assumptions and Risks

- Windows 测试环境支持 `_winapi.CreateJunction`（本机 CPython 已具备）；CI 若在无权限环境，目录链接用例需可跳过或 mock。
- 不清理用户已有的 `data/claude/plugins` 真实脏数据；测试用 tmp_path 不依赖本机 `data/`。
- MCP 表内联 `env` 指向真实 `CODEX_HOME` 时行为交给验证阶段观察，本计划不做路径重写。
- 源或目标 TOML/JSON 非法时：**打印 warning 并忽略（不合并、不覆盖）**，不阻断启动。

## Rollback

- 删除 `home_visibility.py` 与 launcher/managed_config/settings 挂钩即可回到纯隔离 home。
- 已创建的 junction/symlink 留在 `data/*/skills|plugins` 中，可手工删除；不影响真实 user home 内容（删的是链接本身）。
- 已写入 managed profile 的白名单表随下次不合并的 profile 重写消失（回滚代码后 ensure 只写核心字段）。
- `data/claude/.claude.json` 中已合并的 `mcpServers` 可能残留，可手工编辑或删除该键；回滚代码后不再重同步。
