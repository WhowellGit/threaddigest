# Decisions — settled choices, settled negatives, and their revisit triggers

> Append-only; each entry carries a date and a **revisit when**. Before proposing an alternative to anything below, read the entry and its trigger: if the trigger has not fired, the decision stands and is not re-derived. Sources: `docs/PLAN.md` (decisions table, "Corrections from the test-strategy panels", "Adversarial review: what changed", "Decisions taken on the reviewers' open questions"), `docs/insights/INSIGHTS_2026-09-12.md`, `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` § 3 and § 5.
>
> Status: **settled** unless a row says **pending Wes** (a recorded recommendation awaiting confirmation; open items are listed in § 7).

## 1. Settled choices (the plan's decisions table, Q&A 2026-09-12 and 2026-09-13)

| # | Date | Decision | Choice | Revisit when |
|---|---|---|---|---|
| D-01 | 2026-09-12 | Communities (v1) | r/premiere, r/VideoEditing, r/editors; optional r/AfterEffects, r/DavinciResolve. Names are case-insensitive (r/videoediting *is* r/VideoEditing); r/AdobePremierePro likely does not exist | The digest shows Premiere discussion concentrated elsewhere, or a saved search (M3) discovers a subreddit with sustained volume |
| D-02 | 2026-09-12 | "Themes" | Three concepts: subreddit **sources** (polled completely), **themes** (named keyword/regex rule groups tagging posts locally), **saved Reddit-wide searches** as a third source type (M3). #1 priority: surface top Premiere Pro quality issues | Theme precision (M2 per-tag feedback, M3 labeling packet) stays below what the digest needs, or the M5 LLM layer supersedes keyword rules |
| D-03 | 2026-09-12 | UI stack | FastAPI + Jinja2 + HTMX, old-Reddit density, no JS build step | A page needs client state HTMX cannot express; never for density reasons |
| D-04 | 2026-09-12 | Deleted/removed content | Scrub text + author, keep the ID row as a tombstone, render `[deleted]`/`[removed]`; deleted text must not survive in DB, raw files, or exports (bounds in § 2) | Reddit's Data API terms change. Never loosened |
| D-05 | 2026-09-12 | Comment harvesting | Full comment trees for every captured post by default, per-run request budget (1,500), revisit ladder 1/3/7/30/365 d, 16 expansions per pass, per-post cap 40 | The budget cannot drain the due queue for 7 consecutive runs, or the first backfill measures a different requests-per-post cost |
| D-06 | 2026-09-12 | Hosting sequence | All-local on this Mac → Docker on Mac → QNAP Container Station → (optional, lowest priority) remote access via Tailscale | The Mac stops being always-on, or Container Station cannot run the image |
| D-07 | 2026-09-12 | Reddit account | New dedicated account created by Wes; read-only API use; no password stored | Never for the password grant (§ 3). Account only if Reddit requires re-registration of the app |
| D-08 (amended 2026-09-13, see the late section) | 2026-09-13 | Project home | `~/repos/insightminer` for repo and data (outside TCC-protected folders; no spaces in the path); `the archive at ~/repos/insightminer-desktop-archive/Reddit (originals; canonical copies live in docs/reference)` stays the documents folder | The M0 two-minute launchd test job contradicts the TCC constraint on this Mac (the move stands regardless; the *lesson* would be corrected) |
| D-09 | 2026-09-13 (amended late 2026-09-13) | Top-issue ranking | Distinct authors first, then comment count, then score; never raw post count; one function shared by digest, theme pages, export. Amendment: count distinct `author_fullname`, never display name; exclude NULL (scrubbed and account-deleted rows) rather than collapsing them into one bucket; every ranked list prints the identity coverage of the ranked set and annotates rows from incomplete trees, because a proxy's coverage gaps become ranking errors (the earlier project demoted a bucket that hit ~314 devices as a fluke because its reach field was NULL on old builds) | The M3 labeling packet shows the ranking mis-orders issues Wes judged |
| D-10 | 2026-09-12 | Failure alerts | macOS notification + red status banner; the UI status pill computed from `runs` is the canonical alert (2026-09-13); Healthchecks.io ping from M1d is the dead-man; ntfy optional later | M4 (container has no `osascript`); or Wes stops reading the pill |
| D-11 | 2026-09-12 / 13 | Enforcement model | Private GitHub repo; required green CI on `main`; agent opens PRs and merges when green; Wes reviews at will and can flip to human-only merges any time. Human review on enforcement surfaces (CODEOWNERS) **declined 2026-09-13**; compensating controls: positive controls, hard-block hooks, PR bodies listing changed tests, adversarial review, quarterly guard review. Honest status: until the token and plan questions in § 7 are settled, CI is a gate with a git trail, not an enforcement authority | Wes wants human-only merges; the GitHub plan lacks branch protection on private repos; or a loosening merges without a human seeing it |
| D-12 | 2026-09-12 | TDD policy | Layered: test-first for `core/`, `services/`, migrations; probe-first for the Reddit adapter; route tests written alongside UI templates; every bug fix starts with a failing test | A layer's escaped-bug pattern shows the approach misfits it (e.g. adapter bugs escaping cassettes) |
| D-13 | 2026-09-12 | External research | One targeted report on engineering controls for AI-assisted codebases, run by Wes in parallel with M0; findings folded into the gates before M1 feature code | The report arrives (fold in), or it has not arrived by M1 start (proceed without) |
| D-14 | 2026-09-12 | QNAP scope | Only this system: collector + web on one compose file; volume and `runs` table designed so services can be added later | M5 analysis worker joins as a third service |
| D-15 (superseded 2026-09-13, see the late section) | 2026-09-12 | Raw JSON | `raw_json` column per row (scrubbable, long-term store) + per-run JSONL kept 30 days, compressed, rewritten on scrub. **JSONL sidecar pending Wes** (adversarial recommendation: cut; schema rev 1 omits `raw_files` so it stays reversible); `raw_rejects` keeps the same 30-day retention | Wes decides on the sidecar (open item 2). If kept: at M1c when the rewrite-on-scrub cost is measured |
| D-16 | 2026-09-12 | Compliance cadence | Full bulk re-check of every stored item every 2 days while it fits the budget; automatic fallback to tiers (ladder ≤30 d; weekly posts + monthly trees to 1 y; monthly beyond), announced in the digest; all configurable | The full sweep exceeds the budget (automatic), or Reddit's guidance changes |
| D-17 | 2026-09-12 | GitHub | Wes creates the empty private repo `WhowellGit/insightminer` and pastes the URL; the agent connects, pushes, sets branch protection | The repo is shared with a coworker (then access model and token scopes are re-read) |
| D-18 | 2026-09-12 | Name | `insightminer` for repo, package, CLI, and User-Agent app id `com.wesmax.insightminer` | Scope widens beyond Reddit (the name is neutral; the UA id must stay honest) |
| D-19 | 2026-09-12 | Research timing | Wes runs the report in parallel with M0 scaffolding | (See D-13) |
| D-20 | 2026-09-12 | LAN access (M4) | UI open on the home LAN without a password; same-origin middleware still applies (with `Origin`/`Referer` fallback on plain HTTP); `INSIGHTMINER_UI_PASSWORD` enables basic auth. Threat model in § 5 | Anyone outside the household is on the LAN, the UI is reachable beyond it (Tailscale), or a coworker hosts it |
| D-21 | 2026-09-12 | Interim browsing | Read-only Datasette (`mode=ro`) over the same DB between M1 and M2 | Retire as the primary browser at M2; keep as the power view |
| D-22 | 2026-09-12 | Guard design rules | Adopted from the earlier project: shape over list, invariant over proxy, positive control per gate (scoped 2026-09-13 to post-run invariants; unit test for CI ratchets; "last seen red" line for external controls), fail never skip, zero-suppression baseline, hold the count | Each quarterly guard review |
| D-23 | 2026-09-12 | Git identity | `Wes Howell <wes@weshowell.com>` for the project repo (GitHub account WhowellGit) | An audit needs agent-vs-human attribution (enforcement panel proposes an `Agent:` trailer or a second identity; pending Wes) |
| D-24 | 2026-09-12 | Python version | 3.13 pinned via `uv`; informational 3.14 CI job | The 3.14 job is green for 4 consecutive weeks (pin moves up) |
| D-25 | 2026-09-12 | Database engine | SQLite (WAL, FTS5) with dialect-specific code isolated in `db/` behind a `SearchIndex` port and a `backup` module; upserts `ON CONFLICT DO UPDATE`; raw SQL outside `db/` banned by ruff `TID251` | Any trigger in § 4 fires |
| D-26 | 2026-09-12 | Version control | Local git from the first commit; GitHub remote added as soon as it exists and doubles as the off-site backup while the SMB backup server is down; pre-push hook runs `make check` (fast subset proposed, pending Wes); nightly `git bundle` plus data backup to the NAS once the share is back | The SMB share returns (add the NAS backup); the pre-push cost slows the push loop (E13 fast subset) |
| D-27 | 2026-09-12 | Reference corpus | `docs/` with `INDEX.md` router, append-only insights and learnings, prune-stale `STATUS.md`, path-scoped rules; currency test shrunk to the INDEX↔docs check (2026-09-13); agent transcripts never committed, only curated documents | A quarterly review finds the corpus turning into agent exhaust (prune), or `GUARDS.md` grows faster than guards fire |
| D-28 | 2026-09-13 | Operator surface | The web UI is the operator surface for every routine action; the CLI exists for schedulers, containers, tests, and break-glass; both call the same service functions; the CLI mirrors the UI, never the reverse | Never; a routine action without a UI control is a bug (operator-complete gate UI-50) |

## 2. Compliance bounds (2026-09-13; written down instead of over-claimed, **pending Wes confirmation**, open item 3)

| Bound | Value | Why this and not "within 48 h / nowhere" |
|---|---|---|
| Purge latency, items ≤ 30 days old | Scrubbed within **48–72 h** of the Reddit deletion (2-day reconcile cadence plus the daily 06:30 run window); the reconcile-age invariant allows **60 h** | The old claim "within 48 h" was arithmetically false with a daily run |
| Purge latency, 30 days to 1 year | Within **8 days** (weekly tier) | Tier fallback is announced in the digest; the per-tier invariant replaces one 48 h invariant that would be red forever after fallback |
| Purge latency, beyond 1 year | Within **35 days** (monthly tier) | Same |
| Backups | **No backup older than 14 days is retained** (daily/weekly `VACUUM INTO` and pre-migration copies alike); under the retention sweep; the canary asserts file ages | A backup made before a scrub holds the text until it ages out; nothing rewrites backups |
| Exports | **No export older than 7 days is retained**; exports carry live-content JSONL only | Same reasoning; the `raw_json` column is the long-term store |
| `raw_rejects` (the JSONL sidecar was cut on 2026-09-13) | 30-day retention; every retained line for a scrubbed item is rewritten to a tombstone in the same scrub call; compressed files verified before the plain file is deleted | Second compliance surface; the reason the sidecar is recommended for cutting |
| Digests | Computed from the DB as a route (`/reports/{date}`), written to a file only on request; **supersedes** the 2026-09-12 "digest files kept 14 days" | A persisted digest could quote a title deleted the next day |
| Crosspost parent text | Stripped to `{id, subreddit}` at ingest | The parent lives in an unmonitored sub and is never reconciled |
| Edits | An event: reconcile upserts the full normalized row so an edited body replaces the old one in DB, FTS, and `raw_json` | Otherwise a 45-day-old edit removing a name would never propagate |
| Banned or private subreddits | Private: keep data, stop polling, mark stale. Banned: items confirmed gone via `info()` are scrubbed (strict reading); policy flag exposed | (2026-09-12 reviewer question) |

## 3. Settled negatives (do not rebuild these levers)

| # | Date | Not doing | Because | Revisit when |
|---|---|---|---|---|
| N-01 | 2026-09-12 | **No Datasette-only UI** | Intuitive browsing and in-UI management of what is monitored are explicit requirements; Datasette stays the read-only power view and the M1–M2 interim browser | Never for the primary UI |
| N-02 | 2026-09-12 | **No VPS for the fetcher** | Datacenter IPs are treated worse by Reddit; home IP preferred. Remote access, if ever, is Tailscale to the QNAP; a VPS would only host a read-only UI copy | Reddit's stance on residential vs datacenter IPs changes, documented |
| N-03 | 2026-09-12 | **No PRAW password grant**; read-only mode with `client_id` + `client_secret` only | Read-only is all the system needs; no account password is stored anywhere | Never |
| N-04 | 2026-09-12 | **No `INSERT OR REPLACE`**; upserts are `INSERT … ON CONFLICT(reddit_id) DO UPDATE` | It deletes and re-inserts, burns rowids, fires no delete triggers, and detaches FTS rows (the earlier project lost 16,813 rowids; verified again 2026-09-13) | Never |
| N-05 | 2026-09-12 | **No comment-proximity markers**; justifications live in syntax (`reason="#123 …"`, decorators, rule codes) | A check a comment rewrap can defeat measures formatting, not risk | Never |
| N-06 | 2026-09-12 / 13 | **No boolean safety bypasses**: no flag skips reconcile or scrub; `--budget` hard-capped at 5,000; a bypass flag such as `--no-comments` or a stage-only command records a written reason on the run row | A boolean off-switch silently disabled a safety mechanism fleet-wide in the earlier project; the actual lesson is "ceiling + written reason", not "no flag" | Never for reconcile/scrub |
| N-07 | 2026-09-13 | No `mode=ro` engine for web page routes | The web legitimately writes six tables; one rw engine behind a repository limited to the writer map; `mode=ro` for Datasette only | A second web writer appears outside the repository (then the writer-map test, not a second engine) |
| N-08 | 2026-09-13 | No freshness anchor (live `/new?limit=1` vs watermark) | The sweep *is* the live listing in the same run; per-source zero-new detection catches what remains at zero requests | A stale-work-list failure mode appears (two sources of truth), as in the earlier project |
| N-09 | 2026-09-13 | No test-count floor as a gate | A count metric (delete one parametrized test, add ten trivial ones: green); coverage covers "test dir excluded". The enforcement panel's assert-count and collected-test floors under the loosening protocol are the replacement | A test-deletion incident that the coverage ratchet and the loosening protocol both missed |
| N-10 | 2026-09-13 | No mutation-kill-rate ratchet; mutation testing is an optional monthly tool, never a gate | A blocking kill rate would be met with equivalent-mutant suppressions, the grandfathering failure in new clothes | Never as a ratchet |
| N-11 | 2026-09-13 | No 50k/500k stress corpus; four `EXPLAIN QUERY PLAN` index assertions instead | The value is real indexes, not scale; data grows 1–2 GB a year | A hot query regresses in production despite green plans |
| N-12 | 2026-09-13 | No launchd dead-man for the launchd run | A launchd job cannot watch a launchd failure in its own domain; Healthchecks.io ping from M1d | Never |
| N-13 | 2026-09-13 | No runtime schema fingerprint that refuses to run; warning only on `doctor` and `/system`, ordinary tables only, derived by one normalizer from live `sqlite_master` and the packaged `schema.sql` (no stored constant) | `ANALYZE` and FTS shadow tables move the hash; a false positive would stop the daily collector; `alembic_version` and models-vs-DDL remain the gate | A hand-edited DB incident that the warning did not surface |
| N-14 | 2026-09-13 | No hand-maintained bot list | The earlier project's project bots had to be *found*; heuristic surfaced in the UI as "suspected bots" with one-click confirm, flagged per author and never inherited by a megathread's comments | Never as a list |
| N-15 | 2026-09-13 | No hand-typed "catches since" in `GUARDS.md`; derived from CI failures posted to a pinned issue | A typed catch count is narration | Never |
| N-16 | 2026-09-13 | No three hard-block hooks; two ship (no `--no-verify`/direct push to `main`; no hand edits to `.ratchets/` or the hook settings), self-protecting, failing closed | A `PreToolUse` hook has no PR context; command-text matching of "writes to the production DB" is list-policing; the CLI's own destructive gate covers that ring | Never beyond two |
| N-17 | 2026-09-12 | No `unittest.mock.patch` outside `tests/adapters/`; no `time.sleep` in tests; no network in tests | Behavior is tested through the fake gateway, real temp DBs, and an injected `Clock` | Never |
| N-18 | 2026-09-12 | No Windows support | Out of scope unless a coworker needs it; `fcntl` stays behind a clear error | A coworker on Windows |
| N-19 | 2026-09-13 | No CHANGELOG ceremony beyond the version string (adversarial cut list) — **pending**; the plan still lists `CHANGELOG.md` | Reddit blocking a bad version needs only the UA version | Wes rules |
| N-20 | 2026-09-12 | No new abstraction without two concrete uses; four layers only (`web`/`cli` → `services` → `db`/`adapters` → `ports` → `core`) | Over-abstraction is the named AI-assisted failure pattern | Never |

## 4. Postgres exit: the triggers

SQLite stays until one of these is true; none is expected before M5, and the move is a contained job of a few days (a `tsvector` `SearchIndex`, a `pg_dump` backup module, a data copy) because every SQLite-specific statement lives inside `db/`:

1. Concurrent **writers on different hosts** (the flock plus `runs` rows cannot coordinate across machines).
2. A **multi-user web app** (more than one operator writing settings at once, or a public-facing UI).
3. Data in the **hundreds of gigabytes** (the earlier project ran SQLite past 700 GB; its pain was process discipline, not the engine, so this is a soft trigger).
4. Not a trigger: analytics. Datasette and DuckDB read the file directly.

Note (adversarial E16): SQLAlchemy exposes `ON CONFLICT DO UPDATE` per dialect (`dialects.sqlite.insert` vs `dialects.postgresql.insert`), so the exit also touches `db/repo.py`; that is inside `db/` and within the estimate.

## 5. Threat model for the LAN UI (2026-09-13)

**Operator error.** The typed confirmation word on destructive controls is a mistake guard, not an authorization guard. Anyone on the home LAN could type `restore`; that is accepted for a household network. Basic auth on `/system/*`, `/setup`, and delete routes is available by one environment variable (`INSIGHTMINER_UI_PASSWORD`) if the model changes. `/setup` credential POSTs on the LAN without a password: **pending Wes** (recommendation: loopback-only unless the password is set). Revisit when D-20's trigger fires.

## 6. Decisions on the reviewers' open questions (2026-09-12) not already covered above

| Question | Decision | Revisit when |
|---|---|---|
| Cassettes with third-party content | Private repo; prefer recordings from a personal restricted test subreddit seeded by hand | The repo goes public |
| Tree JSON shape | PRAW-attribute JSON for trees, wire JSON for listings and `info()`, shape recorded per line; one canonical dict before `core.normalize`; shape-parity test. **Disputed** by the adversarial review (fetch trees via `reddit.request()` and delete the second shape): decide at M1b after the probes | M1b |
| Initial backfill | Full 1,000 posts per sub with trees, drained by the daily budget or one interactive `--budget 5000` run | The first backfill measures cost |
| Score snapshots | Numeric `item_snapshots` in v1 (cheap; enables M5 trend work) | Never |
| Regex rules in the UI | Allowed, via `regex` with `timeout=`, length cap, server-side compile check | A ReDoS incident |
| Timezone | Storage in UTC epoch seconds; display and "daily" boundaries in the Mac's local timezone (configurable) | Never |
| Secrets in Docker | `env_file` outside the image; never in YAML exports or the export zip; each person registers their own Reddit app | Never |
| Exit codes (proposed 2026-09-13) | 0 ok, 1 failed, 3 partial, 4 rate-limited, 75 locked, 78 config/auth, 130 cancelled; `partial` produces a digest line, not a notification. **Pending Wes** | Open item 5 |
| `[NEW]` badge | First seen in the latest *completed* run only; no "since last visit" toggle | Wes asks for it |
| Stale-run threshold | One settings key shared by collector and UI, 3 minutes given 5-second stage-bearing heartbeats; a held flock means alive regardless of heartbeat age; `queued` rows older than 2 minutes without a pid become `failed` | A run legitimately pauses longer than 3 minutes without heartbeating |
| Operator-complete gate exclusions | `serve`, `probe`, `db init`, `db downgrade` excluded with recorded reasons | A new non-routine command is added (needs its own reason) |

## 7. Pending Wes (recommendations recorded; not decisions yet)

1. GitHub plan allows branch protection on a private repo (Free does not; Pro does); agent token without `administration`/`workflows` scopes after M0.
2. ~~Keep or cut the per-run JSONL sidecar~~ cut, 2026-09-13.
3. Confirm the compliance bounds in § 2 as written.
4. Commercial-use stance for a coworker at the company that makes Premiere Pro (the research report calls product-decision insights a grey area).
5. Exit codes as proposed in § 6.
6. The owner questions consolidated in `docs/TEST_STRATEGY.md` § 6 (loosening approval mode, perimeter width, pre-push scope, `/setup` on the LAN, purge semantics, restore-drill automation, and the rest).


## 2026-09-13 (late) — workspace lifecycle and curation controls

- **Workspace removal:** archive (keep data, stop polling, hide) or delete (destructive gate; removes only data reachable through no other workspace; purge counts recorded). Compliance reconcile is workspace-agnostic. Revisit when: a second workspace exists and shares a source.
- **Curation in the UI:** manual tag overrides never removed by re-tagging; watch/pin a thread past the ladder; promote a rising phrase into a rule; theme rename/merge; ad-hoc Search Reddit with "monitor" / "harvest" actions; per-tag thumbs feedback. Schema revision 2 (at M2) adds `workspaces.archived_at`, `post_themes.origin`, `posts.watch_until` in one migration, exercising the per-revision fixture path for the first time.

## 2026-09-13 (late) — sidecar cut; owner-handled items; redaction

- **Per-run JSONL sidecar: cut** (Wes, 2026-09-13). `raw_json` per row is the single raw store; `probe --save-fixture` captures exact wire payloads for fixtures; `insightminer export` produces live-content JSONL on demand. Removes `raw_files`, the sink adapter, compression/retention/rewrite-on-scrub, and their invariants and tests (JS-01/02, DB-34/35). Revisit when: a debugging need for exact-wire logs actually arises (then a bounded, ignored-by-default debug log, not a compliance surface).
- **Compliance bounds and the commercial-use stance:** Wes is handling these himself outside the plan; the plan keeps the bounds as written until he says otherwise.
- **Earlier-project retrospectives:** redact significant areas (Wes, 2026-09-13): internal identifiers, people, tickets, hosts, paths, service accounts. Originals stay only in the local archive outside the repo. Note: pre-redaction copies remain in local git history; rewrite or accept before the first push.
- **Agent model tiers** (Wes, 2026-09-13): the main session (the main session) plans, synthesizes, and decides; Opus sub-agents for complex or judgement-bearing work (reviews, judges, migrations, deletion and scrub, under-specified services); Sonnet sub-agents for well-specified mechanical work (inventories, scans, codemods, spec-driven tests). Every sub-agent call names its model. **Why:** every sub-agent had inherited the main session, which was overkill and exhausted the session limit mid-workflow. **Revisit when:** an Opus verifier catches a Sonnet miss twice in a row for one class of stage; that class moves up. Recorded in `PLAN.md` § Review harness and `CLAUDE.md`.
- **Theme "precision" is reserved for the blind packet** (2026-09-13, from the retrospectives' fourth reading): the M2 per-tag thumbs surface is operator feedback ("k of n judged"), an operating signal and never the grade, because a reviewer who has already seen the tag is anchored; the M3 packet is stratified by rule, keeps "unsure" in the denominator, writes its pass bar before any label is seen, and hides which rule tagged a post until Wes has judged it. `PLAN.md` § adversarial changes, § curation controls, § M3, and `TEST_STRATEGY.md` CU-07 corrected in the same change. **Revisit when:** never; the two numbers measure different things.
- **A settled fact changed in one place is annotated in every mirror in the same change** (2026-09-13): the adversarial review's cuts were recorded in prose on 2026-09-13 while the gates table sixty lines above kept the retired rows with live fail behaviour (eight rows contradicted this log). Swept the same evening; the rule is now in `CLAUDE.md` and the PR body names the documents swept. A mechanical superseded-claims check is proposed below, not built.
- **Earlier-project retrospectives, value assessment** (2026-09-13, late): eight readers (Sonnet for six files, Opus for two), an Opus judge, and an Opus critic found 15 residual transferable insights (4 high) plus 8 process gaps after three prior passes; residual value judged **low**; judge and critic recommend *distill and remove*; the dissent (fourth reading still found two live specification errors; narrative value reported by five readers; the "mistracked, not untracked" product reframe) is recorded in `LEARNINGS_TRANSFER.md` §7. **Disposition of the raw files: Wes decides**; nothing removed or redacted yet. The residuals are distilled in `LEARNINGS_TRANSFER.md` §7, the two corrections are applied, and the new mechanisms are listed there as proposals.

### Pending (added late 2026-09-13)

- ~~Which question the #1 priority answers~~ **Decided 2026-09-13 (Wes):** the digest's job is the original one: monitor Premiere Pro complaints, make managing them easier, and extract useful insights, above all by piecing together the scattered, vague, non-technical reports into the story of the actual user problem (customers do not think like engineers and rarely give enough detail; assembling that story is the biggest gap in support). The "known but under-weighted" framing from the earlier project is a good idea kept **separable and optional**, not a design driver, and there is no plan to connect Insight Miner to the earlier project's data sources: they are different projects. Recorded as D-28.
- **Proposed mechanisms from the residual scan, Wes's rulings 2026-09-13:** `hard_after=` on relaxed ratchet lines: approved on the recommendation ("seems early, but if small cost, no problem"); build as a small change to `tools/ratchet.py` with a gate test. Duties record: approved, kept light (one table, ages on `/system`, one digest line) at M2. Disposition on every amber: **not adopted**; Wes's reading is that warnings in his environment often never reach him and get dismissed by agents, so the fix is enforcement, not a dismissal button; adopted instead as D-29 (nothing in the development gate is advisory; product ambers are derived state no agent can clear). The two ratios at quarterly review: approved. The superseded-claims doc check: approved by Wes later that evening and built as G34 (`tests/gates/test_superseded_claims.py`, the Retired claims table below). Spec refinements that add no mechanism go into the tranche briefs at M1b to M2.
- ~~Raw retrospectives disposition~~ **Decided 2026-09-13 (Wes, option 4):** keep the three narrative files redacted, move the other five to the archive, rewrite local history before the first push. Executed the same evening; `REDACTION_NOTE.md` in the folder records it.
- **D-28, product intent restated** (Wes, 2026-09-13): Insight Miner monitors Premiere Pro complaints on Reddit to make managing complaints easier and to extract useful insights; the hard, valuable part is assembling the story of the actual user problem from scattered, vague reports. The earlier project's "known but under-weighted" capability stays separable and optional; no bridge to the earlier project's data sources. **Why:** Wes's original intent; a different project from the earlier one. **Revisit when:** the M5 analysis layer is designed (that is where story-assembly across posts lives).
- **D-29, nothing advisory in the gate** (Wes, 2026-09-13): every development-time check either fails the build or lands in a ledger that needs an approval; agents cannot dismiss a warning. Product-side ambers (`partial` runs) are derived from the run row and shown on the UI pill and in the digest; no agent can clear them. **Why:** Wes's experience is that warnings do not reach him and get dismissed by agents; the earlier project's unenforced builds, duplicate builds, and silent failures came from exactly that gap. **Revisit when:** never for the development gate; the product-side dismissal control is reconsidered once Wes has used the UI.
- **Learnings are extracted, systems are not blended** (Wes, 2026-09-13): the earlier project's harness, database, and working practices are source material for lessons; Insight Miner adopts practices on their own evidence and does not import the harness or connect to that system. **Why:** Wes's stated intent, after the harness assessment was framed as "carry forward"; different projects.
- **Prune the reference material** (Wes, 2026-09-13, queued): remove documents or sections that are useless here or that could lead the project down the wrong road again, in the repo and in the archive; Wes approves the removal list first, since the living originals exist only in his earlier project's repo. **Why:** "we've written a lot of things down, and it often doesn't get enforced"; material that misleads is worse than material that is missing.

## Retired claims (machine-read)

Read by `tests/gates/test_superseded_claims.py` (G34): any line of a live document (everything under `docs/` except `reference/`, `insights/`, and this file) that mentions one of these phrases must carry, on the same line, a retirement marker: a `D-NN`/`N-NN` id or a word such as cut, retired, superseded, downgraded, dropped, deferred, declined, replaced. Add a row whenever a decision retires a named mechanism. Keep phrases specific enough not to match legitimate live text.

| Phrase | Retired by | Since |
|---|---|---|
| `per-run JSONL` | D-15 superseded (sidecar cut) | 2026-09-13 |
| `raw_files` | D-15 superseded (sidecar cut) | 2026-09-13 |
| `freshness anchor` | N-08 | 2026-09-13 |
| `test-count floor` | N-09 | 2026-09-13 |
| `kill rate` | N-10 | 2026-09-13 |
| `stress scenario` | N-11 | 2026-09-13 |
| `stress corpus` | N-11 | 2026-09-13 |
| `launchd dead-man` | N-12 | 2026-09-13 |
| `dead-man's switch` | N-12 (the launchd job; Healthchecks.io remains) | 2026-09-13 |
| `at most three` | N-16 (hard-block hooks) | 2026-09-13 |
| `notifier proof` | adversarial review downgrade, PLAN § adversarial changes | 2026-09-13 |
| `trailing-median` | deferred to M3, PLAN § adversarial changes | 2026-09-13 |
| `trailing 7-run median` | deferred to M3, PLAN § adversarial changes | 2026-09-13 |
| `CODEOWNERS` | declined, PLAN decisions table (enforcement model) | 2026-09-13 |
| `feeds theme precision` | operator feedback is not precision (late 2026-09-13 section) | 2026-09-13 |

