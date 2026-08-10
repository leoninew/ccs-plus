# 供应商管理与 CLI 启动器验证记录
最后修改时间: 2026-08-09 23:17:52

流程模式: standard

当前阶段: Verification / 验证

Review status: Draft

## Requirement Alignment

本次实现与已接受的 [Requirement](../requirement/20260809-provider-launcher-manager.md) 对齐：以 `uv` 管理的 Python CLI 直接读写 cc-switch SQLite 数据库，提供供应商管理命令与 Claude、Codex、Grok 原生启动器；稳定 state home 保留会话连续性，API Key 仅进入子进程环境。

关键约束已在实现和测试中覆盖：

- 命令入口为 `ccs-plus`，包含 `providers` 与 `launch` 两个命令组。
- 新增、查询与删除通过带 schema 预检、外键和短事务的 SQLite repository 完成；官方 provider 受保护。
- Claude 使用环境变量和 `--dangerously-skip-permissions`；Codex 使用受管理 profile 与 `--ask-for-approval never`；Grok 使用受管理 model 表、`--sandbox workspace` 和 `--always-approve`。
- Codex/Grok 的托管配置不写入 API Key，文件写入使用锁、备份和原子替换。

## Spec Alignment

不适用。本 feature 使用标准模式 / standard，已接受 Requirement 后直接进入 Plan。

## Plan Alignment

计划的模块边界与实际实现一致：

- `domain.py`、`database.py`、`adapters.py` 分别承担领域模型、cc-switch 数据库和配置转换。
- `settings.py` 通过 Dynaconf 读取 `settings.toml`、`.env` 与环境变量，解析数据库路径和三类稳定 state home。
- `managed_config.py` 维护本应用拥有的 Codex profile 与 Grok model 配置；`launcher.py` 构造无密钥 argv/env/cwd 并启动原生 CLI。
- Click CLI 与测试拆分为 `cli.py`、`test_cli.py`、`test_database.py`、`test_adapters.py`、`test_managed_config.py`、`test_launcher.py`。

计划规定的 Windows 文件锁由 `portalocker` 提供；其 Windows 条件依赖 `pywin32` 由 `uv` 解析并经 `uv.lock` 间接锁定，无需在项目中重复声明直接依赖。

## Actual Diff Summary

相对 `9d46fcb`，当前暂存差异包含 46 个文件：新增 3,135 行、删除 5,027 行。

- 项目从旧的 `cc_switch` 实现重构为 `ccs-plus` CLI，源码目录与 Python 入口统一为 `src/ccs_plus/`。
- 新增需求、计划和 CLI 权限调研文档，以及 `.env.example`、`settings.toml` 和更新后的项目元数据/锁文件。
- 替换旧的 provider 模块、存储层、启动逻辑和测试，新增以 SQLite、TOML profile、稳定 state home 为中心的实现与测试。
- 为保持全仓 Ruff 合规，更新了 `scripts/version-calc.py` 的标准库调用和 import 组织；这是验证中发现的范围扩展，不改变 CLI 业务行为。

## Expected vs Actual Changes

| 预期变更 | 实际状态 |
| --- | --- |
| 新建 `src/ccs_plus/` 及 `ccs-plus` console script | 已完成；源码包、imports 和入口均一致。 |
| 提供 provider CRUD 与三类原生启动器 | 已完成；Click help 显示 `providers` 和 `launch`。 |
| 直接读写兼容 cc-switch 的 SQLite schema | 已完成；repository/adapters 单元测试通过。 |
| 使用 Dynaconf 配置数据库和稳定 state home | 已完成；settings 单元测试通过。 |
| 以受管配置适配 Codex/Grok 并防止密钥落盘 | 已完成；managed config 和 launcher 单元测试通过。 |
| 添加验证阶段文档 | 本文档已创建，尚未由用户确认。 |

## Acceptance Criteria

- [x] `uv run ccs-plus --help` 可运行，显示 `providers` 与 `launch`。
- [x] 列表、JSON 输出、show、删除保护、同名歧义和错误退出码由 CLI/repository 测试覆盖。
- [x] 自定义 provider 的数据库写入、endpoint 关联、联合键删除、官方项保护和 schema 错误由数据库测试覆盖。
- [x] Claude、Codex、Grok 的 argv/env/state home、瞬时 model/effort 覆盖和 API Key 不进入 argv/profile 的约束由 launcher/config 测试覆盖。
- [x] Codex permission profile 与 Grok 受管理 model 表的内容、owner 保护、保留用户配置及原子写入路径由 managed config 测试覆盖。
- [x] 配置加载、路径解析及 `.env`/环境变量行为由 settings 测试覆盖。
- [ ] 三方 endpoint 的真实协议兼容性尚未验证；测试不发送模型请求。
- [ ] 对每种 CLI，在同一工作目录跨供应商创建并恢复真实会话的人工验收尚未执行。
- [ ] Codex 的原生交互界面不再显示 “Update Model Permissions” 需要在安装目标版本的实际 CLI 中人工确认。

## Test Results

| 命令 | 结果 |
| --- | --- |
| `uv run ccs-plus --help` | 通过；显示 `launch` 和 `providers`。 |
| `uv run ruff check .` | 通过，`All checks passed!`。 |
| `uv run pytest tests --tb=short -q` | 通过，`41 passed in 0.53s`。 |
| `git diff --check` | 通过，无空白错误。 |
| `git diff --cached --check` | 通过，无空白错误。 |

## Scope Differences

- 未实施 API 协议转换、代理、供应商编辑、会话迁移或删除 CLI 会话，符合 non-goal。
- 删除 provider 只删除数据库记录和外键 endpoint，不删除 Codex profile、Grok model 表、认证或会话，符合计划的显式限制。
- 额外修复了项目包名与源码目录不一致、Ruff 格式问题及虚拟环境中不完整的间接 Windows 锁依赖；这些修复保障 `uv` 安装、导入和验证可重复执行。

## Risks

- 无确认权限只适用于可信工作目录和供应商。Claude 不提供等价于 Codex/Grok 的工作区级 OS 沙箱。
- provider endpoint 可收到 API Key、提示词和代码上下文；本实现仅验证本地配置与原生协议形态，不验证上游服务安全性或完整兼容性。
- Grok 共享配置与 cc-switch SQLite 数据库仍可能被非合作进程并发修改；文件锁和 SQLite timeout 只能降低相应风险。

## Incomplete Items

需要用户使用可信的真实供应商完成三项人工验收：三种 CLI 的端到端启动、Codex 权限界面行为、以及跨供应商的原生会话恢复可见性。

## Conclusion

自动化验证通过，暂存差异的实现范围与已接受的 Requirement 和 Plan 一致。实网与交互式 CLI 验收尚未执行，因此本文保持 `Draft`，等待用户确认这些剩余人工验收的结论。
