# Guards ledger

> Structure from the enforcement panel report (`docs/reference/reviews/2026-09-13-panel-enforcement.md` § F): **Active**, **Retired** (append-only), **Loosenings** (append-only, written by `make ratchet-loosen`, never by hand). Verdict vocabulary from the earlier project: **EARNED** (fired in anger and was right), **EARNED AT BIRTH ONLY**, **UNPROVEN**, **SELF-SERVING**. "Firings" are derived from CI failures posted to the pinned "Guard firings" issue, never typed here. Reviewed quarterly (`RUNBOOK.md` § 6). Adding a guard needs a birth incident, a positive control, a row here, and a check whether an existing guard can be widened; the guard-count ratchet makes an addition a loosening that pauses for approval.
>
> Seeded 2026-09-13 with the M0 shipped gate set from the plan ("M0 foundation tranche") so the code agents can attach positive-control node ids. Every row is born clean (someone else's incident) and therefore **UNPROVEN**; the adversarial review's point stands that a guard never seen failing is a hypothesis. The `Positive control node` column is filled by the code agents with the pytest node id under `tests/gates/` (`@pytest.mark.gate("<ID>")`); a blank cell after M0 is a doc-currency failure. IDs follow the enforcement panel (G-nn) and, where the guard is a database spec, the database panel (DB-nn), so `TEST_STRATEGY.md`, the reports, and the markers agree.

## Active

| ID | Name | Birth incident | Mechanism | Positive control node | Fails how | Born | Verdict (date) | Firings → pinned issue |
|---|---|---|---|---|---|---|---|---|
| G04 | Layering (import-linter `layers` contract) | Plan § Module map ("layering enforced by import-linter, not convention"); earlier project's hot zones and god modules, `docs/reference/earlier-project-retrospectives/SYSTEM_ARCHITECTURE_AND_REBUILD.md` via reviewer B | `.importlinter` layers `web \| cli` → `services` → `db \| adapters` → `ports` → `core`; `lint-imports` in `make check` and CI | | blocks merge | M0 | UNPROVEN (2026-09-13) | — |
| G05 | External-package chokepoints (`praw` only in `adapters.reddit_praw`; `sqlalchemy`/`alembic`/`sqlite3` only in `db/`; `fcntl` only in `services.lock`) | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` rank 10 (opt-in guard bypassed by the main helper, A #44) | import-linter `forbidden` contracts; ruff `TID251` for `create_engine`, `sqlite3.connect`, `text(` outside `db/` (import-linter cannot ban symbols; adversarial D7) | | blocks merge | M0 | UNPROVEN (2026-09-13) | — |
| G06 | Network block in tests | Plan § Testing strategy principle ("the collector never touches the network in tests"); extended across the subprocess seam by adversarial B4 | `addopts = --block-network` (pytest-recording), `--record-mode=none` in CI; CLI refuses under `PYTEST_CURRENT_TEST` without `--gateway fake`; web routes use an injectable `ProcessRunner` | | test error / blocks merge | M0 | UNPROVEN (2026-09-13) | — |
| G15 | Schema snapshot golden (`db/schema.sql`) | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` rank 12 and 15 (schema version literal copied into six producers; diverging migrations, B S2–S6) | `alembic upgrade head` on an empty DB must reproduce the committed normalized DDL plus the generated column-comment section; `make schema` regenerates; failure prints the diff (DB-01) | | blocks merge | M0 | UNPROVEN (2026-09-13) | — |
| G16 | Models == DDL | Same as G15 ("model edited without a migration" is a named AI-assisted failure pattern, plan § Known patterns) | pytest-alembic `test_model_definitions_match_ddl`, single head, upgrade, up-down consistency; `include_object` excludes `%_fts`, `%_fts_%`, `%_live` (DB-02, DB-03) | | blocks merge | M0 | UNPROVEN (2026-09-13) | — |
| G19 | Data-directory isolation, in-process and across the subprocess seam | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` rank 1 (tests overwrote live artifacts twice; reads honored the test dir, writes did not, A #53–54); adversarial B4 (the same incident one process boundary over) | autouse fixture sets `INSIGHTMINER_DATA_DIR=tmp_path`; `Settings` raises when pytest is loaded and the dir resolves to the default unless `INSIGHTMINER_ALLOW_REAL_DATA_DIR=1`; data dir passed to children through the environment; `Path.home`/`expanduser` banned outside `settings.py` (DB-18, DB-19) | | test error | M0 | UNPROVEN (2026-09-13) | — |
| G31 | Connection chokepoint, behavioral pragma test | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` rank 10 (freshness guard written but never wired; an inert WAL guard on a read-only connection, A #17, #44) | a pooled connection obtained through `db.engine` on a read-write file DB reports `journal_mode=wal`, `foreign_keys=1`, `secure_delete=1`, `busy_timeout=30000`, `synchronous=1`, `temp_store=2` (DB-12) | | blocks merge | M0 | UNPROVEN (2026-09-13) | — |
| DB-20 | Upsert semantics and PK stability | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` rank 3 (`INSERT OR REPLACE` burned 16,813 rowids and raised a false divergence alarm, A #18); adversarial A10 (`AUTOINCREMENT`, drop `max(pk)==count(*)` at runtime) | `INSERT … ON CONFLICT(reddit_id) DO UPDATE` only; `AUTOINCREMENT` on `posts`/`comments`; three fake runs leave `pk` and `first_seen_at` unchanged per `reddit_id`; duplicate-in-page yields one row; purges recorded on the run row (DB-55) | | blocks merge (M1a: run `failed`) | M0 (repo) / M1a (run) | UNPROVEN (2026-09-13) | — |
| G11 | Coverage ratchet | Plan § Gates; enforcement panel § C (hard floor with half a point of slack; a stale floor is red) | coverage json over `core`, `services`, `adapters/reddit_fake.py` vs `.ratchets/coverage.txt`; three-way compare (measured vs file, file vs `render(measured)`, file vs `main`) by `tools/ratchet.py`; direction up | | blocks merge (loosening → approval) | M0 | UNPROVEN (2026-09-13) | — |
| G10 | Suppression ratchet (`noqa`, `type: ignore`, `no cover`, `filterwarnings ignore`, mypy overrides) | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` § 2 rule 8 and `docs/reference/earlier-project-retrospectives/WHY_THE_GUARDS_EXIST.md` (2,250 grandfathered suppressions became a permanent exemption) | `tools/ratchet.py measure`; ceiling 0 per key; every hit printed with file:line on every run; each needs a rule or error code; mypy `praw.*` override declared with a reason and counted | | blocks merge (loosening → approval) | M0 | UNPROVEN (2026-09-13) | — |
| G08/G09 | Skip/xfail ratchet at zero and runtime skipped == 0 | Plan § Gates; adversarial A13 (`-m "not live"` in `addopts` so opt-in suites are deselected, never skipped) | AST count of skip constructs with `reason="#n …"`; junit `skipped` of the required selection must be 0; `tests/live` fails without credentials when explicitly selected | | blocks merge (loosening → approval) | M0 | UNPROVEN (2026-09-13) | — |
| G01 | Exception-policy lint | Plan § Silent-failure controls; `docs/reference/reviews/2026-09-12-db-learnings-review-A.md` § A (silent-failure swallowing in KEY_LEARNINGS) | ruff `E722 BLE001 S110 S112 B904 TRY2xx TRY3xx RUF100`; every handler re-raises or records a warning counter on the run row; any warning makes the run `partial` | | blocks commit and merge | M0 | UNPROVEN (2026-09-13) | — |
| G07 | Warnings are errors in tests | Plan § Silent-failure controls (PRAW and SQLAlchemy deprecations must surface, not rot) | `filterwarnings = error`; proven by running pytest the way CI runs it | | blocks merge | M0 | UNPROVEN (2026-09-13) | — |
| G29 | Pre-commit: ruff format + lint, `dmypy` whole tree, gitleaks, large-file check, `no-commit-to-branch main` | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` rank 8 ("the only thing between a regression and the corpus was someone remembering to run the full suite", B T1) | `.pre-commit-config.yaml` via `uv run` so versions come from `uv.lock`; `make setup` installs the hooks; the weekly portability job commits a fake key and a 2 MB file and expects both rejected | | blocks commit | M0 | UNPROVEN (2026-09-13) | — |

## External controls (no positive control possible; a dated "last seen red" line instead, per the adversarial split)

| Control | Where | Last seen red | Notes |
|---|---|---|---|
| Branch protection / required checks on `main` | GitHub settings | never (not yet created) | Depends on the GitHub plan and the agent's token scope (`DECISIONS.md` § 7). Until settled, CI is a gate with a git trail, not an enforcement authority |
| Hard-block hooks (two): no `--no-verify` or direct push to `main`; no hand edits to `.ratchets/` or the hook settings | `.claude/settings.json` → `tools/hooks/` | never | Self-protecting, fail closed on internal error; govern only Claude Code tool calls in this project. Note (2026-09-13): project hook settings load only from the session's starting directory, so "never seen red" is not evidence the hook is live; sessions start in `~/repos/insightminer` |
| Portability job | CI weekly and on quickstart-file changes | never | Fresh Ubuntu container: `git clone && make setup && make check` |
| Healthchecks.io ping (M1d) | end of `run` | never | Replaces the launchd dead-man |

## Planned at M1a (post-run invariants; proven through `insightminer run --gateway fake` with a planted violation)

Compliance canary (DB-32 / ingest SC-01) and counters-versus-deltas (DB-54) flip a run to `failed`; structural population floors (DB-50, DB-51) and per-source freshness (ingest FR-01) start as `partial`/amber for the first 60 days. Rows are added here when the first of them is wired.

## Retired

| ID | Date | Verdict | Reason | Replaced by |
|---|---|---|---|---|
| | | | | |

## Loosenings

| Date | Key | From | To | Reason | PR |
|---|---|---|---|---|---|
| | | | | | |
