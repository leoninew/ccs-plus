# ccs-plus

管理 cc-switch SQLite 中的 Claude、Codex、Grok provider，并使用选定 provider 启动
对应的原生 CLI。

## 安装

需要 Python 3.11+、[uv](https://docs.astral.sh/uv)、可访问的 cc-switch 数据库，以及
已安装并位于 `PATH` 中的 `claude`、`codex` 或 `grok` CLI。

```powershell
make install
make release
# 或：pip install -e .
```

`make release` 将项目以 editable 方式安装。安装完成后可使用 `ccs-plus` 或其别名
`ccsp` 执行命令。

## 配置

以 [`settings.yaml`](settings.yaml) 为模板，填写数据库路径和 `encryption_key`。可将
[`.env.example`](.env.example) 复制为 `.env`，再以 `CCS_PLUS_*` 环境变量按需覆盖配置：

```text
CCS_PLUS_DATABASE__PATH=~/.cc-switch/cc-switch.db
CCS_PLUS_PROXY=http://127.0.0.1:7890
```

生成 Fernet 密钥：

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

不要提交 `.env`、导出的 provider 备份或密钥。

## 使用

```powershell
# 交互式选择 Agent、provider 和工作目录
ccsp

# 查看 provider
ccsp provider list
ccsp provider list --app codex --json

# 新增 provider
ccsp provider add claude `
  --name "<provider-name>" `
  --endpoint "https://api.example.com/v1" `
  --model "<model-id>"

# 按列表编号启动 provider，例如 x2 表示第二个 Codex provider
ccsp run x2

# 从指定目录启动
ccsp launch codex --provider "<provider-name>" --cwd "C:\work\project"

# 备份、恢复与重置：省略 app 时同时处理 Claude、Codex、Grok
ccsp provider export # data/providers-all-<timestamp>.json
ccsp provider export codex # data/providers-codex-<timestamp>.json
ccsp provider export codex "data/codex-providers.json"
ccsp provider import "data/providers-all-<timestamp>.json"
ccsp provider import codex "data/codex-providers.json"
ccsp provider reset
ccsp provider reset codex --no-dry-run
ccsp provider delete claude "<provider-name>" --yes
```

使用 `ccsp --help` 或任一子命令的 `--help` 查看完整参数。`p`、`l`、`r` 分别是
`provider`、`launch`、`run` 的简写；`provider show` 会输出
API Key，只应在可信终端使用。

## 开发

源码位于 `src/ccs_plus`，测试位于 `tests`。安装依赖后，可用以下命令进行日常开发：

```powershell
make install
make test
make check
```

## 测试

`make test` 运行完整 pytest 套件。`make check` 执行 Ruff 格式化、Ruff 检查和 MyPy。
修改 CLI、配置或 provider 行为时，应同时补充相应测试。

## 贡献

提交前请运行 `make test` 和 `make check`，保持变更聚焦，并更新受影响的用户文档或
SpecFlow 过程文档。不要提交 API Key、`.env`、用户数据库或 provider 导出文件。
