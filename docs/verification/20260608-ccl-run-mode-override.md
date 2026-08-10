# ccl run mode override Verification

## Review status

Accepted

## Mode

light

## Scope note basis

基于 `docs/requirement/20260608-ccl-run-mode-override.md`。

## Actual diff summary

- `cc_provider_launch.py`
  - 为 `run` 新增可选参数 `--mode {direct,proxy}`。
  - `use_proxy` 支持按 `args.mode` 单次覆盖 `proxy_config.proxy_enabled`。
  - `check_proxy()` 改为只检查 proxy 端口可连接，允许 `--mode proxy` 在数据库 `proxy_enabled = 0` 时生效。
- `tests/test_cc_provider_launch.py`
  - 测试 helper 支持 `mode`。
  - 新增 `--mode direct` 覆盖 proxy enabled 的测试。
  - 新增 `--mode proxy` 覆盖 proxy disabled 的测试。
  - 修复 env args 测试受外部环境变量污染的问题。
- `docs/README.md`
  - 更新 `run` 命令形态、示例和启动方式说明。
- `docs/requirement/20260608-ccl-run-mode-override.md`
  - 更新为 light 模式 scope note，状态为 `Accepted`。

## Planned vs actual changed files

计划范围：

- `cc_provider_launch.py`
- `tests/test_cc_provider_launch.py`
- `docs/README.md`
- `docs/requirement/20260608-ccl-run-mode-override.md`
- `docs/verification/20260608-ccl-run-mode-override.md`

实际改动与计划一致。

## Acceptance criteria checklist

- [x] `python cc_provider_launch.py run --help` 包含可选 `--mode {direct,proxy}`。
- [x] 不传 `--mode` 时仍按 `proxy_config.proxy_enabled` 自动选择。
- [x] `--mode direct` 在 `proxy_enabled = 1` 时强制 direct。
- [x] `--mode proxy` 在 `proxy_enabled = 0` 时强制 proxy。
- [x] `--mode proxy` 仍会检查 proxy 端口可连接。
- [x] `--mode direct` 不检查 proxy 端口。
- [x] 不支持 `route`，由 argparse choices 拒绝。
- [x] 覆盖只影响本次运行，不写 cc-switch.db。
- [x] README 更新命令形态和行为说明。

## Test results

```text
python -m unittest tests.test_cc_provider_launch
.......
----------------------------------------------------------------------
Ran 7 tests in 0.021s

OK
```

```text
python cc_provider_launch.py run --help
usage: cc_provider_launch.py run [-h] [--db DB] [--env-file ENV_FILE]
                                 [--cwd CWD] [--mode {direct,proxy}]
                                 app provider_number
```

```text
python cc_provider_launch.py run claude 1 --mode route
cc_provider_launch.py run: error: argument --mode: invalid choice: 'route' (choose from direct, proxy)
```

```text
make check
uv run ruff check cc_provider_launch.py
All checks passed!
uv run mypy
Success: no issues found in 1 source file
```

## Missed or expanded scope

- 未扩展到请求级 / 会话级 provider override。
- 未修改 cc-switch Rust/Tauri proxy。
- 未修改数据库写入逻辑。

## Risks / incomplete items

- `--mode direct` 当前仍会读取 `proxy_config`；这保持了改动最小，但意味着缺少 `proxy_config` 时仍会失败。
- 本次未删除此前生成的 strict-style `spec.md`；light 模式实现未依赖该文件。

## Conclusion

实现满足 light scope note：`ccl run` 支持 `--mode direct` / `--mode proxy` 单次覆盖数据库中的自动判断，并保持默认行为不变。
