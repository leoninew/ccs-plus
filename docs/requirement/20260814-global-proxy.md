# 全局代理环境配置
最后修改时间: 2026-08-14 10:58:45

Review status: Accepted

## Background

`ccs-plus launch` 当前从父进程复制环境变量，再按 Claude、Codex、Grok 的各自需求补充或清理变量。代理行为因此依赖启动 `ccs-plus` 的终端环境，无法通过项目 `settings` 统一管理；当已有代理配置后，也不能通过空配置显式清除子进程继承的代理。

## Goal

- 在 `settings.yaml` 增加一个全局代理地址配置，并遵循现有 Dynaconf 规则支持通过 `.env` 或 `CCS_PLUS_` 环境变量覆盖。
- 每次通过 `ccs-plus launch` 启动 Claude、Codex 或 Grok 时，将该配置写入原生 CLI 子进程的代理环境变量。
- 配置值为非空字符串时，三个 CLI 都接收到同一代理地址；配置值为空字符串时，仍显式写入空字符串，以覆盖父进程中继承的代理并允许清理已设置的代理。

## Non-goal

- 不实现代理服务、协议转换、健康检查、连通性测试或按 provider 单独配置代理。
- 不修改 cc-switch 数据库或 provider 记录。
- 不增加 CLI 参数覆盖全局配置。

## User scenarios

1. 用户在 `settings.yaml` 或 `.env` 设置代理地址后，以任意 Claude、Codex、Grok provider 启动，原生 CLI 请求经该代理发出。
2. 用户此前在终端或项目配置中使用过代理，将全局配置置空后再启动任意 CLI，子进程收到空代理变量，不再继承旧代理。

## Acceptance

- `AppSettings` 能加载全局代理配置，且其值允许为空字符串。
- `build_launch_spec` 为 Claude、Codex、Grok 返回的 `env` 都包含约定的代理变量；非空值原样传递，空值也作为键值对传递。
- 父进程预先存在代理变量时，空配置生成的启动环境仍为显式空值，而非保留父进程值或删除该键。
- 覆盖配置的环境变量命名遵循当前 `CCS_PLUS_` 与 `__` 嵌套键规则，并在用户文档中说明。
- 相关 settings 和 launcher 单元测试覆盖三种 CLI、非空值与空值清理场景。

## Open questions

- 暂无需要用户确认的未决事项。采用跨 CLI 常用的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 及其小写兼容形式，并全部写入同一个全局代理值；本需求不设置 `NO_PROXY`。

## Decisions

- 代理为单一顶层 `proxy` 全局 `settings` 配置，不属于某个 provider 或某种 CLI。
- 空字符串是有效的运行时值，仅用于子进程环境覆盖；它不是“未配置”或回退到父进程环境的信号。

## Risk

- 不同原生 CLI 或其底层网络库对大小写及 `ALL_PROXY` 的支持可能不同；同时写入标准常见键可减少差异，但需确认其符合预期。
- 代理地址可能包含凭据。实现和测试不得将其写入日志、CLI 输出或持久化到 provider 数据中。
