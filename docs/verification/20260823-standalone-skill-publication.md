# ccs-plus 独立 Skill 发布验证
最后修改时间: 2026-08-23 18:16:23

Review status: Accepted

流程模式: light / 轻量模式

## Requirement alignment

实现与 `docs/requirement/20260823-standalone-skill-publication.md` 一致：ccs-plus 仅声明
`ccsp-provider-manage` 独立 skill；项目内 vendored 脚本是新版规范源的完整副本，仅配置区有项目数据。

## Actual diff summary

- `scripts/release.py` 包含完整同步引擎；顶部配置区将 plugin 名称与路径设为 `None`，只声明
  `ccsp-provider-manage` standalone skill；未创建 `release_config.py`、`src/plugin_release`、
  `scripts/sync.py` 或错误拼写的 `relesae.py`。
- `scripts/test_release.py` 是规范源测试副本，覆盖 manifest/marketplace 校验、三端选择、精确
  plugin 操作规划与 standalone skill 叶子目录隔离，并确认未声明的 plugin 资产在写入前失败。
- `Makefile release` 按 `skill check --strict` -> `pip install -e .` -> `skill apply --strict` 顺序执行。
- README 只展示 `scripts/release.py` 的 standalone skill 管理命令。

## Expected vs actual changed files

| 预期文件 | 实际结果 |
| --- | --- |
| `scripts/release.py` | 已整体复制规范源，仅修改顶部项目配置区 |
| `scripts/test_release.py` | 已整体复制规范源测试 |
| `Makefile`、`README.md` | 已更新发布入口和文档 |
| requirement / verification 文档 | 已新增 |

## Acceptance checklist

- [x] 项目不声明 plugin 资产；请求 plugin 时 vendored 引擎在任何写入前返回失败。
- [x] `skill check`、`list`、`apply`、`remove` 均已测试，根命令与 `skill` 无参均显示帮助。
- [x] `apply` 和 `remove` 的 dry-run、显式目标、strict、自动跳过均已测试。
- [x] skill 文件操作仅影响 `skills/ccsp-provider-manage` 叶子目录。
- [x] 仓库不再包含 `sync.py` 或 `relesae.py` 发布入口或活跃调用引用；历史流程记录保留其当时的文件名。

## Test results

- `python scripts/test_release.py`: 10 passed。
- `uv run pytest tests`: 196 passed, 1 skipped。
- `uv run ruff format --check scripts/release.py scripts/test_release.py`: 未通过；规范源副本本身未按本仓库 100 列规则格式化。
- `uv run ruff check scripts/release.py scripts/test_release.py`: 未通过；同一规范源副本包含长行与一个未使用导入。
- `uv run mypy src`: passed。
- `python -m py_compile scripts/release.py scripts/test_release.py`: passed。
- `git diff --check`（受影响文件）: passed。

## Scope deviation

无。规范源已整体复制，未保留旧入口、共享引擎依赖或兼容 wrapper。

## Risks

未执行 `make release` 或真实 `skill apply`，因为它们会安装当前项目并写入真实客户端 Home。
`skill check`、`skill list` 和 `skill apply --dry-run` 已在本机三端 CLI 上验证；规范源测试在临时目录中验证了叶子目录隔离。

规范源的格式与本仓库 lint 规则不一致。不能只在本项目副本中格式化，否则会产生分叉；应先修订规范源，再整体更新所有项目副本。

## Incomplete items

无。

## Conclusion

独立 skill 发布实现与所有子命令行为均已验证，可交付。
