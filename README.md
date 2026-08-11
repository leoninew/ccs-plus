# ccs-plus

管理 cc-switch SQLite 供应商，并使用指定供应商启动 Claude、Codex 或 Grok。三种 CLI 使用稳定的 state home，以保留各自的原生会话历史。

## 快速开始

```powershell
make install
uv run ccs-plus providers list
```

`make release` 使用 `pip install -e .` 安装本项目。

## 配置

配置文件为项目根 `settings.yaml`（语义分组：`database` / `encryption_key` / `apps`）。可用 `.env` 或 `CCS_PLUS_*` 环境变量覆盖，嵌套键用 `__`（如 `CCS_PLUS_APPS__CODEX__HOME`）。完整示例见 `.env.example`。默认 state home 在项目本地 `data/`，不提交到 Git。`providers add/import` 写入 `apps.codex` 默认策略；`launch` 以数据库中的供应商实际配置为准。

### 启动时 skills / plugins / MCP

`launch` 默认会从真实用户 home 带入可见性资源（无 CLI 开关）：

| App | 链接 | 配置合并 |
| --- | --- | --- |
| Claude | `~/.claude` 下 `skills/`、`plugins/` **逐条**链接进 `apps.claude.home` | OS 主目录 `~/.claude.json` 的 `mcpServers` 同步进隔离 home 的 `.claude.json`（非法 JSON 警告并忽略） |
| Codex | `~/.codex` 下 `skills/`（跳过 `.system`）、`plugins/` **逐条**链接进 `apps.codex.home` | **仅 custom**（有 endpoint）把用户 `config.toml` 的 `mcp_servers` / `plugins` / `marketplaces` / `shell_environment_policy` 写入 managed profile |
| Grok | 不链接、不合并 | — |

真实用户 home 默认分别为 `Path.home() / ".claude"` 与 `Path.home() / ".codex"`。一般无需配置；仅在需要时可通过环境变量或 YAML **显式提供**覆盖：

- `CCS_PLUS_APPS__CLAUDE__USER_HOME` / `apps.claude.user_home`
- `CCS_PLUS_APPS__CODEX__USER_HOME` / `apps.codex.user_home`

未提供或为空时使用上述默认，不导致启动失败。Claude 用户级 MCP 源始终为 `Path.home() / ".claude.json"`，不随 Claude user home 覆盖变化。

要点：

- **不是**把整个 user home 或整个 `skills/`、`plugins/` 做成单一链接；只链接子条目。
- 被链接的条目与真实 home 在文件系统上是同一目标：**写入会落到真实 home**。
- Codex 插件启用依赖 **config 表合并**；仅有 `plugins/` 目录链接通常不够。
- 隔离 home 里已有同名**真实**目录/文件时不覆盖；需要链接时请先自行清理该真实条目。
- 源配置缺失或非法（TOML/JSON）时打印警告并跳过，不阻断启动。

## 命令

```text
ccs-plus providers list [--app claude|codex|grok] [--json]
ccs-plus providers add <claude|codex|grok> --name <name> --endpoint <url> --model <id>
ccs-plus providers export [file]
ccs-plus providers import <file>
ccs-plus providers reset [--no-dry-run]
ccs-plus providers show <name>
ccs-plus providers delete <claude|codex|grok> <name> --yes
ccs-plus launch <claude|codex|grok> --provider <name> [--cwd <path>]
```

所有命令均支持 `-h` 和 `--help`。`providers export` 和 `providers import` 从 `CCS_PLUS_ENCRYPTION_KEY` 读取通用 Fernet 加密密钥；在 `.env` 设置实际随机值。省略导出文件名时生成 `data/providers-YYYYMMDD-HHMMSS.json`。`providers show` 会输出已存储的 API Key，请避免在共享终端中使用。

## 开发

```powershell
make check
make test
```
