# ccs run 固定启动目录并立即退出

最后修改时间: 2026-07-21 01:35:45

Review status: Accepted

Flow mode: light / 轻量模式

## Background

`ccs run` 原先使用 `tempfile.TemporaryDirectory` 生成一次性临时配置，并通过 `subprocess.call` **同步等待**目标 CLI 退出后才清理临时目录与共享 home 链接。结果是：

1. 交互会话期间 `ccs` 进程一直挂着，占用父进程位置。
2. CLI 退出后还要经历 detach / rmtree；Windows 上若文件仍被占用可能拖慢甚至卡住退出。
3. 无法在启动后立刻把控制权交还 shell，同时让目标 CLI 继续使用本次配置。

产品需要：按**供应商名称**落到固定启动目录、**不删除**该目录，`ccs run` 启动目标 CLI 后**立即返回**。

## Goal

1. 为每次 `ccs run` 计算稳定启动根目录，键为 **app family + provider name**（名称做路径安全化）。
2. 目录位于系统临时区下的固定前缀，例如： `{tempdir}/cc-provider-launch/{family}/{safe_provider_name}/` 其下仍按现有结构生成 `claude-settings.json` / `codex/` / `grok/` 等。
3. 同一供应商再次 `run` 时**复用**该目录，覆盖写入本次 private 配置（auth/config/settings），**不在 ccs 退出时删除**启动目录。
4. Codex / Grok 的 hybrid home 共享链接写入固定目录后**不再**在 launcher 退出时 detach；重复 run 时刷新已有 link-like 共享项，避免指向过期 real home。
5. `launch_subprocess` 使用 `Popen` 启动目标 CLI，并 **wait 直到子进程退出**，回传子进程退出码；不再在成功启动后立即返回。
6. 现有 direct / proxy、CLI args、env 选择、Codex home 隔离 fail-closed 等行为保持不变。

## Non-goal

1. 不改为 `os.exec*` 进程替换。
2. 不引入后台守护、PID 文件或跨会话进程管理。
3. 不自动清理历史固定目录（可由用户或后续命令处理）。
4. 不改变 provider 选择、proxy 判定、全局配置隔离策略。
5. 不把 `ccs run` 做成“启动后立即把控制权交还 shell”的后台启动器（交互式 CLI 需要前台独占终端）。

## User scenarios

1. 用户执行 `ccs run codex 1`：写入/更新固定目录配置，拉起 `codex`，`ccs` 保持等待直到目标 CLI 退出；会话期间 stdin / Ctrl+C 由目标 CLI 接收。
2. 用户再次对同一供应商 `ccs run`：复用同一路径，private 配置被覆盖为最新 provider 内容；共享 sessions 等链接被刷新到当前 real home。
3. 用户对另一供应商 `ccs run`：落到另一固定子目录，互不覆盖。
4. `ccs -v run ...` 能看到 Launch home 路径与 Launched pid。

## Acceptance

1. 启动目录路径由 family + 安全化 provider name 决定，同名同 family 稳定可复现。
2. `ccs run` 在目标 CLI 退出前保持前台等待，不提前把 shell 提示符交回。
3. 目标 CLI 退出后固定目录与其中配置/共享链接仍存在（不 rmtree）。
4. 不因退出而写回用户全局 Claude/Codex/Grok 配置。
5. 单元测试覆盖：路径稳定/消毒、launch wait 回传退出码、run 路径下 home 仍可共享 sessions；全量 `tests.test_cc_switch` 通过。
6. Windows 在测试清空 env 时仍能创建 junction（`cmd`/`mklink` 使用可靠 COMSPEC + 最小 env）。

## Open questions

无。实现阶段已按下列 Decisions 推进。

## Decisions

1. 根路径：`Path(tempfile.gettempdir()) / "cc-provider-launch" / family / safe_name`。
2. 路径消毒：替换 Windows 非法字符，折叠空白，空名回退 `provider`，保留设备名加 `_` 前缀。
3. 共享链接：保留在固定 home；每次 share 时若目标已是 link-like 则先 unlink 再重建。
4. 退出码：回传目标 CLI 退出码；可执行文件不存在仍抛 `LaunchError` → 退出码 1。
5. Windows `mklink`：通过 `COMSPEC`/`SystemRoot` 解析 `cmd.exe`，并注入最小 process env，避免 `PATH` 清空时 CreateProcess 失败。
6. **2026-07-21 修订**：放弃“Popen 后立即返回”。立即返回会导致 shell 与交互 CLI 争抢 stdin（提示符上出现莫名输入）且 Ctrl+C 无法正常结束会话；固定启动目录仍保留，仅恢复 wait。

## Risk

1. **磁盘残留**：固定目录与可能含密钥的临时配置长期留在 temp；权限依赖 OS temp 目录默认 ACL。
2. **同名供应商**：仅按 name 分目录时，同 family 下重名 provider 会共用目录并互相覆盖 private 配置。
3. **陈旧共享链接**：若刷新逻辑失败，可能指向已删除 real home；已用 link 刷新缓解。
