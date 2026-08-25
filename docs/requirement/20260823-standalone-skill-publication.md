# ccs-plus 独立 Skill 发布
最后修改时间: 2026-08-23 18:05:22

Review status: Accepted

流程模式: light / 轻量模式

## Background

`ccs-plus` 只提供 `ccsp-provider-manage` 独立 skill。同步策略由新版规范源提供，项目将其 完整 vendoring 到 `scripts/release.py` 和 `scripts/test_release.py`；项目配置只位于 `release.py` 顶部配置区。

## Goal

仅发布 `ccsp-provider-manage` 独立 skill，并安全管理每个已安装客户端的精确 skill 叶子目录。

## Non-goal

- 不为 ccs-plus 创建 native plugin、manifest 或 marketplace。
- 不写入真实客户端 Home、共享 `skills/` 父目录、plugin cache 或凭据目录。
- 不修改 provider CLI、数据库或用户配置。

## Acceptance

- 项目配置只声明 `skill` 资产及其 `check`、`list`、`apply`、`remove` 子命令；vendored 引擎收到未声明的 `plugin` 资产时必须在写入前失败。根命令与 `skill` 命令组无参时分别等价于 `--help`。
- `make release` 依次执行 `python scripts/release.py skill check --strict`、`pip install -e .` 与 `python scripts/release.py skill apply --strict`；`check` 和 `apply` 均在写入前完成源和三端预检。
- 自动模式跳过缺失 CLI；显式客户端或 `--strict` 缺失时无写入失败。
- 测试覆盖 `check`、`list`、`apply`、`remove`、`--dry-run`、显式选择与 `--strict`。
- `scripts/release.py` 只在顶部配置区声明项目资产；其余客户端适配器、JSON 解析、Home 计算和目录 替换逻辑必须与规范源整体一致，不创建额外配置模块或同步器。

## Decisions

- `ccsp-provider-manage` 保持 standalone skill，不包含 native plugin、manifest 或 marketplace 兼容层。
- 发布脚本是规范源的本地副本；通用修复先进入规范源，再整体替换本项目两个脚本并重新填写配置区。
- 命令级测试使用 subprocess、临时 Home 与 fake CLI，不接触用户客户端状态。
- 用户明确要求实现后测试所有子命令，本需求直接进入 `Accepted` 并连续进入 Verification。

## Risk

后续若 ccs-plus 新增 native plugin，应单独设计并实现其发布流程，不应向独立 Skill 发布脚本回填插件适配器。
