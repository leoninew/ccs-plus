# ccl run 组合别名选择器需求

Review status: Accepted

Flow mode: light / 轻量模式

## Goal

支持在 `run` 子命令中把 CLI alias 和 provider 数字合并输入，例如：

```bash
ccl run c2
ccl run x1
```

真实 CLI 名称仍使用分离写法，例如：

```bash
ccl run claude 2
ccl run codex 1
```

alias 不再支持分离写法：`ccl run c 2` / `ccl run x 1` 应报错并提示使用组合形式。

## Non-goal

- 不移除真实 CLI 名称的 `ccl run <cli> <provider>` 形式。
- 不改变 provider name selector 在真实 CLI 名称下的既有行为。
- 不重做 `run` 的整体 argparse 结构或启动流程。

## Acceptance

- `run c2` 能解析为 app/alias `c` + provider selector `2`。
- `run x1` 能解析为 app/alias `x` + provider selector `1`。
- 旧 alias 分离形式 `run c 2` / `run x 1` 不再可用。
- 真实 CLI 分离形式 `run claude 2` / `run codex 1` 继续可用。
- 组合形式后面仍可继续传目标 CLI 参数。
- 相关单元测试通过。

## Risk

- `alias+num` 只覆盖数字 provider selector；provider name 仍使用旧形式。
- 如果未来 CLI alias 自身以数字结尾，组合语法会有歧义；当前默认 alias 不包含这种情况。
