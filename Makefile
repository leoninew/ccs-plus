.DEFAULT_GOAL := help

.PHONY: help deps install check test release binary

UV ?= uv
UV_RUN ?= $(UV) run --locked --no-sync
CHECK_FIX := $(filter 1 true yes,$(fix))

RUFF_FORMAT_ARGS := --check
RUFF_CHECK_ARGS :=
TEST_COV_ARGS :=

ifeq ($(OS),Windows_NT)
PYINSTALLER_DATA_SEPARATOR := ;
PROJECT_ROOT := $(shell cygpath -w "$(CURDIR)")
else
PYINSTALLER_DATA_SEPARATOR := :
PROJECT_ROOT := $(CURDIR)
endif

ifneq ($(CHECK_FIX),)
RUFF_FORMAT_ARGS :=
RUFF_CHECK_ARGS := --fix
endif

ifneq ($(filter 1 true yes,$(cov)),)
TEST_COV_ARGS := --cov=src/ccs_plus --cov-report=term-missing --cov-report=html:htmlcov
endif

help: ## Show the public workflow.
	@printf "Usage: make <target> [fix=1] [cov=1]\n"
	@printf "Requires uv; make binary requires make deps first. Docker targets additionally require Docker.\n"
	@printf "\nTargets:\n"
	@printf "make deps                 Sync locked project dependencies\n"
	@printf "make install              Install the CLI as a user editable tool\n"
	@printf "make check [fix=1]        Check format, lint, and types\n"
	@printf "make test [cov=1]         Run tests, optionally with coverage\n"
	@printf "make release              Build source and wheel distributions\n"
	@printf "make binary               Build a local one-file binary with PyInstaller\n"

deps:
	$(UV) sync --all-groups --locked

install:
	$(UV) tool install --editable . --force

test:
	$(UV_RUN) pytest tests $(TEST_COV_ARGS)

check:
	$(UV_RUN) ruff format $(RUFF_FORMAT_ARGS) src tests
	$(UV_RUN) ruff check $(RUFF_CHECK_ARGS) src tests
	$(UV_RUN) mypy src

release:
	$(UV) build

binary:
	$(UV_RUN) pyinstaller \
		--noconfirm \
		--clean \
		--onefile \
		--name ccs-plus \
		--paths src \
		--distpath dist \
		--workpath build/pyinstaller \
		--specpath build/pyinstaller \
		--add-data "$(PROJECT_ROOT)/settings.yaml$(PYINSTALLER_DATA_SEPARATOR)." \
		--hidden-import ccs_plus \
		--collect-all prompt_toolkit \
		--collect-all dynaconf \
		--collect-submodules ccs_plus \
		src/ccs_plus/__main__.py
	@echo "Binary: dist/ccs-plus (or dist/ccs-plus.exe on Windows)"
