# M1a tranche A: the collector without Reddit (execution brief)

> **Status:** in flight, 2026-09-13. Prune-stale: deleted when M1a closes (its decisions move to `DECISIONS.md`, its spec rows flip to `shipped` in `TEST_STRATEGY.md`). Authored by the planning session; reviewed by an Opus panel before implementation (see `docs/reference/reviews/2026-09-13-m1a-tranche-a-review.md` once it exists).

## Why this tranche exists

M1a ("Posts ingestion") needs two things: the PRAW adapter, which is probe-first and therefore needs Wes's Reddit credentials, and everything around it: the repository, the run lifecycle, the sweep service, post-run invariants, `doctor`, the migration command with its pre-migration backup, and the CLI. The second set is decision-independent, is fully specified by `PLAN.md` § Collector algorithm and the M1a rows of `TEST_STRATEGY.md`, and can be built and proven end to end against `FakeRedditGateway` while Wes is away. Tranche B (the PRAW adapter, `probe`, cassettes, the contract suite against real captures) starts when credentials exist.

## Scope

| Module | Responsibility | Spec rows |
|---|---|---|
| `db/repo.py` | The only write path for collector tables. Upserts for `posts` and `comments` with `INSERT … ON CONFLICT(reddit_id) DO UPDATE`, a **field-ownership table per ingest path** (sweep may update score, `num_comments`, `upvote_ratio`, `edited_utc`, title/body/html, flair, and state fields it observes, never `first_seen_at`, `check_stage`, `next_check_at`); `post_sources`, `item_snapshots` (numeric), `authors` aggregates, `raw_rejects`, `subreddits` status transitions, `runs` and `run_subreddits`. Reads needed by the services (known posts in a window for `core.paging`, due posts, counts for invariants) | DB-06, DB-07, DB-13, DB-14, DB-20, DB-21, DB-25, DB-27, DB-48, GT-02, SW-05 |
| `services/lock.py` | `fcntl.flock` on `data/locks/collector.lock`; a held lock means alive; exit 75 with zero gateway calls when held; the only module that imports `fcntl` | RL-02, RL-04 |
| `services/runs.py` | Run lifecycle: on start mark `running` rows without a live flock and with `heartbeat_at` older than `run.stale_after_minutes` (3) as `crashed`, and `queued` rows older than 2 minutes without a pid as `failed`; insert the run row (kind, trigger, pid, app/praw/schema versions, `settings_fingerprint`); heartbeat every 5 s carrying the stage (`rate_wait:37s` is alive); finish with status, counters JSON, `api_requests`, error; exit code via `core.retry.exit_code`; wall-clock ceiling ends the run `partial` after the current batch | RL-03, RL-04, DB-17 |
| `services/sweep.py` | Step 1 of the algorithm for every enabled subreddit: forward `after` paging through `iter_new_pages`, `core.paging.plan_stop` and `gap_suspected`, one DB transaction per page (rows plus `run_subreddits` progress), stickies excluded from stop logic, overlap deduped by the upsert, subreddit identity by `name_lower` with a `t5_` mismatch aborting that sub loudly, status transitions (`forbidden`, `not_found`, `redirect` with auto-disable after N runs, `quarantined` disabled with alert) and recovery clearing `status`, `consecutive_failures`, `last_error`, `gap_suspected_at` after a complete sweep; the outer retry ladder (`core.retry.RetryPolicy` with the injected `Clock`) around each page; `RateLimited` → `plan_rate_limit_wait`; fatal gateway errors (`AuthFailed`, `HtmlBlocked`) abort the run, not the sub; a DB-locked write fails the page cleanly with nothing half-committed; `--dry-run` fetches and counts HTTP but performs zero DB writes | SW-01, SW-02, SW-03, SW-04, SW-07, SS-01, SS-03, SS-04, SS-05, SS-06, TE-01, TE-02, RL-07(a), CF-01 |
| `services/invariants.py` | Post-run checks that flip the run: counters equal table deltas (DB-54); FTS membership equals live rows via `_docsize` (DB-26); structural population floors on live rows with `author_state=known` naming the column (DB-50, NM-03a); every row written this run carries the current `normalizer_version` (DB-48); unknown enum values counted, never coerced (DB-25, NM-02); per-source freshness: every enabled source fetched successfully within the last 2 runs, else `partial`/amber during the first 60 days (FR-01); no `running` rows other than the current one. Each invariant is a named callable returning a violation or nothing; the runner records the list on the run row | DB-26, DB-48, DB-50, DB-54, FR-01, NM-02, NM-03, GT-01, G30 |
| `services/doctor.py` | The no-network subset: settings valid, data dir outside TCC folders, DB reachable and at Alembic head, `quick_check`, schema fingerprint compared (warning only, ordinary tables), free disk, last successful run age against `--alert-if-stale`, lock not stale, credentials present (not validated). Zero HTTP calls, proven with a gateway that has no routes. Each check is a row (name, ok, detail) so `/system` can render it later | CF-01, G18 |
| `services/migrate.py` | `db init` and `db upgrade`: online `sqlite3.Connection.backup()` to `data/backups/pre-migrate-<from>-<to>-<utc>.db`, `quick_check` on the copy, a `backups` row (path, sha256, size, integrity, kind), then `alembic upgrade head`, then `integrity_check` and `foreign_key_check`; on failure restore the copy and exit non-zero; `db current`; keeps the last 3 pre-migration backups | DB-37, DB-38, DB-46 |
| `cli.py` | `run [--gateway fake --fixture PATH] [--budget N] [--dry-run] [--no-comments --reason TEXT]` (comments stage is a no-op stub until M1b; the bypass flag records its reason on the run row), `doctor [--no-network] [--alert-if-stale 36h]`, `db init|upgrade|current`, `config validate`. Exit codes 0/1/3/4/5/75/78/130 from `core.retry.ExitCode`; config and auth failures exit 78 before any run row exists; refuses to start under `PYTEST_CURRENT_TEST` unless `--gateway fake`; `make run` wired | RL-02, CF-01, CF-02 |

Out of scope for this tranche: `adapters/reddit_praw.py`, `probe`, cassettes, comment trees (M1b), revisit/reconcile/scrub (M1c), themes and digest inside `run` (M1d), anything under `web/`.

## Design constraints already decided (do not reopen)

- Layering `web | cli > services > db | adapters > ports > core`; `services/` never imports `praw`; `create_engine`, `text()`, `sqlite3.connect` only inside `db/`; every text open names `encoding`; `fcntl` only in `services/lock.py`.
- Upsert is `ON CONFLICT DO UPDATE`; `pk` and `first_seen_at` never change on rerun; `AUTOINCREMENT` already on `posts` and `comments`.
- One DB transaction per page; a failure inside a page leaves nothing from that page.
- `next_check_at` is NOT NULL and set from `core.milestones.next_check` at first sight.
- Every mutating command takes the flock and writes a run row with a stage-bearing heartbeat.
- Unknown upstream enum values are stored raw and counted as `unknown_enum_values`.
- Dry-run: HTTP yes, DB writes zero. `doctor --no-network` and `config validate`: zero HTTP.
- `--budget` hard-capped at `static.budget.hard_cap` (5,000); bypass flags record a reason.
- A run with any warning is `partial`; `ok` means zero warnings.
- Settings are read from the settings object at call time, never captured at import.
- Services receive their collaborators explicitly (gateway, clock, notifier, engine, settings); `cli.py` is the only place they are constructed.
- Time in tests comes from `FakeClock`; no test sleeps.

## Decisions for the design stage (the Opus designer proposes, the reviewer challenges)

1. Repository API shape: SQLAlchemy Core statements with `sqlite.insert(...).on_conflict_do_update` versus ORM sessions; how the field-ownership table is declared so DB-21/SW-05 can assert it structurally.
2. How the current run is threaded through the services (a `RunContext` dataclass holding run pk, clock, counters, warnings).
3. The invariant contract (`Invariant = Callable[[InvariantContext], Violation | None]`) and how the run path applies them so GT-01/G30's planted violations flip `runs.status` without calling an invariant directly.
4. Counters: which keys exist (`posts_new`, `posts_updated`, `comments_new`, `rejects`, `unknown_enum_values`, `pages`, `api_requests`, `warnings`), stored as JSON on `runs.counters_json`, and how DB-54 computes deltas.
5. `doctor` check contract (name, ok, detail, severity) shared later by `/system`.
6. Whether `db init` on an empty data dir is `alembic upgrade head` plus seeding from `config/seed.yaml` (the plan says seed subreddits and themes are imported on first run).
7. Migration backup: `sqlite3.Connection.backup()` lives in `db/backup.py` (allowed to import `sqlite3`), and `services/migrate.py` calls it.

## Testing plan

- TDD per module: the failing tests come first from the spec rows above; `core/` is untouched except for bug fixes that start with a failing test.
- Service tests run against `FakeRedditGateway` scenarios and a temp DB created by `alembic upgrade head` (the existing `tests/db/conftest.py` engine fixture); `FakeClock` drives time.
- End-to-end tests go through `cli.run` with Typer's `CliRunner` and `--gateway fake`; positive controls for every invariant plant the violation in the fake or the DB and assert `runs.status` flips and the violation is named.
- The compliance canary and PK-stability tests run three reruns and compare `pk`, `first_seen_at`.
- Gates to add: RL-04 (walk the command tree; every mutating command takes the lock and writes a run row), CF-01 (no routes registered → zero HTTP), CF-02 (budget cap), GT-01/G30 (planted violations through the run path).
- Ratchets bump upward in the same commit; TEST_STRATEGY rows flip `planned` → `shipped` with the test path.

## Order, commits, and model tiers

| Step | Work | Tier | Gate before commit |
|---|---|---|---|
| 0 | Design spec: signatures, dataclasses, ownership table, counters, invariant and doctor contracts | Opus designer, Opus adversarial reviewer; the main session decides | brief updated |
| 1 | `db/repo.py` + `db/backup.py` with tests | Sonnet writes failing tests from the rows; Opus implements | `make check` |
| 2 | `services/lock.py`, `services/runs.py` | same | `make check` |
| 3 | `services/sweep.py` | Opus tests and implementation (judgement-heavy: retry, status transitions) | `make check` |
| 4 | `services/invariants.py` with planted-violation positive controls | Opus | `make check` |
| 5 | `services/doctor.py`, `services/migrate.py` | Sonnet tests, Opus implementation | `make check` |
| 6 | `cli.py` commands, `make run`, e2e tests | Opus | `make check` |
| 7 | Panel: two Opus reviewers (correctness and tests; operator and data safety) plus one Opus adversarial reviewer over the whole diff; findings fixed; P0 pauses | Opus; the main session synthesizes | `make check`, review recorded |
| 8 | Docs: TEST_STRATEGY flips, DECISIONS entries, STATUS rewrite, KNOWN_ISSUES for anything found, GUARDS rows for new gates, this brief deleted | The main session | doc-currency gate |

## Design freeze (2026-09-13, late evening)

The design stage ran five adversarial rounds (Opus designer, Opus reviewer). Each round closed the previous round's P0 and P1 findings and each round found new, real ones; by round five the findings were implementation-level (directory creation before the lock, a heartbeat call inside the wrong exception scope, SQL built in `services/` instead of `db/`, the order of the collect body). Those are cheaper to close with tests in hand than on paper, so the design is **frozen at round five**: the spec is `.build/m1a/design-round5.md` (git-ignored agent output, 4,103 lines; the scratch copy is the same file) and the ten round-five findings are carried as **mandatory implementation requirements** in `.build/m1a/round5-findings.json`, each to be closed with a named test. Decisions taken by the planning session on the carried questions: `gap_suspected_at` is a latch cleared only by an exhausted sweep; `runs.error` stays NULL on an invariant-only failure with the detail in `violations_json`; a FAILURE violation outranks a terminal status (the run is `failed`, exit 1); `items_seen` on a failed page keeps round-five behaviour until a test asks otherwise. Everything else in the brief's decision list stands, and the twelve section-19 disagreements were accepted as written (a revision 0002 adding the `network` run status and `violations_json`, with the prior-revision fixture database and the regenerated `schema.sql` the working agreement requires).

Implementation runs as one workflow: an Opus planner turns the spec's § 17 into ordered steps; per step a Sonnet test-writer writes the failing tests from the § 16 test map, an Opus implementer makes them pass without weakening any test and commits on a green `make check`, and a Sonnet verifier confirms the tree is clean and the commit exists; then a three-reviewer Opus panel over the whole diff, fixes, and a final gate. The planning session reads the panel's report and updates the documents (TEST_STRATEGY flips, DECISIONS, STATUS, KNOWN_ISSUES, GUARDS) afterwards.

## Definition of done

`uv run insightminer run --gateway fake --fixture <path>` on an empty data dir creates the DB via `db init`, sweeps the fixture subreddits into `posts` with sources, snapshots, and authors, writes a run row with counters and `api_requests`, passes the post-run invariants, and exits 0; running it again writes zero new posts and leaves every `pk` and `first_seen_at` unchanged; `--dry-run` makes zero DB writes; a held lock exits 75 with zero gateway calls; `doctor --no-network` exits 0 with zero HTTP calls and lists its checks; a planted violation flips the run to `failed` and names the invariant; `make check` is green with ratchets bumped; the panel review is recorded and its P0/P1 findings closed.
