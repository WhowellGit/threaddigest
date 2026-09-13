# STATUS (prune-stale; rewritten, never appended)

**As of 2026-09-13, end of the first build session.** Plan approved. Late on 2026-09-13: the per-run JSONL sidecar was cut from the design (`raw_json` per row is the single raw store) and the agent model-tier policy (the main session plans, Opus judges, Sonnet does mechanical work) was adopted into `PLAN.md` and `CLAUDE.md`. The M0 foundation tranche is built, gated, and committed locally on `main` (M0 commit `e5bd86f`; cleanup commits after it added the plan renderer, curation specs, and handoff fixes; see `git log -1` for HEAD). No GitHub remote yet, so CI has never executed and the no-commit-to-main guard is inactive until `make setup` installs pre-commit and a remote exists.

## What exists and is green
- `make check` passes end to end and was reproduced in a fresh clone by an independent verifier: ruff format + lint (strict rule set incl. banned APIs), mypy strict on `src/` (daemon state now under `.build/`, never tracked), import-linter (3 layering contracts kept), pytest (532 test functions by the ratchet's AST count, 941 collected cases, 97% line coverage, network blocked, warnings are errors), ratchets at the measured baseline.
- `core/`: deletion state machine, revisit ladder, paging rules, budget, models (pydantic rows), normalize (markdown sanitized at ingest, bot heuristic, rejects), themes (regex with timeout), retry policy and exit codes, digest model with denominators and a golden render.
- `db/`: schema revision 1 (17 tables incl. workspaces and backups; AUTOINCREMENT on the two FTS content tables, posts and comments; epoch timestamps; column comments), Alembic with transactional DDL, live-view FTS5 with gated triggers, schema.sql golden + fingerprint, pragma-enforcing engine factory. Verified empirically: FTS `integrity-check` needs `rank=1` to compare against content; `INSERT OR REPLACE` burns keys and detaches FTS rows.
- `ports.py` + `adapters/`: gateway/clock/notifier/process-runner protocols, the fake Reddit scenario builder (failure injection, request accounting, fixtures), fake and macOS notifiers.
- Enforcement: settings with data-dir refusal under pytest, autouse temp data dir, ratchet tool (measure/compare/bump/loosen with ledger), two fail-closed hard-block hooks, the doc-currency gate (G33), CI workflow, pre-commit config, PR template, `CLAUDE.md` working agreement.
- Deployment: launchd plists (06:30/12:30/18:30 + hourly doctor), wrapper with TCC refusal, caffeinate, exit-code mapping and notifications; install/uninstall scripts (not installed).
- Docs: plan (rendered with `make plan-html` to the git-ignored `docs/PLAN.html`), four panel reports and the adversarial review, TEST_STRATEGY v1 (208 specs plus WS/CU specs for workspace lifecycle and curation), DECISIONS, RUNBOOK, KNOWN_ISSUES, GUARDS, INDEX router.

## Queued tasks (added late 2026-09-13)
- **Prune the reference material** (Wes): remove documents, or sections of documents, that are useless for this project or could lead it down the wrong road again, in the repo copies and in the archive. Method: an Opus pass over the eight retrospectives (and the other reference documents) classifying each section keep / remove / misleading, with the reason; Wes approves the removal list before anything is deleted; the harness assessment's transfer calls feed it. Written rules are not enforcement, so the pruning also lists which of the day's written rules have a mechanical check and which do not.
- `hard_after=` on relaxed ratchet lines in `tools/ratchet.py`, with a positive control (approved).

## Not built yet (next)
- M1a: `adapters/reddit_praw.py` (probe-first), `services/` (run lifecycle, sweep, trees, revisit, reconcile, scrub, tagging), CLI commands (`run`, `doctor`, `probe`, `db`; `make run` currently prints that the command is not built), post-run invariants through the real run path, cassettes, `make fixture`.
- M2: schema revision 2 (`workspaces.archived_at`, `post_themes.origin`, `posts.watch_until`), the web UI incl. workspace lifecycle and curation controls (specs WS-01..06, CU-01..10).
- Gate bookkeeping: `GUARDS.md` positive-control cells, `@pytest.mark.gate` markers on the remaining gates, TEST_STRATEGY `planned` → `shipped` flips.
- Small follow-ups: Settings should read `.env` (the launchd wrapper exports it today); suppression baseline is 11 noqa / 7 type-ignores / 5 pragmas (bootstrap level, to be driven down).

## Decisions waiting on Wes
- Compliance bounds and the commercial-use stance: Wes is handling these himself.
- `docs/reference/earlier-project-retrospectives/` (~700 KB of the earlier employer's internal material): the tiered value assessment found 15 residual insights (4 high) plus 8 process gaps; residual value judged low; judge and critic recommend distill and remove; the dissent is recorded. Residuals are distilled in `docs/learnings/LEARNINGS_TRANSFER.md` §7 with a disposition each; two live spec errors were corrected and the plan's gates-table drift was swept. **Disposition of the raw files is Wes's call** (four options in §7; the planning session recommends keeping the three narrative files redacted and moving the rest to the archive, with a history rewrite before the first push). Executed 2026-09-13: option 4 (three narrative files kept redacted, five moved to the archive, local history rewritten after a verified bundle); the harness assessment landed as `docs/reference/reviews/2026-09-13-harness-assessment.md`.
- Wes ruled on the proposals (2026-09-13): `hard_after=` on relaxed gates approved (small change to `tools/ratchet.py`, queued); duties record approved, light, at M2; amber dismissal control not adopted, replaced by D-29 (nothing advisory in the gate); both ratios approved for the quarterly review; the superseded-claims check stands as a recommendation. Product intent restated as D-28 (monitor and manage complaints; assemble the user's actual problem from vague reports; the under-weighted framing separable). Learnings are extracted from the earlier project, not blended (DECISIONS late section).
- Retrospectives disposition done (see above); pre-rewrite bundle in `~/repos/insightminer-desktop-archive/git-bundles/`.
- Wes returns later today to answer: Reddit login and script-app credentials, the GitHub repo, and the agent token scope.

## Session hygiene
- The 2026-09-13 build session ran from `~/Desktop/Test`, so the repo's hard-block hooks were never loaded and the auto-memory was keyed to that path (drift finding 14). Every session for this project starts in `~/repos/insightminer`; the memory was copied there add-only on 2026-09-13.

## Known contradictions to settle in the D0 follow-up
- Test-count floor: the adversarial review cut it, the enforcement panel kept it with the loosening protocol; the tool implements the floors with loosening (kept for now).
- `should_defer_run` semantics and exit codes 4/5/130 are defined in `core/retry.py`; the CLI must adopt them.
