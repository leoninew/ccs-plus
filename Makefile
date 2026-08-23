.DEFAULT_GOAL := help

.PHONY: help install release test check binary

help:
	@echo "Common targets:"
	@echo "  make install       Sync project and development dependencies"
	@echo "  make release       Install this project and publish the standalone skill"
	@echo "  make test          Run the test suite"
	@echo "  make check         Run lint and apply formatting"
	@echo "  make binary        Build a local one-file binary with PyInstaller"

install:
	uv sync --all-groups

release:
	python scripts/release.py skill check --strict
	pip install -e .
	python scripts/release.py skill apply --strict

test:
	uv run pytest tests

check:
	uv run ruff format .
	uv run ruff check .
	uv run mypy src

binary:
	uv pip install "pyinstaller>=6.11,<7"
	uv run pyinstaller \
		--noconfirm \
		--clean \
		--onefile \
		--name ccs-plus \
		--paths src \
		--hidden-import ccs_plus \
		--collect-all prompt_toolkit \
		--collect-all dynaconf \
		--collect-submodules ccs_plus \
		src/ccs_plus/__main__.py
	@echo "Binary: dist/ccs-plus (or dist/ccs-plus.exe on Windows)"
