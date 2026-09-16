# Review-round outputs in version two, part 1 (2026-09-16)

## Claim under test

"Every finding those records accepted, and every ruling they produced (the records mark what was
accepted, declined, deferred; the decisions log records the rulings), is still stated by plan
version two or by the decisions log, in a form that a builder starting tranche B and M1b would
read; nothing version two says contradicts a ruling that has not been explicitly revoked; and
nothing version two dropped was a load-bearing insight without a home."

Records in scope (the first half of the rounds): `docs/reference/reviews/2026-09-12-collector-design-review.md`,
`2026-09-12-db-learnings-review-A.md`, `2026-09-12-db-learnings-review-B.md`, `2026-09-12-ui-design-review.md`,
`2026-09-13-adversarial-review.md`, `2026-09-13-panel-db-integrity.md`, `2026-09-13-panel-ingest.md`,
`2026-09-13-panel-enforcement.md`, `2026-09-13-panel-ui.md`, plus `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md`
as the disposition record for the two database reviews.

## Method

1. Extracted each record's accepted findings and rulings into a numbered list. For the two database
   reviews the accepted set is the ranked table in `DB_LEARNINGS_APPLIED_2026-09-12.md` § 1 plus its
   § 2 guard rules; for the panels it is the "judgements"/"cut list" sections, which are the outputs
   the rounds produced; for the collector and UI design reviews it is the recommendations the plan
   adopted, with the record's own open questions treated as deferred.
2. Located each item in `docs/PLAN.md` (version 2, 2026-09-15) or `docs/decisions/DECISIONS.md`, quoting
   the line. Where an item was absent from both I searched the rest of the tree
   (`docs/TEST_STRATEGY.md`, `docs/runbook/RUNBOOK.md`, `CLAUDE.md`, `src/`, `config/`, `.ratchets/`)
   before calling it a loss, because an item with a home elsewhere is a routing problem, not a loss.
3. Compared version one (`PLAN_v1.md`, the copy in this scratchpad) wherever an item looked missing, to
   separate "the rewrite dropped it" from "it was never in the plan".
4. Checked the built code for every item whose correctness a builder would depend on
   (`core/deletion.py`, `services/invariants.py`, `db/repo.py`, `db/schema.sql`, `config/settings.yaml`),
   because the 2026-09-16 ruling makes the plan answerable to the build.

Status vocabulary: **carried** (stated by the plan or the decisions log), **carried elsewhere** (stated
by a document the plan routes to, but not by the plan or the log), **not found**, **contradicted**.

## Items

### 1. Collector, data model and testing design review (2026-09-12)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| C-01 | Read-only auth, never a password grant | `client_id`+`secret` only; one cheap auth ping before paging | DECISIONS D-07, N-03; PLAN § Collector step 0 "one cheap auth ping so credential failures surface before any paging" | carried |
| C-02 | User-agent from one `__version__` | honest versioned UA | PLAN § Release "the user-agent built from it (`python:com.wesmax.insightminer:v<version> (by /u/<user>)`)" | carried |
| C-03 | prawcore retries are seconds; add an outer ladder per unit of work | outer retry around page, tree, `info` batch | PLAN § Resilience "the outer retry ladder around every page, tree, and info batch on top of prawcore's short retries" | carried |
| C-04 | 429 is not retried by prawcore | catch, bounded sleep, retry once, abort on the second | PLAN failure matrix "Sleep the bounded wait via the injected clock, retry once; a second 429 → run `rate_limited`" | carried |
| C-05 | The rate limiter paces, it does not burst | budget in requests, expect elapsed time | PLAN § Budget reality "PRAW paces requests evenly over its ten-minute window" | carried |
| C-06 | `auth.limits` is for logging; count requests yourself | injected counting session | PLAN § Tech stack "an injected `requests.Session` that counts requests"; § Collector step 2 "counted by our own session hook" | carried |
| C-07 | `timeout=30`, `check_for_updates=False` | both set explicitly | PLAN § Tech stack, same row | carried |
| C-08 | Lazy-fetch footgun | serialize with `vars()` minus private keys; read from the dict | PLAN § Collector step 2 "touching a missing attribute silently fires a request" | carried |
| C-09 | Listing paging: forward `after` only, never `before`; a short page is normal | no "page shorter than 100 → stop" heuristic | PLAN § Collector step 1 "forward `after` paging only" (the `before` reason and the short-page rule are not stated); `docs/TEST_STRATEGY.md` SW-01 `sweep_full_window_forward_after_only`, shipped | carried elsewhere |
| C-10 | Tree fetch costs one request and refreshes the post | count it in the budget | PLAN § Collector step 2 "(one request, which also refreshes the post)" | carried |
| C-11 | `replace_more` semantics | per-pass limit, `count == 0` continue-thread nodes, persist skipped stubs | PLAN § Collector step 2; `comment_more` table | carried (the max-heap "largest first" order is in the record only; TEST_STRATEGY TR-02 asserts it) |
| C-12 | `num_comments` includes deleted items | never a completeness check | PLAN § Silent-failure controls "is Reddit's count including deleted items and is never used in an invariant" | carried |
| C-13 | `info()`: 100 per request, match by fullname, absence ≠ deletion | confirm before scrubbing | PLAN § Collector step 4; § Content-state machine (two omissions) | carried |
| C-14 | Subreddit names are case-insensitive | normalize to lower, keep the `t5_` id | DECISIONS D-01; PLAN § Data model "Subreddit identity is `name_lower` plus the `t5_` id" | carried |
| C-15 | Surrogate integer PK, `reddit_id` unique | FTS5 external content keys on rowid | PLAN § Data model conventions | carried |
| C-16 | `parent_fullname` + nullable `parent_comment_pk`, no FK | skipped `more` parents | PLAN § Data model `comments` row "(null for top level, no FK)" | carried |
| C-17 | `content_state`/`author_state`/`misses`/`scrubbed_at` replace `deleted_at` | four states, not one flag | PLAN § Data model; § Content-state machine | carried |
| C-18 | `next_check_at`/`check_stage` stored, not computed | resumable, testable | PLAN § Data model "`next_check_at` is NOT NULL" | carried |
| C-19 | Numeric-only snapshots; a hash of deleted content is derived content | no `body_hash` | PLAN § "For how long" and `item_snapshots` row "Numeric only: a hash of deleted content is derived content" | carried |
| C-20 | Timestamps as INTEGER epoch | SQLAlchemy drops the zone on SQLite | PLAN § Data model conventions | carried |
| C-21 | Full page-through of `/new` every run | watermark leaves the correctness path; late-approved posts caught; removal signal | PLAN § Collector step 1 | carried |
| C-22 | Order of run steps; config/auth failures leave no `running` row | validate → open DB → lock → run row → ping | PLAN § Collector step 0 | carried |
| C-23 | One transaction per page, one per tree | crash leaves no half-written page | PLAN § Collector steps 1 and 2 | carried |
| C-24 | Skip the tree when `num_comments == 0` | saves a request | PLAN § Collector step 2 "Skip when `num_comments == 0`" | carried |
| C-25 | Per-post replacement cap for huge threads | mark incomplete, follow up later | PLAN § Collector step 2 `comments.per_post_expansion_cap` (see finding 14 on "per post" vs "per fetch") | carried |
| C-26 | Leaf deleted comments vanish from trees | after a complete refetch, batch-`info()` the missing ones | PLAN § Collector step 3 | carried |
| C-27 | Tiered reconcile beyond 30 days | configurable tiers | PLAN § Collector step 4; DECISIONS § 2, D-16 superseded by D-30 | carried |
| C-28 | Digests generated from the DB, never a persisted file | a file quotes tomorrow's deletion | DECISIONS § 2 Digests row; PLAN § Collector step 6 | carried |
| C-29 | `fcntl.flock` beside the DB; stale `running` rows marked crashed; exit 75 | heartbeat, not PID | PLAN § Collector step 0; DECISIONS § 6 stale-run threshold | carried |
| C-30 | WAL so readers do not block writers | plus the local-filesystem rule | PLAN § Release Connections | carried |
| C-31 | Migration practices (batch mode, pre-migration backup, pytest-alembic, expand/contract, `normalizer_version`) | the whole § 4 table | PLAN § Release; § Data model schema revisions | carried |
| C-32 | Personal restricted test subreddit for cassettes | no third-party content in git | PLAN § Testing "a personal restricted test subreddit seeded by hand with the fixture cases"; DECISIONS § 6 | carried (fixture list incomplete — finding 3) |
| C-33 | The record's 14 open questions | a recorded disposition each | DECISIONS § 6 covers cassettes, tree shape, backfill, snapshots, regex, timezone, secrets, exit codes; § 1 covers JSONL (D-15), reconcile cadence (D-16/D-30), banned subs (§ 2), Datasette (D-21), Python pin (D-24) | carried |
| C-34 | The `[?]` live-verification list closed by `probe` | six to seven fixtures before the state machine is trusted | PLAN § Content-state machine "predicates re-confirmed against real captures on the probe day"; § M1a tranche B | carried (contents incomplete — findings 3 and 4) |

### 2. Earlier-project retrospectives, reviewer A (2026-09-12) — accepted set = the ranked table

| # | Item (rank) | What it required | Where stated now | Status |
|---|---|---|---|---|
| A-01 | 1 DATA_DIR isolation is structural | autouse fixture + settings refusal under pytest | PLAN § Gates "`DATA_DIR` isolation"; `CLAUDE.md` irreversible rule 1 | carried |
| A-02 | 2 Runtime outside TCC folders | `doctor` checks the path | DECISIONS D-08; PLAN § Deployment "Location constraint" | carried |
| A-03 | 3 `ON CONFLICT DO UPDATE`, PK stability | never `INSERT OR REPLACE` | DECISIONS N-04; PLAN § Data model | carried |
| A-04 | 4 Fail-closed state machine, unknown enums, `next_check_at NOT NULL` | unknown never defaults to live | PLAN § Data model; § Silent-failure controls "unknown upstream enum values are counted, never coerced" | carried, but the plan's own predicate order contradicts the built one — **finding 1** |
| A-05 | 5 Population floors and coverage counters | trailing-median alarm deferred | PLAN § Silent-failure controls; "the trailing-median alarm on these counters is deferred to M3" | carried |
| A-06 | 6 Zero-new detection per source; freshness separate from run status | the anchor half was cut (N-08) | DECISIONS N-08; PLAN § Silent-failure controls | carried, population narrower than the accepted fix — **finding 5** |
| A-07 | 7 A positive control for every gate | scoped in three tiers | DECISIONS D-22; PLAN § Guard design rules; `docs/runbook/GUARDS.md` § External controls "last seen red" | carried |
| A-08 | 8 Enforcement in the path every change takes | CODEOWNERS declined, compensating controls named | DECISIONS D-11 | carried |
| A-09 | 9 Guard reachability through the real run | never by calling the guard | PLAN § Silent-failure controls "each is planted through `insightminer run --gateway fake` by its positive control (G30)" | carried |
| A-10 | 10 Connection chokepoint; scrub is one function | import-linter + ruff; one call | PLAN § Gates "Connection chokepoint" | carried |
| A-11 | 11 No bypass flags; `--budget` hard-capped | ceiling plus a written reason | DECISIONS N-06; PLAN CLI table | carried |
| A-12 | 12 FTS-aware migrations, one transaction per migration, invariants scoped by version | the checklist | PLAN § Release Schema; § Silent-failure controls | carried (the `foreign_keys` pragma reason lives in `RUNBOOK.md` § 4 — see § What I could not check) |
| A-13 | 13 Every mutating command locks and writes a run row | stage-bearing heartbeat, wall-clock ceiling | PLAN § Collector step 0 | carried |
| A-14 | 14 One canonical shape before normalize; parity test; field-ownership table | the cheap proof | PLAN § Raw JSON policy; § Table-to-writer map | carried |
| A-15 | 15 `normalizer_version`, `settings_fingerprint`, two-gate discipline | semantic change is its own change | PLAN § Silent-failure controls "Two-gate discipline for semantics" | carried |
| A-16 | 16 Destructive-operation gate | recorded verified backup + confirmation, inside the service | PLAN § Gates "Destructive-operation gate" | carried |
| A-17 | 17 Cross-platform controls | `PLW1514`, `os.replace`, guarded `fcntl`, absolute interpreter | PLAN § Silent-failure controls | carried |
| A-18 | 18 The operator reads real output; independent review on four surfaces | seven digests; fresh-context review | PLAN § M1d; `CLAUDE.md` PR protocol | carried |
| A-19 | 19 Metrics as single functions with denominators; distinct authors; bots excluded | one ranking function | DECISIONS D-09; PLAN § From data to insight | carried |
| A-20 | 20 Reference corpus with a router | append-only logs, prune-stale status | DECISIONS D-27; PLAN § Reference corpus | carried |
| A-21 | 21 Notifier proof | downgraded 2026-09-13 | DECISIONS § retired claims `notifier proof`; PLAN § Silent-failure controls "notifications are best-effort" | carried (declined, decline recorded) |
| A-22 | 22 Hold the count; widen before adding | ledger reviewed quarterly | PLAN § Guard design rules "Hold the count" | carried as a review rule; the panel's `guards.count` ratchet was not built — see Items § 8 E-14 |
| A-23 | 23 Stress corpus | cut; `EXPLAIN QUERY PLAN` kept | DECISIONS N-11; PLAN § Data model indexes | carried |
| A-24 | 24 Hard-block hooks | two, then three (amended) | DECISIONS N-16 and its 2026-09-14 amendment | carried |
| A-25 | 25 Compressed raw verified before deletion | moot with the sidecar cut | `DB_LEARNINGS_APPLIED` § Correction 2026-09-13 (late) | carried (retired, retirement recorded) |
| A-26 | 26 Mutation testing | optional, never a gate | DECISIONS N-10 | carried |
| A-27 | § 2 guard design rules 1–8 | eight rules | PLAN § Guard design rules holds seven of them plus three more | rule 5 ("probe each item the way a real record presents it") **not found** in the plan — **finding 12** |
| A-28 | § 3 declines (Windows lock, `caffeinate` scope, tree reimplementation, per-PR review, `jobs` table, ratchet-file floors, `authors` view, labelling packet, path grep, sign-off) | each decline recorded | `DB_LEARNINGS_APPLIED` § 3, with the 2026-09-15 supersession note on `caffeinate` | carried |

### 3. Earlier-project retrospectives, reviewer B (2026-09-12)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| B-01 | E1 launchd/TCC | move before scheduled runs | DECISIONS D-08; PLAN § Deployment | carried |
| B-02 | E2 Empty table / NULL read as absent | presence and populated-rate floors | PLAN § Silent-failure controls "population floors" | carried |
| B-03 | E3 Two paths for one value must match | value parity + per-path ownership | PLAN § Table-to-writer map; § Raw JSON policy shape-parity test | carried |
| B-04 | E4 Guards tested but unreachable | every invariant proven via the real run | PLAN § Silent-failure controls | carried |
| B-05 | E5 CODEOWNERS on enforcement surfaces | declined with compensating controls | DECISIONS D-11 | carried (declined, recorded) |
| B-06 | E6 Batch mode drops FTS triggers | rebuild in the same migration; one transaction per migration | PLAN § Release Schema | carried |
| B-07 | E7 Fail closed on malformed input | unknown never `live`; `next_check_at NOT NULL` | PLAN § Data model | carried (**finding 1** on the predicate order) |
| B-08 | E8 No boolean bypass; reconcile-age invariant | per-tier bound | DECISIONS N-06, § 2; PLAN § Silent-failure controls (M1c, KI-026) | carried |
| B-09 | E9 Destructive writes need a gate | backups table + confirmation | PLAN § Gates; `backups` table in revision 0001 | carried |
| B-10 | E10 Truncation named in the return value | `complete` on the result | PLAN `posts.comments_complete`, `comment_more` | carried |
| B-11 | E12 Two writers need a writer map | web repository exposing only its writes | PLAN § Table-to-writer map | carried |
| B-12 | E13 Metrics are one tested function | shared by UI, digest, export | PLAN § Every count carries its denominator | carried |
| B-13 | E14 Derived counters drift | `authors` counts vs `COUNT(*)` | PLAN § Silent-failure controls (M1b, live rows) | carried |
| B-14 | E15 The alert path must prove delivery | downgraded to the UI pill | DECISIONS D-10; PLAN § Silent-failure controls "Alerts" | carried (downgraded, recorded) |
| B-15 | E16 Runs that hang hold the lock | wall-clock ceiling | PLAN § Collector step 0 `run.wall_clock_ceiling_hours` | carried (launchd `ExitTimeOut` not stated; `deploy/launchd/` owns it) |
| B-16 | E17 Apparatus outran code | agent reports never committed; docs may not restate counts; size ratchets | PLAN § Reference corpus; § Gates code-health ratchets; G45 | carried |
| B-17 | E18 Bot contamination | flag, do not hand-maintain a list | DECISIONS N-14 | carried |
| B-18 | E20 Field names must not lie | `comment=` on every column | PLAN § Data model; `db/schema.sql` carries a `-- COLUMN COMMENTS` section | carried |
| B-19 | E23 Blind labelling packet | M3, pass bar written first | DECISIONS 2026-09-13 late ("theme precision is reserved for the blind packet"); PLAN § M3 | carried |
| B-20 | E25 Data never on a network share | `doctor` check | PLAN § Release Connections | carried |
| B-21 | B8/I1 read-only by default for scripts | web `mode=ro` engine | Superseded by N-07 (one rw engine behind the repository), with the reason recorded | carried (revoked explicitly) |

### 4. Local web UI design review (2026-09-12)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| U-01 | Single worker; fetching always a CLI subprocess | in-process job state | PLAN § Web UI Process model | carried |
| U-02 | Same URL page or fragment on `HX-Request` | dedicated partials only where not page-shaped | PLAN § Web UI design rules row 1 | carried |
| U-03 | Reddit URL scheme and deep links incl. `?context=3` | muscle memory; tombstones link by id | PLAN § Web UI opening paragraph | carried |
| U-04 | Markdown rendered and sanitized at ingest; only `*_html` rendered unescaped | never trust Reddit's HTML | PLAN § Tech stack; § Web UI Content safety | carried |
| U-05 | Comment tree: one query, built in Python, recursive template, depth cap 10, page by top-level with whole subtrees | collapse is CSS | PLAN § Web UI Comment tree | carried |
| U-06 | Honest coverage: "(N captured)", stubs, "as of", harvest button | the gap is a budget, not a bug | PLAN § Web UI Honest coverage | carried |
| U-07 | Tombstone rendering rules | children stay visible; never on author pages | PLAN § Web UI Tombstones | carried |
| U-08 | Subreddit add: debounced validation, one API call, mapped errors, preview card | remove keep vs delete | PLAN § Routes `/settings/subreddits` | carried |
| U-09 | Theme editor: three rule groups, server-side regex validation, live preview with the CLI's matcher, retag preserving timestamps, stale badge | same matcher both sides | PLAN § Routes `/settings/themes` | carried (retag path contradicted — **finding 6**) |
| U-10 | Run now: queued row first, `Popen` the same CLI, poll, 409, cancel, stale detection | one code path | PLAN § Routes `/runs` | carried (cancel mechanism contradicted — **finding 7**) |
| U-11 | Export: backup API not a file copy, integrity check, manifest, retention, disk guard | zip contents listed | PLAN CLI `export`; § Routes `/export`; DECISIONS § 2 Exports | carried |
| U-12 | Search: FTS5 external content, mini-grammar, safe snippets, tabs with counts | never raw input to MATCH | PLAN § Routes `/search`; § Web UI Content safety | carried |
| U-13 | CSRF and Host checks; bind 127.0.0.1 | plus optional basic auth | PLAN § Web UI Security | carried (Host scope narrowed — **finding 9**) |
| U-14 | One hand-written stylesheet with tokens, 13px, light/dark plus cookie override | not a classless framework | PLAN § Web UI Styling | carried |
| U-15 | Datasette read-only as the power view | and the interim browser | DECISIONS D-21, N-01; PLAN § Web UI Power view | carried |
| U-16 | `/healthz` shape; `degraded` when the last success is older than 2× the interval | the pill polls it | PLAN § Routes `/healthz` lists the keys; the `degraded` rule is in `docs/TEST_STRATEGY.md` UI-32 | carried elsewhere |
| U-17 | Accessibility basics (landmarks, one `h1`, `aria-expanded`, `aria-live`, contrast) | asserted per page | `docs/TEST_STRATEGY.md` UI-51, planned | carried elsewhere |
| U-18 | Regex preview timing warning above ~1 s | alongside the length cap | Not in the plan; length cap and `timeout=` are (PLAN § Tech stack Rules) | not found (LOW; the timeout makes the warning cosmetic) |
| U-19 | Build order (feed → settings → runs → search → export → author pages) | each step shippable | PLAN § M2 definition of done lists the same surface without the order | carried elsewhere (review record) |

### 5. Adversarial review (2026-09-13)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| X-01 | A1 FTS count is a proxy | measure membership, not `count(*)` | PLAN `posts_fts` row "counts `posts_fts_docsize`, because `count(*)` on an external-content table can never go red"; KI-022 | carried |
| X-02 | A2 CI is not outside the agent's reach | say what CI is, honestly | DECISIONS D-11 "CI is a gate with a git trail, not an enforcement authority"; § 7 item 1 | carried |
| X-03 | A3 Positive controls split three ways | invariants / ratchets / external | DECISIONS D-22; `GUARDS.md` § External controls | carried |
| X-04 | A4 Notifier proof downgraded | UI pill is canonical | DECISIONS D-10 | carried |
| X-05 | A5 Dead-man moves off launchd | Healthchecks.io from M1d | DECISIONS N-12; PLAN § Gates Dead-man ping | carried |
| X-06 | A6 Hooks cut and redesigned | no command-text list-policing; self-protecting | DECISIONS N-16; PLAN § Gates Hard-block hooks | carried |
| X-07 | A7 "No bypass flags" is ceiling + written reason | not a name list | DECISIONS N-06 | carried |
| X-08 | A8 Freshness anchor cut | zero-new detection kept | DECISIONS N-08 | carried |
| X-09 | A9 Fingerprint warns, never refuses | ordinary tables only | DECISIONS N-13 | carried |
| X-10 | A10 `AUTOINCREMENT`; drop the runtime `max(pk)` equality | rerun check keeps it | PLAN § Data model "`pk INTEGER PRIMARY KEY AUTOINCREMENT`"; the equality appears only in the rerun invariant; the runtime form is "row counts never decrease except through a recorded purge" | carried |
| X-11 | A11 Structural floors only | trend alarms later | PLAN § Silent-failure controls | carried |
| X-12 | A12 Test-count floor cut as a gate | the contradiction recorded | DECISIONS N-09 and the retired-claims row; PLAN § Gates | carried |
| X-13 | A13 Live tests deselected, not skipped | ratchet counts static markers | PLAN § Guard design rules "the only skips allowed are the explicitly opt-in live tests"; `.ratchets/skips.txt` | carried |
| X-14 | A14 Doc currency narrowed to the router check | the rest cut | DECISIONS D-27 (2026-09-13), then explicitly widened again on 2026-09-14 ("the demotion of the documentation-drift gates is declined") and 2026-09-15 | carried (revoked explicitly, with the reason) |
| X-15 | A15 The `normalizer_version` invariant is zero-information; fold it | cut proposed | The invariant is kept (PLAN § Silent-failure controls); the database panel re-justified it (DB-48) | kept against the record; the decline of the cut is **not recorded** (LOW) |
| X-16 | A16 Bot list becomes a heuristic | "suspected bots", one-click confirm | DECISIONS N-14 | carried |
| X-17 | B1 Backups and exports retain scrubbed text | write the bound; canary asserts file ages | DECISIONS § 2 Backups/Exports, D-31; PLAN § Release Backups | carried |
| X-18 | B2 Digest files | a route, not a file | DECISIONS § 2 Digests | carried |
| X-19 | B3 Deleted LINK posts are mis-stated | key on the category first; link-post hold; probe fixture; title canary | Code `core/deletion.py` rules 3 and 7; TEST_STRATEGY RC-01 and the gap list | **contradicted / not found** in the plan — **findings 2 and 3** |
| X-20 | B4 The subprocess seam re-creates the isolation escape | env var, `ProcessRunner`, CLI refusal under pytest | PLAN § Gates `DATA_DIR` isolation; § Web UI Process model | carried |
| X-21 | B5 Edits are an event | reconcile upserts the full row; an "edited" matrix row | DECISIONS § 2 Edits; PLAN § Scrub "Edits are an event". The matrix row is still absent; TEST_STRATEGY § gap list tracks it | carried (the matrix row deferred, recorded) |
| X-22 | B6 Crosspost parent text | stripped to `{id, subreddit}` at ingest | DECISIONS § 2; PLAN § Module map `core.normalize`; KI-016 | carried |
| X-23 | B7 Lid-close vs heartbeat | flock means alive; `caffeinate` on scheduled runs | PLAN § Resilience | carried |
| X-24 | B8 Freshness must not stop looking at auto-disabled sources | iterate `enabled OR status != 'ok'` | Code `db/repo.py::all_sources_for_freshness`; TEST_STRATEGY FR-01 | **contradicted** by the plan — **finding 5** |
| X-25 | B9 Orphan `queued` runs | 2 minutes without a pid → failed | DECISIONS § 6 stale-run threshold | carried |
| X-26 | B10 Bot flag per author, never inherited | megathread comments stay taggable | DECISIONS N-14 | carried (the `is_megathread` heuristic deferred; TEST_STRATEGY gap list) |
| X-27 | B11 LAN threat model | write it down | DECISIONS § 5 | carried |
| X-28 | C cut list (sidecar, mutation, stress, fingerprint, anchor, hooks, test count, doc extras, notifier, `mode=ro`, trend alarms, corpus, panels, changelog, second wire shape) | each cut or kept with a reason | DECISIONS § 3 N-01…N-20, D-15, § retired claims | carried (the second wire shape is still open, decided at M1b per § 6) |
| X-29 | D1 Sec-Fetch on plain HTTP | fall back to `Origin`/`Referer` | PLAN § Web UI Security | carried |
| X-30 | D2 Destructive gate in one place | a confirmation object, checked inside the service | PLAN § Gates "checked inside the service"; TEST_STRATEGY UI-44 names the `Confirmation` object | carried |
| X-31 | D3 Reconcile invariant per tier; state the real latency | not "within 48 h" | DECISIONS § 2 | carried |
| X-32 | D4/D11/D12/D13/D14/D15 (path, ranking, dry run, time box, `next_check_at` sentinel, purge record) | one answer each | DECISIONS D-08, D-09, 2026-09-13 night (dry run), PLAN § Collector step 3 ("the last stage is a year"), § Workspaces ("recording the purge counts on the run row") | carried |
| X-33 | D6/D7 One rw engine; ruff `TID251` for the chokepoint | not import-linter, not two engines | DECISIONS N-07; PLAN § Gates Connection chokepoint | carried |
| X-34 | D8 The praw mypy override must be counted | the ratchet cannot see it otherwise | `.ratchets/suppressions.txt` key `mypy_overrides=1` | carried elsewhere (the plan's gate row does not enumerate keys) |
| X-35 | D9/D10 Mutation out of the gates table; guard reachability split | consistency with the learnings | DECISIONS N-10, D-22 | carried |
| X-36 | E1–E18 unverified claims | each verified or recorded | E3 (pragma) `RUNBOOK.md` § 4 step 2; E4/E5 PLAN § SQLite facts; E7 D-08; E16 DECISIONS § 4 note; E18 D-32 | carried |
| X-37 | G2 Operator load: three recurring duties | not a checklist | PLAN § Intent "The recurring human duties are three" | carried |
| X-38 | G3 Hand-over under-specified | checklist, import without `.env`, commercial stance | PLAN § Portability targets; D-32 | carried (but DECISIONS § 7 item 4 still reads pending — **finding 11**) |
| X-39 | H10 Pull the number-one priority forward | untagged and rising sections at M1d; tag feedback at M2; standing digest reading | PLAN § Two discovery signals; § Curation controls; § Intent | carried |

### 6. Panel: database integrity and migrations (2026-09-13)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| P1-01 | E.1 Membership via `_docsize` | the naive count is banned | PLAN `posts_fts` row | carried |
| P1-02 | E.2 `content='posts_live'` | rebuild and integrity-check become safe | PLAN § Search is over live content only | carried |
| P1-03 | E.3 Batch migration drops and recreates the view | then rebuild | PLAN § SQLite facts; RUNBOOK § 4 step 2 | carried |
| P1-04 | E.4 `max(pk)` equality scoped | runtime form is the purge rule | PLAN § Data model and § Silent-failure controls | carried |
| P1-05 | E.5 One normalizer for both fingerprint sides | no stored constant | DECISIONS N-13 | carried |
| P1-06 | E.6 `foreign_keys=OFF` outside the transaction | it is a no-op inside one | `RUNBOOK.md` § 4 step 2 (the plan says only "foreign keys off during batch migrations") | carried elsewhere |
| P1-07 | E.7 Backup retention as the compliance bound | a written window | DECISIONS § 2, D-31 | carried |
| P1-08 | E.8 `backups` table in revision 1 | the gate keys on a row, not a file | PLAN § Data model `backups` | carried |
| P1-09 | E.9 Column comments section in the dump | SQLite does not persist comments | `src/insightminer/db/schema.sql` line 42 `-- COLUMN COMMENTS` | carried elsewhere (the plan asserts the outcome, not the mechanism) |
| P1-10 | E.10 `raw_rejects` retention | same as the sidecar's was | DECISIONS § 2; PLAN `raw_rejects` row | carried |
| P1-11 | E.11 `authors` counters over live rows | scrub must decrement | PLAN § Silent-failure controls (M1b) | carried |
| P1-12 | E.12 Floors only until seven runs exist | no median on day one | PLAN § Coverage counters | carried |
| P1-13 | E.13 `include_object` excludes shadow tables and views | autogenerate would drop them | PLAN § Release Schema | carried |
| P1-14 | E.14 `AUTOINCREMENT` | a recycled rowid matches a stale FTS entry | PLAN § Data model; KI-014 | carried |
| P1-15 | E.16 Mechanize the restore drill | not a manual checklist | PLAN § Workflows ("or the automated weekly variant if adopted"); § M1d blockers include "scheduled backups with a restore command and one drill" | carried |
| P1-16 | § D Startup sequence and maintenance-only `serve` | the operator surface must not vanish | PLAN § Web UI Process model | carried |
| P1-17 | § C Migration checklist | per-revision fixture from pre-change code, etc. | RUNBOOK § 4; KI-014; PLAN § Release | carried |
| P1-18 | § B Fixture plan generated by a script, never committed by hand | discovered by glob, checked against `alembic history` | PLAN § Data model schema revisions; `tools/make_demo_fixture.py` for demo data | carried |
| P1-19 | § F owner questions (retention, purge semantics, `AUTOINCREMENT`, maintenance mode, fixture size, drill, reprocess boundary, rejects retention) | a recorded answer or an open item | DECISIONS § 2, § 7 item 6 → `TEST_STRATEGY.md` § 6 | carried |

### 7. Panel: ingest and collector failure modes (2026-09-13)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| P2-01 | Fake gateway is a scenario builder over one world; unconsumed injections fail the test | no `mock.patch` | PLAN § Testing strategy (the builder API is named); `TEST_STRATEGY.md` row 20 "unconsumed injections fail the test" | carried |
| P2-02 | D-1 Dry run and no-network defined separately | zero writes; zero calls | DECISIONS 2026-09-13 night ("a dry run writes no run row and performs zero database writes"); PLAN CLI table; the 2026-09-14 round reworded the overstated claim (C-05) | carried |
| P2-03 | D-2 Scope the clock-skew claim | the due-set must change | `TEST_STRATEGY.md` RV-02 "clock-skew claim scoped per ingest D-2"; the plan's matrix row is unchanged | **contradicted** — **finding 8** |
| P2-04 | D-3 Expansion cap is per fetch | drop the cumulative reading | `TEST_STRATEGY.md` TR-02 "cap is per fetch (ingest D-3), pending Wes"; § 6 question 18 | carried elsewhere, still open — **finding 14** |
| P2-05 | D-4 Canary covers `data/**` | backups, logs, exports | PLAN § Verification step 4; DECISIONS § 2 | carried |
| P2-06 | D-5 Removal-signal candidates bounded to the swept window | never a state change without `info()` | PLAN § Collector step 1 "a known post inside the window" | carried |
| P2-07 | D-6 Full exit-code table | tested | DECISIONS § 6; PLAN § Budget reality | carried |
| P2-08 | D-7 Heartbeat during long waits | stage-bearing | DECISIONS § 6; PLAN § Collector step 0 "`rate_wait:37s` counts as alive" | carried (the `wake_at` column was not adopted; the alternative is stated) |
| P2-09 | D-8 Unknown `removed_by_category` fails closed to a removal state | stored raw and counted | Code `core/deletion.py` rule 4 "an unknown value → `removed_by_reddit` (fail closed)" | **contradicted** by the plan — **finding 1** |
| P2-10 | D-9 Scrub latency for `info()` absence | owner decides | DECISIONS § 2 purge latency, re-derived under D-30 | carried |
| P2-11 | D-10 `--gateway fake` must not write the default data directory | a guard | `CLAUDE.md` irreversible rule 1 ("tests and the fake gateway never touch the default one") + `tests/gates/test_data_dir_isolation.py` | carried elsewhere |
| P2-12 | D-11 Budget counts every HTTP response; reserve checked before each tree | the hook cannot tell them apart | PLAN § Collector step 2; failure matrix "stops at the reserve" | carried |
| P2-13 | D-13 Floors over live rows with a known author | otherwise normal deletions trip them | PLAN § Silent-failure controls "`author_fullname` on live rows with a known author" | carried |
| P2-14 | D-14 `probe` needs sub-modes sharing the fake's fixture schema | about / listing / tree / info / search | Only `probe <fullname>` is in the plan's CLI table | **not found** — **finding 4** |
| P2-15 | D-15 State the hypothesis property | never raises; Row or Reject | PLAN failure matrix "fixtures + hypothesis"; the property statement is in the record | carried elsewhere |
| P2-16 | D-16 Cancel at the request boundary, roll back the in-flight tree | latency stated honestly | PLAN § Routes `/runs` "finishes its batch"; RUNBOOK § 3 "ends the run at the next batch boundary" | carried (mechanism contradicted — **finding 7**) |
| P2-17 | D-17 `comments_captured` counts all rows regardless of state | say it in the data dictionary | PLAN § Silent-failure controls (M1b); the "regardless of state" clause is not in the plan | carried elsewhere (column comment) |
| P2-18 | § C probe plan P-01…P-17 | the fixtures that unlock the predicates | The panel record; `TEST_STRATEGY.md` names P-18 as the missing deleted-link-post row | carried elsewhere — **findings 3 and 4** |
| P2-19 | § E owner questions (exit codes, dry run, scrub latency, unknown category, retained copies, banned subs, test sub, public probes, cap, zero-new threshold, budget scope, fake guard, cancel latency, fixture scrubbing) | recorded answers or open items | DECISIONS § 6, § 7 item 6 → `TEST_STRATEGY.md` § 6 | carried |

### 8. Panel: enforcement, gates, ratchets and CI (2026-09-13)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| P3-01 | G01–G07 lint, banned APIs, mypy strict, layering, chokepoints, network block, warnings-as-errors | each with a positive control | PLAN § Gates; `CLAUDE.md` rules table | carried |
| P3-02 | G08/G10 Static skip and suppression ratchets with reasons in syntax | zero baseline | PLAN § Gates; `.ratchets/skips.txt`, `suppressions.txt` | carried |
| P3-03 | G11/G12 Coverage, collected-test and assert floors | stale floor is red | PLAN § Gates; `.ratchets/` | carried |
| P3-04 | G13 Three-way comparison and canonical rendering | hand edits are red | `CLAUDE.md` rules table; PLAN § Gates "the three-way ratchet compare" | carried |
| P3-05 | G15/G16/G17 Schema snapshot, models == DDL, per-revision fixtures | derived from the migration tree | PLAN § Gates | carried |
| P3-06 | G18 Fingerprint derived from the packaged schema | no registry | DECISIONS N-13 | carried (downgraded to a warning, recorded) |
| P3-07 | G19 `DATA_DIR` isolation across the seam | refusal under pytest | PLAN § Gates | carried |
| P3-08 | G20 TCC path and absolute interpreter in the plist | plist test | PLAN § Deployment; § Gates Schedule contract | carried |
| P3-09 | G21 Size caps and complexity rules | no god modules | PLAN § Gates Code-health ratchets (G51) | carried (mechanism changed, recorded 2026-09-14) |
| P3-10 | G23/G24 Hooks and their wiring currency | the hooks registered are the hooks tested | PLAN § Gates Hard-block hooks; DECISIONS 2026-09-14 (the settings test requires the registered set to equal the scripts) | carried |
| P3-11 | G25 `make check` summary derived from artifacts | never typed | PLAN § Gates `make check`; `tools/check_stamp.py` | carried |
| P3-12 | G26/G27 PR-body numeric match and changed-test comment | CI is the authority | `CLAUDE.md` rules table; CI "runs once a GitHub remote exists (none yet, MB)" | carried (deferred with the remote, recorded) |
| P3-13 | G29 Pre-commit contents | same tool versions as `make check` | PLAN § Gates pre-commit | carried |
| P3-14 | G30 Guard reachability registry ↔ marker set | structural scan | PLAN § Silent-failure controls (G30) | carried |
| P3-15 | G31 Behavioural pragma test on the pooled connection | not a test-only connection | PLAN § Gates Connection chokepoint | carried |
| P3-16 | G33 Doc currency both directions | router and ledger | PLAN § Gates Documentation gates (G33, G40, G44, G45, G47, G50, G52, G54) | carried (widened, recorded) |
| P3-17 | E1–E18 cut list (mutation, prose counts, floors, hook #3, dmypy whole tree, restore drill, docker, live tests, portability trigger, review practice, fingerprint, catches column, pre-push, stress, amber, Playwright, containers, runtime controls) | each cut or redesigned | DECISIONS N-09, N-10, N-15, N-16 and 2026-09-13 night; PLAN § Gates; D-26 records the pre-push fast subset as pending | carried |
| P3-18 | § F compensating controls for agent-merges | legibility: weekly audit, sticky comment, one approval click | DECISIONS D-11; PLAN § Gates Review-only ceiling | carried (the GitHub-side half deferred with the remote, recorded 2026-09-14) |
| P3-19 | § G owner questions (plan tier, token scope, approval, perimeter, pre-push, identity, coverage strictness, minutes, channel, review, thresholds, credentials) | recorded answers or open items | DECISIONS § 7 items 1 and 6; D-23; 2026-09-14 ("the ratchet files left the register surface") | carried |
| P3-20 | G14 `guards.count` ceiling as a ratchet | adding a guard is a loosening | `.ratchets/` holds `review_only_rules.txt` (`count`, `guards_without_control`) but no guard-count family; "hold the count" is a review rule in PLAN § Guard design rules | not found as a ratchet (LOW; the review rule and the without-control ceiling cover the intent) |

### 9. Panel: web UI and delivery surface (2026-09-13)

| # | Item | What it required | Where stated now | Status |
|---|---|---|---|---|
| P4-01 | D1 Maintenance-only `serve` | the migration button must be reachable | PLAN § Web UI Process model | carried |
| P4-02 | D2 `backups` table before the controls that need it | no gate keyed on a file | PLAN § Data model `backups` (revision 0001) | carried |
| P4-03 | D3 One rw engine behind a repository | not two engines | DECISIONS N-07; PLAN § Web UI Writes | carried |
| P4-04 | D4 Re-tag always via the CLI subprocess; drop the inline heuristic | one write path, one lock | PLAN § Web UI Writes says subprocess; PLAN § Routes `/settings/themes` still says "inline if quick"; TEST_STRATEGY UI-38 "no inline path" | **contradicted (internally)** — **finding 6** |
| P4-05 | D5 Cancel by `cancel_requested_at` polled at batch boundaries | SIGTERM fails across container PID namespaces | TEST_STRATEGY UI-30 "`cancel_requested_at` polled at batch boundaries (UI D5)"; PLAN § Routes `/runs` "Cancel sends SIGTERM" | **contradicted** — **finding 7** |
| P4-06 | D6 One polling-stop mechanism | no HTTP 286 | PLAN § Routes `/runs` "stops when idle" | carried |
| P4-07 | D7 Host check on every request | DNS rebinding is a read attack | TEST_STRATEGY UI-22 "Host check on every request", planned; PLAN § Web UI Security scopes it to state-changing requests | **contradicted** — **finding 9** |
| P4-08 | D8 `Sec-Fetch-Site` same-origin only; missing rejected | with the plain-HTTP fallback | PLAN § Web UI Security | carried |
| P4-09 | D9 `[NEW]` = latest completed run; drop "since last visit" | one truth per badge | DECISIONS § 6 "no 'since last visit' toggle"; PLAN `ui_state` row still uses `last_visit_at` as its example | **contradicted (residue)** — **finding 10** |
| P4-10 | D10 One stale-run settings key, about three minutes | shared by collector and UI | DECISIONS § 6 | carried |
| P4-11 | D11 `/healthz` for the pill only; no auth exemption | healthcheck is `doctor` | PLAN § Routes `/healthz`; § Deployment M4 `HEALTHCHECK via doctor --no-network` | carried |
| P4-12 | D12 Store the integrity result at creation; add a Verify-now button | O(size) per view otherwise | PLAN `backups` table stores it; the Verify-now button is not in the routes table | carried (button not found, LOW) |
| P4-13 | D13 Archive import from a server-side path | not a browser upload | PLAN § Routes `/system/maintenance` | carried |
| P4-14 | D14 Download config and Regenerate digest controls, or exclusions with reasons | the operator-complete gate needs each command mirrored | DECISIONS § 6 records four exclusions only; `TEST_STRATEGY.md` § 6 question 22 keeps the buttons open | carried elsewhere, still open — **finding 13** |
| P4-15 | D15 One truth for the request count | 2 HTTP calls, 1 API request | PLAN § Verification step 2 | carried |
| P4-16 | D16 CSP | cheap defence for the markdown surface | PLAN § Web UI Content safety | carried |
| P4-17 | D17 `Vary: HX-Request` | the back button otherwise shows a fragment | PLAN § Web UI design rules row 1 | carried |
| P4-18 | D18 Exports exclude raw logs by default | purge honesty | Moot with the sidecar cut; PLAN CLI `export [--no-raw]` | carried (retired, recorded) |
| P4-19 | D19 Plan names win over review names | `content_state`, `tagged_at`, `selftext_html` | PLAN § Data model uses them throughout | carried |
| P4-20 | D20 Typed word verified server-side | `hx-confirm` is not a gate | PLAN § Web UI Operator-first | carried |
| P4-21 | § C setup-wizard threat model (loopback, never echo, `.env` 0600, typed replace, one request, no password field, gitignore) | ten items | PLAN § Routes `/setup`; DECISIONS § 5; TEST_STRATEGY UI-46…UI-48 | carried |
| P4-22 | § B operator-complete checklist | every routine operation has a control | PLAN § Web UI Operator-first; UI-50 | carried (two commands unmirrored — finding 13) |

**Counts.** 185 items checked: 158 carried, 18 carried elsewhere (stated by a document the plan routes
to — chiefly `docs/TEST_STRATEGY.md` and `docs/runbook/RUNBOOK.md` — but not by the plan or the log),
6 contradicted, 3 not found.

## Findings

Only the items that matter for a builder of tranche B, M1b or M1c, or for a reader who would rebuild
something a round killed.

### 1. The plan's content-state machine contradicts the built one on an unknown `removed_by_category` — HIGH

`docs/PLAN.md` § Data model, "Content-state machine": "`== "[removed]"` → `removed_by_moderator`
unless `removed_by_category` names Reddit → `removed_by_reddit`". Read as written, an unrecognised
category value lands in `removed_by_moderator`.

`src/insightminer/core/deletion.py` rule 4 does the opposite and says why: "Any other non-None
`removed_by_category`, whatever the body … `"moderator"` → `removed_by_moderator`; a value in
`REDDIT_REMOVAL_CATEGORIES` → `removed_by_reddit`; an unknown value → `removed_by_reddit` (fail
closed, never live)." That is the ingest panel's ruling D-8 ("unknown → `removed_by_reddit`, stored
raw and counted") and the fail-closed lesson at rank 4 of `DB_LEARNINGS_APPLIED_2026-09-12.md`.
The plan also keys the removal branch on the body (`== "[removed]"`) where the code keys on the
category first, which matters because a removed *link* post has an empty `selftext`, not the marker.

Why it matters: M1c builds reconcile and scrub on this function, and the plan is "canonical for every
design question". A builder or reviewer working from the plan would read the code as wrong and could
"fix" it toward the open direction. **Fix:** rewrite the content-state-machine paragraph of
`docs/PLAN.md` § Data model to state the code's rule order (terminal → `info()` omission → deleted →
any other category → bodyless hold → `[removed]` → link-post hold → live).

### 2. The deleted-link-post hold is gone from the plan, and the sentence that replaced it re-derives the bug — HIGH

Version one carried the fix as an explicit bullet (`PLAN_v1.md` line 486): "Deleted link posts have an
empty `selftext`, so the predicate keys on `removed_by_category='deleted'` first and treats `author is
None` on a link post as deletion pending `info()`; a deleted link post joins the probe list; the
compliance canary phrase lives in a title as well as a body." That bullet was in the retired "what the
adversarial review changed" section.

Version two keeps the first clause and drops the rest, and its remaining sentence is the hazard the
adversarial review B3 named: "`author is None` with intact body → `author_state = account_deleted`
(scrub author fields only, content stays…)". A link post's `selftext` is `""`, which
`core/deletion.py` itself calls intact content ("an empty string is intact content: link posts and
text-less self posts have `selftext == ""`"). A reader implementing from the plan alone classifies a
deleted link post whose category is missing as an account deletion and keeps its title and URL —
exactly the case B3 found, in two of the three target subreddits, which are link-heavy. The code has
the guard (rule 7: "`author is None` on a LINK post with no category → deletion pending an `info()`
check") and `docs/TEST_STRATEGY.md` RC-01 records it; the plan does not.

**Fix:** add the link-post hold to the same content-state-machine paragraph of `docs/PLAN.md` § Data
model, as a rule, not a parenthetical.

### 3. The probe fixture list and the canary description dropped the two cases B3 asked for — MEDIUM

`docs/PLAN.md` § Testing strategy lists the seeded fixture cases as "a normal post, a self-deleted
post, a mod-removed post, a deleted comment with children, a leaf deleted comment, a deep chain, a
crosspost" — the version-one list, unchanged, with no deleted **link** post. The compliance canary is
described as "ingest a unique phrase" with no mention of a title. Both are the B3 ruling; both are
carried only in `docs/TEST_STRATEGY.md` (DB-31, DB-32, SC-01, SC-02 all say "canary in a title"; the
gap list says "the **deleted link post** probe and state row (B3; add to the probe plan as P-18)").

Why it matters: the probe day is inside tranche B's definition of done in the plan's own milestone
table, and the plan is where a tranche B builder reads what to capture. A canary that lives only in a
body cannot catch a deleted link post at all, because the body was always empty.

**Fix:** add the deleted link post to the fixture list in `docs/PLAN.md` § Testing strategy and add
"in a title and a body" to the compliance-canary parenthetical in the same section.

### 4. `probe` has no sub-modes in the plan, so tranche B cannot capture the fixtures it needs — MEDIUM

The ingest panel D-14 is an **Add**: "`probe <fullname>` only … Parity, anchor, clamp, quarantine, and
redirect fixtures need listing/tree/about/search captures, and the fixture format must be the one the
fake loads. Add the sub-modes in C; `probe --save-fixture` and `FakeRedditGateway.from_fixture` share
one schema module."

`docs/PLAN.md` § CLI commands has one row: "`insightminer probe <fullname> [--save-fixture]` | Dump
raw JSON for an item". A fullname-only probe cannot capture an about payload (quarantine shape,
identity change), a listing page (sticky ordering, short pages), or a search page. Four of the round's
seventeen probe cases are unreachable with it, and the shape-parity test (PA-01, an accepted rank-14
item) needs a listing capture and a tree capture of the same post.

**Fix:** widen the `probe` row in `docs/PLAN.md` § CLI commands to name the sub-modes
(`about`, `listing`, `tree`, `info`, `search`) and the shared fixture schema.

### 5. Per-source freshness is stated in the plan with the narrower population the review called the half-adoption — MEDIUM

Adversarial B8: "Freshness iterates `enabled=1 OR status!='ok'`; system-disabled sources sit in a
digest section until acknowledged", with the note that this "is the *one* freshness lesson that
transfers and it is the one half-adopted".

`docs/PLAN.md` § Silent-failure controls: "**per-source freshness**: each enabled subreddit fetched
successfully within the last two runs". That is the pre-B8 wording, unchanged from version one.

The build honours B8: `src/insightminer/db/repo.py::all_sources_for_freshness` — "Enabled sources
**plus** sources disabled by an error status. A subreddit that was auto-disabled by a failure does not
quietly leave the freshness population (ingest B8); one the operator muted by hand, with
`status='ok'`, does." `docs/TEST_STRATEGY.md` FR-01 says the same.

Why it matters: the plan is the design authority, and a subreddit auto-disabled after three redirects
or a quarantine is precisely the source nobody would notice going silent. The narrow wording invites a
future change that matches it.

**Fix:** correct the per-source-freshness clause in `docs/PLAN.md` § Silent-failure controls to the
repository's population, naming the hand-muted exception.

### 6. The plan contradicts itself on the re-tag path, keeping the heuristic the UI panel cut — MEDIUM

`docs/PLAN.md` § Web UI design rules, Writes: "re-tagging runs as the CLI subprocess with a run row,
in-process only for the read-only preview". Twenty lines later, § Routes, `/settings/themes`: "Save
re-tags (inline if quick, a background job with polling if large)".

The second is version one's wording (`PLAN_v1.md` line 244) and is exactly what UI panel D4 said to
drop: "**simplify**: retag always via CLI subprocess with a run row; keep in-process only for the
read-only preview; drop the 'inline if < 2 s' heuristic" — because it is two execution paths for one
write, one of them unlocked. `docs/TEST_STRATEGY.md` UI-38 records the ruling ("re-tag always runs as
the CLI subprocess with a run row (no inline path)").

**Fix:** delete the "(inline if quick, a background job with polling if large)" clause from the
`/settings/themes` row in `docs/PLAN.md` § Web UI routes.

### 7. Cancel is stated as SIGTERM only, against the accepted ruling — MEDIUM

UI panel D5: "Cancel via `os.kill(pid, SIGTERM)` … Fails across container PID namespaces at M4 …
**simplify** to `cancel_requested_at` on the run row polled at batch boundaries; SIGTERM as a local
extra." `docs/TEST_STRATEGY.md` UI-30 carries it. `docs/PLAN.md` § Routes `/runs` still says "Cancel
sends SIGTERM and the CLI finishes its batch", and `runs` has no `cancel_requested_at` column in the
plan's data model, so the M2 schema would not carry the field the ruling needs.

Why it matters: this is a schema consequence, and the curation migration at M2 is the natural place
for the column. Discovering it at M4, in the container, means another migration.

**Fix:** state the ruling in the `/runs` row of `docs/PLAN.md` § Web UI routes and add
`cancel_requested_at` to the `runs` row of § Data model (or to the M2 curation migration list).

### 8. The clock-skew failure-matrix row still over-claims — MEDIUM

Ingest panel D-2 marked "identical rows and decisions" **over-claimed**: "`next_check_at <= now` is
inherently a local-clock comparison, so ±1 day must change the due-set; only stop/gap/state decisions
and the stored `next_check_at` values can be identical." `docs/TEST_STRATEGY.md` RV-02 records the
scoping. `docs/PLAN.md` § Failure-mode matrix still reads "Clock skew | Identical rows and decisions
(all logic in the `created_utc` domain)", identical to version one.

Why it matters: the matrix header says "each row is a test", and M1c writes RV-02. A builder writing
the test from the matrix row writes an assertion that cannot hold, and the cheapest way out of a
failing assertion is to weaken it — the pressure the working agreement exists to remove.

**Fix:** reword that row in `docs/PLAN.md` § Failure-mode matrix to "Identical state, stop and gap
decisions and `next_check_at` values; the due-set legitimately differs".

### 9. The Host check reads as mutation-only — MEDIUM

UI panel D7: "Host check described only for state-changing requests. DNS rebinding is a read attack.
**add** Host check on every request (UI-22)." `docs/PLAN.md` § Web UI Security puts the Host clause
inside the mutation sentence: "middleware rejects state-changing requests unless `Sec-Fetch-Site` is
same-origin, falling back to `Origin`/`Referer` on plain HTTP, and `Host` is allowed". Version one
read the same way, so this is a recommendation that was never folded in rather than a rewrite loss;
`docs/TEST_STRATEGY.md` UI-22 keeps it alive as planned work for M2.

**Fix:** split the Host check into its own clause ("`Host` is checked on every request") in the
Security row of `docs/PLAN.md` § Web UI design rules.

### 10. `last_visit_at` survives as the `ui_state` example after the feature was dropped — LOW

DECISIONS § 6: "`[NEW]` badge | First seen in the latest *completed* run only; **no 'since last visit'
toggle**". `docs/PLAN.md` § Data model: "| `ui_state` | key, value | e.g. `last_visit_at` |" — the
example key is the dropped mechanism's key, carried unchanged from version one. This is the class the
brief names: a settled negative a fresh reader would re-derive, here from the schema itself.

**Fix:** change the example in the `ui_state` row of `docs/PLAN.md` § Data model to a live key (for
instance the appearance settings), and consider a retired-claims row for `last_visit_at`.

### 11. The decisions log says the commercial-use stance is both settled and pending — LOW

D-32 (2026-09-15): "The commercial-use stance that was Wes's own open item is settled as 'none'."
DECISIONS § 7 item 4 still reads: "Commercial-use stance for a coworker at the company that makes
Premiere Pro (the research report calls product-decision insights a grey area)." Items 2 and 5 of the
same list carry their closing annotations; item 4 does not. The stance answers adversarial E18 and
risk G3, so a reader checking whether the round's question was ever answered can land on the wrong
line.

**Fix:** annotate item 4 of `docs/decisions/DECISIONS.md` § 7 in place, the way items 2 and 5 are
("closed 2026-09-15 by D-32: all use is personal").

### 12. One adopted guard-design rule is missing from the plan's table — LOW

`DB_LEARNINGS_APPLIED_2026-09-12.md` § 2 rule 5: "Probe each item the way a real record would present
it: input shape is part of the contract." The plan's § Guard design rules table has ten rows and not
this one; version one's table did not have it either. It is alive in `docs/TEST_STRATEGY.md` § 5 item
11 ("fixtures come through `probe`, tombstones through the real scrub stage (M1c), bot rows through
`normalize_post()` and `normalize_comment()`"), which is where the panels applied it.

**Fix:** add the row to the § Guard design rules table in `docs/PLAN.md`, since that table is what
`CLAUDE.md` routes a guard author to.

### 13. Two routine CLI commands have neither a UI control nor a recorded exclusion — LOW

UI panel D14 asked for Download config and Regenerate digest controls "so the operator-complete gate
has nothing to exclude beyond the four commands". DECISIONS § 6 records four exclusions (`serve`,
`probe`, `db init`, `db downgrade`); `docs/PLAN.md` § CLI commands lists `config show/export/import`
and `report [--date]`; § Routes `/system/maintenance` offers import but no config download and no
digest regeneration. As specified, the operator-complete gate (UI-50) is red at M2 for two commands.
It is recorded as an open owner question in `docs/TEST_STRATEGY.md` § 6 question 22, so nothing is
lost — it is simply unresolved with an M2 deadline.

**Fix:** either add the two buttons to the `/system/maintenance` row of `docs/PLAN.md` § Web UI
routes, or add the two exclusions with reasons to DECISIONS § 6.

### 14. The expansion cap is stated one way and still open the other — LOW

Ingest D-3 ruled the cap is "the per-fetch maximum … drop any cumulative reading". `docs/PLAN.md`
§ Collector step 2 says "`comments.per_post_expansion_cap` per post", which is the cumulative reading,
and `config/settings.yaml` carries the bare value. `docs/TEST_STRATEGY.md` TR-02 records the ruling
and flags it "pending Wes", and § 6 question 18 keeps it open. M1b is the milestone that has to
choose.

**Fix:** either resolve it and say "per fetch" in the plan's collector step 2, or mark the phrase as
pending the way the test strategy does.

## What I could not check

- **Whether every "carried elsewhere" item is reachable in practice.** I verified each has a home and
  that `CLAUDE.md` § Routing sends the relevant task at that document, but whether a builder follows
  the pointer is review, not something I can test. Eighteen items rest on it.
- **The second half of the rounds** (the records held by the other seat), so items those rounds
  revoked or superseded may make some of my "contradicted" calls stale. I looked for revocations in
  the decisions log and found none for findings 1–10.
- **`docs/TEST_STRATEGY.md`'s own accuracy** against the tree. I took its "shipped" rows at face value
  except where I read the code (findings 1, 2, 5), where it agreed.
- **The runbook and the harness page beyond the sections I grepped** (migrations, backups, cancel),
  so an item I call "not found" might sit in a runbook section I did not read. I read RUNBOOK §§ 3–5
  fully and grepped the rest.
- **Whether the plan's silences are deliberate.** Version two's own note says it "states the current
  shape only", so some omissions are editorial. I treated an omission as a finding only where the
  omitted thing changes what a builder would write.

## Verdict

**The claim does not hold as stated, but it holds in substance for all but a handful of items.**

Of 185 extracted items, 158 are stated by plan version two or the decisions log and 18 more are
stated by a document the plan routes to. The rewrite did not lose the rounds' work: every settled
negative, every cut, and every compliance bound I could trace has a home with its reason, and the
decisions log is unusually disciplined about recording declines as declines.

Three things break the claim. First, the plan's content-state-machine paragraph **contradicts the
built, tested state machine** on unknown removal categories and **drops the deleted-link-post rule**
that version one carried, re-stating in its place the sentence that produces the bug the adversarial
review found (findings 1 and 2). Second, two probe-day requirements — the deleted link post and the
title canary — and the `probe` sub-modes are missing from the plan at the exact moment tranche B is
about to run the probe day (findings 3 and 4). Third, four accepted rulings are contradicted by plan
prose that survived the rewrite unchanged: per-source freshness (finding 5), the re-tag path (6), the
cancel mechanism (7), and the clock-skew claim (8).

Every one of these is a paragraph-level correction in `docs/PLAN.md`, and findings 1–4 should land
before tranche B's probe day rather than after it, because the probe day is where the missing fixture
cases become expensive to add.

**Confidence: high** on findings 1, 2, 3, 4, 5 and 6, each resting on a quoted contradiction between
two documents or between a document and the code. **Medium** on findings 7–9, where the plan's
wording is narrower than a ruling but not flatly opposed to it, and a reader could argue the ruling
survives by implication. **High** that nothing version two dropped is homeless: every gap I found is
either stated somewhere else in the tree or is an open item with a recorded owner question.
