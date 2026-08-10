# ccs-plus

管理 cc-switch SQLite 供应商，并使用指定供应商启动 Claude、Codex 或 Grok。三种 CLI 使用稳定的 state home，以保留各自的原生会话历史。

## 快速开始

```powershell
make install
uv run ccs-plus providers list
```

`make release` 使用 `pip install -e .` 安装本项目。

## 配置

在 `settings.toml` 或 `.env` 中设置 cc-switch 数据库和三种 CLI state home。环境变量使用 `CCS_PLUS_` 前缀，完整示例见 `.env.example`。默认 state home 位于项目本地 `data/`，不会提交到 Git。

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
