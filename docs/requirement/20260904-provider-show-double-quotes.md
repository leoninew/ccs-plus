# provider show 双引号命令输出
最后修改时间: 2026-09-04 21:42:09

Flow mode: light / 轻量模式

Stage: Requirement / 需求

Review status: Accepted

## Background

`ccsp provider show <name>` 用于输出可复用的 `provider delete` 和 `provider add` 命令。此前命令参数使用 Bash 单引号语法，复制到 Windows PowerShell 或 `cmd` 时不符合用户预期。

## Goal

- 将 `provider show` 生成的所有 provider 参数统一改为双引号。
- 使包含单引号或双引号的 provider 名称在 PowerShell 和 `cmd` 中保持为一个参数。

## Non-goal

- 不改变 provider 的存储、删除、添加或重置行为。
- 不修改现有 README 或 skill 中已经使用双引号的手工命令示例。
- 不安装或修改开发依赖。

## User scenarios

1. 用户在 PowerShell 中复制 `provider show` 输出的 delete 或 add 命令，可直接保留带空格的参数值。
2. 用户在 `cmd` 中复制相同输出，可直接保留带空格的参数值。
3. provider 名称含单引号或双引号时，输出仍使用双引号作为参数边界，内嵌双引号以 `""` 表示。

## Acceptance

- delete 命令中的 provider 名称使用双引号。
- add 命令中的 `--name`、`--endpoint`、`--api-key`、`--model`、可选 `--effort` 和 `--notes` 均使用双引号。
- 回归测试覆盖普通值、API Key 显示和包含单双引号的名称。
- 全套测试通过，且 `git diff --check` 无空白错误。

## Open questions

暂无需要用户确认的未决事项。

## Decisions

- 使用双引号作为所有显示命令参数的统一边界。
- 参数值中的双引号替换为连续两个双引号，输出格式同时适用于 PowerShell 与 `cmd`。
- 将渲染辅助函数从 Bash 专用命名改为通用的 `_command_quote`。

## Risk

- 跨 shell 的特殊字符规则并不完全一致；本次覆盖空格和嵌套引号，不改变 CLI 对 `$`、反引号或 `%` 等 shell 特殊字符的语义。
