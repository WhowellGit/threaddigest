# Insight Miner developer entry points. Everything runs through uv; nothing else is
# installed globally. `make check` is the one command that gates every change and is
# exactly what CI runs.
# macOS-only tests (launchd, plutil) are deselected off Darwin; they run on the Mac and in a macOS job.
MARKEXPR := $(shell [ "$$(uname -s)" = Darwin ] && echo "not live" || echo "not live and not macos")
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
# The uv installer puts uv in ~/.local/bin; make it visible to the rest of `make setup`.
export PATH := $(HOME)/.local/bin:$(PATH)

UV ?= uv
BUILD_DIR := .build
SUMMARY := $(BUILD_DIR)/check-summary.json
RATCHET := $(UV) run python tools/ratchet.py

.PHONY: help setup check test run schema ratchet-bump ratchet-loosen

help:
	@echo "make setup            install uv if missing, Python 3.13, all dependency groups, .env, pre-commit hooks"
	@echo "make check            ruff format, ruff check, mypy strict, import-linter, pytest+coverage, ratchets"
	@echo "make test             uv run pytest"
	@echo "make run              uv run insightminer run"
	@echo "make schema           regenerate src/insightminer/db/schema.sql from the migrations"
	@echo "make ratchet-bump     tighten ratchet floors to the measured values"
	@echo "make ratchet-loosen   KEY=<key> REASON=\"<why>\"  loosen one floor (lands a GUARDS.md row)"

setup:
	@if ! command -v $(UV) >/dev/null 2>&1; then \
	  if command -v brew >/dev/null 2>&1; then brew install uv; \
	  else curl -LsSf https://astral.sh/uv/install.sh | sh; fi; \
	fi
	$(UV) python install 3.13
	$(UV) sync --all-groups
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example: add your Reddit app credentials."; fi
	$(UV) run pre-commit install

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Every step fails the target on error (bash -e, one command per line).
check: | $(BUILD_DIR)
	$(UV) run ruff format --check
	$(UV) run ruff check
	@rc=0; $(UV) run dmypy run -- src || rc=$$?; \
	if [ $$rc -eq 1 ]; then exit 1; fi; \
	if [ $$rc -ne 0 ]; then echo "dmypy exited $$rc; falling back to mypy"; $(UV) run mypy src; fi
	$(UV) run lint-imports
	$(UV) run pytest -m "$(MARKEXPR)" --cov --cov-report=term --cov-report=json:$(BUILD_DIR)/coverage.json -p no:cacheprovider
	$(RATCHET) measure --write $(SUMMARY)
	$(RATCHET) compare
	@echo "<!-- make-check-summary:begin -->"
	@cat $(SUMMARY)
	@echo
	@echo "<!-- make-check-summary:end -->"

ratchet-bump:
	$(RATCHET) bump

ratchet-loosen:
	@if [ -z "$(KEY)" ] || [ -z "$(REASON)" ]; then \
	  echo 'usage: make ratchet-loosen KEY=<key> REASON="<why>"' >&2; exit 2; fi
	$(RATCHET) loosen KEY=$(KEY) REASON="$(REASON)"

schema:
	$(UV) run python -m insightminer.db.schema_dump

test:
	$(UV) run pytest -m "$(MARKEXPR)"

run:
	$(UV) run insightminer run

plan-html: ## render docs/PLAN.md to docs/PLAN.html for browser review
	$(UV) run python tools/render_plan.py
