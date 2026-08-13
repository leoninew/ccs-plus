# 加密供应商导入导出

最后修改时间: 2026-08-11 09:36:07

Review status: Accepted

Flow mode: standard / 标准模式

## Background

供应商需要在不同环境间迁移，但直接输出 `providers add` 命令会暴露 API Key。项目需要在现有 `providers add` 之外提供可备份、校验和恢复的原生命令，并让加密能力可复用于其他场景。

## Goal

- 新增 `ccs-plus providers export [file]` 与 `ccs-plus providers import <file>`。
- 导出自定义供应商为 JSON；API Key 使用 Fernet 加密，不能以明文出现在备份文件。
- 加密统一使用 `CCS_PLUS_ENCRYPTION_KEY`（对应 `settings.yaml` 的 `encryption_key`），而非导入导出专用密码；配置加载时立即校验它是有效 Fernet key。
- 导入完整解析、解密并校验所有记录后，以单一数据库事务写入。
- 省略导出路径时在项目 `data/` 目录创建 `providers-YYYYMMDD-HHMMSS.json`。
- 移除旧的 `scripts/provider_export.py` 命令导出脚本。
- 新增 `providers reset`，默认仅预览，传入 `--no-dry-run` 才清理全部非官方供应商。

## Non-goal

- 不导出官方供应商、请求历史、CLI 会话或其他 cc-switch 数据。
- 不保存或自动迁移 `CCS_PLUS_ENCRYPTION_KEY`；跨环境恢复时由用户经安全渠道配置同一密钥。
- 不支持旧导出脚本或其他备份格式。
- 不覆盖已有导出文件，不实现 `--force`、upsert 或远程存储。

## User scenarios

1. 用户在 `.env` 设置随机 `CCS_PLUS_ENCRYPTION_KEY` 后执行 `ccs-plus providers export`，项目 `data/` 目录生成带时间戳的加密 JSON。
2. 用户执行 `ccs-plus providers import providers-<timestamp>.json`，使用同一加密密钥恢复全部有效供应商。
3. 配置缺失、示例值、格式无效、备份密钥不匹配、JSON 非法、记录重复或与现有供应商重名时，命令失败且不写入任何供应商。
4. 用户执行 `ccs-plus providers reset` 查看待删除的非官方供应商；确认后执行 `ccs-plus providers reset --no-dry-run` 删除它们，官方供应商保留。

## Acceptance

- `providers add` 行为保持不变；新增 export/import 均支持 `-h` 与 `--help`。
- `.env.example` 说明各配置用途并给出 Fernet key 的 Python 生成命令，`.env` 被 Git 忽略；应用启动加载 `settings.yaml` 时拒绝缺失、占位或非法 Fernet key。
- JSON 含稳定的 `format: "ccs-plus.providers"`、`version: 1`、`encryption.algorithm: "Fernet"` 与供应商列表；每项只保存导入所需字段，`api_key` 为 Fernet token。
- 导出跳过官方供应商；不可解析的自定义供应商报错，不静默遗漏。
- 导入在写入前验证 JSON 结构、版本、Fernet token、应用类型、名称、endpoint、API Key、模型、effort 及重名冲突。
- 导入重建记录时使用当前 `apps.codex` 默认策略（与 `providers add` 相同），不回放备份中的旧 Codex sandbox TOML。
- 批量写入具备数据库事务原子性；任一写入冲突时不保留部分导入。
- reset 默认不修改数据库，`--no-dry-run` 在一个事务中删除所有非官方供应商及外键 endpoint，官方供应商不受影响。
- `make check`、`make test` 和本地配置加载通过。

## Open questions

暂无需要用户确认的未决事项。

## Decisions

- 使用单个通用 `CCS_PLUS_ENCRYPTION_KEY` 直接构造 Fernet，而不使用交互式口令、KDF 或备份文件内的 salt。
- 导出文件只包含自定义供应商的规范化导入数据，导入时重新生成 provider ID。
- 导入经 `build_provider` 重建 cc-switch `settings_config`，Codex 权限字段取自当前应用配置而非备份原文。
- 以 `(app, casefold(name))` 检查导入文件内及目标数据库中的重名，拒绝重复导入而非猜测覆盖策略。
- `--no-dry-run` 作为 reset 的显式破坏性确认；不增加第二个交互确认。

## Risk

- 备份文件中的 API Key 虽为密文，但持有同一 `CCS_PLUS_ENCRYPTION_KEY` 的人可解密；密钥必须独立、安全地分发和保管。
- 丢失密钥无法恢复备份中的 API Key。
- 时间戳精确到秒；同秒重复导出会因 `data/` 中的同名文件已存在而失败，避免静默覆盖。
