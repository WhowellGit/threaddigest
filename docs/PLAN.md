---
purpose: The design of the system as it stands, canonical for every design question.
update-policy: versioned
mirrors: [docs/OVERVIEW.md, docs/THREADDIGEST_HARNESS.md, docs/TEST_STRATEGY.md, docs/runbook/RUNBOOK.md, docs/decisions/DECISIONS.md, docs/recent/STATUS.md, docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md, CLAUDE.md, config/settings.yaml, deploy/launchd/README.md]
verified-at: M1a-A
---
# Plan: Thread Digest (version 2, 2026-09-15)

> **What this is.** The design of the system as it stands, canonical for every design question. Version 2 is a rewrite of the 2026-09-12 plan after three days of reviews and fixes had annotated it past the point of reading cleanly; it states the current shape only. Version 1 and every dated correction are in git history (`git log --follow docs/PLAN.md`), the reasoning behind each choice is in `docs/decisions/DECISIONS.md` (settled choices D-nn, settled negatives N-nn, dated entries), the review records are under `docs/reference/reviews/`, and what is built right now is on `docs/recent/STATUS.md`. A shorter reading for someone who will not read this is `docs/OVERVIEW.md`; the working method is `docs/THREADDIGEST_HARNESS.md`. The plan's policy is in its front matter (versioned: corrected in place between versions, rewritten as a new version once annotations accrete); the sections version 2 retired, and where each now lives, are listed at the end.

## Intent (read this first)

Thread Digest answers one question about a community: *what are people struggling with, how many distinct people, and for how long.* It collects what people say on Reddit on a schedule, keeps it honestly (deletions honoured on the next run, every count shown with its denominator), and helps assemble the actual user problem from scattered, vague, non-technical reports, which is the hardest and most valuable step in understanding any product's users. The first and, for version one, the only focus is Premiere Pro and its adjacent editing communities: a personal project of a long-time editor, with no business application (Wes, 2026-09-15). The same machinery is designed to take a second focus later as a further *workspace* (§ Workspaces), and the whole of it is personal, non-commercial use under Reddit's terms.

It is not a search engine over Reddit, not a bridge to any other system, not a profiler of people, and not a learned ranker: themes are rules Wes writes, ranking is one deterministic function, and an analysis layer comes only at M5. Success is judged by Wes reading seven consecutive scheduled-run digests against Reddit itself at the end of M1d, and by the predictions in `docs/learnings/LEARNINGS_TRANSFER.md` §5. The recurring human duties are three: read the digest, acknowledge alerts in the UI, label tags while browsing. This block carries durable intent only (D-28).

## Context

**Goal.** A personal, rules-compliant system that collects Reddit discussion twice a week, stores it locally in one SQLite file, deduplicates it, and lets Wes browse it in a Reddit-like local web UI. Over months the collection becomes a searchable asset for seeing the top quality issues and complaints in a community, and later feeds summarisation and trend analysis (M5).

**Why this shape.** The research report (`docs/reference/2026-09-11-compass-research-report.md`) and Reddit's own policy pages, read live on 2026-09-14 (`docs/reference/reddit-policy-facts-2026-09-14.md`), fix the constraints: authenticated OAuth through PRAW is the only compliant path; one hundred queries a minute per client id; an honest versioned user-agent; deletions and removals honoured; no automated replies; explicit approval before API access under the Responsible Builder Policy; commercial use only under a separate written agreement (not sought: all use here is personal); no deriving sensitive characteristics about users and no re-identification; a home IP preferred to a datacenter IP. The report recommends starting minimal and growing additively; this plan follows that ladder but with a Reddit-style UI instead of a database browser, because intuitive browsing and in-UI management of what is monitored are explicit requirements. PRAW and prawcore behaviour was checked against upstream on 2026-09-12 and the tested major is pinned (G53).

**The load-bearing choices** are registered in `docs/decisions/DECISIONS.md` § 1 with their revisit triggers, and the choices made after 2026-09-13 (D-30 to D-32 and the deferrals) as dated entries in the log's later sections, each with its trigger; the ones a reader needs before anything else:

| Choice | Decision |
|---|---|
| Communities (workspace one) | r/premiere, r/VideoEditing, r/editors; optional r/AfterEffects, r/DavinciResolve; names are case-insensitive (D-01) |
| Themes | Three concepts: subreddit **sources** polled completely; **themes**, named keyword or regex rule groups tagging posts locally; **saved Reddit-wide searches** as a third source type at M3 (D-02) |
| Ranking | Distinct authors first, then comment count, then score, then a stable id; never raw post count; one function shared by digest, theme pages, and export; identity coverage printed beside every ranked list (D-09) |
| Deleted or removed content | Scrub text and author, keep the id row as a tombstone; deleted text survives nowhere (D-04; bounds in DECISIONS § 2) |
| Comment collection | Full trees for every captured post, under a per-run budget and a revisit ladder (D-05) |
| Cadence | The collector runs automatically twice a week, Monday and Thursday at 06:30; reconcile and a backup on every run; Run now stays available (D-30) |
| Storage | SQLite (WAL, FTS5) with dialect-specific code confined to `db/`; the Postgres exit triggers are in DECISIONS § 4 (D-25) |
| UI | FastAPI + Jinja2 + HTMX, old-Reddit density, no build step; the web UI is the operator surface for every routine action and the CLI mirrors it (D-03, D-28) |
| Reddit account | A dedicated account, read-only API use, no password stored (D-07, N-03) |
| Hosting | This Mac now, Docker on the Mac, then the QNAP; the first remote is a bare repository on the QNAP (milestone MB); GitHub only when CI is wanted (D-06, 2026-09-14) |
| Enforcement | Every rule names its mechanical enforcer or is labelled review-only; hard-block hooks in the path of every tool call; `main` receives only a tree `make check` stamped green (D-11 as amended, D-29; `docs/THREADDIGEST_HARNESS.md`) |
| Project home | `~/repos/insightminer` for repo and data, outside the folders launchd cannot read, no spaces in the path (D-08) |
| Raw JSON | `raw_json` per row is the single raw store; the per-run JSONL sidecar was cut (D-15 superseded, 2026-09-13) |
| Use | Personal interest only, for every workspace; no commercial use is planned or sought (Wes, 2026-09-15) |

## From data to insight

Everything about how the data is stored and queried follows from the one question.

**Our own ranking, not Reddit's.** Reddit's hot and popular listings answer Reddit's question, what is engaging right now, and are never used. Every ranked list uses `core.digest.rank_posts`: distinct authors first, then comment count, then score, then the post id so ties never wobble. Never raw post count, never recency. One prolific poster cannot manufacture a trend and a fresh post is not an important one. Authors are counted by `author_fullname`, never by display name; NULL identities (scrubbed and account-deleted rows) are excluded rather than collapsed into one bucket, and every ranked list prints (from M1d) the identity coverage of the ranked set and annotates rows from incomplete trees, because a proxy's coverage gaps become ranking errors (D-09). The digest models gain explicit identity-coverage and tree-completeness fields beside the count at M1d (a fourth-seat finding, 2026-09-14).

**Themes are rules, not a model.** A theme is a named group of rules in three groups (match any of, exclude if any of, only in these subreddits), each rule a keyword, a regex with a timeout and a length cap, a flair, or a subreddit, scoped to title, body, comments, or any. Tagging records which rule matched and in which field, never a text snippet. The rule set is hashed (`themes.rules_hash`), so a changed theme re-tags everything. Determinism is what makes digests weeks apart comparable. No learned ranker; no conversational agent inside the app before M5 (N-21): exploring what to track happens beside the app and arrives as a rule file through the live preview.

**Two discovery signals for what the rules miss.** The digest's untagged section lists posts no theme matched but three or more distinct people are discussing within the window. Its rising-phrases section compares title phrases in the current window against a trailing four-week baseline. The first says a problem exists that the rules miss; the second says it is growing. Promoting a rising phrase into a rule is one click at M2.

**"For how long" comes from revisiting.** Posts are re-fetched on the ladder in `config/settings.yaml` (`revisit_ladder_days`) after `created_utc`, so comment counts reflect a thread's maturity, and every fetch stores a numeric-only snapshot (`item_snapshots`: score, comment count, upvote ratio), the raw material for velocity at M3 and trend charts at M5. Nothing textual is snapshotted, so a deleted post leaves no derived copy. The third clause of the question, for how long, is therefore answered by the analysis layer, not by the M1d digest, which carries a thread's maturity rather than a problem's duration; M1d adds a per-theme first-seen and weeks-active line to the digest, computed from `post_themes` tag times and `created_utc`; the analysis layer refines it.

**Every count carries its denominator.** The digest and the UI never show a bare number: a theme shows its matches *of* the new posts in the window; the untagged and rising sections state their windows and baselines; the backlog and compliance sections say what was not collected and how old the last full re-check is. Each metric is one function with a golden test, shared by UI, digest, and export.

**Search is over live content only.** FTS5 indexes are external-content tables over the live-only views (`posts_live`, `comments_live`); a scrub removes the entry by trigger and, since revision 0004, clears the term bytes in the index as it runs.

**Workspaces scope every view.** Sources, themes, digest settings, and the ranking rule belong to a workspace; posts and comments are shared. One workspace exists in version one (§ Workspaces).

**What is deliberately not done with the data.** No profiling of authors: the `authors` table is aggregated at ingest and no user endpoint is ever fetched; bot detection is a heuristic surfaced as "suspected" with one-click confirm (N-14). No hash or snippet of deleted content anywhere. No commercial use of any output.

## Architecture

```
 Sources                    Collector (CLI, scheduled)             Store                          Outputs
 subreddit /new  ──┐        ┌──────────────────────┐    upsert   ┌────────────────────┐          ┌─ digest (route; file on request)
 saved searches ───┼──────▶ │ PRAW adapter (read-  │ ──────────▶ │ SQLite (WAL, FTS5) │ ───────▶ ├─ FastAPI + HTMX web UI (M2)
 (M3, Reddit-wide) ┘        │ only, honest UA,     │             │ Alembic-managed    │          ├─ export .zip (M2)
                            │ request budget)      │             │ raw_json per row   │          └─ (M5) JSONL → the analysis layer
                            └──────────────────────┘             └────────────────────┘
                                   ▲
                     launchd (Mac) / supercronic (Docker) ── runs `threaddigest run` Monday and Thursday
```

One Python package, two entry points: a FastAPI app (`threaddigest serve`, M2) that is the operator's surface, and a `typer` CLI used by the scheduler, containers, tests, and break-glass recovery. Both are thin wrappers over the same service functions; after installation no routine operation requires a terminal. Ports and adapters inside: `core/` (pure logic) and `services/` never import `praw`; only the PRAW adapter module does. The UI never talks to Reddit except to validate a subreddit when one is added.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Runtime | Python 3.13 via `uv` (`.python-version`, `requires-python`, `uv.lock`), `src/` layout | A year of bugfix releases and wheels for every dependency; CI runs an informational 3.14 job and the pin moves up when it is green (D-24); Python 3.9 is what stock macOS ships and what silently corrupted the earlier project's output, so the interpreter is always the project's own |
| Reddit | PRAW 8.x, pinned to the tested major (`praw>=8,<9`, G53), in **read-only mode** (client id and secret only) with `check_for_updates=False`, `timeout=30`, and an injected `requests.Session` that counts requests | PRAW handles OAuth refresh, pacing, and short retries; read-only is all the system needs; PRAW 8's `replace_more` discovers up to a hundred comments per request and the budgeting assumes it |
| Storage | SQLite (WAL) via SQLAlchemy 2.0; Alembic (`render_as_batch`); FTS5; `raw_json` per row | System of record plus provenance; zero server; other tools read the file directly |
| CLI | `typer` + `rich` | Discoverable commands, progress output |
| Config | `pydantic-settings`: `.env` for secrets, `config/settings.yaml` for static settings (validated at load, `extra="forbid"`); subreddits, themes, and searches live in the DB, UI-editable, with YAML import and export that never includes secrets | Avoids config-versus-UI drift |
| Web (M2) | FastAPI + Jinja2 (autoescape, StrictUndefined) + HTMX (vendored) + one hand-written stylesheet and a few lines of JavaScript; markdown rendered at ingest with `markdown-it-py` + `nh3` | Old-Reddit density; no build step; single worker |
| Rules | `regex` package (supports `timeout=`), pattern length caps | Regex authored in a UI is a ReDoS risk; the stdlib has no timeout |
| Tests | pytest with the network blocked and warnings as errors; `FakeRedditGateway` as a scenario builder; `pytest-recording` cassettes and `responses` for the adapter; `pytest-alembic`; `time-machine`; `hypothesis`; TestClient + `selectolax` for the web; optional Playwright | The collector never touches the network in tests |
| Quality | ruff, mypy strict, import-linter, pre-commit, `make check` | One command gates every change (`docs/THREADDIGEST_HARNESS.md`) |
| Scheduling | launchd (Mac) now; supercronic in Docker later | launchd runs a missed job on wake; supercronic avoids the QNAP crontab-overwrite gotcha |

**Why SQLite, and the Postgres exit.** One writer, one machine at a time, growth of roughly a gigabyte or two a year. The database is a file that can be backed up, exported, and handed to someone. Postgres would add a server to run, upgrade, and back up, and buys nothing until there are concurrent writers on different hosts, a multi-user web app, or data in the hundreds of gigabytes. To keep the exit cheap: SQLAlchemy and Alembic are the only schema and query layer; every SQLite-specific statement (pragmas, the online backup call, FTS5 DDL and `MATCH`) lives inside `db/`, the search helpers in `db/fts.py` and the copy in `db/backup.py`, as plain modules rather than a port, because a port with one implementation is the abstraction N-20 forbids; upserts use `ON CONFLICT DO UPDATE`, which both engines support; raw SQL outside `db/` is banned by a ruff rule. The triggers for the move are in DECISIONS § 4.

## Repository layout

```
~/repos/insightminer/
├── pyproject.toml  uv.lock  .python-version  alembic.ini  Makefile  README.md  .env.example  .importlinter  .pre-commit-config.yaml
├── CLAUDE.md                          # the working agreement, always loaded
├── .claude/  settings.json (hook registration)  rules/{db,services,web}.md  skills/harden/
├── .ratchets/                         # one-way floors and ceilings, written only by tools/ratchet.py
├── config/   settings.yaml (budgets, ladder, reconcile, retention, display timezone)  seed.yaml (first sources and themes)
├── deploy/   launchd/{run.sh, common.sh, install.sh, uninstall.sh, *.plist, README.md}   docker/ and compose.yaml at M4
├── docs/     PLAN.md OVERVIEW.md THREADDIGEST_HARNESS.md TEST_STRATEGY.md INDEX.md  decisions/ insights/ learnings/ recent/ reference/ runbook/
├── memory-snapshot/                   # add-or-update-only copy of the auto-memory
├── src/threaddigest/
│   ├── cli.py  settings.py  ports.py                     # ports = Protocols + domain exceptions
│   ├── core/      models normalize paging deletion milestones themes budget retry digest   # pure, no I/O
│   ├── adapters/  clock notify reddit_fake/ (package)    reddit_praw
│   ├── db/        engine schema schema.sql schema_dump repo ownership fts backup migrate migrations/versions/0001..0004
│   ├── services/  lock runs collect sweep seed invariants doctor migrate   (trees, revisit, reconcile, scrub, tag, report, export: M1b–M1d)
│   └── web/       (M2) app deps filters routes/ templates/ static/{app.css, app.js, vendor/htmx.min.js}
├── tests/    unit/ db/ adapters/ services/ e2e/ gates/ deploy/ tools/ web/ fixtures/{json/, db/}
├── tools/    ratchet check_stamp code_health hooks_status memory_snapshot review_packet harness_page make_demo_fixture render_plan vulture_whitelist  hooks/*.sh
└── data/     (gitignored) threaddigest.db  reports/  backups/  exports/  logs/  locks/
```

## Reference corpus and memory routing

The corpus lives in `docs/` and travels with the code. Every living document under `docs/` opens with a contract in its front matter: its purpose, its update policy from a fixed vocabulary (`append-only` for the dated logs, `prune-stale` for documents whose affected section is rewritten in place when a fact changes, `versioned` for the plan, `rewritten` for the status page; a generated block such as the harness inventory is a region inside a prune-stale page), the documents it mirrors (declared from both sides), and the milestone it was last verified at; `tools/doc_policy.py` checks the contract, holds append-only documents and reference records to their diff against the merge base with `main`, counts dated annotations in the prose of rewritten documents into a ratchet ceiling (a pressure: an accreting count means a targeted rewrite is due), fails a rewritten document that lags the status page's milestone by more than one or is stamped ahead of it, resolves every document path with a directory that a rewritten document names, and checks the live-facts table in the decisions log against every listed mirror and its configuration or code home (G55); whether a mirror's prose still agrees with its source is review, through the `docs-sweep` skill. The procedure is `docs/runbook/RUNBOOK.md` § 8 and the `docs-sweep` skill. `docs/INDEX.md` is the router: one line per document and when to read it, checked against the tree in both directions (G33). `CLAUDE.md` stays short and always loaded: the irreversible rules, the rules table with an enforcer per row, and a routing table from task to document; path-scoped rule files under `.claude/rules/` load only when a matching file is edited. Update policy by folder: `insights/` and `learnings/` append-only with dated entries; `decisions/` append-only with a revisit trigger per entry and a machine-read retired-claims table (G34); `runbook/` prune-stale, generated where possible; `recent/STATUS.md` the one rewritten resume surface, capped, stamped, and forbidden to restate counts (G45); `reference/` add-never-edit. Every fixed bug lands in `runbook/KNOWN_ISSUES.md` pointing at its regression test (G40). Agent transcripts and raw findings are never committed. The auto-memory outside the repo is snapshotted into `memory-snapshot/` add-or-update only and audited by `make check` (G47). The full working method, with a generated inventory of every mechanism, is `docs/THREADDIGEST_HARNESS.md`.

## Module map (layering enforced by import-linter, not convention)

Layers, outermost to innermost: `web` | `cli` → `services` → `db` | `adapters` → `ports` → `core`. `core` imports nothing from the project or from `praw`; only `adapters/reddit_praw.py` imports `praw`, and the import-linter contract that says so is an error contract since the module landed; `web` never imports `cli`. Boundaries speak typed values: pydantic models for normalized rows, dataclasses for gateway results, `Protocol`s in `ports.py`. `mypy --strict` on the whole `src` tree.

| Module | Responsibility | Depends on | Tested by | State |
|---|---|---|---|---|
| `core.normalize` | raw API dict → `PostRow`/`CommentRow`, typed coercion, rejects; crosspost parents reduced to `{id, subreddit}` | pydantic | unit + hypothesis | built |
| `core.deletion` | content and author state machine, scrub decision | — | exhaustive table test | built |
| `core.paging` | `/new` sweep stop, cap and gap rules; removal-candidate detection | — | unit | built |
| `core.milestones` | revisit ladder (`check_stage` → `next_check_at`) | — | unit, injected clock | built |
| `core.themes` | rule compile (`regex` with timeout, caps) and match; `rules_hash` | regex | unit incl. ReDoS timeout | built |
| `core.budget` | per-run request accounting and reserve | — | unit | built |
| `core.retry` | retry ladder, exception classification, run statuses and exit codes, rate-limit wait planning | — | unit, hypothesis | built |
| `core.digest` | digest model (ranking, theme, untagged, rising, workspace, backlog, compliance sections) → markdown and HTML | jinja2 | golden file | built, not yet assembled from the DB (M1d) |
| `adapters.reddit_fake` | scenario-building fake gateway, a package | — | contract suite (same cases as the real adapter) | built |
| `adapters.reddit_praw` | `RedditGateway` over PRAW; request counting; exception translation | praw | cassettes + `responses` + contract suite | built; failure paths covered by `responses`, cassettes and the contract suite follow the probe day |
| `adapters.notify`, `adapters.clock` | `Notifier` (macOS `osascript`, log, null, and a fake for tests; ntfy is a later option, D-10); injected clock | subprocess | unit | built |
| `db.*` | pragmas, models, upsert repository with the field-ownership table, FTS, backup and restore, migrations, schema dump | sqlalchemy, alembic | db tests, pytest-alembic, snapshot diff | built |
| `services.*` | use cases: lock, runs, collect, sweep, seed, invariants, doctor, migrate | core + ports + db | e2e against the fake | built; trees, revisit, reconcile, scrub, tag, report, export follow in M1b–M1d |
| `cli` | typer wiring, exit codes | services | CliRunner | `run`, `doctor`, `db init/upgrade/current`, `config validate` built |
| `web.*` | routes, templates, partials, security middleware | services, db (read) | TestClient + selectolax, Playwright smoke | M2 |

## Data model (SQLite)

Conventions: integer surrogate primary keys (`pk INTEGER PRIMARY KEY AUTOINCREMENT` on `posts` and `comments`, so a purge cannot recycle a rowid into a stale FTS entry) with `reddit_id TEXT UNIQUE`, because FTS5 external-content tables key on `rowid` and implicit rowids can be renumbered by `VACUUM`. All timestamps are INTEGER epoch seconds (Reddit's `created_utc` domain; SQLAlchemy's timezone-aware `DateTime` silently drops the zone on SQLite). Subreddit identity is `name_lower` plus the `t5_` id, unique within a workspace. Upserts are `INSERT … ON CONFLICT(reddit_id) DO UPDATE`, never `INSERT OR REPLACE`, which deletes and re-inserts, burns rowids, and detaches FTS rows (N-04); a PK-stability gate (`tests/gates/test_pk_stability.py`, three reruns) checks that reruns leave `pk` and `first_seen_at` unchanged; the `max(pk) == count(*)` equality was dropped (A10), and the runtime form of the rule is that row counts never decrease except through a recorded purge. `next_check_at` is NOT NULL, because a NULL is never due and the post would silently never be revisited. Every column carries a SQLAlchemy `comment=`, so `src/threaddigest/db/schema.sql`, the committed golden that `alembic upgrade head` must reproduce (G15), doubles as the data dictionary. Indexes are declared up front, `posts(next_check_at)`, `posts(subreddit_pk, created_utc)`, `posts(author_fullname)`, `posts(content_state)`, `comments(post_pk, parent_comment_pk)`, `comments(author_fullname)`, `post_themes(theme_pk)`, `item_snapshots(item_pk, fetched_at)`, and the `EXPLAIN QUERY PLAN` assertions in `tests/db/test_query_plans.py` prove the hot queries use them (N-11).

**Table-to-writer map.** The collector is the only writer of `posts`, `comments`, `comment_more`, `post_sources`, `item_snapshots`, `authors`, `raw_rejects`. The web layer writes only `subreddits`, `searches`, `themes`, `theme_rules`, `post_themes` (retag), `ui_state`, and `runs` rows in `queued` state, through a repository object that exposes exactly those writes. Each ingest path (sweep, tree fetch, `info()`, search) owns a declared field set (`db/ownership.py`): the sweep may update score, `num_comments`, and `edited_utc` but never `first_seen_at`, `check_stage`, or `next_check_at`; a test asserts the ownership table.

| Table | Key columns | Notes |
|---|---|---|
| `workspaces` | slug (unique), name, description, ranking (default `distinct_authors`), digest_settings_json, created_at | The design unit for a second domain (§ Workspaces); seeded with one; `archived_at` arrives with the curation migration at M2 |
| `subreddits` | workspace_pk, name_lower and subreddit_id (each unique within the workspace), display_name, subreddit_type, subscribers, over18, quarantine, enabled, comment_mode (default `full`), added_at, watermark_created_utc (informational), last_complete_poll_at, status (`ok/forbidden/not_found/redirect/quarantined/error`), last_error, consecutive_failures, gap_suspected_at | Polled sources |
| `searches` (M3) | workspace_pk, query, scope, sort, time_filter, enabled, last_run_at, status | Saved Reddit-wide searches |
| `posts` | reddit_id, fullname, subreddit_pk, author, author_fullname, author_flair_text, author_is_bot, title, selftext, selftext_html (sanitized at ingest), url, domain, permalink, created_utc, edited_utc, score, upvote_ratio, num_comments, flair and flags, crosspost_parent (id and subreddit only), removed_by_category, **content_state** (`live/deleted_by_author/removed_by_moderator/removed_by_reddit/gone_unconfirmed/gone`), **author_state** (`known/account_deleted`), misses, scrubbed_at, first_seen_at, last_fetched_at, comments_fetched_at, comments_captured, comments_complete, more_skipped, more_skipped_count, **next_check_at**, **check_stage**, source, normalizer_version, **raw_json** | Upserted current state; `comments_complete` means the tree fetch succeeded and `replace_more` skipped nothing |
| `comments` | reddit_id, fullname, post_pk, parent_fullname, parent_comment_pk (null for top level, no FK), author, author_fullname, author_is_bot, body, body_html, created_utc, edited_utc, score, depth, permalink, is_submitter, stickied, distinguished, content_state, author_state, misses, scrubbed_at, first_seen_at, last_fetched_at, normalizer_version, raw_json | Tree built in Python per page |
| `comment_more` | post_pk, parent_comment_pk, count | Unexpanded "more" stubs → "N replies not captured" |
| `post_sources` | post_pk, source_type (`subreddit/search`), source_pk, first_seen_at | Provenance; a post can arrive both ways, and through several workspaces |
| `item_snapshots` | item_pk, kind, fetched_at, score, num_comments, upvote_ratio | Numeric only: a hash of deleted content is derived content |
| `authors` | author_fullname (unique), name, first_seen_at, last_seen_at, post_count, comment_count | Aggregated at ingest; never fetch a user endpoint |
| `themes` / `theme_rules` / `post_themes` | themes: workspace_pk, name and slug (unique within the workspace), color, description, enabled, rules_hash, tagged_hash. rules: theme_pk, rule_group (`match/exclude/only_in`), kind (`keyword/regex/flair/subreddit`), pattern, scope, case_sensitive, whole_word, enabled. post_themes: post_pk, theme_pk, rule_pk, matched_field, tagged_at; `origin` (`rule/manual`) arrives at M2 | No matched-text snippets stored |
| `runs` / `run_subreddits` | runs: kind, trigger (`cli/ui/schedule`), started_at, finished_at, heartbeat_at, pid, status (`queued/running/ok/partial/failed/rate_limited/network/skipped_locked/crashed/cancelled`), stage, counters, violations_json, api_requests, app_version, praw_version, schema_rev, settings_fingerprint, error, log_path. run_subreddits: run_pk, subreddit_pk, pages, items_seen, new, updated, stop_reason (`exhausted/cap/error`), error | Drives the Runs page, digest, and gap detection |
| `backups` | path, sha256, size, integrity result, kind, schema_rev, table_counts_json, created_at | The destructive gate keys on a record here; the restore drill compares counts against `table_counts_json` |
| `raw_rejects` | run_pk, raw_json, error, created_at | Rows missing required fields; retention in `config/settings.yaml` |
| `ui_state` | key, value | e.g. a feed filter the operator last chose |
| `posts_fts`, `comments_fts` | FTS5 external-content over the live-only views `posts_live` and `comments_live`, tokenizer `porter unicode61`, sync triggers on the base tables gated on an actual change; persistent `secure-delete` on both indexes | The membership invariant counts `posts_fts_docsize`, because `count(*)` on an external-content table can never go red |

**Schema revisions (Alembic, zero-padded ids).** `0001` the initial schema above; `0002` the `network` run status and `runs.violations_json`; `0003` the FTS update triggers gated on an actual change (`WHEN old.x IS NOT new.x`); `0004` FTS5 persistent secure-delete on both indexes, one `optimize` to merge the delete markers already present, and a minimum SQLite version checked by `doctor` (the `optimize` after each scrub is `db.fts.optimize`, which the M1c scrub stage calls). Each shipped with a prior-revision fixture database under `tests/fixtures/db/`. The next planned revision is the **curation migration** at M2: an archive stamp on workspaces, an origin (rule or manual) on post themes, a watch-until stamp on posts, a cancel-requested stamp on runs (the cancel ruling, UI D5), and the light duties table (last completed, interval), the duties record Wes approved on 2026-09-13, in one migration, with an index on `post_sources` by source for the workspace paths that ask which posts a source reaches.

**Raw JSON policy.** `raw_json` on each row is the single raw store (`db reprocess --below N` re-normalizes without touching Reddit). Exact-wire captures for fixtures come from `probe --save-fixture` (tranche B); JSONL of live content is produced on demand by `export` (M2). Both wire shapes (listing JSON, and PRAW-attribute JSON for trees) are converted to one canonical dict before `core.normalize` runs, and a shape-parity test feeds the same real post captured both ways and asserts identical rows.

**Content-state machine** (pure function in `core/deletion.py`, unit-tested, predicates re-confirmed against real captures on the probe day). The rules apply in this order and the first that fits wins: (1) `deleted_by_author` is terminal; (2) an item that `reddit.info()` did not return counts a miss, `gone_unconfirmed` at the first and `gone`, scrubbed, at the second, which need not be consecutive (KI-021); (3) `removed_by_category='deleted'`, or `selftext/body == "[deleted]"`, → `deleted_by_author`, the category keyed on before any body predicate because a deleted link post carries an empty `selftext`, not the marker; (4) any other `removed_by_category`, whatever the body: `moderator` → `removed_by_moderator`, a value Reddit uses for its own removals → `removed_by_reddit`, and an unknown value → `removed_by_reddit` (fail closed, never live); (5) a returned item with no body at all holds as `gone_unconfirmed` without counting a miss; (6) `== "[removed]"` with no category → `removed_by_moderator`; (7) `author is None` on a link post with no category is a deletion pending the `info()` check, the same hold, because a deleted link post has an empty `selftext` and would otherwise pass as an account deletion (adversarial B3); (8) otherwise the content is intact → `live` with the misses reset, the only way a removed or unconfirmed item returns (moderator removals do return when re-approved), and on intact content `author is None` with `author_fullname` absent → `author_state = account_deleted` (scrub author fields only, content stays, `authors` row deleted).

**Scrub** = null all content, author, and URL columns, replace `raw_json` with a tombstone object, delete `post_themes`, FTS entry removed by trigger with its term bytes cleared, `PRAGMA secure_delete=ON` so freed pages are overwritten, and an index `optimize` so no delete marker lingers. The row and its tree position remain so children still hang and the item is never re-fetched as new. Edits are an event: reconcile upserts the full normalized row so an edited body replaces the old one everywhere.

**SQLite facts the design rests on** (verified empirically 2026-09-13 and later): on an external-content FTS5 table `SELECT count(*)` returns the content table's count; a `rebuild` with live-gated triggers re-indexes tombstones, so the index points at live-only views; Alembic batch recreates fail while a view references the table, so batch migrations drop and recreate the views and triggers and then rebuild the index; `PRAGMA secure_delete` does not reach FTS5's shadow segments, hence revision 0004; the runtime schema fingerprint is derived by one normalizer from the live `sqlite_master` and the packaged `schema.sql`, never a stored constant, and warns rather than refuses (N-13).

## Collector algorithm (`threaddigest run`, twice a week)

0. **Order matters:** validate settings → the database file must exist → the data tree → `fcntl.flock` on `data/locks/collector.lock` (exit 75 if held) → refuse if migrations are pending, checked under the lock because the holder may be a `db upgrade` mid-migration → mark stale `running` rows as `crashed` → insert the `runs` row → one cheap auth ping so credential failures surface before any paging. Config and auth failures never leave a `running` row. Every mutating command (`fetch`, `comments`, `revisit`, `reconcile`, `tag`, `scrub`, `reprocess`, `import`, `db upgrade`, `db restore`) takes the same flock and writes a `runs` row with a stage-bearing heartbeat (`rate_wait:37s` counts as alive); the per-run wall-clock ceiling (`run.wall_clock_ceiling_hours`) ends the run as `partial` after the current batch. A run with no collectable source is never `ok`: it warns, ends `partial`, and the hourly `doctor` reports an error (KI-017).
1. **Sweep `/new` fully** for each enabled subreddit: up to a thousand listing slots (Reddit's cap; normally ten pages of a hundred, with a fail-closed ceiling of a hundred and twenty pages when Reddit serves short ones), forward `after` paging only, one transaction per page. It catches posts approved late from the mod queue at their original position, refreshes score and comment counts for the newest posts for free, and yields a removal signal (a known post inside the window that no longer appears → confirm via `info()`; the detection is built and unit-tested and reconcile wires it at M1c). If the cap is hit before reaching known territory, set `gap_suspected_at` and `stop_reason='cap'` (KI-018); stickies are excluded from stop logic. At the twice-weekly cadence the busiest target produces tens of posts a day, so the cap stays comfortable (D-30; an assumption until the probe day and the first backfill measure it).
2. **Collect comment trees** (M1b) for posts due (`next_check_at <= now`, newest first) within the per-run budget (`budget.per_run_requests`, counted by our own session hook; hard cap `budget.hard_cap`, never exceeded by any flag, N-06). Skip when `num_comments == 0`. `submission.comments` (one request, which also refreshes the post) then `replace_more` up to `comments.replace_more_limit` per pass and `comments.per_post_expansion_cap` per post; each replacement is one request yielding up to a hundred comments, and a `count == 0` node is a continue-this-thread link. Skipped stubs go to `comment_more`; one transaction per tree. PRAW objects are serialized with `vars()` minus private keys and read from the dict: touching a missing attribute silently fires a request.
3. **Revisit ladder** (M1c) via `check_stage`/`next_check_at`, at the days in `revisit_ladder_days` (`[1, 3, 7, 30, 365]`, with a code twin in `core.milestones`, both in the live-facts table) after `created_utc` (posts keep receiving replies for days; the last stage is a year so `next_check_at` is never a far-future sentinel). At two runs a week the first rungs collapse: the ladder advances one rung per check and never skips a rung already in the past, so a post is re-fetched on each of its next three runs before the thirty-day rung means what it says; at this cadence that yields three refreshes in the first nine days, then one at about a month and one at a year, which serves the purpose, so the values stay. After a complete refetch, previously known comments missing from the tree are batch-checked with `info()` (Reddit drops leaf deleted comments from trees).
4. **Reconcile** (M1c) on every scheduled run: re-check every stored post and comment via `reddit.info(fullnames=[…])` at a hundred items per request, matching by fullname (order and omissions are not guaranteed). Estimated cost: roughly eight hundred requests at the four-month mark and about two and a half thousand at one year, under half an hour at PRAW's pacing. Against the shipped `budget.per_run_requests` (one pool for the whole run, the new posts and trees included) a full sweep fits until roughly month seven; from then the tiered fallback is expected unless the budget is raised, and purge latency moves to the tier bounds The budget stays until real numbers exist: the fallback is the design, and a sweep that no longer fits is D-30's revisit trigger. Reconcile re-checks first misses at the end of the same run (M1c, RC-03), so an item `info()` stopped returning is confirmed within one scheduled gap rather than two. The forty-eight-hour recommendation in Reddit's guidance is not met between scheduled runs; the removal obligation is met at the next run, and the bound is `reconcile.tier_max_age_hours` (KI-026). `reconcile.full_sweep_every_hours` is shorter than the gap between runs, so every run is a full sweep while it fits the budget; when it would not, the tiered fallback in `reconcile.tier_max_age_hours` applies and the digest says so. Apply the state machine and scrub.
5. **Tag themes** (M1d) for new and updated posts; re-tag all when a theme's `rules_hash` changed. Bot-authored items are flagged `author_is_bot` and excluded from theme matching and digest counts by default.
6. **Finish:** counters and `api_requests` on the run row; the post-run invariants (§ Silent-failure controls); `PRAGMA wal_checkpoint(TRUNCATE)`; a per-run online backup to `data/backups/<date>.db` (`db/backup.py::online_backup`, SQLite's backup API; M1c, landing with reconcile and the retention sweep in one change, so no copy ever exists without the rule that ages it out) taken *after* reconcile so it is already scrubbed (retention under § Release); the digest computed from the DB and served as a route (`/reports/{date}`), written to a file only on request, so no persisted copy can hold later-deleted text; a notification on failure; the dead-man ping on success (M1d). The run stamps `settings_fingerprint` so a changed budget or filter is visible in the digest; unknown upstream enum values are stored raw and counted, never coerced; a subreddit that recovers from an error has its status, counters, and gap flag cleared in the same run.

**Budget reality.** PRAW paces requests evenly over its ten-minute window, so a run's budget drains in a predictable time and the first backfill (roughly three thousand posts with trees) drains over a few scheduled runs or one interactive run at the hard cap. Exit codes: 0 ok, 1 failed, 3 partial, 4 rate-limited, 5 network, 75 locked, 78 config or auth, 130 cancelled.

**Search source (M3):** each enabled saved search runs `subreddit("all").search(query, sort="new", time_filter="week")` on each scheduled run; posts are stored with `post_sources.source_type='search'` and their trees collected like any other; the UI lists subreddits discovered via search with an **Add to monitored** button. Search is fuzzy and incomplete, so it supplements the sweeps rather than replacing them.

## Resilience to outages (automatic, no operator action)

The system has until its next scheduled run to succeed, so it pauses, retries, and resumes on its own: a connectivity and auth preflight before any paging; the outer retry ladder around every page, tree, and info batch on top of prawcore's short retries; a run that cannot reach Reddit at all exits `network`, writes nothing but its run row, and is retried at the next scheduled slot (a re-covered window costs nothing because the sweep is idempotent); a rate-limited run pauses for the `Retry-After` window in the same process, and if the window exceeds the wall-clock ceiling it exits `rate_limited` and the next run picks up where the watermark and revisit queue left off; the queue-based design means nothing is lost by a missed slot, only delayed; the freshness invariants say so in the digest when a source has not been fetched for two runs (up to a week at two runs a week, longer than the five-day `doctor` alarm, which is the coarser check by design); sleep and lid-close are handled by `caffeinate` and by the flock-means-alive rule. The scheduler's own staleness check (`doctor --alert-if-stale`) defaults to a threshold longer than the longest gap between scheduled runs, so it is quiet when healthy and red once a run is genuinely overdue (D-30, KI-024).

## Workspaces: expanding to other domains

**The design unit.** A workspace is a named set of sources (subreddits, saved searches), themes, digest settings, and a ranking rule. Posts and comments are shared data; sources and themes belong to a workspace; a post is visible in every workspace whose sources reach it (the `post_sources` join). Compliance, budgets, and the collector are workspace-agnostic: the deletion obligation attaches to the stored data, not the focus area, and the request budget is one pool reported per workspace. Revision 0001 carries the `workspaces` table and a `workspace_pk` on `subreddits`, `searches`, and `themes`, seeded with one workspace, so no migration is needed when a second domain arrives; in the UI the workspace is the top-level switch and a "lens" within a workspace isolates a chosen subset of themes.

**What is built and what is not.** The schema, the seed, a workspace section in the digest models, and a schema test for ownership are built. Every service resolves the default workspace and stops there; the `ranking` and `digest_settings_json` columns are written by the migration and read by nothing yet; no command creates a second workspace; no test runs two at once. A second workspace therefore costs a bounded amount of code, not just config: a workspace-add command, a run loop over enabled workspaces with the budget split and reported per workspace, and the two-workspace tests in the failure matrix.

**Direction (Wes, 2026-09-15).** Version one focuses on Premiere Pro only. Workspaces stay the designed option; the run loop and the switcher land when a second workspace is actually wanted, not before, so the first version keeps its focus. Running a second domain as a separate *instance* (its own data directory, on another machine or in another container) is an equally acceptable shape and needs no code at all; the only Reddit-side consideration is that instances sharing one client id share its rate limit. Both domains named so far (Premiere Pro; AI adoption among small and medium businesses) are personal interest with no business application, so every workspace sits on the same non-commercial footing.

**Leaving a domain.** If a focus is dropped entirely, the data goes one of two ways: the workspace path, archive (keep the rows, stop polling, hide) or delete through the destructive gate, which removes the workspace's sources, themes, and tags plus every post and comment reachable through no other workspace, recording the purge counts on the run row (M2); or the instance path, an export (M2) if anything is worth keeping and a fresh data directory with `db init` for the new focus, the old database file kept as an archive or deleted. Either is a short operation, because everything about a focus lives in one workspace or one file. Deleting the database discharges the deletion obligations that attached to its rows only once the retained backups and exports that hold them are gone too (D-31; the copies are the second surface). Sources can also be moved between workspaces without touching captured data.

**What a second domain should expect.** The volume assumptions (the listing cap, the budget, the cadence) were tuned for communities producing tens of posts a day. A very large subreddit produces more than the listing cap between runs at *any* cadence, daily included, so completeness is not available there and the design does not pretend it is: the sweep captures the newest posts up to the cap, the gap detection records `stop_reason='cap'` and the digest says so, and per-subreddit `comment_mode` bounds the tree cost. A diffuse topic therefore leans on saved searches (M3), which reach matching posts across all of Reddit, more than a product community does. Two levers are deliberately deferred until a second domain actually has its sources chosen, each with the trigger that adopts it (DECISIONS 2026-09-15): moving to a daily cadence, which is a configuration change (the two schedule entries, the staleness threshold, the reconcile threshold, the acceptance wording) because nothing in the collector assumes a cadence; and a per-workspace *ingest filter* that stores only posts matching the workspace's rules from a high-volume source, which shrinks both the storage and the compliance surface but changes the "sweep everything" assumption and so needs its own design round. Neither is built or needed for workspace one. And the system reports what people say, never who they are: the profiling limits above hold for every workspace.

**Lifecycle (decided 2026-09-13).** Archiving sets `archived_at`, hides the workspace from the switcher and the digest, and disables its sources; compliance reconcile keeps running over all stored items regardless of workspace. Deleting goes through the destructive gate (recorded verified backup plus a typed confirmation, with an export offered first). The curation migration at M2 adds `workspaces.archived_at`.

## CLI commands (automation, containers, tests, and break-glass; every command is a thin wrapper over a service function the UI also calls)

| Command | Purpose | State |
|---|---|---|
| `threaddigest run [--budget N] [--no-comments] [--dry-run] [--gateway fake]` | Steps 0–6 above; `--dry-run` fetches and writes nothing, not even a run row; `--no-comments` records a written reason on the run row (N-06) | built (posts; trees and later stages arrive with M1b–M1d) |
| `threaddigest doctor [--no-network] [--alert-if-stale 5d] [--json]` | Every check in `services/doctor.py` by name: config valid, the data directory writable and outside the folders launchd cannot read, credentials present, SQLite new enough for secure-delete, DB present and at head, quick integrity check, the fingerprint warning, free disk, no stale running rows, last successful run age against a threshold that defaults to longer than the schedule's longest gap, at least one collectable source, lock not stale, git hooks installed; the auth ping printing rate-limit headers arrives with tranche B | built |
| `threaddigest db init/upgrade/current` · `db downgrade/backup/restore/vacuum/check/reprocess` | Schema and files; `upgrade` backs up before any migration it actually runs | first three built; the rest M1c–M2 |
| `threaddigest config validate` · `config show/export/import` | DB-backed config with YAML round-trip | `validate` built |
| `threaddigest fetch [--sub X]` · `comments [--post ID] [--budget N]` · `revisit` · `reconcile [--older-than 30d]` · `tag [--all]` · `search-run` | Individual stages | M1b–M3 |
| `threaddigest report [--date]` | Regenerate the digest from the DB | M1d |
| `threaddigest export [--out] [--no-raw]` | Zip of a DB snapshot (backup API plus integrity check), live-content JSONL, config YAML without secrets, redacted settings, a manifest | M2 |
| `threaddigest subs add/remove/list/enable/disable` · `themes list/add-rule/test` | Source and theme management from the terminal | M2 |
| `threaddigest probe about r/<sub>` · `probe listing r/<sub>/new [--limit N]` · `probe tree <id> [--more-limit N]` · `probe info <fullname,...>` · `probe search "<q>"`, each with `--save-fixture <name>` | Dump raw JSON for a subreddit's about, a listing page, a tree, an `info()` batch, or a search (the ingest panel's sub-modes, adopted 2026-09-16); the probe day (runbook § 9) turns unverified Reddit behaviours into scrubbed fixtures before M1b | tranche B |
| `threaddigest serve [--port 8765]` | Web UI, bound to 127.0.0.1 | M2 |

## Web UI (FastAPI + Jinja2 + HTMX)

Old-Reddit density and Reddit's URL scheme so muscle memory works: `/r/{sub}`, `/r/{sub}/comments/{id}/{slug}`, `/u/{name}`, themes at `/t/{slug}`. Every post and comment has a `www.reddit.com` deep link opening in a new tab (comments use `/_/{comment_id}/?context=3`); replies are always written by hand on Reddit. The workspace is the top-level switch in the header once a second one exists.

**Design rules**

| Rule | Detail |
|---|---|
| Same URL, page or fragment | List routes return the full page normally and only the rows fragment when the `HX-Request` header is present (`hx-push-url` keeps URLs shareable); dedicated partial routes only for validate, preview, run panel, subtree, "more comments"; `Vary: HX-Request` on list routes |
| Comment tree | One query per post (flat rows), tree built in Python, rendered with a recursive Jinja loop so collapse is pure CSS plus a few lines of event-delegated script; depth cap 10 with "continue this thread"; long threads page by top-level comments with whole subtrees, about three hundred comments per page |
| Honest coverage | Post header shows "N comments on reddit (M captured)"; `comment_more` stubs render as "N replies not captured, view on reddit"; a per-post **Collect full tree** button spawns the CLI for that post; scores and counts labelled "as of <last fetch>" |
| Tombstones | Row still renders (children stay visible), author `[deleted]` unlinked, body `[deleted]`/`[removed]` by `content_state`, no reply link, never listed on author pages |
| Content safety | Only ingest-time sanitized `*_html` columns render unescaped; FTS snippets are built with control-character markers and HTML-escaped before `<mark>` insertion; `Content-Security-Policy: default-src 'self'` |
| Mutations | POST/DELETE via HTMX or plain forms (work without JS); validation errors return 422 with the re-rendered form; flash messages via out-of-band swap |
| Security | Bind `127.0.0.1` on the Mac; on the QNAP bind the LAN address with no password (D-20); middleware rejects state-changing requests unless `Sec-Fetch-Site` is same-origin, falling back to `Origin`/`Referer` on plain HTTP; `Host` is checked on every request, reads included, against DNS rebinding (UI D7); `THREADDIGEST_UI_PASSWORD` turns on basic auth; threat model in DECISIONS § 5 |
| Process model | Single worker; in-process job state for retag and export; fetching is always the CLI in a subprocess through an injectable `ProcessRunner` port; `serve` starts in **maintenance-only mode** (system, backups, health, setup) when migrations are pending or the fingerprint mismatches |
| Writes | One read-write engine behind a repository limited to the writer map (N-07); re-tagging runs as the CLI subprocess with a run row, in-process only for the read-only preview |
| Styling | One stylesheet with tokens (`--bg --fg --link --visited --muted --thread --new`), a 13px system font, light and dark via `prefers-color-scheme` plus a cookie override |
| Power view | Optional: `uvx datasette data/threaddigest.db`, read-only, for ad-hoc SQL (N-01, D-21); also the interim browser before M2 lands |
| Operator-first | Every routine operation has a UI control (the operator-complete gate walks the CLI command tree and requires a marked UI test per command, with the recorded exclusions); destructive ones show the gate state (the last verified backup, exactly what will be deleted or replaced) and require typing a confirmation word; the CLI mirrors the UI, never the reverse |

**Routes**

| Route | Page | Key interactions |
|---|---|---|
| `/` | Feed across monitored subs; sort new / comments / score; filters subreddit, theme, flair, author, date; `[NEW]` badge for items first seen in the latest completed run; sidebar with per-sub and per-theme new counts and last-run status | rows fragment paging |
| `/r/{sub}` | Subreddit feed and metadata (subscribers, last fetched, captured counts, monitored state, status badge) | same |
| `/t/{slug}` | Theme feed, rules summary, per-rule hit counts, matched rule per post | same, plus edit theme and re-tag now |
| `/r/{sub}/comments/{id}/{slug}` (`/p/{id}` redirects) | Post and nested comment tree; comment sort top / new / old | collapse, continue thread, load more, deep links |
| `/r/{sub}/comments/{id}/{slug}/{cid}` | Comment permalink: subtree rooted at `cid` with "show parent / full thread" | same |
| `/search` | FTS5 over posts and comments (tabs with counts), relevance or new, filters | input converted through a mini-grammar (`"phrase"`, `-word`, `word*`, `OR`), never passed raw to MATCH; advanced-syntax checkbox with a friendly error |
| `/u/{name}` | Everything captured from a username | sort, paging, open profile on reddit |
| `/settings/subreddits` | Add with debounced live validation via the API (one request; error kinds mapped to plain messages) and a preview card; per-sub comment mode; pause and resume; remove with **Stop, keep data** vs **Stop and delete captured data** | HTMX partials |
| `/settings/themes` | List and editor: rule groups, regex validated server-side, live preview "would tag N posts (M in the window)" with per-rule hits and highlighted sample titles using the same matcher as the CLI; Save re-tags and preserves existing match timestamps; stale badge when rules changed since the last tag | HTMX partials |
| `/settings/searches` (M3) | Saved Reddit-wide searches; discovered subreddits with **Add to monitored** | |
| `/settings/appearance` | light/dark/auto, reddit host, display timezone, page size | plain form |
| `/runs`, `/runs/{id}` | History with per-sub outcomes and warnings; **Run now** (full run, fetch only, reconcile only, re-tag only, saved searches only) spawns the same CLI launchd uses after inserting a `queued` row; 409 while a run is active; the panel polls `/runs/current` every two seconds and stops when idle; a heartbeat every five seconds enables stale-run detection; Cancel sets a cancel-requested stamp on the run row, which the CLI polls at batch boundaries (the column arrives with the curation migration at M2; UI D5), with SIGTERM as a local extra; errors mapped to plain text with the log below | HTMX polling |
| `/export` | Builds the export zip in a background thread with progress; keeps the last few; refuses when free disk is short | HTMX polling, then download |
| `/setup` | First-run wizard: paste Reddit app credentials (stored in `.env` with owner-only permissions, never displayed again), **Test connection**, choose subreddits, first sweep with live progress; loopback-only unless a password is set | plain forms + polling |
| `/system` | Every `doctor` check as a row with **Run checks** (no-network by default, a checkbox for the auth ping); version, paths, disk, scheduler status, migration state with **Apply pending migration** (automatic backup first), last backup, **Send test notification** | HTMX partials |
| `/system/backups` | Backups with size, date, and integrity result; **Create backup now**; **Restore** behind the destructive gate | HTMX partials |
| `/system/maintenance` | Reconcile now, re-tag all, reprocess from raw, import a config YAML or an export archive (from a server-side path), recent logs | HTMX polling |
| `/healthz` | JSON: status, version, DB state, last run summary, run in progress, lock held, disk free, credentials present | the header status pill polls it |

**Curation controls (decided 2026-09-13).** Beyond adding and removing sources and themes, the UI carries the hand-curation Wes expects to do over months: a manual tag override on any post (a post-theme row records its origin, `rule` or `manual`, and re-tagging never removes a manual tag); a **watch** control that pins a thread so the ladder keeps refreshing it past its last stage (a watch-until stamp on the post, M2); one-click promotion of a rising phrase into a theme rule; theme rename and merge (merging re-points `post_themes` rows and records the change); an ad-hoc **Search Reddit** box that runs one API search and offers "monitor this subreddit" or "collect this thread" per result; and a per-post thumbs up or down on each theme tag, recorded as operator feedback ("k of n judged"), an operating signal and never the grade: the word *precision* is reserved for the M3 blind packet. Manual tags need a nullable rule key, and which curation records survive a failed restore or reset is decided at M2 (workflow seat, 2026-09-14).

## Testing strategy

**Principle:** the collector never touches the network in tests (`--block-network`). `RedditGateway`, `Clock`, `Notifier`, and `ProcessRunner` are Protocols speaking plain values; `PrawGateway` is the only adapter doing HTTP. `FakeRedditGateway` is a scenario builder (`add_post`, `add_comment`, `add_more`, `delete`, `remove`, `vanish`, `delete_account`, `fail_page`, `rate_limit_next`, `set_status`) that records every call, ships in `src/` so `threaddigest run --gateway fake` works for demos, and drives the whole failure matrix; its known fidelity limits (a single large `more` subtree is revealed in one request, KI-023) are validated against the real adapter on the probe day. Tests control time through the injected `Clock` and never sleep. The spec-level detail (every test id with its layer, phase, and status) is `docs/TEST_STRATEGY.md`, gated so that every cited test exists.

| Layer | What | Tools |
|---|---|---|
| Unit (`core/`) | normalize, the deletion state machine, paging, the ladder, budget, theme rules including the regex timeout, the digest golden file, UA format | pytest, hypothesis |
| Collector e2e | Full `run` against the fake and a temp DB created by `alembic upgrade head`: idempotent rerun, counters and `run_subreddits`, ladder and reconcile transitions, the **compliance canary** (ingest a unique phrase, delete it in the fake, reconcile, scan the DB, the index bytes, and a fresh export) | pytest, tmp_path, time-machine |
| Adapter | Failure paths with `responses` asserting exact request counts, built and green; happy paths from recorded cassettes (`--record-mode=none`, auth headers and tokens filtered by the `vcr_config` fixture, which ships before the first cassette) and a contract suite running the same cases against the fake and PRAW so the fake stays honest, both after the probe day | pytest-recording, responses |
| Migrations | pytest-alembic built-ins plus upgrade-from-fixture per prior revision, FTS works after upgrade, integrity ok, pre-migration backup created; the migration checklist (sequence re-stamped, triggers present, FTS integrity) lands before the next migration on posts or comments (KI-014) | pytest-alembic |
| Web (M2) | TestClient per route with a seeded DB and DOM assertions; tombstones, deep links, escaping, fragment versus page, CRUD round-trips, Run now, cross-site rejection, export integrity, FTS sanitizer under adversarial input | TestClient, selectolax, hypothesis |
| Workflow | Cross-stage scenarios through one fake corpus (sweep → trees → revisit → reconcile → tag → digest → backup) and the operator workflows (setup → first sweep; theme edit → retag; backup → restore drill; pending migration → apply; export → import), asserting end state, counters, and the delivered artifacts | pytest, fake gateway, temp data dir |
| Deploy | The schedule and staleness contract read from the plist and the wrapper on every platform; the launchd artefacts exercised on the Mac | plistlib; `plutil`, `launchctl` (macOS-only, deselected on Linux) |
| Gates | Every guard's positive control (`tests/gates/`), see `docs/THREADDIGEST_HARNESS.md` | pytest `gate` marker |
| Live smoke (opt-in) | `pytest -m live`: auth ping, a handful of posts, rate-limit headers present; never in CI | real PRAW |
| Sweeps in production | Post-run invariants after every run; per-source freshness in the digest; hourly `doctor`; the dead-man ping from M1d; the compliance reconcile on every scheduled run; the restore drill on the runbook's cadence; the quarterly guard review | launchd and the runbook |

**Failure-mode matrix (each row is a test once its stage lands; a row naming a milestone is planned):**

| Failure | Expected behaviour | Simulation |
|---|---|---|
| 429 with `Retry-After` | Sleep the bounded wait via the injected clock, retry once; a second 429 → run `rate_limited`, nothing half-written | `responses` 429×2; fake `rate_limit_next` |
| 401 at the token endpoint | `AuthFailed` before any listing request; no `running` row left; exit 78; notification | `responses` 401 |
| 401 `invalid_token` mid-run | prawcore refreshes and retries transparently | `responses` sequence |
| 403 private subreddit | `status=forbidden`, `consecutive_failures+1`; others continue; run `partial`; data retained; `doctor` counts the source as uncollectable (KI-017) | `responses` 403; fake `set_status` |
| 404 banned subreddit | `status=not_found`; alert; content handled per the banned-sub policy | `responses` 404 |
| Nonexistent subreddit | `Redirect` → `status=redirect`; auto-disabled after three runs, loudly | `responses` 302 |
| Casing or identity change | Two spellings normalize to one row; a differing `t5_` id aborts that sub loudly | about fixtures |
| 5xx or timeout mid-page | prawcore retries, then the outer ladder via the fake clock; persistent → that sub fails, committed pages stay, watermark untouched | `responses` 503 sequences; fake `fail_page` |
| Crash between pages | Rerun → no duplicates, no gaps, `first_seen_at` unchanged | fake raises after page 2; run twice |
| Crash mid comment-tree | Nothing committed for that post; still due; rerun completes | fake raises after N comments |
| Overlapping run | Second process exits 75 with zero API calls and a `skipped_locked` row | hold the flock; invoke the CLI |
| DB locked by another writer | Retries within `busy_timeout`, then fails cleanly | second connection holds `BEGIN IMMEDIATE` |
| Stale `running` row | Marked `crashed` on next start; the new run proceeds | old heartbeat |
| Malformed or missing fields | Optional → NULL; required missing → `raw_rejects`, run continues | fixtures + hypothesis |
| Deleted or removed content | State transitions; content columns null; `raw_json` tombstone; index entry and bytes gone; `post_themes` gone; canary absent everywhere | fake `delete()`/`remove()` + reconcile |
| Account deletion | Author fields nulled everywhere, `authors` row deleted, content kept | fake `delete_account` |
| Missing from `info()` | `gone_unconfirmed`, `misses=1`, content kept; second omission → scrub; a bodyless return holds without a miss | fake omits the id |
| Config validation errors | Exit 78 before any API call | CliRunner + fake; zero calls |
| DB missing or behind head | Refuse with instructions | bad path; downgraded temp DB |
| Disk write failure (backup or export) | Aborted, no partial file, run `failed`, notification | read-only dir / `ENOSPC` |
| Clock skew | Identical stop, gap and state decisions and identical stored `next_check_at` values (all logic in the `created_utc` domain); the due set moves with the local clock, as it must (ingest D-2) | injected clock (M1c, RV-02) |
| Empty subreddit or zero new | Run `ok`, `stop_reason=exhausted`, watermark unchanged | fake with no posts |
| Cloudflare HTML 403 | Abort the run (not per-sub), alert, no tight retry loop | `responses` 403 text/html |
| Overlapping listing pages | Upsert dedupes; counts correct | fake overlapping pages |
| Quarantined subreddit | `status=quarantined`, disabled with alert | fixture 403 JSON |
| Budget exhausted mid-run | Tree collection stops at the reserve; posts still captured; the queue drains next run | fake reports low remaining |
| Listing cap hit before known territory | `gap_suspected_at` set and `stop_reason='cap'` recorded, never `exhausted` | fake with more than a thousand newer posts |
| Column silently all NULL | Population-floor invariant closes the run `partial` (a warning) and names the column | the field nested elsewhere |
| A gate gone inert | Its positive control fails | remove the precondition and assert red |
| Source freshness | Per-source freshness is a warning: the run closes `partial` and the digest names the source | one sub fails quietly across two runs |
| Test suite pointed at the real data dir | Settings refuse to start | unset the opt-in variable |
| Repeated reruns churn primary keys | PK-stability gate fails (`tests/gates/test_pk_stability.py`) | run three times and compare |
| Same post normalizes differently via two paths | Shape-parity test fails | probe fixture both ways |
| Subreddit recovers after an error | Status, counters, `last_error`, and the gap flag cleared after a complete sweep | fail twice, then succeed |
| Dry run or no-network mode touches the network or the DB | Zero HTTP calls, zero DB writes | fake with no routes; DB opened read-only |
| Restore fails after the live file is gone | The live file is copied aside before anything is deleted and put back on failure (KI-015) | fail the rename |
| A crosspost parent's text survives ingest | The parent is reduced to `{id, subreddit}` whatever shape it arrives in (KI-016) | mapping and non-mapping parent entries |
| Deleting a workspace removes data another still reaches | Only rows with no remaining source go; shared posts kept; purge recorded | two workspaces share a subreddit; delete one |
| Re-tagging removes a manual tag | Manual origins survive every retag | change the rule; retag |
| A watched thread falls off the ladder | `watch_until` keeps it due until it expires | old post with a future watch |

Gates: `make check` = ruff, mypy strict, import-linter, pytest with the network blocked and warnings as errors, coverage against the floor in `.ratchets/coverage.txt`, code health, the ratchet compare, the hooks line, the memory audit, and the green stamp. Optional but recommended: a personal restricted test subreddit seeded by hand with the fixture cases (a normal post, a self-deleted post, a mod-removed post, a deleted comment with children, a leaf deleted comment, a deep chain, a crosspost), so cassettes contain no third-party content.

## Robustness, enforcement and portability

The failure pattern in AI-assisted projects is rarely the first build; it is drift afterwards: tests quietly weakened, exceptions swallowed, schema edited without a migration, "passes locally" claims never checked. The controls below are mechanical; the first set went in at M0 before any feature code, the rest as their birth incidents arrived, some are still ahead of the code they guard (marked by milestone), and all are inventoried on `docs/THREADDIGEST_HARNESS.md`, whose generated block is gated (G54). Every guard has a ledger row in `docs/runbook/GUARDS.md` with its birth incident, mechanism, positive control, and verdict.

### Guard design rules (carried over from Wes's earlier database project)

Source: `WHY_THE_GUARDS_EXIST.md` in `docs/reference/earlier-project-retrospectives/` (kept, redacted), where an audit found that half the guards had never fired, that many gates could not fail, and that grandfathered suppressions had become a permanent exemption. Every gate in this plan must satisfy these rules.

| Rule | What it means here |
|---|---|
| Scan a structural shape, never police a hand-maintained list | Ratchets count what a tool finds in the whole tree (ruff, import-linter, pytest collection, marker counts), never entries in a registry the same person curates |
| Key on the invariant, not a proxy | Post-run checks query the real thing through the same connection path the app uses (index rows versus live rows, rows stamped with the current version), never a config flag, a docstring, or a file's existence |
| A gate that cannot fail is not a gate | Every gate, ratchet, and invariant ships with a **positive control** in `tests/gates/`: construct the bad state and assert the gate goes red. A gate never seen failing is a hypothesis |
| Structural markers, not comment proximity | Justifications live in syntax (`reason="#123 …"` arguments, decorators, rule codes), never "a comment within N lines" (N-05) |
| Assert on the delivery surface | UI and digest tests assert on rendered output; a field with two guards is single-sourced so the guards cannot disagree |
| Fail, never skip, inside the required gate | Missing preconditions fail; the only skips allowed are the explicitly opt-in live tests; the gate is verified by running it the way CI runs it |
| Zero-suppression baseline | The skip ratchet starts at zero and stays there; the suppression ratchet started at the counts in `.ratchets/suppressions.txt` with a rule code on every entry, and those grandfathered entries are a backlog to clear or to re-approve with an expiry date at the quarterly guard review, never a permanent exemption; every exception is printed on every run |
| Probe each item the way a real record presents it | Input shape is part of the contract: fixtures come through `probe`, tombstones through the real scrub stage (M1c), bot rows through the real normalizer, never a hand-typed shape |
| A positive control sits inside the guard's own scope fence | The control plants the bad state in the population the guard scans, so a dead scope path (a clean count over files never opened) is red too |
| Hold the count | A new guard is added only for a recurring class, after checking whether an existing guard can be widened; the ledger records each guard's birth incident, positive control, and what it has caught since, reviewed quarterly |
| Derive state, never narrate it | The Runs page, the digest, the `make check` summary, the status page, and the harness inventory are computed from the DB and tool output, never from a claim in a message or a hand-typed count |
| Show the denominator | Every count in the UI or digest carries its population; each metric is one function with a golden test, shared by UI, digest, and export |

### TDD policy by layer

| Layer | Approach |
|---|---|
| `core/` | Strict TDD: red test → green → refactor. Every failure-matrix row is a failing test before the service code exists |
| `services/` | TDD against `FakeRedditGateway` and a temp DB created by `alembic upgrade head` |
| `adapters/reddit_praw.py` | Probe-first for every wire shape: `probe` captures the real payload → scrubbed fixture or cassette → characterization test → adapter code. Reddit's behaviour is observed, never assumed; one credentialed probe day precedes M1b. The offline half landed first because it needs no capture: the exception translation and the request counting are read from the installed library and driven with `responses` |
| `db/migrations/` | Test-first: add the fixture DB of the previous revision and the expected `schema.sql` snapshot, then write the migration until both pass |
| `web/` | Test-with: the route test with DOM assertions is written alongside the template; Playwright smoke after each page lands |
| Bug fixes | A failing test that reproduces the bug, a `KNOWN_ISSUES.md` row citing it, the strongest enforcer that fits, mirrors swept, proof pasted (the `harden` skill) |

### Gates and ratchets

The shipped set, each with a ledger row; the M0 menu that the adversarial review cut down is history (DECISIONS § 3 and the 2026-09-13 entries).

| Gate or ratchet | Where | Enforces | Fails how |
|---|---|---|---|
| pre-commit | every commit | ruff format and lint, dmypy on the whole `src` tree, gitleaks, no files over 1 MB, no commits on `main` | commit blocked |
| `make check` | before every merge, and in CI once a remote exists | full pytest with the network blocked and warnings as errors, coverage against the floor, mypy strict, ruff, import-linter, the schema snapshot, pytest-alembic, code health, the three-way ratchet compare, the memory audit; its last step stamps the tree it passed | non-zero exit with the pasted summary |
| Hard-block hooks | Claude Code `PreToolUse`, inventoried on the harness page | no `--no-verify`, no push to `main`, no merge into `main` of a tree without the green stamp (fast-forward only, `main` an ancestor); no hand edits to `.ratchets/`, the hook scripts, or the hook settings; read-before-touch log-first until its ledger review; self-protecting, failing closed on internal error; continuations joined, comments and redirections stripped, indirection resolved; mistake prevention, not a security boundary (G23) | tool call blocked |
| Coverage ratchet | `.ratchets/coverage.txt` | coverage may not drop; bumped by `make ratchet-bump` when it rises | red showing old versus new |
| Skip, suppression, assert-count, and collected-test floors | `.ratchets/skips.txt`, `suppressions.txt`, `tests.txt` | counts move one way; every skip or suppression carries a reason or rule code; a loosening pauses for approval and lands a ledger row (N-09 cut the test count as a *gate*; the assert-count and collected-test floors remain under the loosening protocol, a contradiction recorded in DECISIONS) | red |
| Code-health ratchets | `.ratchets/code_health.txt`, measured by `tools/code_health.py` | function and module maintainability, size rules, dead code, and duplication counts may not rise; birth relaxations carry expiry dates that `bump` clears at zero (G51) | red (loosening → approval; expiry → red) |
| Review-only ceiling | `.ratchets/review_only_rules.txt` | the number of rules with no mechanical enforcer, and of active guards without a positive control, only goes down (G39) | red |
| import-linter | `make check` | the layering contracts, `praw` confined to the adapter, `web` never importing `cli` (G04, G05) | red naming the illegal import |
| Network block | pytest config | any test that touches the network errors (G06) | test error |
| Schema snapshot; models == DDL | `db/schema.sql` golden; pytest-alembic | `alembic upgrade head` on an empty DB reproduces the committed snapshot; models match the migrated schema (G15, G16) | test fails with the diff |
| Runtime schema fingerprint | `doctor`, `/system` | a warning only, ordinary tables, derived by one normalizer (N-13) | warning |
| Post-run invariants | end of every run | § Silent-failure controls, proven through `threaddigest run` with the fake planting each violation (G30) | a failure closes the run `failed` with a notification; a warning closes it `partial`, seen in the digest line (§ Silent-failure controls names which is which) |
| Dead-man ping | end of each successful run, from M1d | a run that never happens is noticed by an external service; the launchd hourly `doctor` remains for the UI health rows (N-12) | notification |
| `DATA_DIR` isolation | autouse fixture, `settings.py`, and the subprocess seam | tests always run against a temp data dir; settings refuse the default dir under pytest; the CLI refuses to start under pytest without `--gateway fake` (G19) | test error |
| Connection chokepoint | import-linter, ruff `TID251`, a behavioural pragma test | only `db.engine` creates engines; a connection through the public path proves WAL, foreign keys, and secure delete (G31); scrub is one function whose test asserts the row, the index, and `post_themes` changed in the same call (M1c) | red |
| Destructive-operation gate | CLI and UI (M1c–M2) | restore, downgrade, reprocess, delete-data, container init, and the retention sweep require a recorded verified backup plus the typed confirmation, checked inside the service | refuses, exit 78 |
| No bypass flags | design rule with tests (N-06) | no flag skips reconcile or scrub; the budget is hard-capped; a bypass flag records a written reason; a dry run makes zero writes | test fails |
| Documentation gates | `tests/gates/` | router ↔ tree (G33); retired claims not stated as live (G34); no imported identifiers (G35); rules name an existing enforcer (G39); register node ids and cited hashes resolve, every gate file has a ledger row (G40); routing pointers resolve (G44); the status-page contract (G45); the memory snapshot never behind live (G47); the review register (G50); the packet from the committed tree only (G52); the harness inventory derived from the tree (G54) | red |
| Dependency pins | `tests/gates/test_dependency_pins.py` | a pin that carries a behavioural contract keeps its bound (G53) | red |
| Schedule contract | `tests/deploy/` | the plist schedule, the staleness threshold, and the doctor default agree with D-30 on every platform | red |
| Portability job | CI weekly and on quickstart changes, once a remote exists | fresh Ubuntu container: clone, `make setup`, `make check` | red |
| Restore drill | the runbook's cadence | the latest backup restores to a temp path and `doctor` passes | manual, logged |

### Silent-failure controls

- **Exception policy:** ruff `E722`, `BLE001`, `S110`, `S112`, `B904`, `TRY*`; catch specific exceptions only; every handler re-raises or records a warning on the run row. A run with any warning is `partial`, shown amber; `ok` means zero warnings. Exception text never reaches an error column with content in it (KI-010).
- **Warnings are errors in tests** (`-W error`), so PRAW and SQLAlchemy deprecations surface immediately.
- **Post-run invariants** (each is planted through `threaddigest run --gateway fake` by its positive control, G30). Severity, not the list, decides the status (`services/invariants.py`, read by `services.runs.resolve_status`): a failure flips the run to `failed` with a notification; a warning closes it `partial`, amber on the pill and named in the digest line, with no notification, because alerting on amber would train the operator to ignore the alert. Built as failures: run counters equal table deltas; no `running` rows other than the current one; index membership equals the live rows by content, not by count alone (KI-022; a failure, because an index that holds what the store does not is a compliance surface). Built as warnings: every row written this run carries the current `normalizer_version`; unknown upstream enum values are counted, never coerced; **population floors** per column over the recent live rows (`author_fullname` on live rows with a known author, `selftext_html` on every self post, `permalink` on every row), which catch the "column all NULL while every gate passes" failure; **per-source freshness**: every enabled source, plus every source disabled by an error status (ingest B8), fetched successfully within the last two sweeping runs (up to a week at two runs a week), checked separately from run status. A run in which every source succeeds and nothing is new is plain `ok`. No clock promotes a warning to a failure; the M1c compliance bound ships as a failure for the same reason, and the floors, freshness, the normalizer stamp and the enum count stay warnings; the rulings are in the decisions log under 2026-09-16. Planned with their stages: `comments_captured` equals the actual count per fetched post and `authors` counts equal `COUNT(*)` over live rows (M1b); live rows have all required columns and scrubbed rows have none of the content columns, row counts never decrease except through a recorded purge, and the last complete reconcile is within the per-tier bound in `config/settings.yaml` at the end of each run, so compliance cannot lapse quietly (M1c; the bound is tied to the schedule by test, KI-026); every post has at least one `post_sources` row (M3, when a second source type exists). A new invariant ships scoped to rows at or above the `normalizer_version` that satisfies it, so it cannot turn every run red on day one.
- **Coverage counters** on the run row and in the digest, each with its denominator: the share of self posts with `selftext_html`, of comments with `author_fullname`, of due posts collected, of posts tagged, plus `raw_rejects` and `unknown_enum_values`; the structural floors above are the gate, and the trailing-median alarm on these counters is deferred to M3 after a baseline exists.
- **Structured logs** per run (JSON lines; M1d, the counts on the run row and in the digest arriving with them; today the only per-run log is the launchd wrapper's plain-text file); the launchd wrapper maps the exit code to an operator action and notifies on failure and never on `partial`: an amber run is read in the digest line and on the Runs page, and alerting on it would train the operator to ignore the alert; the wrapper is aligned with the code.
- **Typed boundaries** validated once: pydantic at the normalize boundary, `Protocol`s at the gateway boundary, mypy strict inside.
- **No mocking of internals:** `unittest.mock.patch` is banned outside `tests/adapters/` (N-17); behaviour is tested through the fake gateway and real temp DBs.
- **Cross-platform and environment controls:** Linux is the primary CI matrix once a remote exists, the Docker build the second; `encoding="utf-8"` on every text open (ruff `PLW1514`); `os.replace` over `os.rename`; no platform-hostile characters in generated file names; `fcntl` imported only inside the lock module; settings read at call time and never captured at import; the settings model uses `extra="forbid"`.
- **Two-gate discipline for semantics:** a refactor keeps the reprocess golden byte-identical; a semantic change to an existing column is a separate change with a `normalizer_version` bump and updated golden rows. Field names are contracts: `num_comments` is Reddit's count including deleted items and is never used in an invariant; `more_skipped_reason` keeps one label from covering three causes; theme previews show each rule's hit rate as a share of all captured posts, so a keyword that tags most of everything is visibly non-diagnostic.
- **Alerts:** the UI status pill computed from `runs` is the canonical alert surface; notifications are best-effort; `notify --test` is a manual check from `/system`.

### Known AI-assisted-development failure patterns → control

| Pattern | Control |
|---|---|
| Assertion loosened or test deleted to get green | tests changed in a PR are listed in the PR body with a reason each; the assert-count and collected-test floors (kept under the loosening protocol although N-09 cut the count as a gate); the working-agreement rule; Wes spot-checks PR bodies |
| Tests skipped or xfailed to unblock | skip ratchet with an issue reference; `xfail_strict` |
| Mocks that mock the thing under test | fake gateway plus the contract suite; `mock.patch` banned outside adapter tests |
| Broad `except … pass` hiding failures | lint rules, the exception policy, `partial` status |
| Hallucinated library APIs or fields | probe-first for the adapter; the contract suite; `-W error`; the pinned major |
| Model edited without a migration | models == DDL; the schema snapshot; the runtime fingerprint warning |
| "Works on my machine" | `uv.lock`, `.python-version`, the Docker image, the portability job, `doctor` |
| Time-dependent flaky tests | injected `Clock`; no `sleep` in tests (gated) |
| Partial run reported as success | invariants; counters reconciled; `ok` requires zero warnings |
| "Tests pass" claimed on a subset | the pasted `make check` block is the authority; the collected-test floor (under the loosening protocol, N-09); the green stamp names the tree |
| Over-abstraction | four layers only; no new abstraction without two concrete uses (N-20) |
| Docs drift | the documentation gates above; the README quickstart executed by the portability job |
| A hook present but never installed, or a script never registered | `doctor` and the hooks line of `make check`; the settings test requires every hook script to be registered |

### Working agreement

`CLAUDE.md` in the repo applies to any agent or human: the irreversible four at the top, the rules table with an enforcer per row, the routing table, the PR protocol, the agent model tiers, and the practices carried from the earlier project. The plan does not repeat it.

### Workflows, cadence and verification points

| Workflow | Frequency | Verification points |
|---|---|---|
| Scheduled run | Monday and Thursday 06:30, automated (D-30) | lock → pre-run checks → per-page and per-tree transactions → reconcile → backup → post-run invariants → digest → notification on failure; the dead-man ping if it never happens (M1d) |
| Staleness check | hourly `doctor` under launchd | last-run age against a threshold longer than the longest scheduled gap; the UI health rows |
| Config change (subreddit, theme, search) | ad hoc, via the UI | validation before save; live preview; retag; `config export` committed so config history is in git |
| Code change | many per week in M1–M2, monthly afterwards | failing test first → pre-commit → `make check` stamps the tree → fast-forward into `main` → `make deploy` (M1d; pull, `uv sync --frozen`, `db upgrade`, restart) → post-deploy `doctor` |
| Schema migration | several in M1, rare afterwards | the code-change path plus the previous-revision fixture DB, the snapshot, pytest-alembic, the pre-migration backup, `foreign_key_check` |
| Dependency bump | monthly | lockfile update; cassette and contract tests as the gate; a PRAW bump also runs the live smoke by hand and, for a major, replays the adapter fixtures |
| Compliance reconcile | every scheduled run; the canary test on every change | scrub counts on the run row; the canary absent from the DB, the index bytes, backups within retention, and the export |
| Restore drill | quarterly, or the automated weekly variant if adopted (runbook § 5) | restore the latest backup to a temp path; `doctor` passes; counts compared |
| Guard review | quarterly | the ledger's verdicts and firings; the read-before-touch ledger on 2026-09-28; suppression review dates |

### Portability targets

- **Fresh machine in under ten minutes:** `git clone` → `make setup` → edit `.env` → `threaddigest doctor` → `make run`. For a non-developer: `docker compose up` (M4), then the `/setup` wizard; no terminal after that.
- **12-factor config:** every setting via `THREADDIGEST_*` variables with `settings.yaml` defaults; `DATA_DIR` relocatable; no hardcoded paths; the display timezone configurable (an IANA name, `UTC` shipped, validated at load, KI-011); the `Notifier` chosen by config so Linux and the QNAP work without macOS assumptions.
- **The Docker image is the portable artifact** (multi-arch); a compose file (M4) with an `env_file`.
- **Move data:** `export` on the old machine, `import` on the new one (restores the DB and config, runs `db upgrade`).
- **Each person registers their own Reddit app**; secrets are never shared or exported.
- **The working agreement, the runbook, and the harness page** so a coworker, or a coworker's agent, inherits the same rules, deploy steps, and drills.

### QNAP as a service host (M4)

Container Station runs the same compose file: a `collector` service (supercronic schedule) and a `web` service sharing one local-volume `data/` directory. WAL allows the web service and later analysis workers to read while the collector writes; any future writer coordinates through the `runs` table and the same flock rather than a message broker. The data directory must be on a local volume, never a network share. The M5 analysis worker is a third service on the same compose file reading the DB and writing its own tables.

## Release, upgrade and migration practices

- **Schema:** every change is an Alembic migration (`render_as_batch=True`, a naming convention so batch operations can drop constraints by name), reversible, never edited after being applied; FTS virtual tables and triggers created with `IF NOT EXISTS`; `include_object` excludes the index shadow tables and the live views from autogenerate; foreign keys off during batch migrations; expand and contract for column changes (add nullable → write both → backfill from `raw_json` → switch reads → drop later); never rename in place. SQLite batch mode recreates the table, which drops FTS triggers and orphans external-content rows, so any batch operation on `posts` or `comments` recreates the triggers and rebuilds the index in the same migration, passes `sqlite_autoincrement` and re-stamps the sequence so a purged top key is never reused (KI-014, open until the migration-checklist tests land), the per-revision fixture test asserts index membership equals live rows after upgrade, and Alembic runs one transaction per migration.
- **Safety:** `db upgrade` takes an online backup before any migration it actually runs (nothing pending, no copy), runs `quick_check` on the copy, migrates, then `integrity_check` and `foreign_key_check`; on failure it restores the copy and exits non-zero. `db restore` copies the live file aside before it deletes anything and puts it back on failure (KI-015), swapping atomically under the lock.
- **Backups and retention (decided 2026-09-15, on the round-one ruling; none of it built yet).** The database is the long-term archive; backups are disaster-recovery copies, never a second archive. Decided: one online-backup copy per scheduled run, taken after reconcile so it is already scrubbed; the two most recent post-reconcile copies kept plus the off-machine copy once the NAS remote exists (MB), and the last few pre-migration copies; a retention sweep that prunes by age under `retention.backups_days` in `config/settings.yaml`; a compliance canary that asserts file ages. Built today: only the pre-migration copy `db upgrade` takes before a migration it actually runs, pruned by count, not age, and the configured bound is read by nothing. The per-run copy lands with reconcile at M1c in the same change as the retention sweep, so no copy ever exists without the rule that ages it out; the canary is an M1d blocker. Nothing rewrites a backup: a copy made before a scrub holds the text until it is pruned, which is why the keep count is small and why the copies and exports must go with a workspace's data when that data is deleted.
- **Connections:** on every connection `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, a `busy_timeout`, `temp_store=MEMORY`, `secure_delete=ON`; `wal_checkpoint(TRUNCATE)` at the end of a run (retried three times; when a reader still holds the log the run records a `wal_checkpoint_busy` warning and the pages written this run, scrubbed or not, stay in the write-ahead log until a later checkpoint, KI-013); a minimum SQLite version for the FTS5 secure-delete format, checked by `doctor`. The DB lives on a local filesystem, never a network share.
- **Reprocessing:** `normalizer_version` on rows plus `raw_json` mean derived columns can be rebuilt; a test asserts a full reprocess reproduces identical rows (planned with the `reprocess` command, DB-47 and PA-02).
- **Versioning:** single source in `pyproject.toml`; `__version__` via `importlib.metadata`; the user-agent built from it (`python:io.github.whowellgit.threaddigest:v<version> (by /u/<user>)`); stamped on `runs`; SemVer; git tags; `uv.lock` committed, `uv sync --frozen` in Docker. No changelog ceremony beyond the version string unless N-19 is ruled otherwise.
- **Startup checks:** `run` and `serve` refuse if migrations are pending; `/healthz` and `doctor` expose version, migration state, and last-run age.
- **Containers (M4):** the entrypoint verifies the volume holds the DB (or an explicit init flag), runs `db upgrade` with its backup, then `exec supercronic`; migrations and runs share the flock; the image is tagged with the version; roll back is the previous tag plus a restored backup; never auto-downgrade.

## Deployment path

| Stage | Where | How |
|---|---|---|
| Now (M0–M3) | This Mac | `uv run threaddigest serve` on 127.0.0.1 (M2); launchd runs `run` Monday and Thursday at 06:30 and `doctor --alert-if-stale 5d` hourly at :15 (D-30); a missed job runs on wake. Logs in `data/logs/`. On failure the wrapper posts a macOS notification and the UI shows the red pill. The wrapper invokes the project's virtualenv interpreter by absolute path (never `python3`), refuses to run from a folder launchd cannot read, loads `.env` without printing values, and wraps the job in `caffeinate -i` so a closed lid cannot strand a run. Scheduled jobs run only inside a logged-in session: after a reboot the collector idles until login, the dead-man ping is the detector, and the install notes say to enable automatic login or accept the pause (ruling 2026-09-14). **Location constraint:** launchd is silently denied access to `~/Desktop`, `~/Documents`, `~/Downloads`, and `/Volumes/*`; the repo and `DATA_DIR` live at `~/repos/insightminer` and `doctor` checks the path |
| MB (when the new QNAP arrives) | QNAP over SSH | A bare repository reached over SSH, every push gated by the pre-push `make check`; a nightly `git bundle` as the second copy; data-directory backups to the NAS on the run schedule; GitHub added later only when CI is wanted. Until then: local only, bundles to the archive folder and to the external drive when mounted |
| M4 | Docker on the Mac → QNAP Container Station | `python:3.13-slim` + `uv sync --frozen --no-dev`; `compose.yaml` with a local volume, `env_file` for secrets, the supercronic schedule, `HEALTHCHECK` via `doctor --no-network`. Same image on the QNAP; home IP preserved; the login-session question is moot in a container |
| Optional, lowest priority | Remote access | Tailscale to the QNAP UI rather than moving the fetcher to a VPS (N-02) |

## Milestones

Built-versus-planned is stated on `docs/recent/STATUS.md`, not here.

| # | Milestone | Definition of done | Tests that must pass |
|---|---|---|---|
| **D0** | Design lock-down | Walked 2026-09-13 and recorded (DECISIONS § 1, § 6), except two sections left open in the walk (the UI routes, which Wes was reviewing, and the milestone sequencing); both were overtaken by the UI panel's specifications and by the milestones as executed, without a formal close | — |
| **M0** | Setup and enforcement scaffolding | Done 2026-09-13: the repo, `uv`, the working agreement, pre-commit, the ratchet files, import-linter, mypy strict, the network block, the schema snapshot, the guards ledger with positive controls, `make setup/check/run`; the enforcement tranche and the hooks followed (DECISIONS 2026-09-13 night, 2026-09-14) | the gate set |
| **M1a** | Posts ingestion | Tranche A done 2026-09-13: revision 0001 and 0002, the repository with the field-ownership table, lock and run lifecycle, sweep, post-run invariants, `doctor`, migration commands, the `run` command, proven end to end against the fake. **Tranche B**: the real adapter and `probe`, after credentials and the API access approval; one credentialed probe day capturing the shapes the deletion predicates and the fake assume | collector e2e; pytest-alembic; the contract suite against PRAW |
| **M1b** | Comment trees and budget | Newest-first queue drains within budget; `comments_complete` and `comment_more` accounting; one transaction per tree; the first full backfill completed over a few runs | fixtures with `more` and continue-thread nodes; crash mid-tree; budget exhaustion |
| **M1c** | Revisit, reconcile, scrub | The ladder; the state machine; `info()` misses; author scrub; the compliance canary green at the byte level; the private-subreddit rule for reconcile; the migration-checklist tests (KI-014) | every deletion scenario; the canary; `info()` ordering and absence |
| **M1d** | Themes, digest, the schedule | Seed themes; the digest assembled from the DB with identity coverage and tree completeness beside every ranked count, and a per-theme first-seen and weeks-active line; launchd installed; a notification fires on a forced failure; **seven consecutive successful scheduled runs**; the dead-man ping, scheduled backups with a restore command and one drill, retention pruning, a free-disk precondition on `run`, and signal handling are blockers, not features (Wes, 2026-09-14); Wes reads the seven digests against Reddit itself and files mismatches as issues | the rule engine including the regex timeout; the digest golden; every failure-matrix row; the schedule contract |
| **M2** | UI v1 | Feed, subreddit, theme, post and thread, search, author, settings CRUD, runs and Run now, export, healthz, appearance, system, backups, maintenance, and setup pages; the curation migration; **operator-complete**: every routine operation from the UI without a terminal; the rev-2 design items from the workflow seat (DECISIONS 2026-09-14) | the web suite including the operator checklist; optional Playwright smoke |
| **M3** | Reach and polish | Saved Reddit-wide searches with subreddit discovery; snapshots and velocity visible; reconcile tiers tuned; the full destructive-operation gate; a blind labelling packet per theme with the pass bar written before any label is seen; precision per theme and rule in the digest | search-run tests; the labelling packet recorded |
| **M4** | Containerize | Same behaviour in Docker on the Mac for a week, then on the QNAP with data on a local volume | entrypoint tests; one scheduled run in the container |
| **MB** | Backup and remote | A bare repository over SSH on the QNAP; the first push green through the pre-push hook; the nightly bundle installed; a restore from the NAS copy passes `doctor` | `git bundle verify`; the restore drill |
| **M5** | Analysis layer (later, out of scope here) | JSONL batches → summaries and classification; trend charts from `item_snapshots` | — |

## Things only Wes can do

1. Create the dedicated Reddit account, verify its email, register the script app, accept the Data API terms, and request API access through the form linked from the Data API wiki (approval is required before any data is accessed); paste the credentials into `.env` (never committed), or into `/setup` once the UI exists.
2. Settle the remaining owner items: the QNAP remote when the hardware arrives (MB); the read-before-touch ledger review on 2026-09-28; the pruning pass-one ruling on the reference material; the data-controls opt-out on each consumer plan before an external packet is uploaded.
3. Read the seven digests against Reddit at the end of M1d and file mismatches as issues; label tags while browsing from M2.
4. Optional but recommended: a personal restricted test subreddit seeded with the fixture cases, so cassettes contain no third-party content.
5. Later: the first Reddit-wide search queries and whether to add the optional subreddits; whether and when a second workspace, or a second instance, is wanted.

## Verification (end-to-end, after each milestone)

1. `make check` passes and stamps the tree.
2. `uv run threaddigest doctor` → every check green; with the network, auth OK with rate-limit headers and exactly two HTTP calls (tranche B).
3. `uv run threaddigest run --budget 200` → rows in `posts` and `comments`; run again → zero new posts; the interim browser shows the tables.
4. Compliance drill on the fake gateway: `run --gateway fake`, delete an item in the scenario, reconcile, then scan the data directory, the index bytes, and a fresh export for the canary phrase → no hits.
5. `uv run threaddigest serve` (M2) → the feed shows posts, a post page renders the nested tree with coverage counts, search returns hits, add and remove a subreddit, Run now completes with live progress, the export opens and passes its integrity check.
6. Migration drill: `db upgrade` on a copy of a previous-revision DB; the pre-migration backup appears first; integrity ok.
7. Scheduler: the Runs page shows a `schedule`-triggered run at each Monday and Thursday slot for seven runs; kill a run mid-way and confirm the next start marks it `crashed` and proceeds; sleep the Mac through a slot and confirm the run fires on wake.

## Review harness (agentic panels at critical points)

Wes leans on agent panels for review and for decisions. The panels used at lock-down are a standing protocol, and the earlier project's rule applies: reviews are aimed at the previous round's conclusion, with teeth to retract, and same-model builders agreeing is not confirmation. Every review on a review-required surface has a row in `docs/reference/reviews/REGISTER.md` (G50) and a record beside it.

| Trigger | Panel | Output |
|---|---|---|
| New module, new service, or any schema migration | Two focused reviewers (correctness and tests; operator and data safety) plus one adversarial reviewer, fresh-context and read-only | Ranked findings with a positive control demanded for every new guard; a cut list; P0 findings pause the change |
| A big change, a new phase plan, or a change to the enforcement surfaces | The same composition plus the decision panel below when a choice is involved | The same, plus "what would go wrong" per finding |
| Every ordinary change | One fresh-context review pass over the diff | Advisory unless a P0 is found |
| Large changes and milestone merges | Wes may trigger the built-in multi-agent cloud review of the branch; it is user-triggered and billed, so the harness only recommends it | Findings on the change |
| A milestone or a design freeze | An external round: a packet built from the committed tree by `tools/review_packet.py` (allowlisted, hashed, with the refute-framed brief in `docs/reference/reviews/templates/external-deep-research.md` and the claims list), sent to more than one provider; every finding re-run against the tree before it is believed; a code-executing seat in every round, because the two rounds so far found their defects only by running the code | A triage record, register rows, `KNOWN_ISSUES.md` rows for reproduced defects |
| A decision Wes must make | A three-perspective panel (simplicity, robustness, operator experience) plus an adversarial pass; the main session synthesizes options with a recommendation and confidence; Wes decides | A dated entry in `DECISIONS.md` with the reasoning and the dissent |

Round construction: every reviewer prompt is refute-framed ("find what is wrong with this and what it would cost"), never confirm-framed, and a prompt template is a gate artifact reviewed like code; findings are weighed by independence, evidence, and expertise, never tallied, so one evidenced dissent outranks three agreements; each round records what the reviewer was given; when two rounds disagree, the tie-break is re-running the specific check both reasoned about; rounds stop when a round surfaces nothing new. After each tranche one fresh-context agent audits the claims against the tree before the status page is rewritten.

### Agent model tiers (decided 2026-09-13)

The main session does the detailed planning, synthesis, and final judgement; sub-agents run on the least capable model that fits the work, and every call names its model.

| Tier | Use for | Examples in this project |
|---|---|---|
| The main session | Detailed planning, design lock-down, synthesis of panel output, the final decision or recommendation, anything that edits the plan or the enforcement surfaces | Writing and amending this plan; deciding what a panel's findings change; authoring workflows; the last word on a review |
| Opus | Complex areas and work where judgement matters | Adversarial and design reviewers; the judge or critic stage of a workflow; reviewing or implementing migrations, `core/deletion`, `services/scrub` (M1c), `db/repo`; a service whose spec leaves choices open; debugging a red gate; extracting insight from long documents |
| Sonnet | Well-specified, mechanical, or high-volume work | Per-file inventories and scans; applying a deterministic map or codemod; writing tests from a spec-table row; fixture scrubbing; doc-currency and residue sweeps; renames and formatting; first-pass reading to build a map |
| Haiku | Not part of the policy | Add only with a recorded reason in `DECISIONS.md` |

Rules: a Sonnet stage that turns out to need judgement gets an Opus verifier behind it rather than being promoted wholesale; when unsure which tier a stage needs, pick the higher one and say why in the workflow's description; the tier of each stage is recorded so the run log shows it; when an Opus verifier catches something a Sonnet stage missed twice in a row, that class of stage moves to Opus and the decision is logged.

## Version history

| Version | Date | What changed |
|---|---|---|
| 1 | 2026-09-12 | The original plan from the kickoff, corrected in place with dated annotations through 2026-09-15 |
| 2 | 2026-09-15 | Rewritten as the current state after the two panels of 2026-09-14, external round one, the cadence decision, and the round-one fixes. Added: the intent reframed around the one question and personal use; "From data to insight"; the built-versus-planned state on the module and CLI tables; Alembic revision ids; the backup retention decision; the workspace direction, the leaving-a-domain path, and the instance option; the harness page and the overview as companions. Retired, with the home of each: the 2026-09-12 decisions table (DECISIONS § 1), the reviewers'-questions table (DECISIONS § 6), the D0 open-items list and walk status (DECISIONS § 7 and the status page), the appendix of retrospective changes (`docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` and `LEARNINGS_TRANSFER.md`), the proposed-panels appendix (executed; `docs/TEST_STRATEGY.md` and the panel reports), the research brief (the report never arrived; the external review rounds took its place, DECISIONS 2026-09-15), the "what the adversarial review changed" section (DECISIONS § 3 and the 2026-09-13 entries), the two UI wireframes (git history; the feed sketch is in `docs/reference/reviews/2026-09-12-ui-design-review.md`), and the corpus rule that every measured result lands a three-line note (never practised; the deferred results-ledger trigger in `docs/reference/earlier-project/EARLIER_PROJECT_REFERENCE.md` § 6.3 replaces it). A refute-framed review of version two against version one (`docs/reference/reviews/2026-09-15-plan-v2-review.md`) restored what the rewrite had compressed away and found two cadence residues in code (KI-025, KI-026) |
