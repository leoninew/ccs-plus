# ccl editable install / release 需求

Review status: Accepted

Flow mode: light / 轻量模式

## Background

当前本地使用入口依赖 `scripts/ccl.sh` / `scripts/install.sh` 或手工 alias。为了降低维护成本，希望改成更标准的本地安装方式：通过 editable install 安装项目，并让本地命令入口由 Python packaging 机制提供。

## Goal

- 增加一个面向本地使用的 editable install 入口。
- 使用 `pip install -e .` 将当前项目以 editable 模式安装到本地 Python 环境。
- 项目提供标准 CLI 入口，使安装后可以直接执行 `ccl`。
- 减少或移除手写安装脚本带来的占位符替换、路径注入和维护复杂度。
- alias 如果保留，应作为用户快捷方式，而不是指向源码文件的安装机制。

## Non-goal

- 不发布到 PyPI 或远程包仓库。
- 不自动修改用户 shell 配置文件（如 `.bashrc`、`.zshrc`）。
- 不执行 git commit / push。
- 不在本阶段重构与 provider 选择、backup、restore、run 行为无关的业务逻辑。

## User scenarios

- 用户在仓库中执行 `pip install -e .` 后，可以在本地 shell 中运行 `ccl list`。
- 用户移动或编辑源码后，editable install 下的 `ccl` 能使用最新源码。
- 用户可以自行添加类似 `alias c1='ccl run claude 1'` 的快捷 alias，但不需要 alias 指向 `cc-switch.py`。

## Acceptance

- `pyproject.toml` 声明可安装的 CLI 入口，例如 `ccl = "...:main"`。
- `pip install -e .` 能执行 editable install。
- 安装后 `ccl list` / `ccl alias` 等命令可通过 console script 入口运行。
- `just install` 的职责保持清晰：用于安装开发依赖，或与 editable install 的职责不混淆。
- 如果 package 化导致默认 `.env` 查找路径变化，需要明确处理，避免从项目根目录意外变成 package 目录。
- 不再依赖 `scripts/install.sh` 的占位符替换安装方式；是否删除 `scripts/ccl.sh` 可在实现时根据兼容需要决定。

## Open questions

- 暂无。

## Decisions

- 将 `ligth start` 按 `light start` 理解，当前使用轻量模式 / light。
- editable install 使用 `pip install -e .`。
- 安装入口使用 Python packaging 的 console script 生成 `ccl`，不再通过 alias 指向源码文件。
- 删除不再需要的脚本，包括旧的安装脚本；如果实现后 `scripts/ccl.sh` 不再承担兼容职责，也删除。
- 实现必须保证默认 `.env` 查找路径不因 editable install 或模块/package 化而意外改变；优先继续读取仓库根目录 `.env`，除非后续明确迁移配置目录。
- 本阶段只记录需求，不修改产品代码。

## Risk

- 如果 `pip install -e .` 安装到的 Python 环境和用户实际 shell 使用的 Python / PATH 不一致，`ccl` 可能不可见或依赖不可用。
- 将单文件脚本改成 package 可能影响 `Path(__file__)` 派生出的默认路径，尤其是 `.env`。
- 删除旧脚本可能影响已有文档或用户习惯，需要在实现时同步 README。