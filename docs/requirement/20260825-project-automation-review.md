# ccs-plus Makefile 审查结果

最后修改时间: 2026-08-25 21:32:18

Review status: Accepted

## 结论

`FAIL`。`install` 只同步 `.venv`，`release` 执行裸 pip editable 安装，`check` 默认格式化源码，且缺少 `deps`、`fix=1`、`cov=1`。

## 证据

- `Makefile:13-14` 使用 `uv sync --all-groups`。
- `Makefile:16-17` 使用 `pip install -e .` 充当 release。
- `Makefile:22-25` 的 `ruff format .` 默认写入源码。

## 目标规范

将依赖同步移到 `deps` 并使用 `--locked`；`install` 使用 `uv tool install --editable . --force`；`check` 直接执行 format/lint/typecheck，只有 `fix=1` 可以修改；`test cov=1` 组织覆盖率；新增 `release: uv build`，PyInstaller 的 `binary` 作为额外显式任务保留。
