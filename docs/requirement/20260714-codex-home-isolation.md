# Codex 临时配置隔离修复
最后修改时间: 2026-07-14 09:32:29

Review status: Accepted

## Background

已安装的 `ccs run xN` 能选中 Codex provider 并生成临时 `auth.json` 与 `config.toml`，但仅从父进程读取 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV`。当该选择器仅位于配置文件时，启动器无法向 Codex 子进程注入临时 Home，因安全保护拒绝启动。

## Goal

让 `ccs` 以可预测、可移植的方式解析 Codex Home 选择器，并仅为子进程注入指向临时目录的 `CODEX_HOME`（或明确配置的兼容变量名）。

## Non-goal

- 不引入 Codex `--profile` 作为 provider 选择机制。
- 不读写或回退到全局 `~/.codex`。
- 不修改 cc-switch 数据库、provider 数据或 proxy 路由语义。

## User scenarios

- 用户在 `.env`、显式 `CC_SWITCH_ENV_FILE` 指向的文件，或稳定用户配置文件中设置 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV=CODEX_HOME` 后，执行 `ccs run x2`。
- 用户在父进程中设置该变量时，父进程配置优先于文件配置。
- 用户遗漏、留空或错误配置环境变量名时，启动器在创建 Codex 子进程前拒绝执行。

## Acceptance

- 成功的 Codex direct 和 proxy 启动都仅将临时 `<temp>/codex` 注入到子进程 Home 环境变量。
- 父进程配置优先，其次为选定 env 文件；不得扫描当前工作目录 `.env`。
- 安装制品可通过 `CC_SWITCH_ENV_FILE` 或 `~/.cc-switch/.env` 获取配置。
- 源码 checkout `.env` 仅在同目录存在 `pyproject.toml` 时视为有效，避免误用 site-packages 附近文件。
- 缺失、空白或非法选择器必须 fail-closed，且不调用子进程。
- 示例与文档准确说明 `CODEX_HOME` 及配置文件优先级。

## Open questions

暂无需要用户确认的未决事项。

## Decisions

- 使用 `CODEX_HOME` 作为样例默认值。
- 保留可配置的变量名以兼容不同 Codex 版本或包装器。
- 不使用 profile：profile 仅叠加已有 `CODEX_HOME` 内的配置文件，不能替代隔离。

## Risk

`CC_SWITCH_ENV_FILE` 改变配置文件定位契约；实现需保持父进程配置优先，且避免隐式读取工作目录中的配置文件。
