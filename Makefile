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
CODE_HEALTH := $(BUILD_DIR)/code_health.json

.PHONY: help setup hooks check test run fixture schema ratchet-bump ratchet-loosen plan-html \
        memory-check memory-export code-health

help:
	@echo "make setup            install uv if missing, Python 3.13, all dependency groups, .env, pre-commit hooks"
	@echo "make hooks            install the pre-commit hooks into this checkout (nothing else)"
	@echo "make check            ruff format, ruff check, mypy strict, import-linter, pytest+coverage, ratchets"
	@echo "make test             uv run pytest"
	@echo "make fixture          generate the demo corpus into data/demo.json (generated, never committed)"
	@echo "make run              fixture, db init, then run --gateway fake against .build/run-data"
	@echo "make schema           regenerate src/insightminer/db/schema.sql from the migrations"
	@echo "make code-health      measure code health into .build/code_health.json (check does this first)"
	@echo "make ratchet-bump     tighten ratchet floors to the measured values"
	@echo "make ratchet-loosen   KEY=<key> REASON=\"<why>\" [HARD_AFTER=YYYY-MM-DD]  loosen one floor"
	@echo "                      (lands a GUARDS.md row; HARD_AFTER turns it red again on that date)"
	@echo "make memory-check     audit this machine's Claude Code memory (also runs at the end of check)"
	@echo "make memory-export    snapshot that memory into memory-snapshot/, add-or-update only"

setup:
	@if ! command -v $(UV) >/dev/null 2>&1; then \
	  if command -v brew >/dev/null 2>&1; then brew install uv; \
	  else curl -LsSf https://astral.sh/uv/install.sh | sh; fi; \
	fi
	$(UV) python install 3.13
	$(UV) sync --all-groups
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from .env.example: add your Reddit app credentials."; fi
	$(MAKE) hooks

# Standalone so an existing checkout can install the hooks without a full `make setup`, and
# so `make check`'s closing line has something to name. `make setup` calls this target
# rather than repeating the command: one installer, one place to fix it.
hooks: ## install the git hooks and pre-build their environments (network on first run)
	$(UV) run pre-commit install --install-hooks

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Every step fails the target on error (bash -e, one command per line). The green stamp from an
# earlier run is removed first, so a check that goes red cannot leave yesterday's stamp behind.
check: | $(BUILD_DIR)
	@rm -f $(BUILD_DIR)/check-green.json
	$(UV) run ruff format --check
	$(UV) run ruff check
	@rc=0; $(UV) run dmypy --status-file $(BUILD_DIR)/dmypy.json run -- src || rc=$$?; \
	if [ $$rc -eq 1 ]; then exit 1; fi; \
	if [ $$rc -ne 0 ]; then echo "dmypy exited $$rc; falling back to mypy"; $(UV) run mypy src; fi
	$(UV) run lint-imports
	$(UV) run pytest -m "$(MARKEXPR)" --cov --cov-report=term --cov-report=json:$(BUILD_DIR)/coverage.json -p no:cacheprovider
	$(UV) run python tools/code_health.py --write $(CODE_HEALTH)
	$(RATCHET) measure --write $(SUMMARY)
	$(RATCHET) compare
	@echo "<!-- make-check-summary:begin -->"
	@cat $(SUMMARY)
	@echo
	@echo "<!-- make-check-summary:end -->"
	@$(UV) run python tools/hooks_status.py
	@$(UV) run python tools/memory_snapshot.py check
	@$(UV) run python tools/memory_snapshot.py diff
	@$(UV) run python tools/check_stamp.py

# Claude Code's auto-memory: the one asset here that no rebuild can regenerate. It is keyed to
# this checkout's absolute path and lives outside git, so `check` audits it (unreachable files,
# dangling index links, the index budget, the frontmatter contract) and `export` mirrors it into
# memory-snapshot/ add-or-update only -- a file deleted upstream is reported, never deleted here.
# Both print their findings; on a machine with no memory directory (CI) they say exactly that.
memory-check:
	$(UV) run python tools/memory_snapshot.py check

memory-export:
	$(UV) run python tools/memory_snapshot.py export

# Code health (Wes, 2026-09-14): complexipy, radon, ruff's size rules, vulture with a counted
# whitelist, and pylint's duplicate-code, written to one report the ratchet reads like the
# coverage report. bump and loosen depend on it so a stale report can never set a floor.
code-health: | $(BUILD_DIR)
	$(UV) run python tools/code_health.py --write $(CODE_HEALTH)

ratchet-bump: code-health
	$(RATCHET) bump

ratchet-loosen: code-health
	@if [ -z "$(KEY)" ] || [ -z "$(REASON)" ]; then \
	  echo 'usage: make ratchet-loosen KEY=<key> REASON="<why>"' >&2; exit 2; fi
	$(RATCHET) loosen KEY=$(KEY) REASON="$(REASON)" $(if $(HARD_AFTER),HARD_AFTER=$(HARD_AFTER),)

schema:
	$(UV) run python -m insightminer.db.schema_dump

test:
	$(UV) run pytest -m "$(MARKEXPR)"

# `run` is the documented first-run sequence (design-round5 §19.10, Wes's Q9): `db init`
# creates the schema, `run` refuses a database that does not exist. INSIGHTMINER_DATA_DIR is
# explicit and NOT the default ./data, because `--gateway fake` is refused against the real
# data directory (D-10 / CF-02) and a developer smoke run must never touch collected data.
RUN_DATA_DIR ?= $(BUILD_DIR)/run-data
# Generated, never committed (data/ is git-ignored): `make fixture` is the only producer,
# and `make run` regenerates it so a demo never collects from a stale corpus.
RUN_FIXTURE ?= data/demo.json

fixture:
	$(UV) run python tools/make_demo_fixture.py $(RUN_FIXTURE)

run: fixture | $(BUILD_DIR)
	INSIGHTMINER_DATA_DIR=$(RUN_DATA_DIR) $(UV) run insightminer db init
	INSIGHTMINER_DATA_DIR=$(RUN_DATA_DIR) $(UV) run insightminer run --gateway fake --fixture $(RUN_FIXTURE)

plan-html: ## render docs/PLAN.md to docs/PLAN.html for browser review
	$(UV) run python tools/render_plan.py
