# ccs-plus

<p align="center">
  <strong>cc-switch provider manager · multi-agent CLI launcher · fullscreen TUI</strong><br/>
  <sub>Claude · Codex · Grok — one command, one pane, zero context switching</sub>
</p>

<p align="center">
  <img src="docs/assets/tui-launcher.png" alt="ccs-plus interactive launcher TUI" width="920"/>
</p>

<p align="center">
  <sub>Interactive launcher — app badges, provider picker, directory-scoped sessions, Codex permission presets</sub>
</p>

---

`ccs-plus` 管理 [cc-switch](https://github.com/farion1231/cc-switch) SQLite 中的 Claude / Codex / Grok provider，并用选定 provider **启动原生 CLI**。

只做 provider 管理、运行配置与启动编排——不实现 GUI、本地代理、请求转换或跨 CLI 会话迁移。

## Highlights

| | |
| --- | --- |
| **Fullscreen TUI** | 无参启动进入 opencode 风格多面板：App · Provider · Directory · Permissions · Sessions |
| **Session resume** | 按当前目录过滤历史会话，`a` 切换 all projects；Resume 使用 session 自带 cwd |
| **Permission presets** | Codex：YOLO / On request / Auto workspace / Ask |
| **Provider shortcuts** | `providers list` 显示 `c1` / `x2` / `g1`，`ccs-plus run x2` 一键启动 |
| **Isolated homes** | 每 app 稳定 state home；skills / plugins / MCP 按需可见，不污染用户真实 Home |
| **Release binaries** | GitHub Release 自动构建 Linux / macOS / Windows 单文件二进制 |

## 快速开始

要求：Python 3.11+、[uv](https://docs.astral.sh/uv/)、cc-switch 数据库，以及 `PATH` 中的 `claude` / `codex` / `grok`。

```bash
make install
make release          # 或: pip install -e .
ccs-plus              # 进入 TUI
ccs-plus providers list
```

PowerShell:

```powershell
make install
make release
ccs-plus
uv run ccs-plus providers list
```

### TUI 速查

| 操作 | 按键 |
| --- | --- |
| 切换面板 | `tab` / `s-tab` |
| 列表移动 | `↑↓` · `j/k` · 鼠标滚轮 |
| 点选 | 鼠标点击 |
| 过滤 provider / sessions | `/` 后输入 |
| 会话范围 this dir ↔ all | sessions 焦点下按 `a` |
| 启动 / 取消 | `enter`（Launch）· `esc` |
| 数字跳转 | `1`–`9` |

- **New session**：显示可编辑 directory（默认当前目录）
- **Resume**：隐藏 directory，cwd 来自会话本身

## 配置

根目录 [`settings.yaml`](settings.yaml) 即配置模板。也可用 `.env` 或 `CCS_PLUS_*` 覆盖（嵌套键用 `__`）：

```text
CCS_PLUS_DATABASE__PATH=~/.cc-switch/cc-switch.db
CCS_PLUS_APPS__CODEX__HOME=data/codex
CCS_PLUS_PROXY=http://127.0.0.1:7890
```

`encryption_key` 用于 provider 导入导出，须为有效 Fernet key：

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`proxy` 为 Claude / Codex / Grok 共用启动代理，写入 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`（及小写兼容变量）；空字符串会清除从父进程继承的代理。

自定义 provider 的 endpoint、API Key、模型与推理强度来自数据库记录。`launch` 的 `--model` / `--effort` 仅单次覆盖。权限字段优先 provider：Claude `permission_mode`，Codex `approval_policy` + `sandbox_mode`，Grok `sandbox_mode` + `always_approve`；缺失时回退 `apps.*`。

## 使用方式

```bash
# 列表（含启动编号 Alias：c1 / x2 / g1）
uv run ccs-plus providers list
uv run ccs-plus run x2

uv run ccs-plus providers list --app codex --json

uv run ccs-plus providers add claude \
  --name "<provider-name>" \
  --endpoint "https://api.example.com/v1" \
  --model "<model-id>" \
  --effort high

uv run ccs-plus providers show "<provider-name>"
uv run ccs-plus providers export
uv run ccs-plus providers import "data/providers-<timestamp>.json"
uv run ccs-plus providers delete claude "<provider-name>" --yes

uv run ccs-plus providers reset codex
uv run ccs-plus providers reset codex --no-dry-run

uv run ccs-plus launch claude --provider "<provider-name>"
uv run ccs-plus launch codex --provider "<provider-name>" --cwd "/path/to/project"
uv run ccs-plus launch grok --provider "<provider-name>"
uv run ccs-plus launch grok --provider "<provider-name>" --model "<model-id>" --effort high
```

所有命令支持 `-h` / `--help`。`Alias` 按当前列表排序、每 app 从 1 起。同名 provider 时启动/删除会拒绝。官方 provider 不可删。

导出为 JSON 外壳 + Fernet 加密 API Key。`providers show` 会输出明文 Key，仅在可信终端使用。

### 本地二进制

```bash
make binary    # dist/ccs-plus （Windows: dist/ccs-plus.exe）
```

发布 GitHub Release（tag）时，Actions 会自动构建并上传：

- `ccs-plus-linux-x86_64`
- `ccs-plus-macos-arm64` / `ccs-plus-macos-x86_64`
- `ccs-plus-windows-x86_64.exe`

## 运行模型

每种 CLI 使用配置中的稳定 state home，切换 provider 不会替换原生会话目录：

| CLI | 状态目录 | provider 配置方式 |
| --- | --- | --- |
| Claude | `apps.claude.home` | 环境变量 + 稳定 `CLAUDE_CONFIG_DIR` |
| Codex | `apps.codex.home` | provider 独立 managed profile；统一会话 provider 标识 |
| Grok | `apps.grok.home` | provider 独立 managed model profile |

Claude / Codex 启动时按需暴露用户 skills、plugins、MCP；Grok 不同步这些资源。不会把整个用户 Home 替换为隔离 Home。

Claude 默认 `permission_mode` 模板为 `bypassPermissions`。Grok 模板默认 `workspace` + `always_approve`。Codex 新增/导入默认 `danger-full-access`；缺字段时回退 `apps.codex`。高权限仅应在可信目录与可信 provider 下使用。

## 开发

```text
CLI 编排 → settings / domain → database / adapters → launcher
                                      ↘ managed_config / home_visibility / tui
```

```bash
make install       # uv sync --all-groups
make test          # pytest
make check         # ruff + mypy
make binary        # 本地 PyInstaller 单文件
```

测试使用临时 SQLite 与临时 Home，不连接真实用户库。配置/CLI/安全相关变更请同步更新本 README。

## 文档规则

当前规范：本 README 与 [`docs/README.md`](docs/README.md)。`docs/archive/` 为历史材料，仅供追溯，不代表当前实现。
