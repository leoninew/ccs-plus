# Codex SSH MCP 启动兼容性
最后修改时间: 2026-08-29 11:12:18

Review status: Draft

## Background

用户通过以下命令注册全局 SSH MCP：

```bash
codex mcp add pomelo-orbit-ssh -- npx -y ssh-mcp -- --host=111.229.185.157 --user=ubuntu --key=C:/Users/leon/.ssh/id_rsa
```

`codex mcp list` 显示该 server 为 `enabled`，但由 `ccsp` 启动的 Codex 会话没有对应工具。排查确认 `ccs-plus` 的 managed profile 是叠加在 `CODEX_HOME` 基础用户配置之上的；同一 profile 下的 `codex mcp list` 也能看到该条目。因此问题不是 `ccs-plus` 过滤或覆盖了全局 MCP。

根因发生在 stdio server 启动阶段。npm `latest` 当前解析到 `ssh-mcp@2.4.0`，其依赖解析在当前环境中启动失败，Node 报 `ERR_MODULE_NOT_FOUND`，无法加载 `zod-to-json-schema`。server 在 MCP `initialize` 前退出，因此没有工具可注册；配置仍会被 `codex mcp list` 列出。

上游已发布 `v2.5.0`，但 npm `latest` 尚未更新。该版本移除了旧的 `zod-to-json-schema` override 并升级到 Zod 4，正是针对这条依赖链的修复。

## Goal

- 使全局 `pomelo-orbit-ssh` 在原生 Codex 与 `ccsp` managed profile 下都能被发现并完成 MCP 初始化。
- 固定到已验证可启动的上游 `ssh-mcp` 新版本，避免 npm `latest` 的 2.4.0 依赖问题。

## Non-goal

- 不修改 `ccs-plus` 的 Codex profile、`CODEX_HOME` 或 MCP 合并逻辑。
- 不改动项目级 `pomelo_delivery` MCP。
- 不创建本 feature 的 `docs/verification/` 文档。

## User scenarios

1. 用户在 `pomelo-orbit` 中运行 `ccsp` 并选择受管 Codex provider 时，可使用 SSH MCP 工具。
2. 用户直接运行 `codex mcp list` 或为受管 profile 运行 `codex --profile <name> mcp list` 时，均可看到相同的 `pomelo-orbit-ssh` 注册。

## Acceptance

- `pomelo-orbit-ssh` 使用 `github:tufantunc/ssh-mcp#v2.5.0`，而不是未修复的 npm `latest` 2.4.0。
- MCP server 能回应 `initialize` 与 `tools/list`，并注册 SSH 操作工具。
- 基础配置与 `ccs-plus` managed profile 的 MCP 列表均保留该 server。

## Open questions

- 上游何时将 `v2.5.0` 更新为 npm `latest`。在此之前继续固定 Git tag，避免无意回退到 2.4.0。

## Decisions

- 全局 MCP 配置改为：

  ```bash
  npx -y github:tufantunc/ssh-mcp#v2.5.0 -- --host=111.229.185.157 --user=ubuntu --key=C:/Users/leon/.ssh/id_rsa
  ```

- 以 Git tag `v2.5.0` 固定来源，优先使用已发布的上游新版，而不是未更新的 npm dist-tag。
- 不对 `ccs-plus` 源码做补偿性改动；此次问题属于外部 MCP server 的依赖启动失败。

## Risk

- Git 依赖需要启动时访问 GitHub；网络不可用会使 MCP 无法安装或启动。
- `v2.5.0` 的 tool schema 相对 2.4.x 有可观察变化，调用方不应依赖旧 schema 的文本或字段顺序。
- SSH MCP 具有远端执行与文件传输能力；应继续仅向受信任的会话和主机配置开放。
