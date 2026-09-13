# STATUS (prune-stale; rewritten, never appended)

**As of 2026-09-13, end of the first build session.** Plan approved. The M0 foundation tranche is built, gated, and committed locally on `main` (M0 commit `e7a6f8a`; cleanup commits after it added the plan renderer, curation specs, and handoff fixes; see `git log -1` for HEAD). No GitHub remote yet, so CI has never executed and the no-commit-to-main guard is inactive until `make setup` installs pre-commit and a remote exists.

## What exists and is green
- `make check` passes end to end and was reproduced in a fresh clone by an independent verifier: ruff format + lint (strict rule set incl. banned APIs), mypy strict on `src/` (daemon state now under `.build/`, never tracked), import-linter (3 layering contracts kept), pytest (532 test functions by the ratchet's AST count, 941 collected cases, 97% line coverage, network blocked, warnings are errors), ratchets at the measured baseline.
- `core/`: deletion state machine, revisit ladder, paging rules, budget, models (pydantic rows), normalize (markdown sanitized at ingest, bot heuristic, rejects), themes (regex with timeout), retry policy and exit codes, digest model with denominators and a golden render.
- `db/`: schema revision 1 (17 tables incl. workspaces and backups; AUTOINCREMENT on the two FTS content tables, posts and comments; epoch timestamps; column comments), Alembic with transactional DDL, live-view FTS5 with gated triggers, schema.sql golden + fingerprint, pragma-enforcing engine factory. Verified empirically: FTS `integrity-check` needs `rank=1` to compare against content; `INSERT OR REPLACE` burns keys and detaches FTS rows.
- `ports.py` + `adapters/`: gateway/clock/notifier/process-runner protocols, the fake Reddit scenario builder (failure injection, request accounting, fixtures), fake and macOS notifiers.
- Enforcement: settings with data-dir refusal under pytest, autouse temp data dir, ratchet tool (measure/compare/bump/loosen with ledger), two fail-closed hard-block hooks, the doc-currency gate (G33), CI workflow, pre-commit config, PR template, `CLAUDE.md` working agreement.
- Deployment: launchd plists (06:30/12:30/18:30 + hourly doctor), wrapper with TCC refusal, caffeinate, exit-code mapping and notifications; install/uninstall scripts (not installed).
- Docs: plan (rendered with `make plan-html` to the git-ignored `docs/PLAN.html`), four panel reports and the adversarial review, TEST_STRATEGY v1 (208 specs plus WS/CU specs for workspace lifecycle and curation), DECISIONS, RUNBOOK, KNOWN_ISSUES, GUARDS, INDEX router.

## Not built yet (next)
- M1a: `adapters/reddit_praw.py` (probe-first), `services/` (run lifecycle, sweep, trees, revisit, reconcile, scrub, tagging), CLI commands (`run`, `doctor`, `probe`, `db`; `make run` currently prints that the command is not built), post-run invariants through the real run path, cassettes, `make fixture`.
- M2: schema revision 2 (`workspaces.archived_at`, `post_themes.origin`, `posts.watch_until`), the web UI incl. workspace lifecycle and curation controls (specs WS-01..06, CU-01..10).
- Gate bookkeeping: `GUARDS.md` positive-control cells, `@pytest.mark.gate` markers on the remaining gates, TEST_STRATEGY `planned` → `shipped` flips.
- Small follow-ups: Settings should read `.env` (the launchd wrapper exports it today); suppression baseline is 11 noqa / 7 type-ignores / 5 pragmas (bootstrap level, to be driven down).

## Decisions waiting on Wes
- Reddit account + script app credentials; GitHub private repo `WhowellGit/insightminer` and whether the plan allows branch protection; agent token scope after M0.
- Keep or cut the per-run JSONL sidecar (recommendation: cut).
- Confirm compliance bounds (14-day backups, 7-day exports, per-tier reconcile ages) and the commercial-use stance for a coworker.
- `docs/reference/earlier-project-retrospectives/` contains the earlier project's internal identifiers (Jira URLs, a named employee email, another user's home paths). The repo is private; decide before any handoff to a coworker whether to keep, redact, or drop the folder in favor of `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md`.

## Known contradictions to settle in the D0 follow-up
- Test-count floor: the adversarial review cut it, the enforcement panel kept it with the loosening protocol; the tool implements the floors with loosening (kept for now).
- `should_defer_run` semantics and exit codes 4/5/130 are defined in `core/retry.py`; the CLI must adopt them.
