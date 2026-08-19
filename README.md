# ccs-plus

管理 cc-switch SQLite 中的 Claude、Codex、Grok provider，并使用选定 provider 启动对应的原生 CLI。

## 安装

需要 Python 3.11+、[uv](https://docs.astral.sh/uv)、可访问的 cc-switch 数据库，以及已安装并位于 `PATH` 中的 `claude`、`codex` 或 `grok` CLI。

```bash
make install
make release
# 或：pip install -e .
```

`make release` 将项目以 editable 方式安装。安装完成后可使用 `ccs-plus` 或其别名 `ccsp` 执行命令。

## 配置

[`settings.yaml`](settings.yaml) 已包含默认数据库路径和运行配置。复制 [`.env.example`](.env.example) 为 `.env`，并将其中的 `CCS_PLUS_ENCRYPTION_KEY` 占位值替换为有效 Fernet key：

```bash
cp .env.example .env
```

生成 Fernet 密钥：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

只有默认数据库路径不适用时才设置 `CCS_PLUS_DATABASE__PATH`；只有需要代理时才设置 `CCS_PLUS_PROXY`。不要提交 `.env`、导出的 provider 备份或密钥。

## 使用

以下示例均在 Bash 中执行，并以 `ccsp` 作为命令入口。

### 命令约定

使用 `ccsp --help` 或任一命令后的 `-h`、`--help` 查看完整参数。`provider`、`launch`、`run` 分别可简写为 `p`、`l`、`r`。

### 管理 provider

#### 1. 查看与复用配置

查看所有 provider：

```bash
ccsp provider list
```

`list --app <app>` 可筛选 Claude、Codex 或 Grok，`--json` 可输出 JSON 元数据。

`provider show` 会为名称完全匹配的 provider 输出一条或多条可复用的 `provider add` 命令。默认将 API Key 替换为 `xxxx`：

```bash
ccsp provider show "<provider-name>"
```

执行脱敏命令前需将 `xxxx` 替换为实际密钥。仅在可信终端使用 `--show-secret` 查看原始 API Key。

#### 2. 添加 provider

添加 provider 时省略 `--api-key`，命令会以隐藏输入提示输入密钥：

```bash
ccsp provider add claude --name "<provider-name>" --endpoint "https://api.example.com/v1" --model "<model-id>"
```

可通过 `--api-key` 非交互式传入密钥，`--effort` 和 `--notes` 分别设置默认推理等级和备注。

### 启动

直接运行 `ccsp` 可交互式选择 Agent、provider 和工作目录：

```bash
ccsp
```

也可以按 provider 列表中的编号启动，例如 `x2` 表示第二个 Codex provider；`launch` 用于启动明确的 provider：

```bash
ccsp run x2
ccsp launch codex --provider "<provider-name>"
```

使用 `launch --cwd "<directory>"` 可指定启动目录；`--model` 和 `--effort` 可覆盖本次启动使用的默认模型和推理等级。

### 数据维护

#### 1. 备份

`export` 会备份自定义 provider；省略 app 时涵盖 Claude、Codex 和 Grok：

```bash
ccsp provider export
```

在 `export` 后附加 `claude`、`codex` 或 `grok` 可只备份一个应用，也可指定输出文件。未指定路径时，文件写入 `data/providers-all-<timestamp>.json` 或 `data/providers-<app>-<timestamp>.json`。

#### 2. 恢复

`import` 会恢复备份文件中的所有自定义 provider：

```bash
ccsp provider import "data/providers-all-<timestamp>.json"
```

在 `import` 后附加 `claude`、`codex` 或 `grok` 可只恢复一个应用。恢复时必须配置生成备份时使用的同一个 `encryption_key`。

#### 3. 清理

重置会删除非官方 provider，删除单个 provider 需要显式确认：

```bash
ccsp provider reset
ccsp provider delete claude "<provider-name>" --yes
```

`reset` 省略 app 时会处理 Claude、Codex 和 Grok；附加 app 名可只处理一个应用。该命令默认只预览，传入 `--yes` 才会执行删除。

## 开发

源码位于 `src/ccs_plus`，测试位于 `tests`。安装依赖后，可用以下命令进行日常开发：

```bash
make install
make test
make check
```

### 测试

`make test` 运行完整 pytest 套件。`make check` 执行 Ruff 格式化、Ruff 检查和 MyPy。修改 CLI、配置或 provider 行为时，应同时补充相应测试。

### 贡献

提交前请运行 `make test` 和 `make check`，保持变更聚焦，并更新受影响的用户文档或 SpecFlow 过程文档。不要提交 API Key、`.env`、用户数据库或 provider 导出文件。
