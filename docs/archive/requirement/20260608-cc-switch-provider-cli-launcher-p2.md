# cc-switch 指定供应商 CLI 启动器 P2 Requirement

## 背景

P1 启动器已经可以通过 Bash + Python 读取 cc-switch 数据库，为 Claude Code CLI / Codex CLI 生成临时配置。

cc-switch 新版本已有正式路由模式：CLI 可以连接本地 proxy，由 cc-switch 根据当前 provider 或 failover queue 转发请求。launcher 不需要实现请求级 provider override，也不需要修改 cc-switch 当前 provider。

## 目标

P2 目标是移除用户可见的 `--mode` 参数，改为自动读取 cc-switch 数据库判断启动方式：

```bash
./scripts/ccl.sh run claude <provider_number>
./scripts/ccl.sh run codex <provider_number>
```

判断规则：

- `proxy_config.proxy_enabled = 0`：direct 启动，使用命令中的 provider 编号。
- `proxy_config.proxy_enabled = 1`：路由启动，CLI 连接 cc-switch 本地 proxy。

路由启动时，provider 编号不用于切换 cc-switch 当前 provider；实际 provider 由 cc-switch 当前状态或 failover queue 决定。

## 范围

### 必须支持

- 移除 `run --mode` 参数。
- Claude 自动 direct / 路由启动。
- Codex 自动 direct / 路由启动。
- 启动器读取 `proxy_config.proxy_enabled` 判断是否路由。
- 路由启动前检查 proxy 端口可连接。
- 路由启动不写 `providers.is_current`。
- 路由启动不写本地 settings 当前 provider 字段。
- 路由启动不修改 proxy takeover 状态。

### 应支持

- 帮助信息不再展示 `--mode`。
- 文档不再要求用户手动选择 direct 或路由参数。
- 错误信息区分：proxy 未启用、proxy 端口不可连接、provider 编号越界、Codex config-home override 未配置。

## 非目标

- 不实现请求级 / 会话级 provider override。
- 不修改 cc-switch Rust/Tauri proxy。
- 不改变 cc-switch current provider 语义。
- 不替代 failover queue。
- 不要求支持远程代理。
- 不要求支持 GUI 配置。
- 不要求支持 Claude/Codex 之外的 app。
- 不在启动器中重写 Anthropic/OpenAI/Gemini 协议转换。

## 验收标准

- `python cc_provider_launch.py run --help` 不包含 `--mode`。
- `proxy_config.proxy_enabled = 0` 时，Claude 使用 provider direct settings 启动。
- `proxy_config.proxy_enabled = 1` 时，Claude settings 指向 cc-switch proxy。
- `proxy_config.proxy_enabled = 0` 时，Codex 使用 provider auth/config 生成临时目录。
- `proxy_config.proxy_enabled = 1` 时，Codex `base_url` 指向 cc-switch proxy `/v1`。
- 路由启动不修改 cc-switch current provider。
- 路由启动不修改全局 live config。
- 输出中不泄露 API key/token。

## 风险

- 如果 `proxy_enabled = 1` 但本地 proxy 服务未运行，启动会失败并提示端口不可达。
- 路由启动实际使用的 provider 由 cc-switch 当前 provider / failover queue 决定，不保证等于命令行 provider 编号。
- Codex CLI 的临时配置目录机制仍依赖 `CC_PROVIDER_LAUNCH_CODEX_HOME_ENV`。

## 待议事项

- 是否需要在路由启动摘要中显式提示“provider 编号不强制路由”。
- 是否需要提供只读命令展示当前 `proxy_config.proxy_enabled` 状态。
