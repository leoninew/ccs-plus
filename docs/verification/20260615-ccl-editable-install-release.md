# ccl editable install / release 验证

Review status: Accepted

Flow mode: light / 轻量模式

## What changed

- 将入口模块从 `cc-switch.py` 移动为 `src/cc_switch/cli.py`，采用主流 `src` package layout。
- 在 `pyproject.toml` 中增加 `build-system`、`project.scripts` 和 setuptools package discovery 配置。
- 项目包名从 `cc-switch-provider-launcher` 改为 `cc_switch`。
- 新增 console script：`ccl = "cc_switch.cli:main"`。
- 新增 Python packaging 的 editable install 入口，执行 `pip install -e .` 后可使用 `ccl` console script。
- 构建/开发入口从 `Makefile` 迁移到 `justfile`：`install` 安装开发依赖，`dev` 执行 `uv run ccl ...`，`check` 运行 ruff/mypy。
- 删除不再需要的 `scripts/ccl.sh` 和 `scripts/install.sh`。
- README 改为说明 `pip install -e .` 和安装后的 `ccl` 用法，不再推荐 `scripts/ccl.sh`。
- 测试改为直接 `import cc_switch.cli as launcher`。
- `.gitignore` 和 `clean` 增加 `*.egg-info` 清理/忽略，避免 editable install 生成物进入版本控制。

## Acceptance

- [x] `pyproject.toml` 声明可安装的 CLI 入口：`ccl = "cc_switch.cli:main"`。
- [x] `pip install -e .` 成功安装 `cc-switch-0.1.0`。
- [x] 安装后生成的 `ccl` console script 可执行。
- [x] `ccl --help` 可通过 console script 输出 CLI help。
- [x] `ccl alias` 可通过 console script 读取默认 `.env` 并展示 alias。
- [x] `ccl list` 可通过 console script 读取默认数据库并展示 provider 列表。
- [x] `DEFAULT_ENV_FILE` 仍指向仓库根目录 `.env`，未因 editable install 或 `src` package layout 变成 package 子目录路径。
- [x] 不再存在 `cc-switch-provider-launcher` 文本引用。
- [x] 不再依赖 `scripts/install.sh` 或 `scripts/ccl.sh`。
- [x] 相关 lint、format、typecheck 和 unit tests 通过。

## Commands

```bash
just check
# OK: ruff check passed, ruff format --check passed, mypy passed

pip install -e .
# OK: editable install successfully built and installed cc-switch-0.1.0
# Note: pip reported existing invalid distributions in the Python environment and warned about one script directory not being on PATH.

python -m unittest tests.test_cc_switch
# OK: Ran 23 tests

ccl --help
# OK: console script printed CLI help

ccl alias
# OK: console script printed configured CLI aliases

ccl list
# OK: console script printed provider list

python -c "import cc_switch.cli as cli; from pathlib import Path; print(Path(cli.DEFAULT_ENV_FILE)); print(Path(cli.DEFAULT_ENV_FILE).parent == Path(cli.__file__).resolve().parents[2])"
# OK: printed D:\SourceCodes\mywork\cc-switch\.env and True

rg cc-switch-provider-launcher
# OK: no matches found
```

## Remaining risk

- `pip install -e .` 使用调用时的 `pip`，如果用户 shell 中 `pip`、`python` 和 `PATH` 指向不同环境，可能出现 `ccl` 安装到了非预期 Scripts 目录的问题；本次验证环境中 `ccl --help`、`ccl alias`、`ccl list` 均可运行。
- `pip install -e .` 会生成 egg-info 元数据；已加入 `.gitignore` 和 `just clean` 清理规则。
- 本次删除了旧脚本入口；依赖 `./scripts/ccl.sh` 的历史用法需要改为 `pip install -e .` 后使用 `ccl`，或开发时使用 `just dev ...`。
