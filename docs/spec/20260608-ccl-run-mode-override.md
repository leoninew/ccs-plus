# ccl run mode override Spec

## 状态

Draft

## Requirement Basis

基于 `docs/requirement/20260608-ccl-run-mode-override.md`。

Requirement 当前状态为 Draft，用户明确要求继续进入 Spec。以下设计将 requirement 中未正式 Approved 的内容作为 assumption 延续。

## Overview

为 `ccl run` 增加可选参数：

```bash
ccl run <cli-or-alias> <provider_number> --mode {direct,proxy}
```

行为：

- 未传 `--mode`：保持现状，读取 `proxy_config.proxy_enabled` 自动判断。
- `--mode direct`：本次运行强制 direct，忽略 `proxy_config.proxy_enabled`。
- `--mode proxy`：本次运行强制 cc-switch proxy，忽略 `proxy_config.proxy_enabled`。

`--mode` 只影响进程内的 `use_proxy` 计算，不写数据库、不修改 cc-switch current provider、不修改全局配置。

## Design Decisions

### 1. CLI 参数设计

在 `parse_args()` 的 `run_parser` 上新增：

```python
run_parser.add_argument(
    "--mode",
    choices=("direct", "proxy"),
    help="override proxy_config.proxy_enabled for this run",
)
```

不提供默认值，让 `args.mode is None` 表示继续使用数据库自动判断。

非法值由 argparse 处理，例如 `--mode route` 直接报错；不做兼容别名。

### 2. 启动模式计算

当前逻辑：

```python
proxy = load_proxy_config(db_path, family)
use_proxy = proxy.proxy_enabled
```

调整为：

```python
proxy = load_proxy_config(db_path, family)
if args.mode == "direct":
    use_proxy = False
elif args.mode == "proxy":
    use_proxy = True
else:
    use_proxy = proxy.proxy_enabled
```

保持仍然读取 `proxy_config`，原因：

- auto 模式需要 `proxy_enabled`。
- proxy 模式需要 `listen_address` / `listen_port`。
- direct 模式虽然不需要端口，但保持统一读取可避免引入更大分支；如果未来希望 direct override 在 proxy_config 缺失时也能运行，可作为单独需求处理。

### 3. Direct 行为

`use_proxy = False` 时沿用现有分支：

- Claude：`build_claude_direct(provider, temp_dir)`。
- Codex：`build_codex_direct(provider, temp_dir)`。

不调用 `check_proxy(proxy)`，因此 `--mode direct` 不检查 proxy 端口。

### 4. Proxy 行为

`use_proxy = True` 时沿用现有分支：

- Claude：调用 `check_proxy(proxy)`，再 `build_claude_proxy_current(proxy, temp_dir)`。
- Codex：调用 `check_proxy(proxy)`，再 `build_codex_proxy_current(proxy, temp_dir)`。

`check_proxy()` 当前会检查 `proxy.proxy_enabled`，这与 override 需求冲突：当数据库 `proxy_enabled = 0` 但用户传 `--mode proxy` 时，不应因为 `proxy.proxy_enabled` 为 false 而失败。

因此需要调整 `check_proxy()`：

- 删除或跳过 `if not proxy.proxy_enabled: raise LaunchError("cc-switch proxy is not enabled")`。
- 让它只负责端口可连接性检查。

auto 模式下 `proxy_enabled = 0` 不会调用 `check_proxy()`，所以删除该检查不影响自动 direct 行为。

### 5. Launch summary

继续使用现有 `launch_summary(provider, family, use_proxy, selected_proxy)`。

- direct override：显示 provider 的 direct API URL。
- proxy override：显示 proxy URL。

不输出 mode 字段，避免扩大输出格式；如后续需要可单独增加。

## Affected Components

### `cc_provider_launch.py`

- `parse_args()`：新增 `run --mode` 可选参数。
- `run()`：新增 mode override 到 `use_proxy` 的计算。
- `check_proxy()`：改为只检查 proxy 端口可连接，不再要求数据库 `proxy_enabled = 1`。

### `tests/test_cc_provider_launch.py`

新增或调整测试：

- helper `run_args()` 支持传入 `mode`。
- `--mode direct` 覆盖 `proxy_enabled=True`，不调用 `check_proxy()`，走 direct command。
- `--mode proxy` 覆盖 `proxy_enabled=False`，调用 proxy config 构建逻辑。
- 不传 `mode` 时保留现有行为。

### `docs/README.md`

更新：

- 命令形态加入 `[--mode {direct,proxy}]`。
- 当前支持的启动方式说明：默认读取 db，可用 `--mode` 单次覆盖。
- 示例加入：
  - `ccl run claude 1 --mode direct`
  - `ccl run claude 1 --mode proxy`

## Interfaces

### CLI

```bash
ccl run <cli-or-alias> <provider_number> [--db <path>] [--env-file <path>] [--cwd <path>] [--mode {direct,proxy}]
```

`--mode`：

- optional。
- choices：`direct`、`proxy`。
- 不支持 `route`。

### Internal state

新增读取：

```python
args.mode: str | None
```

不新增持久化状态。

## Technical Questions

无。

## Risks

- Requirement 仍为 Draft，未标记 Approved；风险是后续实现可能需要随 review 再调整文档和代码。
- `check_proxy()` 语义从“proxy_enabled 且端口可达”收窄为“端口可达”，如果未来有调用方依赖旧错误文案，需要同步调整。但当前代码只在 `use_proxy=True` 分支调用。
- `--mode direct` 仍会读取 `proxy_config`；若数据库缺少 proxy_config，即使 direct override 也会失败。当前设计为保持改动最小，若用户希望 direct override 不依赖 proxy_config，需要新增需求。

## Alternatives

### A. 增加 `resolve_use_proxy(proxy, mode)` helper

可以让测试更集中，但当前逻辑只有三行，直接放在 `run()` 更简单。

### B. 支持 `route` 别名

不采用。用户明确要求使用 `--mode proxy`，不向后兼容。

### C. 让 `--mode direct` 不读取 proxy_config

不采用。这样需要把 `load_proxy_config()` 移入 proxy/auto 分支，且 auto 仍需读取；会增加分支复杂度。当前需求只要求覆盖 `proxy_enabled`，不要求绕过 `proxy_config` 存在性。

## User Review Notes

- 用户决定：使用 `--mode proxy`，不向后兼容 `route`。
