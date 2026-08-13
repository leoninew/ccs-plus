# ccl run mode override Requirement

## Review status

Accepted

## Mode

light

## 背景

当前 `ccl run` 已移除用户可见的 `--mode` 参数，默认根据 cc-switch 数据库中的 `proxy_config.proxy_enabled` 自动选择启动方式：

- `proxy_enabled = 0`：direct，使用指定 provider 的临时配置。
- `proxy_enabled = 1`：proxy，通过 cc-switch 本地 proxy。

实际使用中，需要临时覆盖数据库配置，显式指定本次运行方式，而不修改 cc-switch.db 或全局状态。

## 目标

- 为 `ccl run` 加回可选 `--mode` 参数。
- `--mode` 用于覆盖 `cc-switch.db` 中 `proxy_config.proxy_enabled` 的自动判断。
- 不传 `--mode` 时，保持当前行为：继续读取 `proxy_config.proxy_enabled` 自动选择。
- 支持显式选择 direct 或 proxy 运行方式。
- 覆盖只影响本次 launcher 进程，不写数据库、不修改 cc-switch 当前 provider、不修改全局配置。

## 非目标

- 不恢复必须传 `--mode` 的旧交互。
- 不实现请求级 / 会话级 provider override。
- 不修改 cc-switch Rust/Tauri proxy。
- 不改变 failover queue 或 current provider 语义。
- 不绕过现有 Codex config-home override 安全限制。
- 不改变 `list` / `alias` / CLI alias / 默认 CLI args 语义。

## 用户场景

### 场景 1：数据库开启 proxy，但本次强制 direct

当 `proxy_config.proxy_enabled = 1` 时，用户仍可执行：

```bash
ccl run claude 1 --mode direct
```

本次启动使用 provider 1 的 direct 配置，不连接 cc-switch proxy，也不修改数据库。

### 场景 2：数据库关闭 proxy，但本次强制 proxy

当 `proxy_config.proxy_enabled = 0` 时，用户可执行：

```bash
ccl run claude 1 --mode proxy
```

本次启动生成指向 cc-switch 本地 proxy 的临时配置，并在启动前检查 proxy 端口可连接。

### 场景 3：不传 mode 时保持自动行为

```bash
ccl run claude 1
```

仍按 `proxy_config.proxy_enabled` 自动选择 direct 或 proxy。

## 需求

### 必须支持

- `ccl run <cli-or-alias> <provider_number> --mode <value>`。
- `--mode` 为可选参数。
- 支持的 mode 值仅包含：
  - `direct`
  - `proxy`
- `--mode direct` 强制走 direct，不使用 `proxy_config.proxy_enabled` 的结果。
- `--mode proxy` 强制走 cc-switch proxy，不使用 `proxy_config.proxy_enabled` 的结果。
- 未传 `--mode` 时，行为与当前实现一致。
- proxy 模式继续读取 `proxy_config.listen_address` / `listen_port` 并检查 proxy 可连接。
- direct 模式继续使用命令中的 provider 编号选择 provider 配置。
- 输出不得泄露 API key/token。

### 应支持

- `run --help` 展示 `--mode {direct,proxy}` 或等价说明。
- 错误信息能区分：非法 mode、proxy_config 缺失、proxy 模式下 proxy 不可达、provider 编号越界。
- 文档说明 `--mode` 是单次运行覆盖，不会写入 cc-switch.db。

## 验收标准

- `python cc_provider_launch.py run --help` 包含可选 `--mode`。
- 不传 `--mode` 时，`proxy_config.proxy_enabled = 0` 仍走 direct。
- 不传 `--mode` 时，`proxy_config.proxy_enabled = 1` 仍走 proxy。
- 传 `--mode direct` 时，即使 `proxy_config.proxy_enabled = 1` 也走 direct。
- 传 `--mode proxy` 时，即使 `proxy_config.proxy_enabled = 0` 也走 proxy。
- `--mode proxy` 时如果 proxy 端口不可达，启动失败并提示不可达。
- `--mode direct` 不检查 proxy 端口。
- proxy 启动不修改 cc-switch current provider。
- proxy/direct 覆盖不写入 cc-switch.db。
- README 或相关文档更新命令形态和行为说明。

## Open Questions

- 无。

## Decisions

- `--mode` 是可选覆盖参数；不传时继续使用数据库自动判断。
- mode 值仅支持 `direct` 和 `proxy`。
- 不兼容 `route` 等旧称或别名；传入非 `direct` / `proxy` 的值应由 argparse 直接报错。
- 覆盖范围仅限本次 launcher 进程。
- `direct` / `proxy` 都不改变 provider 编号语义：direct 使用编号配置，proxy 编号只表达启动意图，实际 provider 仍由 cc-switch proxy 决定。

## User Review Notes

- 用户要求轻量模式：加回可选参数，用于覆盖 cc-switch.db 配置，显式指定运行方式。
