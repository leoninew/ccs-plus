# ccs-plus

管理 cc-switch SQLite 中的 Claude、Codex、Grok provider，并使用选定 provider 启动对应的原生 CLI。

项目只负责 provider 管理、运行配置和 CLI 启动，不实现 cc-switch GUI、本地代理、请求转换或跨 CLI 会话迁移。

## 快速开始

要求：Python 3.11+、[uv](https://docs.astral.sh/uv/)、cc-switch 数据库，以及已安装并位于 `PATH` 中的 `claude`、`codex` 或 `grok` CLI。

```powershell
make install
make release
ccs-plus
uv run ccs-plus providers list
```

安装完成后，可使用 `ccs-plus --help` 查看命令；确认 `settings.yaml` 和 cc-switch 数据库已配置后，再列出已有 provider：

```bash
ccs-plus --help
ccs-plus providers list
```

也可以使用 `pip install -e .` 安装 editable 版本。

直接运行 `ccs-plus` 会进入交互式启动器：选择 Agent 后会显示其 Provider（按使用次数排序），默认选择该 Agent 上次使用的 Provider；工作目录默认是当前目录，可编辑，确认后启动原生 CLI。启动历史保存为项目本地 `data/launch-history.json`，不写入 cc-switch 数据库。

## 配置

项目根目录的 [`settings.yaml`](settings.yaml) 就是配置模板，请直接在该文件中配置。也可以使用 `.env` 或 `CCS_PLUS_*` 环境变量覆盖；嵌套键使用双下划线，例如：

```text
CCS_PLUS_DATABASE__PATH=~/.cc-switch/cc-switch.db
CCS_PLUS_APPS__CODEX__HOME=data/codex
CCS_PLUS_PROXY=http://127.0.0.1:7890
```

`encryption_key` 用于 provider 导入导出，必须是有效的 Fernet key：由 32 字节密钥编码成 URL-safe Base64 字符串（通常为 44 个字符），不能为空或保留占位值。可用以下命令生成：

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`proxy` 是 Claude、Codex、Grok 共用的启动代理地址。每次启动都会将它写入 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写兼容变量；保留为空字符串会显式清除从父进程继承的这些代理变量。通过环境变量覆盖时使用 `CCS_PLUS_PROXY`。

对于自定义 provider，三个应用启动时都会读取数据库中所选 provider 的实际 endpoint、API Key、模型和推理强度。`launch` 的 `--model`、`--effort` 是可选的单次覆盖，不回写 provider；未传时始终使用 provider 配置。官方 provider 不解析自定义配置，使用原生内置配置。权限属性优先读取 provider 记录：Claude 的 `permission_mode`，Codex 的 `approval_policy` 与 `sandbox_mode`，Grok 的 `sandbox_mode` 与 `always_approve`。这些必需权限项在 provider 缺失时才回退到对应的 `apps.*` 配置。`apps.codex.approval_policy` 和 `sandbox_mode` 也作为新增/导入 provider 时写入的初始策略。

## 使用方式

```powershell
# 列出所有 provider（默认不显示 API Key）
# Alias 列显示可用于启动的 provider 编号。
uv run ccs-plus providers list

# 启动列表中第二个 Codex provider（c=Claude、x=Codex、g=Grok）
uv run ccs-plus run x2

# 只列出 Codex provider，并以 JSON 输出
uv run ccs-plus providers list --app codex --json

# 新增一个 Claude provider。
# 将尖括号中的占位符替换为实际值；省略 --api-key 时会隐藏输入。
uv run ccs-plus providers add claude `
  --name "<provider-name>" `
  --endpoint "https://api.example.com/v1" `
  --model "<model-id>" `
  --effort high

# 查看指定名称的 provider（此命令会输出 API Key）
uv run ccs-plus providers show "<provider-name>"

# 导出全部自定义 provider；默认写入 data/providers-<timestamp>.json
uv run ccs-plus providers export

# 从加密备份导入 provider；替换为实际备份文件路径
uv run ccs-plus providers import "data/providers-<timestamp>.json"

# 按应用和名称删除自定义 provider；--yes 是必要的确认参数
uv run ccs-plus providers delete claude "<provider-name>" --yes

# 预览删除指定应用的全部自定义 provider；加入 --no-dry-run 后才实际删除
uv run ccs-plus providers reset codex
uv run ccs-plus providers reset codex --no-dry-run

# 使用指定 provider 启动 Claude；provider 名称必须已存在于数据库
uv run ccs-plus launch claude --provider "<provider-name>"

# 在指定工作目录启动 Codex；替换为实际目录和 provider 名称
uv run ccs-plus launch codex --provider "<provider-name>" --cwd "C:\work\project"

# 使用指定 provider 启动 Grok；模型与推理强度默认由 provider 配置决定
uv run ccs-plus launch grok --provider "<provider-name>"

# 只在本次启动覆盖 provider 的模型和推理强度
uv run ccs-plus launch grok --provider "<provider-name>" --model "<model-id>" --effort high
```

所有命令都支持 `-h` 和 `--help`。`Alias` 列显示可用于启动的编号，例如 `c1`、`x2`、`g1`；使用 `ccs-plus run <编号>` 启动对应 provider。编号按当前列表排序、每个应用从 1 开始。provider 按名称选择；同一应用中存在重名时，启动和删除会拒绝执行。官方 provider 不允许删除。

导出文件是 JSON 外壳，API Key 使用 Fernet 加密。持有同一个 Fernet key 的人可以解密备份；不要提交备份文件或密钥。`providers show` 会输出 API Key，只应在可信终端使用。

## 运行模型

每种 CLI 使用配置中的稳定 state home，因此切换 provider 不会替换原生会话目录：

| CLI | 状态目录 | provider 配置方式 |
| --- | --- | --- |
| Claude | `apps.claude.home` | 环境变量 + 稳定 `CLAUDE_CONFIG_DIR` |
| Codex | `apps.codex.home` | provider 独立 managed profile；统一会话 provider 标识 |
| Grok | `apps.grok.home` | provider 独立 managed model profile |

Claude 和 Codex 启动时会按需让隔离 Home 看见用户的 skills、plugins、MCP 配置；Grok 不同步这些用户资源。不会把整个用户 Home 直接替换为隔离 Home。

对于自定义 provider，启动配置分为两层：连接、模型和推理配置来自数据库中所选 provider 的实际记录；权限字段也优先使用该记录，缺失时才回退到 `settings.yaml` 中对应应用的配置。Codex 的 `apps.codex.*` 还会在新增或导入时写入初始值。官方 provider 不解析自定义 provider 配置。

Claude 启动器使用 provider 的 `permission_mode`，缺失时使用 `apps.claude.permission_mode`；模板默认值 `bypassPermissions` 等价于跳过权限确认。Grok 对 `sandbox_mode` 与 `always_approve` 使用相同的 provider 优先、应用级回退规则；模板默认值为 `workspace` 和 `true`。ccs-plus 新增/导入的 Codex provider 默认使用 `danger-full-access`，但缺少权限字段的既有记录会回退到 `apps.codex`。这些高权限行为只应在可信目录和可信 provider 下使用。

## 开发方式

代码位于 `src/ccs_plus`，测试位于 `tests`。主要职责边界如下：

```text
CLI 编排 → settings / domain → database / adapters → launcher
                                      ↘ managed_config / home_visibility
```

- `settings.py`：加载并校验 YAML、`.env` 和环境变量。
- `domain.py`：provider 数据模型和输入校验。
- `database.py`：兼容 cc-switch schema 的 SQLite 访问、事务和官方 provider 保护。
- `adapters.py`：cc-switch JSON/TOML 配置与统一运行时模型之间的转换。
- `launcher.py`：生成子进程参数和环境，不把 API Key 放进命令行或日志。
- `managed_config.py`、`home_visibility.py`：维护隔离 Home、managed profile、链接和配置合并。

日常开发循环：

```powershell
make install       # 安装运行和开发依赖
make test          # uv run pytest tests
make check         # ruff 格式化、ruff 检查、mypy
```

修改 provider 或启动行为时，应同时更新对应测试；测试使用临时 SQLite 和临时 Home，不应连接或修改真实用户数据库。涉及配置语义、CLI 命令或安全边界的变更，更新本 README 的简短说明即可。

## 文档规则

当前规范只有本 README 和 [`docs/README.md`](docs/README.md)。`docs/archive/` 中的内容是历史需求、方案、验证记录和数据库研究，仅用于追溯，不是当前实现的规范；开发时不要引用、修改或据此推断当前行为。
