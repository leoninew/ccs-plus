# ccl run 额外参数透传 Scope note

## 状态

Accepted

## 背景

当前 `ccl run` 的 `run` 子命令只接受 launcher 自己定义的参数。用户执行：

```bash
ccl run m 1 -c
```

时，`-c` 会被 `argparse` 作为 `cc_provider_launch.py` 的未知参数处理，导致：

```text
cc_provider_launch.py: error: unrecognized arguments: -c
```

但用户预期 `run` 命令中 app 和 provider number 之后的额外参数直接追加到目标 CLI。

## 目标

- 支持 `ccl run <app-or-alias> <provider_number> [extra args...]`。
- 将 `[extra args...]` 原样按 argv token 追加到最终目标 CLI 命令。
- 保留 launcher 自己已有参数：`--db`、`--env-file`、`--cwd`、`--mode`。
- 兼容 inline alias，例如 `ccl run m 1 -c` 中 `m` 先解析成实际 CLI，再透传 `-c`。

## 非目标

- 不改变 `CC_PROVIDER_LAUNCH_<FAMILY>_ARGS` 的默认启动参数语义。
- 不引入 shell 字符串拼接或 `shell=True`。
- 不改变 provider 选择、proxy/direct 选择、临时配置生成逻辑。
- 不支持在 extra args 后继续解析 launcher 参数；launcher 参数应放在 extra args 之前。

## 验收标准

- `ccl run m 1 -c` 不再因 `-c` 报 `unrecognized arguments`。
- `-c` 被追加到最终启动的目标 CLI command。
- 默认 family args 和本次 extra args 可以共存，顺序为：CLI 名称、默认 family args、launcher 注入参数、用户 extra args。
- Claude 启动仍包含 `--settings <temporary-settings-path>`。
- Codex 启动仍保留临时配置目录环境变量逻辑。

## 风险 / 假设

- `argparse.REMAINDER` 会把 provider number 后的所有 token 作为用户 extra args，因此 launcher 自己的可选参数需要放在 provider number 之前。
- 对目标 CLI 的 `-h`、`--help` 等参数也会被透传，不再触发 launcher help。

## User Review Notes

- 用户明确要求“新起需求”并继续实现，因此本轻量范围说明标记为 Accepted。
