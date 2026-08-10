.DEFAULT_GOAL := help

.PHONY: help install release test check

help:
	@echo "Common targets:"
	@echo "  make install       Sync project and development dependencies"
	@echo "  make release       Install this project in editable mode"
	@echo "  make test          Run the test suite"
	@echo "  make check         Run lint and apply formatting"

install:
	uv sync --all-groups

release:
	pip install -e .

test:
	uv run pytest tests

check:
	uv run ruff format .
	uv run ruff check .
	uv run mypy src
