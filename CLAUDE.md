# Insight Miner: working agreement

Personal, rules-compliant Reddit harvester. Plan: `docs/PLAN.md`. Doc router: `docs/INDEX.md`.
Everything runs through `uv`: `make setup` once, then `make check` before every PR.
This file applies to every agent and human working in the repo.

## Rules and what enforces them

Enforcement is mechanical wherever possible. "Review" is the PR body plus a human or an
independent agent; it is the weakest column and appears only where no tool can check the rule.
The table is itself enforced: `tests/gates/test_rules_name_their_enforcer.py` resolves every
backticked path, pytest marker, ruff code and `make` target in the right-hand column against the
tree, so a row may not name an enforcer that does not exist; a row with no resolving enforcer must
say "review", and the number of review-only rows is a ceiling in `.ratchets/review_only_rules.txt`
that only goes down.

| Rule | Enforced by |
|---|---|
| Never weaken, skip, or delete a test to make a change pass | PR body "Tests changed" table (one reason per file); skip/xfail ratchet, each needing `reason="#issue …"`; assert-count, collected-test, and coverage floors in `.ratchets/`; `xfail_strict` |
| Never `git commit --no-verify`; never push to `main` | hard-block PreToolUse hook `tools/hooks/no_bypass_git.sh` (fails closed), proven by `tests/gates/test_hooks.py`; pre-commit `no-commit-to-branch` in `.pre-commit-config.yaml`; required CI in `.github/workflows/ci.yml` |
| Never catch a broad exception without recording it on the run row | ruff `E722`, `BLE001`, `S110`, `S112`, `B904`, `TRY*`; a run with any warning is `partial`, never `ok` |
| Every bug fix starts with a failing test and a `docs/runbook/KNOWN_ISSUES.md` row pointing at it | PR body; `tests/gates/test_known_issues_cite_collected_tests.py` (every node id a register row cites must name a test that exists) |
| Every schema change ships a migration, a prior-revision fixture DB in `tests/fixtures/db/`, and an updated `src/insightminer/db/schema.sql` | schema snapshot test; pytest-alembic models == DDL; `make schema` |
| Never hand-edit `.ratchets/` or the hook settings | hard-block hook; `tools/ratchet.py` is the only writer; floors are compared three ways on every `make check`, so a stale or hand-edited floor is red |
| Never touch the production DB by hand | `tests/gates/test_data_dir_isolation.py`: tests run in a temp `DATA_DIR` and settings refuse the default dir under pytest; a destructive operation takes a recorded fresh backup first (`tests/services/test_migrate_service.py`); the typed confirmation is review until the mutating commands land |
| Never store or log credentials | gitleaks in `.pre-commit-config.yaml`; `.env` is gitignored (`.gitignore`); config export never includes secrets |
| Report results by pasting the `make check` block, never by describing it | review of the PR body against the pasted-block section of the PR template; CI is the authority, not the message |
| A new guard needs a birth incident, a positive control in `tests/gates/`, a `docs/runbook/GUARDS.md` row, and a check whether an existing guard can be widened | `gate` marker; `tests/gates/` review; GUARDS.md quarterly review |
| No new abstraction without two concrete uses | review |
| Four layers only: `web \| cli` > `services` > `db \| adapters` > `ports` > `core`; `praw` only in `adapters/reddit_praw.py` | import-linter contracts in `.importlinter`; `tests/gates/test_layering.py` |
| `create_engine`, `text()`, `sqlite3.connect` only inside `db/`; `mock.patch` only in `tests/adapters/`; `encoding=` on every text open | ruff `TID251`, `PLW1514` |
| Tests never touch the network; warnings are errors | pytest `--block-network -W error` in `pyproject.toml`; `tests/gates/test_pytest_config.py` |

## Routing: read before you touch

| If you are about to… | Read first |
|---|---|
| Start a session | `docs/recent/STATUS.md` |
| Touch the schema, migrations, upserts, FTS, backups | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §1–§2, then `docs/runbook/RUNBOOK.md` § migrations |
| Touch deletion, scrubbing, reconcile, or anything compliance-related | `docs/PLAN.md` § Data model (content-state machine), `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §2, `docs/runbook/KNOWN_ISSUES.md` |
| Add or change a gate, ratchet, invariant, or test policy | `docs/PLAN.md` § Robustness → "Guard design rules", `docs/reference/reviews/2026-09-12-db-learnings-review-A.md` §B, `docs/runbook/GUARDS.md` |
| Change the collector's fetch, budget, revisit, or search behavior | `docs/PLAN.md` § Collector algorithm, `docs/reference/reviews/2026-09-12-collector-design-review.md` §1 |
| Change the web UI | `docs/PLAN.md` § Web UI, `docs/reference/reviews/2026-09-12-ui-design-review.md` |
| Wonder why something was decided the way it was | `docs/insights/INSIGHTS_2026-09-12.md`, then `docs/decisions/DECISIONS.md` |
| Evaluate a new approach or library | `docs/decisions/DECISIONS.md` § settled negatives first (do not rebuild a killed lever) |
| Run a retrospective, or judge whether a lesson from the earlier project held | `docs/learnings/LEARNINGS_TRANSFER.md` (§5 predictions; §6 how to evolve it) |

## PR protocol

1. Branch from `main`. Write the failing test first (`core/` is strict TDD; `services/` test
   against the fake gateway and a temp DB created by `alembic upgrade head`).
2. `make check` is green locally. Pre-commit runs on every commit: ruff, dmypy on the whole
   `src` tree, gitleaks, no files over 1 MB, no commits on `main`.
3. Open the PR with `.github/pull_request_template.md`: **What**; **Tests changed** (every file
   under `tests/`, with a reason); the pasted **make check** block; **Ratchets** moved;
   **Independent review** for anything under `db/migrations`, `services/scrub`, `core/deletion`,
   or `db/repo`.
4. Ratchets move only through `make ratchet-bump` (tighter) or
   `make ratchet-loosen KEY=… REASON="…"` (a loosening pauses for approval and lands a
   `GUARDS.md` row).
5. Merge only when CI is green; never push to `main` directly. Every fixed bug lands a
   `KNOWN_ISSUES.md` row and every settled choice a `DECISIONS.md` entry.

## Operator surface

The web UI is the operator surface for every routine action: runs, harvesting a post,
reconcile, re-tag, backups and restore, health checks, config and archive import/export,
first-run setup. The CLI exists for schedulers, containers, tests, and break-glass recovery.
The CLI mirrors the UI, never the reverse: both call the same `services/` functions, and
`web` never imports `cli` (import-linter enforces it).

## Reporting to Wes

Clarity, not brevity. Write for a typical engineer who does not carry the project's whole history in
their head: plain English, jargon reduced and explained on first use, more context where the logic is
complicated, never dumbed down. An update opens with a short summary of what happened and offers
detail rather than dumping it. Never bring a half-formed question: assess thoroughly first, then
present a plain-English summary with context, a recommendation, a confidence level, and the pros,
cons, and risks; ask only if a genuine choice remains. Every set of findings or options carries a
recommendation and a confidence level. Applies to chat, PR bodies, and document summaries.

## Practices carried from the earlier project (2026-09-13)

- **Claim provenance.** Any claim of the form "X works / is fixed / improved" in a PR body, commit
  message, or `DECISIONS.md` entry names the exact test, command, or query that verifies it; the
  review pass checks that the cited test asserts the claim, not that a similarly named test exists.
  A count, percentage, or date range an agent reports gets one spot-check against the data before it
  is written into a document. The operator is never the first to question a load-bearing claim.
- **Every mirror in the same change.** A decision that changes a settled fact is not complete until
  every document stating the old fact is annotated in the same PR, and the PR body names the
  documents swept.
- **Swept and clean.** A suspicion investigated and found not to be a bug is recorded in
  `docs/runbook/KNOWN_ISSUES.md` § Swept with how it was checked, so no later session re-investigates it.
- **Partial findings early.** On work spanning more than one stage or touching a core surface
  (deletion, scrub, migrations, `db/repo`, the ranking, the digest), the first partial finding or
  open question goes to Wes as a three-line note when it exists, not at the end.
- **Sessions start in the repo root.** Project hook settings load only from the session's starting
  directory, so a session that starts elsewhere runs without the hard-block hooks.

## Agent model tiers

Every sub-agent call (the `Agent` tool or a workflow `agent()`) names its model; nothing inherits.
The main session carries planning, synthesis, decisions, and edits to the plan or enforcement
surfaces. **Opus** for judgement-bearing work: reviewers, judges and critics, migrations,
`core/deletion`, `services/scrub`, `db/repo`, under-specified services, red-gate debugging.
**Sonnet** for well-specified mechanical work: inventories, scans, codemods, tests written from a
spec row, fixture scrubbing, residue sweeps. Unsure → the higher tier, with the reason in the
workflow's `meta.description`. Full table: `docs/PLAN.md` § Review harness → "Agent model tiers".

## Commands

`make setup` · `make check` · `make test` · `make run` · `make schema` · `make ratchet-bump` ·
`make ratchet-loosen KEY=… REASON="…"`
