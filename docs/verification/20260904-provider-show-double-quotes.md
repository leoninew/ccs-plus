# provider show 双引号命令输出验证
最后修改时间: 2026-09-04 21:42:09

Flow mode: light / 轻量模式

Stage: Verification / 验证

Review status: Draft

## Requirement alignment

实现与 [Requirement / 需求](../requirement/20260904-provider-show-double-quotes.md) 一致：`provider show` 的 delete 和 add 命令全部改为双引号参数，原 Bash 单引号专用渲染已移除。

## Spec alignment

不适用。light / 轻量模式未创建独立 Spec / 规格文档。

## Plan alignment

不适用。light / 轻量模式依据 Requirement / 需求直接实现和验证。

## Actual diff summary

- `src/ccs_plus/cli.py` 将 `_bash_quote` 替换为 `_command_quote`，并将 delete/add 命令的所有参数接入该函数。
- `_command_quote` 始终生成双引号边界，并将参数内的 `"` 转为 `""`。
- `tests/test_cli.py` 更新 show 命令的预期输出，并增加同时包含单引号和双引号的 provider 名称覆盖。
- 补充本 Requirement / 需求和 Verification / 验证文档。

## Expected vs actual changed files

| 预期范围 | 实际文件 | 结果 |
| --- | --- | --- |
| show 命令参数渲染 | `src/ccs_plus/cli.py` | 一致 |
| show 命令回归测试 | `tests/test_cli.py` | 一致 |
| 过程文档 | `docs/requirement/20260904-provider-show-double-quotes.md`、本文件 | 一致 |

## Acceptance checklist

- [x] delete 命令的 provider 名称使用双引号。
- [x] add 命令的必填与可选 provider 参数均使用双引号。
- [x] 名称中的单引号保留，内嵌双引号输出为 `""`。
- [x] 定向 show 测试通过。
- [x] 全套测试通过。
- [x] diff 无空白错误。

## Test results

| 命令或检查 | 结果 |
| --- | --- |
| PowerShell 参数透传：`"O'Connor ""quoted"""` | 通过；Python 收到 `O'Connor "quoted"` |
| `cmd` 参数透传：`"O'Connor ""quoted"""` | 通过；Python 收到 `O'Connor "quoted"` |
| `python -m pytest tests/test_cli.py -k provider_show` | 通过；4 passed, 37 deselected |
| `python -m pytest` | 通过；198 passed, 1 skipped |
| `git diff --check` | 通过；无输出 |
| `python -m ruff check src/ccs_plus/cli.py tests/test_cli.py` | 未通过；当前 Python 环境未安装 `ruff`，报 `No module named ruff` |

## Scope deviation

无。实际产品代码仅涉及命令渲染函数及其测试；过程文档为本次记录所需新增文件。

## Risks and gaps

- 本次只验证了空格、单引号和双引号。`$`、反引号和 `%` 等特殊字符在 PowerShell 与 `cmd` 的解析规则不同，仍可能需要按使用 shell 额外转义。
- Ruff 静态检查未运行，因为当前 Python 环境未安装开发依赖中的 `ruff`；未为此修改依赖或环境。

## Incomplete items

在包含 Ruff 的开发环境中运行 `python -m ruff check src/ccs_plus/cli.py tests/test_cli.py`，可补齐静态检查记录。

## Conclusion

`provider show` 已统一输出双引号命令，核心行为和完整测试套件均通过。验证记录保留为 Draft，等待用户复核；除缺失 Ruff 静态检查外，没有未完成的代码验证项。
