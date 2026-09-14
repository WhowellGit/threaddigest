# Plan: Reddit Insight Miner (working name `insightminer`)

## Intent (read this first)

Insight Miner exists to make managing Premiere Pro complaints easier: it collects what people say on Reddit every day, keeps it honestly (deletions honoured, coverage shown with its denominator), and helps assemble the actual user problem from scattered, vague, non-technical reports, which is the hardest and most valuable step in support. The one question it answers is *what are people struggling with, how many distinct people, and for how long*. It is not a search engine over Reddit, not a bridge to any other system, and not a learned ranker: themes are rules Wes writes, ranking is one deterministic function, and an analysis layer comes only at M5. Success is judged by Wes reading seven consecutive daily digests against Reddit itself at the end of M1d, and by the predictions in `docs/learnings/LEARNINGS_TRANSFER.md` §5. The recurring human duties are three: read the digest, acknowledge alerts in the UI, label tags while browsing. Live status lives in one place, `docs/recent/STATUS.md`; this block carries durable intent only (D-28, 2026-09-13).

## Context

**Goal.** A personal, rules-compliant system that harvests Reddit discussion about Premiere Pro and adjacent video-editing communities every day, stores it locally, deduplicates it, and lets Wes browse it in a Reddit-like local web UI. Over 3–4 months the collection becomes a searchable asset for spotting the top Premiere Pro quality issues and customer complaints, and later feeds LLM summarization and trend analysis.

**Why this shape.** The Compass research report (Sept 2026, now `docs/reference/2026-09-11-compass-research-report.md`) fixed the constraints: authenticated OAuth via PRAW is the only compliant path, 100 queries/minute per client ID, honest versioned User-Agent, deletions/removals must be honored, no automated replies, home IP is preferable to a datacenter IP. It recommends starting minimal (poll `/new` → SQLite) and growing additively. This plan follows that ladder but with a Reddit-style UI instead of Datasette, because intuitive browsing and in-UI management of what is monitored are explicit requirements. Two independent design reviews (collector/data/tests; UI) were folded in; PRAW/prawcore behavior was checked against upstream `main` (PRAW 8.0.3, prawcore 4.0.0) on 2026-09-12.

**Decisions made (Q&A 2026-09-12):**

| Decision | Choice |
|---|---|
| Communities (v1) | r/premiere, r/VideoEditing, r/editors; optional r/AfterEffects, r/DavinciResolve. (Subreddit names are case-insensitive: r/videoediting *is* r/VideoEditing; the report's "distinct lowercase variant" is wrong. r/AdobePremierePro likely does not exist; the add-subreddit validator will say so.) |
| Product intent (restated 2026-09-13) | Monitor Premiere Pro complaints to make managing them easier and extract useful insights; the valuable, hard part is assembling the story of the actual user problem from scattered, vague, non-technical reports. The earlier project's "known but under-weighted" framing stays separable and optional; no connection to the earlier project's data sources (D-28) |
| "Themes" | Three concepts: **subreddit sources** (polled completely), **themes** = named keyword/regex rule groups that tag captured posts locally, **saved Reddit-wide searches** as a third source type (M3). #1 priority: surface top Premiere Pro quality issues/complaints |
| UI stack | FastAPI + Jinja2 + HTMX, old-Reddit density, no JS build step |
| Deleted/removed content | Scrub text + author, keep the ID row as a tombstone, render `[deleted]`/`[removed]`; deleted text must not survive anywhere (DB, raw files, exports) |
| Comment harvesting | Full comment trees for every captured post by default, with a request budget and a revisit ladder |
| Hosting sequence | All-local on this Mac → Docker on Mac → QNAP Container Station → (optional, lowest priority) remote access |
| Reddit account | New dedicated account (Wes creates it); read-only API use, no password stored |
| Project home | `~/repos/insightminer` for repo and data (Wes: a folder inside `~/repos`), outside the TCC-protected folders that launchd cannot read; the space in "Insight Miner" is dropped because space-containing paths broke globs and shell paths in the earlier project; documents live in the repo's `docs/`; the original Desktop material was archived to `~/repos/insightminer-desktop-archive/` on 2026-09-13 |
| Top-issue ranking | Distinct authors first, then comment count, then score; never raw post count; one function shared by the digest, theme pages, and export; counted over distinct `author_fullname` excluding NULL, with identity coverage and tree completeness shown beside every ranked list (2026-09-13) |
| Failure alerts | macOS notification + red status banner in the UI; ntfy/Healthchecks.io optional later |
| Enforcement model | Private GitHub repo; branch protection requires green CI on `main`; I open PRs and merge when green; Wes reviews at will and can flip to human-only merges at any time. Human review on enforcement surfaces (CODEOWNERS) was considered and **declined** on 2026-09-13; compensating controls: positive controls for every gate, hard-block hooks, PR bodies listing every changed test with a reason, the adversarial review, and the quarterly guard review |
| TDD policy | Layered: test-first for core, services, migrations; probe-first for the Reddit adapter; route tests alongside UI templates |
| External research | One targeted report on engineering controls for AI-assisted codebases, run by Wes using the brief in the appendix; findings folded into the gates table before M0 |
| QNAP scope | Only this system for now: collector + web services on one compose file; volume and jobs table designed so services can be added later |
| Raw JSON | `raw_json` column per row (scrubbable, single raw store); the per-run JSONL sidecar was cut on 2026-09-13 (provenance via `raw_json` and `probe --save-fixture`; live-content JSONL comes from export on demand) |
| Compliance cadence | Full bulk re-check of every stored item every 2 days while it fits the request budget; automatic fallback to the tiered schedule, announced in the digest |
| GitHub | Wes creates the empty private repo `insightminer` and pastes the URL; I connect, push, and set branch protection |
| Name | `insightminer` for repo, package, CLI, and User-Agent app id `com.wesmax.insightminer` |
| Research timing | Wes runs the targeted report in parallel with M0 scaffolding; findings are folded into the gates before M1 feature code |
| LAN access (M4) | UI open on the home LAN without a password (Wes's call); same-origin middleware still applies; `INSIGHTMINER_UI_PASSWORD` enables basic auth if that ever changes |
| Interim browsing | Read-only Datasette over the same DB between M1 and M2 |
| Guard design rules | Adopted from Wes's earlier project (Robustness section): shape over list, invariant over proxy, positive control for every gate, fail never skip, zero-suppression baseline, hold the count |
| Git identity | `Wes Howell <wes@weshowell.com>` for the project repo (matches GitHub account WhowellGit) |
| Python version | 3.13 pinned via `uv`; informational 3.14 CI job; pin moves up when green |
| Database engine | SQLite, with dialect-specific code isolated in `db/` and search behind a port so a Postgres move stays a contained job; move triggers recorded in `DECISIONS.md` |
| Version control | Local git from the first commit; the GitHub private remote is added as soon as it exists and doubles as the off-site backup while the SMB backup server is down; a pre-push hook runs `make check` regardless; a nightly `git bundle` plus data backup to the NAS once the share is back |
| Reference corpus | `docs/` with an `INDEX.md` router, append-only insights and learnings, prune-stale status, and path-scoped rules (section below) |
| Operator surface | The web UI is the operator surface for every routine action: runs and run options, harvesting a post, reconcile, re-tag, backups and restore, maintenance, health checks, alert test, config and archive import/export, first-run setup. The CLI exists for schedulers, containers, tests, and break-glass recovery; both call the same service functions |

**Assumptions:** package/CLI name `insightminer`; Python 3.13 pinned via `uv` with an informational 3.14 CI job (rationale under Tech stack); `uv` to be installed with your approval; Docker only needed at M4 (OrbStack or Docker Desktop then); the repo stays private.

---

## Architecture

```
 Sources                    Collector (CLI, daily)                 Store                          Outputs
 subreddit /new  ──┐        ┌──────────────────────┐    upsert   ┌────────────────────┐          ┌─ digest report (.md/.html)
 saved searches ───┼──────▶ │ PRAW adapter (read-  │ ──────────▶ │ SQLite (WAL, FTS5) │ ───────▶ ├─ FastAPI + HTMX web UI
 (M3, Reddit-wide) ┘        │ only, honest UA,     │             │ Alembic-managed    │          ├─ export .zip
                            │ request budget)      │             │ raw_json per row   │          └─ (later) JSONL → Claude
                            └──────────────────────┘ ──────────▶ │ (no sidecar)       │
                                   ▲                             └────────────────────┘
                     launchd (Mac) / supercronic (Docker)  ── schedules `insightminer run`
```

One Python package, two entry points: a FastAPI app (`insightminer serve`) that is the operator's surface, and a `typer` CLI used by the scheduler, containers, tests, and break-glass recovery. Both are thin wrappers over the same service functions; after installation no routine operation requires a terminal. Ports-and-adapters inside: `core/` (pure logic) and `services/` never import `praw`; only `adapters/reddit_praw.py` does. The UI never talks to Reddit except to validate a subreddit when you add one.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Runtime | Python 3.13 via `uv` (`.python-version`, `requires-python = ">=3.13,<3.14"`, `uv.lock`), `src/` layout | 3.13 has had a year of bugfix releases and every dependency here ships wheels for it. 3.14 is eleven months old and a few C-extension packages may still lag, so CI runs an informational 3.14 job and the pin moves up when it is green. Python 3.9 is end-of-life and is the version whose silent behavior corrupted the earlier project's output. Reproducible; the same lockfile drives Docker later |
| Reddit | PRAW 8.x in **read-only mode** (client_id + secret only) with `check_for_updates=False`, `timeout=30`, an injected `requests.Session` that counts requests | PRAW handles OAuth refresh, pacing, and short retries; read-only is all we need |
| Storage | SQLite (WAL) via SQLAlchemy 2.0; Alembic (`render_as_batch`); FTS5; `raw_json` per row (no JSONL sidecar) | System of record + provenance; zero server; Datasette/DuckDB can read it later |
| CLI | `typer` + `rich` | Discoverable commands, progress output |
| Config | `pydantic-settings`: `.env` for secrets, `config/settings.yaml` for static settings; subreddits/themes/searches live in the DB (UI-editable) with YAML import/export (never includes secrets) | Avoids config-vs-UI drift |
| Web | FastAPI + Jinja2 (autoescape, StrictUndefined) + HTMX (vendored) + one hand-written `app.css` (~350 lines, token-based, light/dark) + ~25 lines vanilla JS; markdown rendered at ingest with `markdown-it-py` + `nh3` | Old-Reddit density (classless CSS frameworks fight it); no build step; single uvicorn worker |
| Rules | `regex` package (supports `timeout=`), pattern length caps | Regex authored in a UI is a ReDoS risk; stdlib `re` has no timeout |
| Tests | pytest, `pytest-recording` (vcrpy) cassettes for the adapter, `responses` for HTTP failure paths, hand-scrubbed JSON fixtures, `FakeRedditGateway`, `pytest-alembic`, `time-machine`, `hypothesis`, FastAPI TestClient + `selectolax`, optional Playwright | Collector never touches the network in tests (`--block-network`) |
| Quality | ruff, mypy, pre-commit, `make check` | One command gates every change |
| Scheduling | launchd (Mac) now; supercronic in Docker later | launchd runs missed jobs on wake; supercronic avoids the QNAP crontab-overwrite gotcha |

**Why SQLite, and the Postgres exit.** This system has one writer, runs on one machine at a time, and grows by roughly 1–2 GB a year. The database is a file you can back up, export, and hand to a coworker, and FTS5, Datasette, and DuckDB all read it directly. Postgres would add a server to run, upgrade, and back up, and buys nothing until there are concurrent writers on different hosts, a multi-user web app, or data in the hundreds of gigabytes. The earlier project ran SQLite past 700 GB; its pain was process discipline, not the engine. To keep the exit cheap: SQLAlchemy and Alembic are the only schema and query layer; every SQLite-specific statement (pragmas, `VACUUM INTO`, FTS5 DDL and `MATCH` queries) lives inside `db/` behind a `SearchIndex` port and a `backup` module; upserts use `ON CONFLICT DO UPDATE`, which both engines support; raw SQL outside `db/` is banned by a ruff rule. A Postgres move is then a contained job of a few days: a `tsvector` search implementation, a `pg_dump` backup module, and a data copy. The triggers for making that move are written down in `DECISIONS.md` so nobody relitigates it early.

---

## Repository layout

```
~/repos/insightminer/                     # git repo (local first; GitHub remote added during setup)
├── pyproject.toml  uv.lock  .python-version  alembic.ini  Makefile  README.md  .env.example  .gitignore  .pre-commit-config.yaml
├── docs/                                 # reference corpus and memory routing (next section)
├── config/settings.yaml                  # paths, budgets, revisit ladder, retention, UA app-id, display timezone
├── config/seed.yaml                      # initial subreddits + themes (imported on first run)
├── src/insightminer/
│   ├── __init__.py  cli.py  settings.py  ua.py  ports.py          # ports = Protocols + domain exceptions
│   ├── core/       models.py normalize.py paging.py deletion.py milestones.py themes.py budget.py retry.py digest.py   # pure, no I/O
│   ├── adapters/   reddit_praw.py reddit_fake.py clock.py notify.py
│   ├── db/         engine.py schema.py repo.py fts.py backup.py migrations/{env.py, versions/}
│   ├── services/   lock.py runs.py fetch_new.py harvest_comments.py revisit.py reconcile.py scrub.py tag_themes.py search_run.py report.py export.py config_io.py doctor.py
│   └── web/        app.py deps.py filters.py routes/ templates/ static/{app.css, app.js, vendor/htmx.min.js}
├── tests/          unit/ db/ adapters/{cassettes/} e2e/ web/ live/  fixtures/{json/, db/}
├── deploy/         launchd/*.plist  docker/{Dockerfile, entrypoint.sh, crontab}  compose.yaml
└── data/           (gitignored) insightminer.db  reports/  backups/  exports/  logs/  locks/
```

## Reference corpus and memory routing

Wes's earlier projects worked best with a curated memory system: hard-earned learnings kept separately from recent-work guidance, and a small router that points to the right document only when it is needed. This project adopts the same shape inside the repo, so it travels with the code and any agent or coworker inherits it.

```
docs/
├── INDEX.md          # the router: one line per document and when to read it (kept short, always current)
├── insights/         # dated captures of strategy discussions and the reasoning behind decisions (append-only)
├── learnings/        # hard-earned lessons: LEARNINGS.md (canonical) + dated applied notes (DB_LEARNINGS_APPLIED_2026-09-12.md)
├── decisions/        # DECISIONS.md: settled choices and settled negatives, so no session re-derives them
├── reference/        # external material: research reports, prior-project retrospectives, reviewer reports, API notes
├── runbook/          # RUNBOOK.md, KNOWN_ISSUES.md, GUARDS.md, DATA_DICTIONARY.md (generated from schema.sql)
└── recent/STATUS.md  # what is in flight and next; the only document that is rewritten rather than appended
```

Routing: `CLAUDE.md` stays short and always loaded; it holds the working agreement plus a routing table ("touching `db/migrations` → read `learnings/DB_LEARNINGS_APPLIED_*.md` and `runbook/RUNBOOK.md` § migrations"; "touching deletion or scrub → read the compliance section and `KNOWN_ISSUES.md`"). Path-scoped rule files under `.claude/rules/` load automatically when matching files are edited, so the database rules appear only during database work. Update policy: insights and learnings are append-only with dated entries; `STATUS.md` is prune-stale; every fixed bug lands in `KNOWN_ISSUES.md` pointing at its regression test; every measured result lands a three-line why / outcome / implication note. One currency test checks `INDEX.md` and `docs/` against each other in both directions. Agent transcripts and raw analysis are never committed; only curated documents are. Seeded on 2026-09-12 in `~/Desktop/Reddit/insightminer-docs/` and moved into the repo at M0.

## Module map (layering enforced by import-linter, not convention)

Layers, outermost to innermost: `web` → `cli` → `services` → `db` / `adapters` → `ports` → `core`. `core` imports nothing from the project or from `praw`; only `adapters/reddit_praw.py` imports `praw`; `web` is read-mostly and never imports `praw`. Boundaries speak typed values: pydantic models for normalized rows (`PostRow`, `CommentRow`), dataclasses for gateway results (`Page`, `TreeResult`, `Limits`), `Protocol`s in `ports.py`. `mypy --strict` on `core/`, `ports.py`, `services/`, `adapters/`.

| Module | Responsibility | Depends on | Tested by |
|---|---|---|---|
| `core.normalize` | raw API dict → `PostRow`/`CommentRow`, typed coercion, rejects | pydantic | unit + hypothesis (random key deletion) |
| `core.deletion` | content/author state machine + scrub decision | — | exhaustive table test |
| `core.paging` | `/new` sweep stop, cap and gap rules; removal-candidate detection | — | unit |
| `core.milestones` | revisit ladder (`check_stage` → `next_check_at`) | — | unit, time-machine |
| `core.themes` | rule compile (`regex` with timeout, caps) + match | regex | unit incl. ReDoS timeout |
| `core.budget` | per-run request accounting and reserve | — | unit |
| `core.retry` | retry ladder, exception classification, run statuses and exit codes, rate-limit wait planning, defer-run rule | — | unit, hypothesis |
| `core.digest` | digest model → markdown/html | jinja2 | golden file |
| `adapters.reddit_praw` | `RedditGateway` over PRAW; request counting; exception translation | praw | cassettes + `responses` + contract suite |
| `adapters.reddit_fake` | scenario-building fake gateway | — | contract suite (same cases as the real adapter) |
| `adapters.notify` | `Notifier`: macOS `osascript`, ntfy, log | subprocess/http | unit |
| `db.*` | pragmas, models, upsert repo, FTS, backup/restore, schema fingerprint | sqlalchemy, alembic | db tests, pytest-alembic, snapshot diff |
| `services.*` | use cases: lock, runs, fetch_new, harvest_comments, revisit, reconcile, scrub, tag_themes, search_run, report, export, doctor, config_io | core + ports + db | e2e against the fake |
| `cli` | typer wiring, exit codes 0/75/78 | services | CliRunner |
| `web.*` | routes, templates, partials, security middleware | services, db (read) | TestClient + selectolax, Playwright smoke |

---

## Data model (SQLite)

Conventions: integer surrogate PKs (`pk INTEGER PRIMARY KEY`) with `reddit_id TEXT UNIQUE`, because FTS5 external-content tables key on `rowid` and implicit rowids can be renumbered by `VACUUM`. All timestamps are INTEGER epoch seconds (Reddit's `created_utc` domain; SQLAlchemy `DateTime(timezone=True)` silently drops tz on SQLite). Subreddit identity is `name_lower` plus the `t5_` id. Upserts are `INSERT … ON CONFLICT(reddit_id) DO UPDATE`, never `INSERT OR REPLACE`, which deletes and re-inserts, burns rowids, and detaches FTS rows (the earlier project lost 16,813 rowids that way); a PK-stability invariant checks that repeated reruns leave `pk`, `first_seen_at`, and `max(pk) == count(*)` unchanged. `next_check_at` is NOT NULL, because a NULL is never due and the post would silently never be revisited. Every column carries a SQLAlchemy `comment=` so the `schema.sql` golden doubles as the data dictionary. Indexes are declared up front: `posts(next_check_at)`, `posts(subreddit_pk, created_utc)`, `posts(author_fullname)`, `posts(content_state)`, `comments(post_pk, parent_comment_pk)`, `comments(author_fullname)`, `post_themes(theme_pk)`, `item_snapshots(item_pk, fetched_at)`.

**Table-to-writer map.** The collector CLI is the only writer of `posts`, `comments`, `comment_more`, `post_sources`, `item_snapshots`, `authors`, `raw_rejects`. The web layer writes only `subreddits`, `searches`, `themes`, `theme_rules`, `post_themes` (retag), `ui_state`, and `runs` rows in `queued` state, through a repository object that exposes exactly those writes. Each ingest path (sweep, tree fetch, `info()`, search) owns a declared field set: the sweep may update score, `num_comments`, and `edited_utc` but never `first_seen_at`, `check_stage`, or `next_check_at`; a test asserts the ownership table. `authors` counts are checked by invariant against `COUNT(*)`.

| Table | Key columns | Notes |
|---|---|---|
| `subreddits` | name_lower (unique), display_name, subreddit_id (t5_), subreddit_type, subscribers, over18, quarantine, enabled, comment_mode (default `full`), added_at, `watermark_created_utc` (max seen in last complete sweep, informational), last_complete_poll_at, status (`ok/forbidden/not_found/redirect/quarantined/error`), last_error, consecutive_failures, gap_suspected_at | Polled sources |
| `searches` (M3) | query, scope (`all` or sub list), sort, time_filter, enabled, last_run_at, status | Saved Reddit-wide searches |
| `posts` | reddit_id, fullname, subreddit_pk, subreddit_id, author, author_fullname, author_flair_text, `author_is_bot`, title, selftext, selftext_html (sanitized at ingest), url, domain, permalink, created_utc, edited_utc, score, upvote_ratio, num_comments, link_flair_text, over_18, spoiler, is_self, is_video, is_gallery, post_hint, locked, stickied, archived, distinguished, crosspost_parent, num_crossposts, removed_by_category, **content_state** (`live/deleted_by_author/removed_by_moderator/removed_by_reddit/gone_unconfirmed/gone`), **author_state** (`known/account_deleted`), misses, scrubbed_at, first_seen_at, last_fetched_at, comments_fetched_at, comments_harvested, comments_complete, more_skipped, more_skipped_count, **next_check_at**, **check_stage**, source, normalizer_version, **raw_json** | Upserted current state; `comments_complete` = tree fetch succeeded and `replace_more` skipped nothing |
| `comments` | reddit_id, fullname, post_pk, parent_fullname, parent_comment_pk (null for top level, no FK), author, author_fullname, `author_is_bot`, body, body_html, created_utc, edited_utc, score, depth, permalink, is_submitter, stickied, distinguished, content_state, author_state, misses, scrubbed_at, first_seen_at, last_fetched_at, normalizer_version, raw_json | Index `(post_pk, parent_comment_pk)`; tree built in Python per page |
| `comment_more` | post_pk, parent_comment_pk, count | Unexpanded "more" stubs → "N replies not captured" |
| `post_sources` | post_pk, source_type (`subreddit/search`), source_pk, first_seen_at | Provenance; a post can arrive both ways |
| `item_snapshots` | item_pk, kind, fetched_at, score, num_comments, upvote_ratio | Numeric only (no body hashes: a hash of deleted content is derived content) |
| `authors` | author_fullname (unique), name, first_seen_at, last_seen_at, post_count, comment_count | Aggregated at ingest; never fetch `/user/{name}/about` |
| `themes` / `theme_rules` / `post_themes` | themes: name, slug, color, description, enabled, rules_hash, tagged_hash. rules: theme_pk, group (`match/exclude/only_in`), kind (`keyword/regex/flair/subreddit`), pattern, scope (`title/body/comments/any`), case_sensitive, whole_word, enabled. post_themes: post_pk, theme_pk, rule_pk, matched_field, tagged_at | No matched-text snippets stored (they are content) |
| `runs` / `run_subreddits` | runs: kind, trigger (`cli/ui/schedule`), started_at, finished_at, heartbeat_at, pid, status (`queued/running/ok/partial/failed/rate_limited/skipped_locked/crashed/cancelled`), stage, counters, api_requests, app_version, praw_version, schema_rev, error, log_path. run_subreddits: run_pk, subreddit_pk, pages, items_seen, new, updated, stop_reason (`exhausted/cap/error`), error | Drives the Runs page, digest, and gap detection |
| `raw_rejects` | run_pk, raw_json, error, created_at | Rows missing required fields (`id`, `created_utc`, `subreddit`); 30-day retention |
| `ui_state` | key, value | e.g. `last_visit_at` |
| `posts_fts`, `comments_fts` | FTS5 external-content on `pk`, tokenizer `porter unicode61`; insert/update triggers gated `WHEN new.content_state='live'`, delete-old on update/delete | Search; scrubbing empties the index entry |

**Raw JSON policy.** `raw_json` on each row is the single raw store (`insightminer db reprocess --below N` re-normalizes without touching Reddit). The per-run JSONL sidecar was cut on 2026-09-13 on the adversarial reviewer's recommendation: it was a second compliance surface with its own rewrite, retention, and verification machinery, and nothing depended on it. Exact-wire captures for fixtures come from `probe --save-fixture`; LLM-ready JSONL of live content is produced on demand by `insightminer export`. Both wire shapes (listing JSON, and PRAW-attribute JSON for trees) are converted to one canonical dict before `core.normalize` runs, and a shape-parity test feeds the same real post captured both ways (via `probe`) and asserts identical rows; the earlier project's most repeated failure was two producers of one record drifting apart, four times.

**Content-state machine** (pure function in `core/deletion.py`, unit-tested): `selftext/body == "[deleted]"` → `deleted_by_author` (terminal); `== "[removed]"` → `removed_by_moderator` unless `removed_by_category` names Reddit → `removed_by_reddit` (moderator removals may return to `live` if re-approved); `author is None` with intact body → `author_state = account_deleted` (scrub author fields only, content stays, `authors` row deleted); absent from `reddit.info()` → `gone_unconfirmed` (`misses = 1`), scrubbed at the second miss.

**Scrub** = null all content/author/URL columns, replace `raw_json` with a tombstone object, delete `post_themes`, FTS entry removed by trigger, `PRAGMA secure_delete=ON` so freed bytes are overwritten. The row and its tree position remain so children still hang and the item is never re-fetched as new.

**Corrections from the test-strategy panels (2026-09-13).** The database panel verified three things empirically on SQLite 3.53: on an external-content FTS5 table `SELECT count(*) FROM posts_fts` returns the content table's count and can never go red, so the FTS invariant counts `posts_fts_docsize` instead; with `content='posts'` and live-gated triggers, FTS `rebuild` re-indexes tombstones and `integrity-check` reports the index malformed, so the FTS tables point at live-only views (`posts_live`, `comments_live`) with the sync triggers on the base tables; and Alembic batch recreates fail while a view references the table, so batch migrations drop and recreate the views and triggers and then rebuild FTS. Further adoptions: `AUTOINCREMENT` on `posts` and `comments` so a purge cannot recycle a rowid into a stale FTS entry; the `backups` table (path, sha256, size, integrity result, kind, created_at) ships in schema revision 1 so the destructive gate keys on a record from day one; `raw_rejects` keeps a 30-day retention; the runtime schema fingerprint is derived by one normalizer applied to both the live `sqlite_master` and the packaged `schema.sql`, never a stored constant; `schema.sql` carries a generated column-comment section because SQLite discards comments; new invariants are scoped by `normalizer_version`; coverage medians apply only once seven runs exist. From the UI panel: `serve` starts in **maintenance-only mode** (system, backups, health, and setup pages) when migrations are pending or the fingerprint mismatches, instead of refusing; page routes read through a `mode=ro` engine and every write goes through a repository limited to the writer map; re-tagging always runs as the CLI subprocess with a run row, in-process only for the read-only preview; the Host check applies to every request, with a `Content-Security-Policy` of `default-src 'self'` and `Vary: HX-Request` on list routes; one stale-run threshold (3 minutes, given 5-second heartbeats that carry the stage) is shared by collector and UI; exports carry live-content JSONL only (there is no raw sidecar); the operator-complete gate walks the CLI command tree and requires a marked UI test per command, with `serve`, `probe`, `db init`, and `db downgrade` excluded with recorded reasons.

---

## Collector algorithm (`insightminer run`, daily)

0. **Order matters:** validate settings → open DB, refuse if Alembic migrations are pending → `fcntl.flock` on `data/locks/collector.lock` (exit 75 if held) → mark stale `running` rows (heartbeat > 45 min) as `crashed` → insert `runs` row → one cheap auth ping (`/r/premiere/about`) so credential failures surface before any paging. Config/auth failures never leave a `running` row. Every mutating command (`fetch`, `comments`, `revisit`, `reconcile`, `tag`, `scrub`, `reprocess`, `import`, `db upgrade`, `db restore`) takes the same flock and writes a `runs` row with a stage-bearing heartbeat (`rate_wait:37s` counts as alive, so a rate-limit pause is never mistaken for a hang); a per-run wall-clock ceiling (default 3 h) ends the run as `partial` after the current batch.
1. **Sweep `/new` fully** for each enabled subreddit: up to 10 pages of 100 (the 1,000-item cap), forward `after` paging only (never `before`), one DB transaction per page (posts + `run_subreddits` progress). At ~30 requests/day for three subs this is cheaper than being clever: it catches posts approved late from the mod/spam queue at their original chronological position, refreshes score/num_comments/edits for the newest ~1,000 posts per sub for free, and yields a removal signal (a known post inside the window that no longer appears → confirm via `info()`). If the cap is hit before reaching known territory, set `gap_suspected_at` and `stop_reason='cap'`; stickies are excluded from stop logic.
2. **Harvest comment trees** for posts due (`next_check_at <= now`, newest first) within a per-run request budget (default 1,500; counted by our own Session hook, not `auth.limits`). Skip the fetch when `num_comments == 0`. `submission.comments` (1 request, also refreshes the post) then `replace_more(limit=N)` (default 16, per-post cap 40; each replacement is 1 request and yields ≤100 comments; `count==0` nodes are "continue this thread" links). Record skipped stubs in `comment_more`; one transaction per tree. Serialize PRAW objects with `vars()` minus private keys and read `author_fullname` from the dict: touching a missing attribute on a PRAW object silently fires a request.
3. **Revisit ladder** via `check_stage`/`next_check_at`: after discovery, re-fetch the tree at 1d → 3d → 7d → 30d after `created_utc` (posts keep receiving replies for days; daily capture of only new posts would miss most of them). After a complete refetch, previously known comments missing from the tree are batch-checked with `info()` (Reddit drops leaf `[deleted]` comments from trees).
4. **Reconcile** (every 2 days, meeting Reddit's 48-hour guidance): re-check every stored post and comment via `reddit.info(fullnames=[…])` at 100 items per request, matching results by fullname (order and omissions are not guaranteed). Cost: roughly 800 requests at the 4-month mark and 2,400 at one year, under 25 minutes at PRAW's pacing. When a full sweep would exceed the configured budget it falls back to tiers (posts weekly and trees monthly beyond 30 days, monthly beyond a year) and says so in the digest. Apply the state machine and scrub.
5. **Tag themes** for new/updated posts (title, selftext, crosspost parent text, optionally comment bodies); re-tag all when a theme's `rules_hash` changed. Bot-authored items (AutoModerator, moderator-distinguished bot stickies, a small known-bot list) are flagged `author_is_bot` and excluded from theme matching and digest counts by default, so AutoMod boilerplate cannot masquerade as a complaint trend.
6. **Finish:** counters + `api_requests` on the run row, `PRAGMA wal_checkpoint(TRUNCATE)`, daily `VACUUM INTO data/backups/daily-<date>.db` (keep 7 daily + 4 weekly), digest served as a route (`/reports/{date}`) computed from the DB and written to a file only on request, so no persisted copy can hold later-deleted text (per theme: posts ranked by distinct `author_fullname` then comments, never by display name, with NULL identities excluded rather than collapsed into one bucket, the identity coverage of the ranked set printed beside the list ("42 distinct authors, 96% of rows identified"), and rows from incomplete trees annotated "(tree incomplete: N replies not captured)" (corrected 2026-09-13); with deep links; top untagged posts of the last 7 days with three or more distinct authors; rising title phrases against the trailing four weeks; per subreddit counts and statuses; backlog, gaps, errors), macOS notification on failure, and a Healthchecks.io ping on success as the dead-man switch. The run also stamps a `settings_fingerprint` (hash of the resolved non-secret settings) so a changed budget or filter is visible in the digest; unknown upstream enum values (`removed_by_category`, `post_hint`, `subreddit_type`) are stored raw and counted as `unknown_enum_values`, never coerced to a known value; and a subreddit that recovers from an error has its `status`, `consecutive_failures`, `last_error`, and `gap_suspected_at` cleared in the same run, so transient state never lingers as a false alarm.

Budget reality: PRAW's limiter paces requests evenly over the 10-minute window, so a 600-request day takes ~10 minutes and the first-time backfill (~3,000 posts + trees ≈ 4,500 requests) drains over a few daily runs or one interactive run with `--budget 5000` (~1 hour). Exit codes: 0 ok, 75 locked, 78 config/auth error.

**Search source (M3):** each enabled saved search runs `subreddit("all").search(query, sort="new", time_filter="week")` daily; posts stored with `post_sources.source_type='search'`, trees harvested like any other post; the UI lists "subreddits discovered via search" with an **Add to monitored** button. Search is fuzzy and incomplete, so it supplements the subreddit sweeps rather than replacing them.

---

## CLI commands (automation, containers, tests, and break-glass; every command is a thin wrapper over a service function the UI also calls)

| Command | Purpose |
|---|---|
| `insightminer doctor [--no-network] [--alert-if-stale 36h]` | Config valid, DB reachable and at head, quick integrity check, free disk, last successful run age, lock not stale, optional auth ping printing rate-limit headers |
| `insightminer db init/upgrade/downgrade/current/backup/restore/vacuum/check/reprocess` | Schema and files; `upgrade` always backs up first |
| `insightminer run [--budget N] [--no-comments] [--dry-run]` | Steps 0–6 above (`--dry-run` fetches but writes nothing to the DB) |
| `insightminer fetch [--sub X]` · `comments [--post ID] [--budget N]` · `revisit` · `reconcile [--older-than 30d]` · `tag [--all]` · `search-run` (M3) | Individual stages |
| `insightminer report [--date]` | Regenerate the digest from the DB |
| `insightminer export [--out] [--no-raw]` | Zip of DB snapshot (SQLite backup API + integrity check), live-content JSONL dump, config YAML (no secrets), redacted settings, `MANIFEST.json`, `README.txt` |
| `insightminer subs add/remove/list/enable/disable` · `themes list/add-rule/test` · `config validate/show/export/import` | DB-backed config with YAML round-trip |
| `insightminer probe <fullname> [--save-fixture]` | Dump raw JSON for an item; used in M1 to turn unverified Reddit behaviors into test fixtures |
| `insightminer serve [--port 8765]` | Web UI, bound to 127.0.0.1 |

---

## Web UI (FastAPI + Jinja2 + HTMX)

Old-Reddit density and Reddit's URL scheme so muscle memory works: `/r/{sub}`, `/r/{sub}/comments/{id}/{slug}`, `/u/{name}`, themes at `/t/{slug}`. Every post and comment has a `www.reddit.com` deep link (comments use `/_/{comment_id}/?context=3`) opening in a new tab; replies are always written by hand on Reddit.

**Design rules**

| Rule | Detail |
|---|---|
| Same URL, page or fragment | List routes return the full page normally and only the rows fragment when the `HX-Request` header is present (`hx-push-url` keeps URLs shareable). Dedicated partial routes only for validate, preview, run panel, subtree, "more comments" |
| Comment tree | One query per post (flat rows), tree built in Python, rendered with a recursive Jinja loop so collapse is pure CSS plus a 10-line event-delegated toggle. Depth cap 10 with "continue this thread" (HTMX swaps the subtree in place; the `href` also works as a permalink page). Long threads page by top-level comments with whole subtrees, ~300 comments per page |
| Honest coverage | Post header shows "58 comments on reddit (52 captured)"; `comment_more` stubs render as "N replies not captured, view on reddit"; a per-post **Harvest full tree** button spawns the CLI for that post; score/counts labeled "as of <last fetch>" |
| Tombstones | Row still renders (children stay visible), author `[deleted]` unlinked, body `[deleted]`/`[removed]` by `content_state`, no reply link, never listed on author pages |
| Content safety | Only ingest-time sanitized `*_html` columns render unescaped; FTS snippets are built with control-character markers and HTML-escaped before `<mark>` insertion |
| Mutations | POST/DELETE via HTMX or plain forms (work without JS); validation errors return 422 with the re-rendered form; flash messages via out-of-band swap |
| Security | Bind `127.0.0.1` on the Mac; on the QNAP bind the LAN address with no password (Wes's decision for the home network); middleware always rejects state-changing requests unless `Sec-Fetch-Site` is same-origin and `Host` is allowed (blocks CSRF and DNS rebinding from other open sites); `INSIGHTMINER_UI_PASSWORD` turns on basic auth if that ever changes |
| Process model | Single uvicorn worker (in-process job state for retag/export); fetching is always the CLI in a subprocess |
| Styling | One `app.css` with tokens (`--bg --fg --link --visited --muted --thread --new …`), 13px system font, light/dark via `prefers-color-scheme` plus a cookie override |
| Power view | Optional: `uvx datasette data/insightminer.db` read-only for ad-hoc SQL (zero code); also a good interim browser before M2 lands |
| Operator-first | Every routine operation has a UI control; destructive ones show the gate state (last verified backup, exactly what will be deleted or replaced) and require typing a confirmation word; the CLI mirrors the UI, never the reverse |

**Routes**

| Route | Page | Key interactions |
|---|---|---|
| `/` | Feed across monitored subs; sort new / comments / score; filters subreddit, theme, flair, author, date; `[NEW]` badge for items first seen in the latest run; sidebar with per-sub and per-theme new counts and last-run status | rows fragment paging |
| `/r/{sub}` | Subreddit feed + metadata (subscribers, last fetched, captured counts, monitored state, status badge) | same |
| `/t/{slug}` | Theme feed, rules summary, per-rule hit counts, matched rule per post | same + edit theme, re-tag now |
| `/r/{sub}/comments/{id}/{slug}` (`/p/{id}` redirects) | Post + nested comment tree; comment sort top / new / old | collapse, continue thread, load more, deep links |
| `/r/{sub}/comments/{id}/{slug}/{cid}` | Comment permalink: subtree rooted at `cid` with "show parent / full thread" | same |
| `/search` | FTS5 over posts and comments (tabs with counts), relevance or new, filters sub/theme/date/author/flair, `<mark>` snippets | input converted through a mini-grammar (`"phrase"`, `-word`, `word*`, `OR`), never passed raw to MATCH; advanced-syntax checkbox with friendly error |
| `/u/{name}` | Everything captured from a username (Overview / Posts / Comments) | sort, paging, open profile on reddit |
| `/settings/subreddits` | Add with debounced live validation via the API (one request; not-found / private / banned / quarantined / bad-credentials mapped to plain messages) showing a preview card (display name, subscribers, description, NSFW); per-sub comment mode (default **full**); pause/resume; remove with **Stop, keep data** vs **Stop and delete captured data** | HTMX partials |
| `/settings/themes` | List and editor: name, slug, color; rule groups **Match any of** (keyword whole-word or substring, regex, flair) / **Exclude if any of** / **Only in** subreddits; regex validated server-side with length cap and timing warning; live preview "would tag N posts (M in last 7 days)" with per-rule hits and 10 highlighted sample titles using the same matcher as the CLI; Save re-tags (inline if quick, background job with polling if large), preserves existing match timestamps; stale badge when rules changed since last tag | HTMX partials |
| `/settings/searches` (M3) | Saved Reddit-wide searches CRUD; discovered subreddits with **Add to monitored** | |
| `/settings/appearance` | light/dark/auto, reddit host www vs old, display timezone, page size | plain form |
| `/runs`, `/runs/{id}` | History (status, trigger, duration, counters, per-sub outcomes, warnings). **Run now** (options: full run, fetch only, reconcile only, re-tag only, saved searches only) spawns the same CLI launchd uses (`Popen`, log to file, own session) after inserting a `queued` run row; 409 if a run is active; panel polls `/runs/current` every 2 s and stops when idle; heartbeat every 5 s enables stale-run detection; Cancel sends SIGTERM and the CLI finishes its batch; errors mapped to plain text (401 credentials, 403 UA/blocked, 429 backed off, network, DB locked) with full log and traceback | HTMX polling |
| `/export` | Builds `data/exports/insightminer-<ts>.zip` in a background thread with progress; keeps last 3; refuses if free disk < 2× data size | HTMX polling, then download link |
| `/setup` | First-run wizard for a new machine or a coworker: paste Reddit app credentials (stored in `.env` with owner-only permissions, never displayed again), **Test connection**, choose subreddits, run the first sweep with live progress | plain forms + HTMX polling |
| `/system` | Health and status: every `doctor` check as a green/red row with **Run checks**; version, paths, disk free, scheduler status, migration state with **Apply pending migration** (automatic backup first), last backup, **Send test notification** | HTMX partials |
| `/system/backups` | Backups with size, date, and integrity result; **Create backup now**; **Restore** behind the destructive gate (shows what will be replaced, requires typing `restore`) | HTMX partials |
| `/system/maintenance` | Reconcile now, re-tag all themes, reprocess from raw, import a config YAML or an export archive, recent logs | HTMX polling |
| `/healthz` | JSON: status ok/degraded/error, version, DB ok + size + migration rev, last run summary, run in progress, lock held, disk free, credentials present | Docker healthcheck later; header status pill polls every 60 s |

**Curation controls (decided 2026-09-13).** Beyond adding and removing subreddits, saved searches, and rule-based themes, the UI carries the hand-curation Wes expects to do over months: a manual tag override on any post (add or remove a theme on the post page; `post_themes.origin` is `rule` or `manual`, and re-tagging never removes a manual tag); a **watch** control that pins a thread so the revisit ladder keeps refreshing it past 30 days (`posts.watch_until`); one-click promotion of a "rising phrase" from the digest into a theme rule, with the live preview showing what it would tag; theme rename and merge (merging re-points `post_themes` rows and records the change); an ad-hoc **Search Reddit** box on the settings page that runs one API search and offers "monitor this subreddit" or "harvest this thread" per result, so new sources are found from inside the tool rather than by hand; and the per-post thumbs up or down on each theme tag, recorded as operator feedback ("k of n judged"): an operating signal, never the grade, and no string rendered from the feedback table says "precision" (corrected 2026-09-13; precision comes only from the M3 blind packet). Schema revision 2 adds `post_themes.origin`, `posts.watch_until`, and `workspaces.archived_at` together.

Wireframe (feed):
```
┌ insightminer  [Feed] [r/premiere] [r/VideoEditing] [r/editors] [Themes ▾] [Search…] [Runs] [Settings] [Export] ┐
│ sort: new | comments | score      filter: theme ▾ flair ▾ since ▾            last run 06:31 ✓ (+42 posts) │
├───────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ▲ 128  Premiere 2026 crashes on export with H.264 after update            r/premiere · u/name · 3h · Bug  │
│        84 comments (80 captured) · themes: Export failures, Crashes · open on reddit ↗              [NEW] │
│ ▲  12  Playback stutters with proxies on M3 Max                            r/VideoEditing · u/name · 5h    │
│        9 comments · themes: Playback/performance · open on reddit ↗                                        │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
Wireframe (post page):
```
┌ ▲128  Premiere crashes on export with H.264 (self.premiere)                          open on reddit ↗ ┐
│       submitted 3h ago by u/editorguy to r/premiere [Help] · themes: Crashes, Export failures         │
│       ┌ selftext (sanitized markdown) ─────────────────────────────────────────────────────────────┐   │
│       └─────────────────────────────────────────────────────────────────────────────────────────────┘   │
│       58 comments on reddit (52 captured) · sorted by: top | new | old · as of 06:00 · reply on reddit ↗│
├────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ [-] u/helper  45 points  2h                                                      permalink · reply ↗  │
│  │  Try turning off hardware-accelerated encoding in the export settings…                              │
│  │  [-] u/editorguy [OP]  12 points  1h                                           permalink · reply ↗  │
│  │   │  That fixed it, thanks!                                                                          │
│  │   │  [+] u/other  3 points  55m  (2 children)                                                        │
│  │  [-] [deleted]  5 points  2h                                                              permalink  │
│  │   │  [removed]                                                                                       │
│  │   │  [-] u/someone  2 points  1h   … continue this thread →                                          │
│ [ load more comments (14 remaining) ]        3 replies not captured · view on reddit ↗                 │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Testing strategy

**Principle:** the collector never touches the network in tests (`pytest --block-network`). `RedditGateway`, `RawSink`, `Clock`, `Notifier` are Protocols speaking plain dicts; `PrawGateway` is the only adapter doing HTTP. `FakeRedditGateway` is a scenario builder (`add_post`, `add_comment`, `add_more`, `delete`, `remove`, `delete_account`, `fail_page`, `rate_limit_next`, `set_status`) that records every call, ships in `src/` so `insightminer run --gateway fake` works for demos, and drives the whole failure matrix. Tests control time through the injected `Clock` and never sleep.

| Layer | What | Tools |
|---|---|---|
| Unit (`core/`) | normalize (raw → rows, typed coercion, missing keys), deletion state machine, paging/stop/gap rules, milestones ladder, budget, theme rules (incl. regex timeout), digest golden file, UA format | pytest, hypothesis (random key deletion) |
| Collector e2e | Full `run` against Fake + temp DB created via `alembic upgrade head`: idempotent rerun → zero duplicates, `first_seen_at` unchanged; counters and `run_subreddits` correct; ladder and reconcile transitions; **compliance canary**: ingest a unique phrase, delete it in the fake, reconcile, then scan the DB, FTS, and a fresh export for the phrase | pytest, tmp_path, time-machine |
| Adapter | Happy paths from recorded cassettes (`--record-mode=none` in CI, auth headers/tokens filtered); failure paths with `responses` (429 + Retry-After, 401 refresh, 503 sequences, `ReadTimeout`, HTML 403) asserting exact request counts; a contract suite runs the same cases against Fake and PRAW adapters so the fake stays honest | pytest-recording, responses |
| Migrations | pytest-alembic built-ins (single head, upgrade, model/DDL match, up-down consistency) plus upgrade-from-seeded-fixture per prior revision (`tests/fixtures/db/<rev>.sqlite`), FTS works after upgrade, integrity check ok, pre-migration backup created | pytest-alembic |
| Web | TestClient per route with seeded DB (HTML parsed with `selectolax`): nested comments are DOM descendants at the seeded depth; depth-11 → "continue thread"; tombstones render and never appear on author pages; deep-link hrefs exact; `<script>` in a body renders escaped; `HX-Request` → fragment, plain → full page; invalid regex → 422 inside the rule row; settings CRUD round-trips; Run now inserts a queued row and 409s while running; cross-site POST rejected; export zip passes `integrity_check`, excludes in-progress run, contains no deleted text; FTS sanitizer never raises on adversarial input | FastAPI TestClient, selectolax, hypothesis |
| E2E (optional) | Browser flows: open post → collapse → continue thread; add subreddit (fake gateway) → Run now (stub CLI with heartbeats) → post page | Playwright |
| Live smoke (opt-in) | `pytest -m live`: auth ping, fetch 5 posts from r/premiere, rate-limit headers present; skipped without credentials | real PRAW |
| Workflow | Cross-stage scenarios that run the whole daily pipeline through one fake corpus (sweep → trees → revisit → reconcile → tag → digest → backup) and the operator workflows (setup → first sweep; theme edit → retag; backup → restore drill; pending migration → apply; export → import on a fresh data dir), asserting end state, counters, and the delivered artifacts. The earlier project found a mis-ordered step, a swallowed crash, and two tests passing against an empty directory only when cross-stage tests were added | pytest, fake gateway, temp data dir |
| Sweeps (scheduled, in production) | Post-run invariants after every run; per-source freshness in the digest; hourly `doctor` for the UI health rows; the Healthchecks.io ping as the dead-man from M1d; every 2 days the compliance reconcile; weekly the portability job and the restore drill into a temp dir; quarterly the guard pedigree review (the freshness anchor, stress scenario, and weekly notifier proof were cut or downgraded on 2026-09-13) | launchd and CI schedules |

**Failure-mode matrix (each row is a test):**

| Failure | Expected behavior | Simulation |
|---|---|---|
| 429 with `Retry-After` | Sleep `min(retry_after, 300)` via injected clock, retry once; second 429 → run `rate_limited`, nothing half-written | `responses` 429×2; fake `rate_limit_next` |
| 401 at token endpoint | `AuthFailed` before any listing request; no `running` row left; exit 78; notification | `responses` 401 on `/api/v1/access_token` |
| 401 `invalid_token` mid-run | prawcore refreshes and retries transparently; run continues | `responses` sequence token/401/token/200 |
| 403 private subreddit | Sub `status=forbidden`, `consecutive_failures+1`; others continue; run `partial`; data retained | `responses` 403; fake `set_status` |
| 404 banned subreddit | `status=not_found`; alert; content handled per banned-sub policy (scrub after confirmation) | `responses` 404 |
| Nonexistent subreddit | prawcore `Redirect` → `status=redirect`; auto-disabled after N runs with alert | `responses` 302 to `/subreddits/search` |
| Casing / identity change | `VideoEditing` vs `videoediting` normalize to one row; differing `t5_` id → abort that sub loudly | about.json fixtures |
| 5xx / timeout mid-page | prawcore retries 3× (seconds), then our outer retry (30 s → 2 m → 5 m via fake clock); persistent → that sub fails, pages already committed stay, watermark untouched | `responses` 503 sequences; fake `fail_page` |
| Crash between pages | Rerun → no duplicates, no gaps, `first_seen_at` unchanged | fake raises after page 2; run twice |
| Crash mid comment-tree | Nothing committed for that post; still due; rerun completes | fake raises after N comments |
| Overlapping run | Second process exits 75, zero API calls | hold `flock` in test, invoke CLI |
| DB locked by another writer | Retries within `busy_timeout`, then fails cleanly, watermark untouched | second connection holds `BEGIN IMMEDIATE` |
| Stale `running` row | Marked `crashed` on next start; new run proceeds | insert row with old heartbeat |
| Malformed / missing fields | Optional → NULL; required missing → `raw_rejects`, run continues, raw preserved | fixtures (`edited` false/float, absent `author_fullname`, nulls) + hypothesis |
| Deleted / removed content | State transitions; all content columns null; `raw_json` tombstone; FTS empty; `post_themes` gone; canary absent everywhere | fake `delete()`/`remove()` + reconcile |
| Account deletion | Author fields nulled everywhere, `authors` row deleted, content kept | fake `delete_account` |
| Missing from `info()` | `gone_unconfirmed`, `misses=1`, content kept; second miss → scrub | fake omits id twice |
| Config validation errors | Exit 78 before any API call (bad client id, invalid sub name, invalid regex, negative budget, unwritable data dir) | CliRunner + fake; assert zero calls |
| DB missing / behind head | Refuse with instructions (protects against an unmounted Docker volume) | bad path; downgraded temp DB |
| Disk write failure (backup or export) | Operation aborted, no partial file left behind, run `failed`, notification | read-only backups dir / `OSError(ENOSPC)` |
| Clock skew ±1 day | Identical rows and decisions (all logic in `created_utc` domain) | time-machine |
| Empty subreddit / zero new | Run `ok`, `stop_reason=exhausted`, watermark unchanged | fake with no posts |
| Cloudflare HTML 403 | Abort run (not per-sub), alert, no tight retry loop | `responses` 403 text/html |
| Overlapping listing pages | Upsert dedupes; counts correct | fake returns overlapping pages |
| Quarantined subreddit | `status=quarantined`, disabled with alert | fixture 403 JSON |
| Budget exhausted mid-run | Tree harvesting stops at reserve; posts still captured; queue drains next run | fake reports low remaining |
| Column silently 100% NULL (field read from the wrong shape) | Population-floor invariant fails the run and names the column | fixture with the field nested elsewhere than the normalizer expects |
| A gate that has gone inert (skips instead of failing) | Its positive control fails CI | remove the gate's precondition in a test environment and assert red |
| Source freshness (a subreddit quietly not fetched for days while runs stay green) | Per-source freshness check flags `degraded`; digest names the source | fake makes one sub fail quietly across 2 runs |
| Uniform staleness (everything equally old, every relative check passes) | Freshness anchor flags `degraded`; digest says "no new items for K runs" | fake returns the same listing for K runs while the live anchor shows newer posts (freshness anchor cut 2026-09-13, N-08; per-source zero-new detection kept) |
| Test suite pointed at the real data dir | Settings refuse to start; tests only ever touch temp dirs | unset the opt-in variable and run a test from the repo root |
| Repeated reruns churn primary keys | PK-stability invariant fails | run the fake scenario 3× and compare `pk`, `first_seen_at`, `max(pk)` |
| Same post normalizes differently via two paths | Shape-parity test fails | probe fixture captured via listing and via tree |
| Subreddit recovers after an error | `status=ok`, failure counters, `last_error`, and gap flag cleared after a complete sweep | fake fails for 2 runs, then succeeds |
| Dry-run or no-network mode still touches the network or the DB | Test fails: zero HTTP calls, zero DB writes | fake with no routes; DB opened read-only |
| Deleting a workspace removes data another workspace still reaches | Delete removes only rows with no remaining source; shared posts kept; purge recorded | two workspaces share a subreddit in the fake; delete one |
| Re-tagging removes a manual tag or re-adds a manually removed one | Manual origins survive every retag | change the rule so the post no longer matches; retag |
| A watched thread falls off the revisit ladder | `watch_until` keeps it due until it expires | post older than 30 d with a future watch; advance the clock |

Gates: `make check` = ruff + mypy + pytest with coverage ≥ 90% on `core/`, `services/`, `adapters/reddit_fake.py`; pre-commit runs ruff. Optional but recommended: a personal restricted test subreddit (readable by anyone, only you post) seeded by hand with a normal post, a self-deleted post, a mod-removed post, a deleted comment with children, a leaf deleted comment, a deep chain, and a crosspost, so cassettes contain no third-party content. If you later share separate testing reference documents, this section will be adapted.

---

## Robustness, enforcement and portability

The failure pattern in AI-assisted projects is rarely the first build; it is drift afterwards: tests quietly weakened, exceptions swallowed, schema edited without a migration, "passes locally" claims that were never checked. The controls below are mechanical, not aspirational, and they go in at M0, before any feature code, because retrofitting ratchets onto a moving codebase is where they usually get skipped.

### Guard design rules (carried over from Wes's earlier database project)

Source: `WHY_THE_GUARDS_EXIST.md` in `docs/reference/earlier-project-retrospectives/` (kept, redacted), where 29 guards were audited and fourteen had never fired, nine of about twenty gates were unfalsifiable, and 2,250 grandfathered suppressions had become a permanent exemption. Every gate in this plan must satisfy these rules.

| Rule | What it means here |
|---|---|
| Scan a structural shape, never police a hand-maintained list | Ratchets count what a tool finds in the whole tree (ruff, import-linter, pytest collection, marker counts), never entries in a registry the same person curates |
| Key on the invariant, not a proxy | Post-run checks query the real thing through the same connection path the app uses (FTS count vs live count, rows stamped with the current version), never a config flag, a docstring, or a file's existence |
| A gate that cannot fail is not a gate | Every gate, ratchet, and invariant ships with a **positive control** in `tests/gates/`: construct the bad state and assert the gate goes red. A gate never seen failing is a hypothesis |
| Structural markers, not comment proximity | Justifications live in syntax (`reason="#123 …"` arguments, decorators, rule codes), never "a comment within N lines" |
| Assert on the delivery surface | UI and digest tests assert on rendered output; a field with two guards is single-sourced so the guards cannot disagree |
| Fail, never skip, inside the required gate | Missing preconditions fail CI; the only skips allowed are the explicitly opt-in live tests; the gate is verified by running it the way CI runs it, not by reading a decorator |
| Zero-suppression baseline | Greenfield means the suppression and skip ratchets start at zero, and any exception is printed on every run |
| Hold the count | A new guard is added only for a recurring class, after checking whether an existing guard can be widened; `GUARDS.md` records each guard's birth incident, positive control, and what it has caught since, reviewed quarterly |
| Derive state, never narrate it | The Runs page, digest, and `make check` summary are computed from the DB and tool output, never from a claim in a message or a hand-edited count |
| Show the denominator | Every count in the UI or digest carries its population ("12 of 60 new posts matched Crashes"); each metric is one function with a golden test, shared by UI, digest, and export |

### TDD policy by layer

| Layer | Approach |
|---|---|
| `core/` | Strict TDD: red test → green → refactor. Every failure-matrix row is written as a failing test before the service code exists |
| `services/` | TDD against `FakeRedditGateway` + temp DB created by `alembic upgrade head` |
| `adapters/reddit_praw.py` | Probe-first: `probe` captures the real payload → scrubbed fixture or cassette → characterization test → adapter code. Reddit's behavior is observed, never assumed |
| `db/migrations/` | Test-first: add the fixture DB of the previous revision and the expected `schema.sql` snapshot, then write the migration until both pass |
| `web/` | Test-with: the route test with DOM assertions is written alongside the template; Playwright smoke after each page lands |
| Bug fixes | Start with a failing test that reproduces the bug; the fix is not done until that test is green and stays in the suite |

### Gates and ratchets

| Gate / ratchet | Where | Enforces | Fails how |
|---|---|---|---|
| pre-commit | every commit | ruff format + lint, mypy on changed files, secret scan (`gitleaks`), no files > 1 MB | commit blocked |
| `make check` | before every PR and in CI | full pytest with `--block-network` and `-W error`, coverage ≥ ratchet, mypy strict, ruff, import-linter contracts, schema snapshot diff, pytest-alembic | non-zero exit with summary (tests run / skipped / coverage) |
| Required CI on `main` | GitHub Actions + branch protection | PR cannot merge unless green; I merge when green; every PR body lists changed test files and the `make check` summary so Wes can spot-check; branch protection can be tightened to human-only merges at any time | red check |
| Coverage ratchet | `.ratchets/coverage.txt` | coverage may not drop; bumped in the same PR when it rises | CI fails showing old vs new |
| Skip/xfail ratchet | `.ratchets/skips.txt` | count of `skip`/`xfail` may not rise; each needs `reason="#issue …"` | CI fails |
| Suppression ratchet | `.ratchets/suppressions.txt` | `noqa` and `type: ignore` counts may not rise; each needs a rule code | CI fails |
| Test-count floor | `.ratchets/tests.txt` | *Cut as a gate 2026-09-13 (N-09)*; the enforcement panel's assert-count and collected-test floors remain under the loosening protocol, so `tools/ratchet.py` still implements the floors (recorded contradiction, `STATUS.md`) | CI fails |
| import-linter | CI | layering contracts from the module map | CI fails naming the illegal import |
| Network block | pytest config | any test that touches the network errors | test error |
| Schema snapshot | `src/insightminer/db/schema.sql` golden file | `alembic upgrade head` on an empty DB must reproduce the committed snapshot, so every schema change is visible in the PR diff | test fails with diff |
| Models == DDL | pytest-alembic | SQLAlchemy models match the migrated schema (no drift) | test fails |
| Runtime schema fingerprint | `doctor`, `/system` | *Downgraded 2026-09-13 (N-13)*: a warning only, ordinary tables, derived by one normalizer from the live `sqlite_master` and the packaged `schema.sql`; `alembic_version` and models-vs-DDL remain the gate | warning |
| Portability job | CI weekly + on README change | fresh Ubuntu container: `git clone && make setup && make check` | CI fails |
| Mutation testing | `make mutate`, optional | *Removed from the gates 2026-09-13 (N-10)*: an optional monthly tool on `core/deletion.py`, `core/paging.py`, `core/normalize.py`; never a ratchet | report only |
| Post-run invariants | `doctor --post-run`, end of every run | DB invariants below | run → `failed`, notification |
| Dead-man switch | Healthchecks.io ping at the end of each successful run, from M1d | a run that never happens is noticed; *the launchd hourly dead-man was dropped 2026-09-13 (N-12)* because a launchd job cannot watch a launchd failure in its own domain; the hourly `doctor` job remains for the UI health rows | notification |
| Restore drill | quarterly checklist in `RUNBOOK.md` | latest backup restores to a temp path and `doctor` passes | manual, logged in the runbook |
| Guard reachability | `tests/gates/` | every post-run invariant and failure-matrix row is proven through `insightminer run` with the fake planting the violation and `runs.status` flipping, never by calling the guard function directly (the earlier project shipped a gate that was unit-tested and called by nothing) | positive control fails |
| `DATA_DIR` isolation | autouse pytest fixture + `settings.py` | tests always run against a temp data dir; settings refuse the default data dir when pytest is loaded unless an explicit opt-in variable is set (the earlier project's tests overwrote live artifacts twice) | test error |
| Connection chokepoint | import-linter + behavioral test | only `db.engine` may call `create_engine`; a connection obtained through the public path proves `journal_mode=wal`, `foreign_keys=1`, `secure_delete=1`; scrub is one function whose test asserts DB, FTS, and `post_themes` changed in the same call (opt-in guards were bypassed by the main helper in the earlier codebase) | CI fails |
| Destructive-operation gate | CLI + UI | `db restore/downgrade/reprocess`, `subs remove --delete-data`, container `INIT`, and the retention sweep require a backup recorded in a `backups` table (sha256, size, integrity result) made within N hours, plus `--yes`; Datasette opens the DB `mode=ro`; web routes use one read-write engine behind the writer-map repository (*N-07, 2026-09-13*) | refuses, exit 78 |
| No bypass flags | CLI design + tests | *A design rule, not a gate, since 2026-09-13 (N-06)*: no flag skips reconcile or scrub; `--budget` hard-capped at 5,000; a bypass flag such as `--no-comments` records a written reason on the run row; `run --dry-run` fetches but makes zero DB writes; `doctor --no-network` and `config validate` make zero HTTP calls, tested with no routes registered | test fails |
| Size ratchets | ruff `C901`, `PLR0915` (ruff has no max-file-length rule) | no god-functions or god-modules form (the earlier project had a 1,509-line function and a 5,359-line script) | CI fails |
| Freshness anchor | `doctor` | *Cut 2026-09-13 (N-08)*: the sweep is the live listing in the same run; per-source zero-new detection and per-source freshness (separate from run status) remain at zero extra requests; revisit if uniform staleness ever occurs (`LEARNINGS_TRANSFER.md` P5) | digest names the source |
| Coverage counters | run row + digest | % self posts with `selftext_html`, % comments with `author_fullname`, % due posts harvested, `raw_rejects`, `unknown_enum_values`, % posts tagged; structural floors at M1a (100% on live rows with `author_state=known`); *the trailing-median amber alarm is deferred to M3 after 60 days of baseline (2026-09-13)* | run `partial` |
| Stress scenario | `pytest -m slow`, weekly CI | *Cut 2026-09-13 (N-11)*: the four `EXPLAIN QUERY PLAN` assertions that hot queries use the declared indexes remain | test fails |
| Hard-block hooks | Claude Code `PreToolUse`, exactly two (N-16) | no `--no-verify` or direct push to `main`; no hand edits to `.ratchets/` or the hook settings; self-protecting, failing closed on internal error; project hook settings load only when the session starts in the repo root, so sessions start in `~/repos/insightminer` | tool call blocked |
| Doc currency | one test | *Reduced 2026-09-13 to the INDEX-to-docs check in both directions* (`tests/gates/test_doc_currency.py`); `KNOWN_ISSUES.md` rows pointing at their regression tests, `DECISIONS.md` settled negatives, and "no counts restated in prose" are review-checked; the retired-claims check (G34, 2026-09-13) fails any live-document line that states a retired mechanism without its retirement marker | CI fails |

### Silent-failure controls

- **Exception policy:** ruff `E722`, `BLE001`, `S110`, `S112`, `B904`, `TRY*` enabled; catch specific exceptions only; every handler re-raises, or records a warning counter and message on the run row. A run with any warning is `partial`, shown amber; `ok` means zero warnings.
- **Warnings are errors in tests** (`-W error`), so PRAW deprecations and SQLAlchemy warnings surface immediately instead of rotting.
- **Post-run invariants** (violations flip the run to `failed`): run counters equal table deltas; no `running` rows other than the current one; live rows have all required columns and scrubbed rows have none of the content columns; FTS row counts equal live row counts; `comments_harvested` equals the actual count per fetched post; every post has at least one `post_sources` row; `alembic_version` is at head and the schema fingerprint matches; **population floors** per column over the last 7 days of live rows (`author_fullname` over 95% non-null, `selftext_html` present on every self post, `permalink` on every row), which catch the "column 100% NULL while every gate passes" failure from the earlier project; row counts never decrease except through a recorded purge; every row written this run carries the current `normalizer_version`; **per-source freshness**: each enabled subreddit fetched successfully within the last 2 runs, checked separately from run status; a zero-yield run across all sources flags `degraded`; the last complete reconcile is within 48 h plus a 12 h grace period, otherwise the run is `partial` so compliance cannot lapse quietly.
- **Structured logs** per run (JSON lines) with counts of errors and warnings mirrored on the run row and in the digest; the launchd wrapper checks the exit code and notifies on non-zero.
- **Typed boundaries** validated once: pydantic at the normalize boundary, `Protocol`s at the gateway boundary, mypy strict inside.
- **No mocking of internals:** `unittest.mock.patch` is banned (ruff `banned-api`) outside `tests/adapters/`; behavior is tested through the fake gateway and real temp DBs.
- **Cross-platform and environment controls** (the earlier project met Linux as a cluster of silent Mac-first bugs): CI runs on Linux as the primary matrix from day one even though development is on a Mac, with the Docker build as the second; `encoding="utf-8"` on every text open (ruff `PLW1514`); `os.replace` instead of `os.rename`; no colons or other platform-hostile characters in generated file names; `fcntl` imported only inside the lock module; settings are read from the settings object at call time and never captured at import (`from insightminer.settings import CONST` banned via ruff `banned-api`); the settings model uses `extra="forbid"` so a misspelled key fails fast instead of silently doing nothing.
- **Two-gate discipline for semantics:** a refactor must keep the reprocess golden byte-identical; a semantic change to an existing column is a separate PR with a `normalizer_version` bump, updated golden rows, and a CHANGELOG line. Field names are contracts: `num_comments` is Reddit's count including deleted items and is never used in an invariant; `more_skipped_reason` (`budget/cap/error`) keeps one label from covering three causes; theme previews show each rule's hit rate as a share of all captured posts, so a keyword that tags 60% of everything is visibly non-diagnostic.
- **Notifier proof (downgraded 2026-09-13):** the UI status pill computed from `runs` is the canonical alert surface; notifications are best-effort; `insightminer notify --test` is a manual check from `/system`, not a weekly launchd job.

### Known AI-assisted-development failure patterns → control

| Pattern | Control |
|---|---|
| Assertion loosened or test deleted to get green | tests changed in a PR are listed in the PR body with a one-line reason each; mutation testing; working-agreement rule; Wes spot-checks PR bodies |
| Tests skipped/xfailed to unblock | skip ratchet with issue reference |
| Mocks that mock the thing under test | fake gateway + contract suite against real cassettes; `mock.patch` banned outside adapter tests |
| Broad `except … pass` hiding failures | lint rules + exception policy + `partial` status |
| Hallucinated library APIs or fields | probe-first for the adapter; contract suite; `-W error` |
| Model edited without a migration | models == DDL test; schema snapshot golden; runtime fingerprint |
| "Works on my machine" | `uv.lock`, `.python-version`, Docker image, portability CI job, `doctor` |
| Time-dependent flaky tests | injected `Clock`; time-machine; no `sleep` in tests |
| Partial run reported as success | invariants; counters reconciled; `ok` requires zero warnings |
| "Tests pass" claimed on a subset | CI is the authority; test-count floor; `make check` summary (test-count floor cut as a gate 2026-09-13, N-09; assert-count and collected-test floors remain) |
| Over-abstraction | four layers only; rule: no new abstraction without two concrete uses |
| Docs drift | README quickstart executed by the portability job |

### Working agreement (`CLAUDE.md` in the repo, applies to any agent or human)

Never weaken, skip, or delete a test to make a change pass; never commit with `--no-verify`; never catch a broad exception without recording it on the run; every bug fix starts with a failing test; every schema change ships with migration + previous-revision fixture DB + updated snapshot; every PR body lists files under `tests/` that changed and why; never touch the production DB by hand; never store or log credentials; report test results by pasting the `make check` summary, not by describing it.

### Workflows, cadence and verification points

| Workflow | Frequency | Verification points |
|---|---|---|
| Daily run | daily, automated | lock → pre-run `doctor` → per-page/per-tree transactions → post-run invariants → digest → notification on failure; dead-man switch if it never runs |
| Config change (subreddit/theme/search) | ad hoc, via UI | validation before save; live preview; retag; `config export` committed so config history is in git |
| Code change | many per week in M1–M2, monthly afterwards | failing test first → pre-commit → PR CI → human merge → `make deploy` (pull, `uv sync --frozen`, `db upgrade`, restart) → post-deploy `doctor` |
| Schema migration | several in M1, rare afterwards | code-change path plus: previous-revision fixture DB, snapshot updated, pytest-alembic, pre-migration backup during deploy, `foreign_key_check` |
| Dependency bump | monthly (Renovate PR) | lockfile update; cassette and contract tests as the gate; PRAW bump also runs the live smoke manually |
| Compliance reconcile | weekly automated; canary test on every PR | scrub counts on the run row; canary must be absent from DB, FTS, backups within retention, export |
| Restore / rollback drill | quarterly | restore latest backup to a temp path; `doctor` passes; counts compared |

### Portability targets

- **Fresh machine in under 10 minutes:** `git clone` → `make setup` (installs `uv` if missing, `uv sync --frozen`, copies `.env.example`, `db init`) → edit `.env` → `insightminer doctor` → `make run`. The portability CI job proves it weekly on a clean container. For a coworker who is not a developer: `docker compose up` (or the one-line installer), then the browser `/setup` wizard; no terminal after that.
- **12-factor config:** every setting via `INSIGHTMINER_*` env vars with `settings.yaml` defaults; `DATA_DIR` relocatable; no hardcoded paths; timezone configurable; the `Notifier` adapter is chosen by config so Linux and the QNAP work without macOS assumptions.
- **Docker image is the portable artifact** (multi-arch amd64/arm64 so an ARM or x86 QNAP both work); `compose.yaml` + `env_file`.
- **Move data:** `insightminer export` on the old machine → `insightminer import <zip>` on the new one (restores DB and config, runs `db upgrade`).
- **Each person registers their own Reddit script app**; client secrets are never shared or exported. README documents the five-minute app registration.
- **`CLAUDE.md`, `CONTRIBUTING.md`, `RUNBOOK.md`** so a coworker, or a coworker's agent, inherits the same rules, deploy steps, and drills.

### QNAP as a service host (M4)

Container Station runs the same compose file: a `collector` service (supercronic schedule) and a `web` service sharing one local-volume `data/` directory. WAL allows the web service and later analysis workers to read while the collector writes; any future writer coordinates through the `runs`/`jobs` tables and the same flock rather than a message broker. The data directory must be on a local NAS volume, never a network share. A future LLM analysis worker (M5) is a third service on the same compose file reading the DB and writing its own tables.

### Adversarial review: what changed (2026-09-13)

The adversarial reviewer's central charge was that the plan cites the earlier project's "hold the count" rule and then ships roughly 28 gates and 15 invariants on day zero, several of them unfalsifiable. That charge is correct. The gates table above is the menu; the shipped set starts smaller and grows only on recurrence. Adopted:

- **Gates cut or downgraded:** test-count floor (cut; coverage covers it); freshness anchor (cut; per-source zero-new detection kept, which costs no requests); runtime schema fingerprint (downgraded to a warning on `doctor` and `/system`, limited to ordinary tables; `alembic_version` and models-vs-DDL remain the gate); mutation testing (removed from the gates table; optional tool, never a ratchet); stress corpus (cut; four `EXPLAIN QUERY PLAN` assertions kept); doc-currency extras (only the INDEX-to-docs bidirectional check remains); hard-block hooks (two, in the project settings, per the enforcement panel below and N-16); "no bypass flags" as a gate (a design rule instead: bypass flags such as `--no-comments` record a written reason on the run row, the earlier project's actual lesson); trailing-median coverage alarms (deferred to M3 after 60 days of baseline; structural floors only until then); the `mode=ro` web engine (one read-write engine behind a repository limited to the writer map; `mode=ro` for Datasette only); notifier proof (the UI status pill computed from `runs` is the canonical alert; notifications are best-effort); the launchd dead-man (replaced by a Healthchecks.io ping from M1d, since a launchd job cannot watch a launchd failure in its own domain).
- **Positive controls, split honestly:** post-run invariants are proven through `insightminer run --gateway fake` with a planted violation; CI ratchets get a unit test of their compare function; external controls (branch protection, pre-commit, launchd, the portability job) get a dated "last seen red" line in `GUARDS.md` and no test. "A positive control for every gate" leaves the M0 definition of done.
- **Enforcement stated honestly:** with the agent using Wes's own GitHub login, branch protection is not "outside the agent's reach". Two fixes, both pending Wes: the agent authenticates with a fine-grained token or machine user with write but not admin rights, and Wes confirms the GitHub plan allows branch protection on a private repo (GitHub Free does not; Pro does). Until then CI is a gate with a git trail, not an enforcement authority, and the plan says so.
- **CSRF on the LAN:** browsers send `Sec-Fetch-Site` only to HTTPS and localhost origins, so on `http://192.168.x.x` every POST would have failed. The middleware falls back to comparing the `Origin` or `Referer` host with the allowed `Host` list when the header is absent.
- **Isolation across the subprocess seam:** web routes call an injectable `ProcessRunner` port; the data directory is passed to the child through the environment; the CLI refuses to start under `PYTEST_CURRENT_TEST` unless `--gateway fake` is set. Without this the web tests would spawn the real collector against the real database, the earlier project's incident one process boundary over.
- **State machine shape locked, predicates unlocked** until the probe fixtures exist. Deleted link posts have an empty `selftext`, so the predicate keys on `removed_by_category='deleted'` first and treats `author is None` on a link post as deletion pending `info()`; a deleted link post joins the probe list; the compliance canary phrase lives in a title as well as a body.
- **Compliance bounds written down instead of over-claimed:** backups and old exports can hold scrubbed text until they age out, so no backup older than 14 days and no export older than 7 days is retained, both under the retention sweep, and the canary asserts file ages; the reconcile-age invariant is per tier (60 h under 30 days, 8 days to a year, 35 days beyond); real purge latency is recorded in `DECISIONS.md` rather than claimed as "within 48 h". Crosspost parent text is stripped to `{id, subreddit}` at ingest. Edits are an event: reconcile upserts the full normalized row so an edited body replaces the old one everywhere.
- **The #1 priority pulled forward:** distinct-author ranking, a "top untagged posts" section, and "rising title phrases" in the digest at M1d; a per-post thumbs up or down on each theme tag at M2, recorded as operator feedback ("k of n judged"), which is an operating signal and never the grade, because a reviewer who has already seen the tag is anchored; the word precision is reserved for the M3 blind labeling packet (corrected 2026-09-13); Wes reading the digest against Reddit becomes a standing weekly practice. Recurring human duties are held to three: read the digest, acknowledge alerts in the UI, label tags while browsing.
- **Smaller fixes:** the flock being held means alive, taking precedence over heartbeat age; `queued` run rows older than 2 minutes without a pid become `failed`; bot detection is a heuristic surfaced in the UI as "suspected bots" with one-click confirm, flagged per author and never inherited by a megathread's comments; the destructive gate is a `Confirmation` value object constructible only by the UI's typed phrase or the CLI's flag, checked inside the service; `ruff` `TID251` bans `create_engine` and `text(` outside `db/` (import-linter cannot ban symbols); mypy overrides for untyped PRAW are declared with a reason and counted by the suppression ratchet; the revisit ladder gains a 365-day stage so `next_check_at` is never a far-future sentinel; purges are recorded on their run row so the row-count invariant can read them; `-m "not live"` sits in `addopts` so the skip ratchet stays at zero; there is no "max file length" rule in ruff, so size ratchets are `C901` and `PLR0915` only; the LAN threat model is recorded as "operator error", with basic auth on system and delete routes available by one env var.
- **From the enforcement panel (adopted):** ratchet files are `key=value` under `.ratchets/` written only by `tools/ratchet.py`, compared three ways on every run (measured vs file, file vs what the script would render, file vs `main`) so a stale floor is red and any move against direction is a "loosening" that pauses for a one-click approval (or, if the GitHub plan lacks environment reviewers, a required label plus an auto-opened issue) and lands a row in the `GUARDS.md` loosenings ledger; coverage has a hard floor with half a point of slack; `dmypy` checks the whole tree in pre-commit rather than changed files; the assert-count and collected-test floors replace the "2% free drop"; `GUARDS.md` "catches since" is derived from CI failures posted to a pinned issue, never typed; the Docker matrix starts at M4 and the live smoke never runs in CI; two hard-block hooks ship in the project settings, self-protecting and failing closed on internal error: no `--no-verify` or direct push to `main`, and no hand edits to `.ratchets/` or the hook settings; after M0 the agent's GitHub token drops `administration` and `workflows` scopes so protection and workflow YAML sit outside its write perimeter. The panel's M0 fit check puts the shipped gate set at roughly 16 to 22 hours of work; if the two-day box overruns, the PR-body numeric check, the weekly audit, and the settings-drift check defer to M1.
- **Disputed or deferred, for Wes:** the per-run JSONL sidecar was **cut on 2026-09-13** (Wes's decision; `raw_json` plus `probe --save-fixture` cover provenance); fetching trees through `reddit.request()` to eliminate the second wire shape (decide at M1b after the probes); the reference corpus is kept because Wes asked for it, but its currency test shrinks to the INDEX check and `GUARDS.md` starts when the first guard fires.

---

## Release, upgrade and migration practices

- **Schema:** every change is an Alembic migration (`render_as_batch=True`, naming convention so batch ops can drop constraints by name), reversible, never edited after being applied; FTS virtual tables and triggers created with `op.execute(... IF NOT EXISTS)`; `include_object` excludes `%_fts%` shadow tables from autogenerate; `PRAGMA foreign_keys=OFF` during batch migrations. Expand/contract for column changes (add nullable → write both → backfill from `raw_json` → switch reads → drop later); never rename in place. SQLite batch mode recreates the table, which drops FTS triggers and orphans external-content rows: any batch operation on `posts` or `comments` must recreate the triggers and run the FTS `rebuild` command in the same migration, the per-revision fixture test asserts FTS count equals live count after upgrade, and Alembic runs with `transaction_per_migration=True` so a failed step never leaves a half-migrated DB. A new post-run invariant ships scoped to rows at or above the `normalizer_version` that satisfies it, or after a backfill, so a new check cannot turn every run red on day one.
- **Safety:** `db upgrade` always does an online `sqlite3.Connection.backup()` to `data/backups/pre-migrate-<from>-<to>-<utc>.db`, `quick_check` on the copy, migrate, then `integrity_check` + `foreign_key_check`; on failure restore the copy and exit non-zero. Keep the last 3 pre-migration backups plus 7 daily / 4 weekly `VACUUM INTO` backups. `db restore <file>` swaps atomically under the lock.
- **Connections:** on every connection set `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=30000`, `temp_store=MEMORY`, `secure_delete=ON`; `wal_checkpoint(TRUNCATE)` at end of run. The DB must live on a local filesystem (QNAP local volume, never a network share).
- **Reprocessing:** `normalizer_version` on rows + `raw_json` mean derived columns can be rebuilt; a test asserts a full reprocess reproduces identical rows.
- **Versioning:** single source in `pyproject.toml`; `__version__` via `importlib.metadata`; UA built from it (`python:com.wesmax.insightminer:v0.1.0 (by /u/<user>)`, prawcore appends its own version); stamped on `runs`; SemVer (minor for new commands or migrations, patch for fixes); `CHANGELOG.md`; git tags; `uv.lock` committed, `uv sync --frozen` in Docker.
- **Startup checks:** `run` and `serve` refuse if migrations are pending; `/healthz` and `doctor` expose version, migration state, last-run age.
- **Containers (M4):** entrypoint `set -euo pipefail`, verify the volume holds the DB (or `INSIGHTMINER_INIT=1`), `db upgrade --backup`, then `exec supercronic`; migrations and runs share the flock; image tagged with the version; roll back = previous tag + restore backup; never auto-downgrade.

---

## Deployment path

| Stage | Where | How |
|---|---|---|
| Now (M0–M3) | This Mac | `uv run insightminer serve` on 127.0.0.1 (or a launchd `KeepAlive` agent); launchd `StartCalendarInterval` runs `run` daily (e.g., 06:30; runs on wake if the Mac was asleep). Logs in `data/logs/`. Alerts: on failure the CLI posts a macOS notification (`osascript display notification`) and the UI shows a red banner; a second small launchd job runs `insightminer doctor --alert-if-stale 36h` hourly for the UI health rows (the launchd dead-man's switch was dropped 2026-09-13, N-12; the Healthchecks.io ping is the dead-man from M1d). The launchd wrapper invokes the project's virtualenv interpreter by absolute path (never `python3`, which is 3.9 on stock macOS) and wraps long backfills in `caffeinate -i`. **Location constraint:** launchd jobs are silently denied access to TCC-protected folders (`~/Desktop`, `~/Documents`, `~/Downloads`, `/Volumes/*`), which the earlier project hit directly; the repo and `DATA_DIR` live at `~/repos/insightminer`, outside them, and `doctor` checks the path; scheduled runs are wrapped in `caffeinate -i` so a closed lid cannot strand a run |
| M4 | Docker on Mac → QNAP Container Station | `python:3.13-slim` + `uv sync --frozen --no-dev`; `compose.yaml` with `./data` local volume, `env_file` for secrets, supercronic schedule, `HEALTHCHECK` via `doctor --no-network`. Same image on QNAP; home IP preserved (best for Reddit). Optional Healthchecks.io/ntfy ping at the end of each successful run |
| Optional, lowest priority | Remote access | Prefer Tailscale to reach the QNAP UI from anywhere over moving the fetcher to a VPS: datacenter IPs are treated worse by Reddit. A VPS would only host a read-only UI copy if ever needed |

---

## Milestones

| # | Milestone | Definition of done | Tests that must pass |
|---|---|---|---|
| **D0** | Design lock-down (now) | Wes and I walk this document section by section and record explicit yes/no on: data model and raw-JSON policy, content-state machine, module boundaries, TDD policy, enforcement model, gates and ratchets, workflows and cadence, portability targets, QNAP service layout. Nothing is scaffolded before this is done | — |
| **M0** | Setup + enforcement scaffolding (days 1–2) | Wes: account, email verified, script app at reddit.com/prefs/apps (type *script*, redirect `http://localhost:8765`), client id/secret + username in `.env`, empty private GitHub repo `insightminer` created and its URL shared. Me: `brew install uv gh` (Homebrew present; neither installed yet), git identity configured (none set on this Mac), `uv python install 3.13`, repo scaffolded with `CLAUDE.md`, pre-commit, CI workflow, ratchet files, import-linter contracts, mypy strict, `--block-network`, schema snapshot test, `GUARDS.md` ledger with a positive control for every gate in `tests/gates/`, `make setup/check/run`; `make check` green; `insightminer doctor` reports auth OK with rate-limit headers (exactly 2 HTTP calls: token + about) | settings + UA unit tests; adapter cassette; portability job (fresh-container `make setup && make check`) |
| **M1a** | Posts ingestion. *Tranche A shipped 2026-09-13 (everything except the real Reddit adapter, proven end to end against the fake gateway: revision 0002, repository with the field-ownership table, lock and run lifecycle, sweep, post-run invariants, doctor, migration commands, the `run` command; five design rounds, a three-reviewer panel, 24 findings closed). Tranche B, the adapter and `probe`, waits on credentials.* | Schema rev 1 with FTS; `fetch` sweeps `/new` for the 3 subs into SQLite; idempotent rerun; gap detection; `run_subreddits`; `probe` has captured raw JSON for a deleted post, removed post, deleted comment, removed comment into fixtures; interim browsing via Datasette works | collector e2e (crash between pages, overlapping pages, empty sub), pytest-alembic suite, timestamp-type test |
| **M1b** | Comment trees + budget | Newest-first queue drains within budget; `comments_complete`/`comment_more` accounting; one transaction per tree; first full backfill completed over a few runs | fixtures with `more`/continue-thread nodes; crash mid-tree; budget exhaustion |
| **M1c** | Revisit, reconcile, scrub | Ladder via `next_check_at`; state machine; `info()` misses; author scrub; compliance canary green | all deletion scenarios; canary; `info()` ordering/absence |
| **M1d** | Themes + digest + daily run | Seed themes (Crashes, Export failures, Playback/performance, Audio issues, GPU/drivers, Media offline/import, Update regressions, Feature requests); digest generated; launchd installed; macOS notification fires on a forced failure; **7 consecutive successful scheduled runs**; Wes reads the seven digests against Reddit itself and files mismatches as issues (the earlier project's highest-impact bugs were caught by the operator reading real output) | rule engine (incl. regex timeout), digest golden file, every failure-matrix row, `plutil -lint` on the plist |
| **M2** | UI v1 (weeks 3–4) | Feed, subreddit, theme, post/thread, search, author, settings CRUD, runs + Run now with options, export, healthz, appearance, **system, backups, maintenance, and setup pages**; **operator-complete**: a checklist of every routine operation is performed from the UI without a terminal | web suite including the operator checklist; optional Playwright smoke |
| **M3** | Reach + polish | Saved Reddit-wide searches with subreddit discovery; snapshots/velocity visible; reconcile tiers tuned; full destructive-operation gate with the `backups` table; a 30-post blind labeling packet per theme, stratified by rule, with "unsure" kept in the denominator and the pass bar written down before any label is seen, scored by Wes before the packet reveals which rule tagged each post or whether it was tagged at all; precision per theme and per rule shown in the digest; optional ntfy/Healthchecks | search-run tests; alert test; labeling packet recorded |
| **M4** | Containerize | Same behavior in Docker on Mac for a week, then on QNAP with data on a local NAS volume | entrypoint tests (empty volume refuses; DB behind head upgrades with backup); one scheduled run in container |
| **M5** | Analysis layer (later, out of scope here) | JSONL batches → Claude summaries/classification; trend charts from `item_snapshots` | — |

**M0 foundation tranche (decision-independent; buildable before the remaining panels return).** Repo at `~/repos/insightminer` with git, `uv`, Python 3.13, `pyproject`, ruff and mypy strict configuration, pytest with `--block-network` and `-W error`, pre-commit, Makefile (`setup/check/run/schema/fixture`), `.env.example`, `.gitignore`; the `docs/` corpus moved in with `CLAUDE.md`, `INDEX.md`, `KNOWN_ISSUES.md`, `DECISIONS.md`, `GUARDS.md`; import-linter contracts for the module map; `.ratchets/` files at zero baselines; the `tests/gates/` harness with the first positive controls (data-directory refusal, connection chokepoint, block-network); `core/` pure modules built test-first (deletion state machine, paging rules, revisit ladder, budget, theme rules with regex timeout, normalize with rejects); schema revision 1 with Alembic, live-view FTS, `schema.sql` golden and fingerprint, the `backups` table; the CI workflow file. Shipped gate set for M0 after the adversarial review: import-linter layering, network block, schema snapshot, models-vs-DDL, data-directory isolation (in-process and across the subprocess seam), pragma behavioral test, upsert and PK stability, coverage and suppression ratchets, exception lint policy, `-W error`, pre-commit ruff and gitleaks; invariants at M1a start with the compliance canary, counters-versus-deltas, structural population floors, and per-source freshness, and only the first two flip a run to `failed` during the first 60 days. Schema revision 1 omits `raw_files` (the JSONL sidecar was cut) and includes `AUTOINCREMENT`, the `backups` table, and purge counters on runs. Deferred to M1: anything in `services/`, `adapters/reddit_praw.py`, or `web/`. *Shipped 2026-09-13 (commit e5bd86f and cleanup commits): ratchets sit at the measured baseline rather than zero; there is no `fixture` target yet (M1a); the connection-chokepoint control lives in `tests/db/test_engine_pragmas.py`; the enforcement panel returned and its ratchet formats and CI matrix are built; the doc-currency gate exists as `tests/gates/test_doc_currency.py`.*

---

## Things only Wes can do

1. Create the dedicated Reddit account and verify its email (I cannot create accounts or enter credentials).
2. Register the script app (accept the Data API terms when prompted) and paste `client_id`, `client_secret`, and the username into the `/setup` page once the UI exists, or into `.env` during M0 (never committed; `.env.example` documents the keys).
3. Approve installing `uv` and `gh` via Homebrew (M0) and a container runtime (M4); create the empty private GitHub repo `WhowellGit/insightminer` on github.com (your account per the screenshot) and paste its URL.
4. Prior-learnings material: the eight documents (three kept redacted in `docs/reference/earlier-project-retrospectives/`, five moved to the archive outside the repo on 2026-09-13) were reviewed on 2026-09-12 (see the appendix). They reference four more that would sharpen the database side further if you can share them: its issue register, its database integrity reference, its breakage-pattern catalogue, and its update-semantics note.
5. Optional but recommended: create a personal restricted test subreddit with the new account and seed it with the fixture cases listed under Testing (if Reddit's account-age rules allow; otherwise we rely on scrubbed fixtures).
6. Later: first Reddit-wide search queries (e.g., `"premiere pro" crash`) and whether to add r/AfterEffects / r/DavinciResolve.

---

## Verification (end-to-end, after each milestone)

1. `make check` passes (lint, types, tests with coverage gate, network blocked).
2. `uv run insightminer doctor` → auth OK, UA correct, migrations current, exactly two HTTP calls.
3. `uv run insightminer run --budget 200` → rows in `posts`/`comments`, digest in `data/reports/`; run again → zero new posts (idempotency); `uvx datasette data/insightminer.db` shows the tables.
4. Compliance drill on the fake gateway: `insightminer run --gateway fake`, delete an item in the scenario, `reconcile`, then grep the data directory and a fresh export for the canary phrase → no hits.
5. `uv run insightminer serve` → `http://127.0.0.1:8765`: feed shows posts, a post page renders the nested tree with coverage counts, search returns hits, add/remove a subreddit, Run now completes with live progress, export zip opens and contains `insightminer.db`, `posts.jsonl`, `comments.jsonl`, `config.yaml`, `MANIFEST.json`.
6. Migration drill: `db upgrade` on a copy of a previous-revision DB; pre-migration backup appears first; integrity check ok.
7. Scheduler: the Runs page shows a `schedule`-triggered run each morning for a week; kill a run mid-way and confirm the next start marks it `crashed` and proceeds.

## Decisions taken on the reviewers' open questions

| Question | Decision |
|---|---|
| Raw JSON policy | `raw_json` column (scrubbable) is the single raw store; the per-run JSONL sidecar was cut on 2026-09-13 |
| Reconcile cadence | Full bulk re-check every 2 days while affordable; tiered fallback (ladder ≤30 d; weekly posts + monthly trees to 1 y; monthly after); all configurable |
| Banned/private subreddit content | Private: keep, stop polling, mark stale. Banned: items confirmed gone via `info()` are scrubbed (strict reading); policy flag exposed |
| Cassettes with third-party content | Private repo; prefer the personal test subreddit for recordings |
| Tree JSON shape | PRAW-attribute JSON for trees, wire JSON for listings/info; shape recorded on the row's `source` |
| Initial backfill | Full 1,000 posts per sub with trees, drained by the daily budget (or one interactive `--budget 5000` run) |
| Score snapshots | Numeric snapshots in v1 (cheap; enables trend work in M5) |
| Regex rules in UI | Allowed, via `regex` with timeout, length cap, server-side compile check |
| Digest persistence | Files kept 14 days, always regenerable from the DB |
| Timezone | Storage in UTC epoch; display and "daily" boundaries in the Mac's local timezone (configurable) |
| Secrets in Docker | `env_file` outside the image; never in YAML exports or the export zip |

## Remaining open items (to settle in D0)

*Approved 2026-09-13; the table below is kept for history. All five panel reports exist; the corpus lives in the repo `docs/`; the M0 tranche is built (see `docs/recent/STATUS.md`).*

- Enforcement panel delivered; its adoptions are recorded in the Robustness section.
- **For Wes, raised by the adversarial review:** (1) check whether your GitHub plan allows branch protection on a private repo (Free does not; Pro does) and whether the agent may use a non-admin token; (2) the per-run JSONL sidecar: cut (decided 2026-09-13); (3) and (4) the compliance bounds and the commercial-use stance: Wes is handling these outside the plan (2026-09-13); (5) exit codes: 0 ok, 1 failed, 3 partial, 4 rate-limited, 75 locked, 78 config, 130 cancelled, with `partial` producing a digest line rather than a notification (proposed).
- Owner questions raised by the panels, to answer during M0 (recommendations in parentheses): backups may hold deleted text until they age out, so backup retention is the compliance bound (accept the 4-week window and document it); purge semantics for "stop and delete captured data" (hard delete with a recorded purge run); whether `/setup` and destructive actions on the LAN require a loopback client or the password when no password is set (loopback-only for those unless the password is set); archive import at M2 from a server-side path rather than browser upload (yes); Playwright local-only at M2 (yes); `[NEW]` means first seen in the latest completed run only (yes); `/system` Run checks default to no-network with a checkbox for the auth ping (yes).

**D0 section walk status**

| Section | Status | Decisions recorded |
|---|---|---|
| Data model and state machine | Locked | Accepted as written; deleted account → scrub author fields only, content stays; moderator-removed items may return to live, author deletions terminal |
| Collector algorithm and budgets | Locked | Full-window `/new` sweep every run, watermark for gap detection only; defaults accepted: full trees, 16 expansions per pass, per-post cap 40, per-run budget 1,500 requests, ladder 1/3/7/30 days; first run backfills the full window with trees; digest files kept 14 days and regenerable |
| UI routes and design rules | In progress | Wes reviewing the section (plan pane + pasted inline); locked so far: UI open on the home LAN, read-only Datasette as interim browser |
| Wes's prior database learnings | Reviewed | All eight documents read (two directly, six by two reviewers); changes folded in are listed in the appendix and in `insightminer-docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md`; two decisions raised: project location vs launchd, and human review on enforcement surfaces |
| Reference corpus and memory routing | Locked (built at M0) | Pattern in its own section; seeded in `~/Desktop/Reddit/insightminer-docs/` with the insights, applied learnings, and the four reviewer reports |
| Test-strategy panels | 5 of 5 delivered | Database (55 specs, 3 empirical corrections), UI (55 specs, operator checklist, setup threat model), ingest (scenario-builder API, ~60 specs, probe plan, exit-code and dry-run fixes), and the adversarial review (16 unfalsifiable gates, 11 gaps, a cut list; adopted changes recorded in the Robustness section) delivered; all five in `docs/reference/reviews/`; the consolidated `TEST_STRATEGY.md` is the first M0 document |
| Milestones and sequencing | Pending | |

---

## Appendix: what the earlier project's retrospectives changed in this plan

**How these were assessed.** Two of the eight documents were read directly; six were digested by two independent reviewer agents whose raw reports are in the corpus. The adoption decisions are mine, made the same day, with a deliberate bias toward adopting because the sources are audited failures rather than opinions; several recommendations were declined or scoped, and the ranked view with confidence, importance, value, and cost per item is in `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md`. An adversarial review of the applied set has **not** yet run; it is part of the proposed panels.

The earlier system (a bug-intelligence pipeline over an issue tracker, pull requests, crash events, and release notes, feeding a very large SQLite store) differs in scale and domain, so its embedding, eval-leak, and multi-machine lessons do not transfer. Its SQLite integrity, migration, silent-failure, two-path-drift, and agent-behavior lessons transfer almost verbatim. What changed here:

| Finding in the retrospectives | Change made to this plan |
|---|---|
| launchd is blocked by TCC for repos under `~/Desktop`, `~/Documents`, `/Volumes/*` (hit directly) | Location constraint added to Deployment; runtime moved to `~/repos/insightminer`; `doctor` checks the path |
| Guards audited: 14 of 29 never fired; 9 of ~20 gates unfalsifiable; 2,250 grandfathered suppressions | Guard design rules table; positive control for every gate; zero-suppression baseline; `GUARDS.md` ledger; hold the count |
| A gate was unit-tested and called by nothing; predicates that fired zero times | Guard-reachability rule: invariants proven through `insightminer run` with the fake planting the violation |
| Tests overwrote live artifacts twice (read path honored the test dir, write path did not) | `DATA_DIR` isolation: autouse fixture plus settings refusing the default dir under pytest |
| `INSERT OR REPLACE` burned 16,813 rowids and produced a false cross-machine divergence alarm | Upsert pinned to `ON CONFLICT DO UPDATE`; PK-stability invariant |
| Two producers of one record shape drifted four times; 52,816 rows with a NULL column while every gate passed | One canonical dict before normalize; shape-parity test via `probe`; population floors and coverage counters (the trailing-median alarm deferred to M3) |
| Everything uniformly stale for two weeks; relative freshness checks passed | Zero-new-items detection and per-source freshness separate from run status (the live freshness anchor was cut on 2026-09-13, N-08) |
| Opt-in write guard bypassed by the main DB helper; freshness guard written but never wired | Connection chokepoint enforced by import-linter; scrub as one function; every mutating command takes the lock and writes a run row |
| Silent accept of unknown enum values caused weeks of drift; schema version literal copied into 6+ producers | Unknown values stored raw and counted; single `normalizer_version`; `settings_fingerprint` on runs; two-gate discipline for semantic changes |
| Boolean off-switch silently disabled a safety mechanism fleet-wide | No flag may skip reconcile or scrub; budget is a hard-capped ceiling |
| Half-built DB promoted to live; destructive scripts one mistake from data loss | Destructive-operation gate with a recorded verified backup plus `--yes`; web and Datasette open read-only |
| Ratchets ran only in the full suite, not in the commit path; "the only thing between a regression and the corpus was someone remembering to run the full suite" | Gates in pre-commit and required CI; human review on enforcement surfaces (CODEOWNERS) was considered and declined on 2026-09-13 in favour of compensating controls |
| Small-input tests hid a 90-minute production merge | Weekly stress scenario with wall-time budgets and `EXPLAIN QUERY PLAN` index assertions; indexes declared up front (stress scenario cut 2026-09-13, N-11; the EXPLAIN QUERY PLAN assertions remain) |
| `python3` resolved to 3.9 and silently corrupted output; a second OS surfaced a cluster of silent Mac-first bugs | Absolute interpreter path in launchd; Linux as the primary CI matrix; utf-8, `os.replace`, guarded `fcntl` |
| Fixed-template notifications lied; an alert path could itself be broken | Digest composed from state; the UI status pill derived from `runs` is the canonical alert; `notify --test` is a manual check (the weekly proof was downgraded 2026-09-13) |
| Process outran the product: ~74 ADRs and hundreds of docs before code moved; 81% of docs were agent exhaust | Gates time-boxed to two days; guard count held; agent reports never committed; four living docs with one currency test; size ratchets |
| Operator reading real output caught the highest-impact bugs; the AI's "ship it" was overruled by a third review round that found a security hole | M1d requires Wes to read seven digests against Reddit; zero-context second review proposed for PRs touching deletion, scrub, migrations, and the upsert repo |
| Bot accounts nearly doubled a "human" corpus | `author_is_bot` flag; AutoModerator excluded from themes and digest by default |

Open questions the reviewers raised for Wes: whether Windows is ever in scope (it is not, unless a coworker needs it); the "zero new posts" alarm threshold per subreddit (r/editors may be quiet on weekends); how "top issue" should rank (proposal: distinct authors, not post count); and whether the four referenced documents can be shared.

## Appendix: proposed test-strategy panels (if approved)

Five focused reviewers, run in parallel, each producing concrete test specifications (name, given/when/then, fixture, phase, positive control) rather than prose, followed by one adversarial pass that produces a cut list:

| Panel | Scope | Output |
|---|---|---|
| Database integrity and migrations | upsert semantics, PK stability, FTS sync and rebuild, Alembic batch mode, backup/restore gate, schema snapshot and fingerprint, `DATA_DIR` isolation | ~30 specified tests + fixture DB plan per revision |
| Ingest and collector failure modes | fake-gateway scenario catalogue for every failure-matrix row, parity across ingest paths, state machine table, freshness anchor, budget and ladder, reconcile | scenario builder API + ~50 specified tests (freshness anchor cut 2026-09-13, N-08; per-source zero-new detection kept) |
| Enforcement, gates, and CI | ratchet implementations, positive controls, import-linter contracts, CODEOWNERS, hooks, portability job, `GUARDS.md` structure | CI workflow design + gate-by-gate positive-control specs (CODEOWNERS declined 2026-09-13) |
| UI and delivery surface | route and DOM assertions, security middleware, Run now, export integrity, FTS sanitizer, Playwright smoke | ~40 specified tests |
| Adversarial review | attacks the combined strategy for unfalsifiable gates, list-policing guards, gaps against the failure catalogue, and over-engineering | prioritized cut list and the final `TEST_STRATEGY.md` outline |

Estimated cost: substantial but affordable at the current budget (each panel reads the plan and the learnings folder). The consolidated result becomes `TEST_STRATEGY.md` in the repo at M0 and drives the failing-tests-first order for M1.

## Appendix: research brief (paste into your research tool together with this plan)

**Title:** Engineering controls for AI-assisted codebases: preventing silent failures and unenforced discipline in a small Python data pipeline.

**Context:** Single-developer Python 3.13 project built largely by an AI coding agent. Daily batch collector (PRAW → SQLite via SQLAlchemy 2.0 and Alembic) plus a FastAPI web UI. GitHub Actions CI with branch protection. Goal: a codebase that stays trustworthy for years and can be handed to a coworker. The attached plan's "Robustness, enforcement and portability" section is the current design; critique it.

**Questions:**
1. Which mechanical controls have documented effectiveness against: tests weakened to pass, skipped tests accumulating, over-mocking, broad exception swallowing, schema drift, environment drift, flaky time-dependent tests, partial runs reported as success? Cite sources and tools.
2. Ratchet design: how do teams implement one-way metrics (coverage, type errors, lint suppressions, skip counts, test count) in CI with minimal friction? Concrete implementations for pytest, coverage.py, mypy, ruff.
3. Post-run data invariants and "data unit tests" for batch pipelines (Great Expectations, dbt tests, plain SQL assertions): which patterns fit a SQLite pipeline without heavy dependencies?
4. Working agreements for coding agents (`CLAUDE.md` / `AGENTS.md`, PR templates, review checklists): which rules measurably reduce drift, with evidence from teams using Claude Code, Cursor, or Copilot agents?
5. Mutation testing in Python (mutmut, cosmic-ray): practical cadence and scope for a small project; known pitfalls.
6. SQLite production failure modes worth a gate: WAL on network filesystems, busy handling, backup consistency, VACUUM and rowid stability, FTS5 external-content pitfalls, Alembic batch mode on SQLite.
7. Known anti-patterns in AI-generated Python (over-abstraction, hallucinated APIs, dead code, inconsistent error handling) and which static checks catch them (vulture, ruff rule sets, mypy strict, pyright, import-linter).

**Deliverable:** a prioritized list of controls with cost, what each catches, and how to implement each in GitHub Actions + pytest for this stack; and a list of anything in the plan's gates table that is missing, redundant, or over-engineered.
- Reddit-side behaviors marked unverified by the review (`removed_by_category` values, leaf-deleted-comment disappearance, `info()` on deleted items, `/comments` limit clamp, quarantine response shape) are closed in M1a with the `probe` command and become fixtures.

## Review harness (agentic panels at critical points)

Wes will lean on Claude and on agent panels for PR review and for decisions. The panels used on 2026-09-13 become a standing protocol, and the earlier project's rule applies: reviews are aimed at the previous round's conclusion, with teeth to retract, and same-model builders agreeing is not confirmation.

| Trigger | Panel | Output |
|---|---|---|
| New module, new service, or any schema migration | Two focused reviewers (correctness and tests; operator and data safety) plus one adversarial reviewer, all fresh-context and read-only, reading the plan, the module, and its tests | Ranked findings with a positive control demanded for every new guard; a cut list; P0 findings pause the PR |
| A big change, a new phase plan, or a change to the enforcement surfaces (`tests/gates`, `.ratchets`, migrations, `schema.sql`, `CLAUDE.md`, `.github`) | Same composition plus the decision panel below when a choice is involved | Same, plus an explicit "what would go wrong" per finding |
| Every ordinary PR | One fresh-context review pass over the diff at medium effort (the built-in `/code-review` skill, which Wes can also run with `--comment` to post findings inline); the PR body's `## Independent review` section carries the verdict | Advisory unless a P0 is found |
| Large PRs, milestone merges | Wes may trigger the built-in multi-agent cloud review of the branch or PR (`/code-review ultra`); it is user-triggered and billed, so the harness only recommends it | Findings posted to the PR |
| A decision Wes must make | A three-perspective panel (simplicity, robustness, operator experience) plus an adversarial pass; Claude synthesizes options with a recommendation and the cost of each; Wes decides | A dated entry in `DECISIONS.md` with the reasoning and the dissent |

Mechanics: a `tools/review/` script (M1) takes a PR number or a diff plus a prompt template and runs a reviewer; providers are pluggable so reviewers from OpenAI or elsewhere can be added later without changing the protocol; every review run is recorded in `docs/reference/reviews/` with its date, provider, and the PR it reviewed; panel findings that turn into guards follow the "adding a guard" rule (birth incident, positive control, `GUARDS.md` row). The protocol is conservative by design: it adds review, never removes a gate, and the human remains the decider. Round construction (added 2026-09-13 from the earlier project's panel mechanics): every reviewer prompt is refute-framed ("find what is wrong with this and what it would cost"), never confirm-framed, and a prompt template is a gate artifact reviewed like code; findings are weighed by independence, evidence, and expertise, never tallied, so one evidenced dissent outranks three agreements; each round records what the reviewer was given, because a reviewer handed the prior verdict inherits its blind spots; when two rounds disagree, the tie-break is re-running the specific check both reasoned about, never a vote; and rounds stop when a round surfaces nothing new, not at a fixed count.

### Agent model tiers (decided 2026-09-13)

Wes's rule: the main session does the detailed planning, synthesis, and final judgement; sub-agents run on the least capable model that fits the work. Until 2026-09-13 every sub-agent inherited the main session's model, which was overkill and exhausted the session limit in the middle of a workflow. From now on every `Agent` call and every workflow `agent()` call names its model explicitly; "inherit" is not a choice.

| Tier | Use for | Examples in this project |
|---|---|---|
| The main session | Detailed planning, design lock-down, synthesis of panel output, the final decision or recommendation, anything that edits the plan or the enforcement surfaces | Writing and amending `PLAN.md`; deciding what a panel's findings change; authoring workflows; handoff verification; the last word on a review |
| Opus | Complex areas and work where judgement still matters | Adversarial and design reviewers; the judge or critic stage of a workflow; reviewing or implementing migrations, `core/deletion`, `services/scrub`, `db/repo`; a service whose spec leaves choices open; debugging a red gate; extracting insight from long documents |
| Sonnet | Well-specified, mechanical, or high-volume work | Per-file inventories and scans; applying a deterministic map or codemod; writing tests from a spec-table row; fixture scrubbing; doc-currency and residue sweeps; renames and formatting; first-pass reading to build a map |
| Haiku | Not part of the policy | Add only with a recorded reason in `DECISIONS.md` |

Rules: a Sonnet stage that turns out to need judgement gets an Opus verifier behind it rather than being promoted wholesale; when unsure which tier a stage needs, pick the higher one and say why in the workflow's `meta.description`; the tier of each stage is recorded in `meta.phases[].model` so the run log shows it; review panels mix providers once `tools/review/` (M1) can call one that is not Anthropic, because same-family agreement is not confirmation. Promotion rule: when an Opus verifier catches something a Sonnet stage missed twice in a row, that class of stage moves to Opus and the decision is logged.

## Workspaces: expanding to other domains

Wes expects to point the same system at other niches within a month or so (for example, AI adoption among small and medium businesses, for a consulting practice). The design unit for that is a **workspace**: a named set of sources (subreddits, saved searches), themes, digest settings, and ranking rules. Posts and comments are shared data; sources and themes belong to a workspace; a post can be visible in several workspaces through its sources. Schema revision 1 carries a `workspaces` table and a `workspace_pk` on `subreddits`, `searches`, and `themes`, seeded with one workspace (`premiere`), so no migration is needed when the second domain arrives. In the UI the workspace is the top-level switch in the header: every feed, theme page, digest, settings page, and export is scoped to the active workspace, and a "lens" within a workspace isolates a chosen subset of themes for focused reading. Compliance, budgets, and the collector are workspace-agnostic; the request budget is shared and reported per workspace.

**Workspace lifecycle (decided 2026-09-13).** A workspace can be *archived* or *deleted*. Archiving sets `archived_at`, hides the workspace from the switcher and the digest, disables its sources so nothing is polled for it, and keeps every captured row; compliance reconcile keeps running over all stored items regardless of workspace, because the obligation attaches to the data, not the focus area. Deleting a workspace goes through the destructive gate (recorded verified backup plus a typed confirmation, with an export offered first) and removes its sources, themes, and theme tags, plus the posts and comments reachable through no other workspace's sources (decided by the `post_sources` join), recording the purge counts on the run row so the row-count invariant can read them. Sources can also be moved between workspaces without touching captured data. Schema revision 2 (at M2, when the UI ships) adds `workspaces.archived_at`; nothing else in revision 1 needs to change.


## Resilience to outages (automatic, no operator action)

The system has most of the day to succeed, so it is built to pause, retry, and resume on its own: a connectivity and auth preflight before any paging; the outer retry ladder (30 s, 2 min, 5 min) around every page, tree, and info batch on top of prawcore's short retries; a run that cannot reach Reddit at all exits with a distinct `network` status, writes nothing but its run row, and is retried by the scheduler at two later intervals the same day (launchd runs the job at 06:30, 12:30, and 18:30; a successful run makes the later ones near no-ops because the sweep is idempotent and cheap); a rate-limited run pauses for the `Retry-After` window and resumes in the same process, and if the window exceeds the run's wall-clock ceiling it exits `rate_limited` and the next interval picks up where the watermark and revisit queue left off; the queue-based design (`next_check_at`, per-post budgets) means nothing is lost by a missed interval, only delayed; the freshness invariants say so in the digest when a source has not been fetched for two intervals; sleep and lid-close are handled by `caffeinate` and by the flock-means-alive rule.
