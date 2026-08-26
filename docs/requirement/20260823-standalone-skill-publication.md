# ccs-plus 独立 Skill 源码交付
最后修改时间: 2026-08-26

Review status: Accepted

流程模式: light / 轻量模式

## Background

`ccs-plus` 在 `skills/ccsp-provider-manage/` 维护独立 skill 源码，并提供可分发的 Python CLI。当前 checkout 不包含 `scripts/install.py`、`scripts/release.py` 或对应同步测试；项目也没有声明负责把该 skill 安装到用户客户端目录。

## Goal

维护 `ccsp-provider-manage` 的仓库内 skill 源码和 ccs-plus Python 发布包。skill 的用户级安装由采用它的交付流程或客户端工具显式决定，不由本项目自动执行。

## Non-goal

- 不为 ccs-plus 创建 native plugin、manifest 或 marketplace。
- 不写入真实客户端 Home、共享 `skills/` 父目录、plugin cache 或凭据目录。
- 不修改 provider CLI、数据库或用户配置。
- 不因仓库包含 skill 源码而引入同步脚本或用户级安装副作用。

## Acceptance

- `skills/ccsp-provider-manage/` 是当前唯一的 standalone skill 源；不创建 native plugin、marketplace 或客户端 Home 镜像。
- `make install` 只执行用户级 editable CLI 安装；它不承担 skill 同步。
- `make release` 只执行 `uv build`，在 `dist/` 构建 source distribution 和 wheel；不安装 CLI、不写入客户端目录，也不上传制品。
- 若未来明确要由 ccs-plus 管理客户端 skill 生命周期，应新增 `scripts/install.py` 的 `skill check/apply` 契约，并仅从 `make install` 调用；不得恢复 `release.py` 或让 `release` 承担同步。

## Decisions

- `ccsp-provider-manage` 保持 standalone skill，不包含 native plugin、manifest 或 marketplace 兼容层。
- skill 源码的存在不隐含用户级同步责任；当前项目只维护源码和 Python 包构建。
- 若将来引入同步，通用逻辑先在规范源演进，再以 `scripts/install.py` 和对应测试整体复制，并通过显式安装工作流验证。

## Risk

后续若 ccs-plus 新增 native plugin 或接管 standalone skill 同步，应单独设计安装契约、manifest 预检和用户目录写入边界；不能把该副作用放回 `release`。
