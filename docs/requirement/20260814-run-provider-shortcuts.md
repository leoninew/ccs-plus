# Provider 快捷启动（run）
最后修改时间: 2026-08-14 11:00:24

Flow mode: light

Stage: Requirement

Review status: Accepted

## Background

通过 `launch codex --provider <name>` 启动 provider 需要输入较长的应用名和 provider 名称。现有 `providers list` 已提供可用于选择的排序结果，但没有可直接引用的编号。

## Goal

- 在 `providers list` 的最后一列展示每个 provider 的完整快捷启动命令。
- 新增 `run <target>` 命令，其中 `c`、`x`、`g` 分别代表 Claude、Codex、Grok，编号从该应用列表的 1 开始，例如 `run c1`、`run x2`、`run g1`。
- 快捷启动使用与无覆盖参数的 `launch <app> --provider <name>` 相同的 provider 配置、当前工作目录和退出码处理。

## Non-goal

- 不修改 cc-switch 数据库排序或写入额外编号。
- 不为 `run` 增加 `--cwd`、`--model`、`--effort` 等参数。
- 不改变既有 `launch` 命令或交互式启动器的行为。

## User scenarios

- 用户执行 `providers list`，看到 Codex 的 `ccs-plus run x1`、`ccs-plus run x2` 等快捷启动命令。
- 用户执行 `run x2`，启动列表中第二个 Codex provider。
- 用户输入无效目标或不存在的编号时，得到可操作的错误信息。

## Acceptance

- 列表中的 Claude、Codex、Grok 编号各自从 1 开始，且 `run` 使用同一排序。
- 表格不显示独立的编号或 target 列，最后的 `Shortcut` 列展示完整命令；JSON 输出包含 `shortcut`。
- `run c1`、`run x1`、`run g1` 能选择相应应用的 provider 并复用现有启动路径。
- 非法格式、零编号和超出范围的编号被拒绝，且不启动原生 CLI。
- README 说明快捷目标和用法；相关测试通过。

## Open questions

暂无需要用户确认的未决事项。

## Decisions

- 编号只反映当前 `ProviderRepository.list()` 的展示顺序，不持久化到数据库。
- `x` 作为 Codex 前缀，遵循用户指定；快捷目标匹配不区分大小写。
- `Shortcut` 使用 `ccs-plus run <target>` 形式，不额外展示 `No.` 或 `Run` 列。

## Risk

- provider 的排序变化会改变编号指向；列表和 `run` 使用同一 repository 排序以降低误选风险。
