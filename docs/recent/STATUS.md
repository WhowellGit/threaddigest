# STATUS (prune-stale; rewritten, never appended)

**As of 2026-09-13 (end of the first build session).** Plan approved; the M0 foundation tranche is built, gated, and committed locally on `main`. No GitHub remote yet.

## What exists and is green
- `make check` passes end to end: ruff format + lint (strict rule set incl. banned APIs), mypy strict on `src/`, import-linter (3 layering contracts kept), pytest (532 test functions, ~900 cases, 97% line coverage, network blocked, warnings are errors), ratchets at the measured baseline.
- `core/`: deletion state machine, revisit ladder, paging rules, budget, models (pydantic rows), normalize (markdown sanitized at ingest, bot heuristic, rejects), themes (regex with timeout), retry policy and exit codes, digest model with denominators and a golden render.
- `db/`: schema revision 1 (17 tables incl. workspaces and backups; AUTOINCREMENT keys; epoch timestamps; column comments), Alembic with transactional DDL, live-view FTS5 with gated triggers, schema.sql golden + fingerprint, pragma-enforcing engine factory. Verified empirically: FTS `integrity-check` needs `rank=1` to compare against content; `INSERT OR REPLACE` burns keys and detaches FTS rows.
- `ports.py` + `adapters/`: gateway/clock/notifier/process-runner protocols, the fake Reddit scenario builder (failure injection, request accounting, fixtures), fake and macOS notifiers.
- Enforcement: settings with data-dir refusal under pytest, autouse temp data dir, ratchet tool (measure/compare/bump/loosen with ledger), two fail-closed hard-block hooks, CI workflow, pre-commit, PR template, `CLAUDE.md` working agreement.
- Deployment: launchd plists (06:30/12:30/18:30 + hourly doctor), wrapper with TCC refusal, caffeinate, exit-code mapping and notifications; install/uninstall scripts (not installed yet).
- Docs: plan, five panel reports, adversarial review, TEST_STRATEGY v1 (208 specs), DECISIONS, RUNBOOK, KNOWN_ISSUES, GUARDS, INDEX router.

## Not built yet (next)
- M1a: `adapters/reddit_praw.py` (probe-first), `services/` (run lifecycle, sweep, trees, revisit, reconcile, scrub, tagging), CLI commands (`run`, `doctor`, `probe`, `db`), post-run invariants through the real run path, cassettes.
- Wes: Reddit account + script app credentials; GitHub private repo (and plan check for branch protection); decision on the JSONL sidecar (recommendation: cut); confirm compliance bounds; commercial-use stance for a coworker.
- Small follow-ups: Settings should read `.env` (wrapper exports it today); `types-regex` stub replaced the ignore; suppression baseline is 11 noqa / 7 type-ignores / 5 pragmas (bootstrap level, to be driven down); GUARDS.md positive-control cells to fill with test node ids.

## Known contradictions to settle in D0 follow-up
- Test-count floor: the adversarial review cut it, the enforcement panel kept it with the loosening protocol; the tool implements the floors with loosening (kept for now).
- `should_defer_run` semantics and exit codes 4/5/130 are defined in `core/retry.py`; the CLI must adopt them.
