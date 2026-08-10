# ccl run provider selector Scope note

Review status: Accepted

## Goal

`run` 的 provider 参数支持两种形式：`list` 展示的纯数字编号，或供应商名称。名称匹配必须在当前 app family 下唯一命中一个 provider。

## Non-goal

- 不改变 `list` 展示格式。
- 不改变 CLI alias 解析语义。
- 不支持模糊匹配或跨 app family 匹配。

## Acceptance

- `ccl run <app> 1` 继续按编号启动。
- `ccl run <app> <provider-name>` 可按唯一供应商名称启动。
- 名称没有命中或命中多个 provider 时给出错误，不启动 CLI。
- 额外 CLI 参数透传行为保持不变。

## Risk

供应商名称可能重复；实现必须显式拒绝多命中，避免静默选错 provider。
