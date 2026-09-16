# A1 — Disposition table: plan version one → version two

Method note: every heading, paragraph, table (as one unit, plus one row-unit per row for tables over five rows), list item, and fenced block in `PLAN_v1.md` is numbered `v1-001` upward in document order and given a disposition. Classifications are mechanical judgments about *where content went*, not about whether the loss matters — that is for the next seat. Quotes are kept short (five to twelve words) and used only where they decide the classification.

Legend: **carried** = same content present in v2, same or reworded. **moved** = content now lives in the decisions log, overview, or harness page. **reduced** = v2/log keeps the fact but drops stated details (listed). **absent** = no home found anywhere searched. **superseded** = v2 or the log says explicitly this was changed/retired, with the entry id.

## Table

| v1 id | v1 section | unit type | disposition | home (v2 section, or log/overview/harness section) | dropped details or key content |
|---|---|---|---|---|---|
| v1-001 | Title | heading | carried | v2 title | renamed "version 2, 2026-09-15" |
| v1-002 | Intent | heading | carried | v2 "Intent (read this first)" | — |
| v1-003 | Intent | paragraph | carried | v2 Intent paragraph | reworded around "the one question"; D-32 personal/non-commercial framing added alongside |
| v1-004 | Context | heading | carried | v2 "Context" | — |
| v1-005 | Context | paragraph (Goal) | carried | v2 Goal paragraph | "3–4 months" → "over months"; scope generalized from "Premiere Pro quality issues" to "a community" |
| v1-006 | Context | paragraph (Why this shape) | carried | v2 Why-this-shape paragraph | v2 adds the 2026-09-14 policy-pages research and Responsible Builder Policy detail |
| v1-007 | Context | table (Decisions made Q&A) | reduced | v2 "The load-bearing choices" table; DECISIONS §1 | v2's inline table cut from 30 rows to 14; full text moved to DECISIONS §1 |
| v1-008 | Context | row: Communities (v1) | carried | v2 choices row "Communities"; DECISIONS D-01 | — |
| v1-009 | Context | row: Product intent (restated) | moved | DECISIONS D-28; v2 Intent paragraph | — |
| v1-010 | Context | row: "Themes" | carried | v2 choices row "Themes"; DECISIONS D-02 | — |
| v1-011 | Context | row: UI stack | carried | v2 choices row "UI"; DECISIONS D-03 | — |
| v1-012 | Context | row: Deleted/removed content | carried | v2 choices row; DECISIONS D-04 | — |
| v1-013 | Context | row: Comment harvesting | carried | v2 choices row; DECISIONS D-05 | ladder numbers moved to config reference |
| v1-014 | Context | row: Hosting sequence | carried | v2 choices row "Hosting"; DECISIONS D-06 | — |
| v1-015 | Context | row: Reddit account | carried | v2 choices row; DECISIONS D-07, N-03 | — |
| v1-016 | Context | row: Project home | carried | v2 choices row; DECISIONS D-08 | — |
| v1-017 | Context | row: Top-issue ranking | carried | v2 choices row "Ranking"; DECISIONS D-09; v2 "From data to insight" | — |
| v1-018 | Context | row: Failure alerts | moved | DECISIONS D-10 | not in v2's condensed choices table |
| v1-019 | Context | row: Enforcement model | moved | DECISIONS D-11 | GitHub/PR-merge wording superseded (see v1-025); v2 choices row is a short paraphrase |
| v1-020 | Context | row: TDD policy | moved | DECISIONS D-12; v2 "TDD policy by layer" section | — |
| v1-021 | Context | row: External research | superseded | DECISIONS D-13 "closed... report never arrived" | — |
| v1-022 | Context | row: QNAP scope | moved | DECISIONS D-14 | — |
| v1-023 | Context | row: Raw JSON | carried | v2 choices row "Raw JSON"; DECISIONS D-15 | JSONL-sidecar half superseded (cut 2026-09-13); "single raw store" fact carried |
| v1-024 | Context | row: Compliance cadence | superseded | DECISIONS D-16 "superseded 2026-09-15 by D-30" | replaced by twice-weekly cadence |
| v1-025 | Context | row: GitHub | superseded | DECISIONS D-17; DECISIONS 2026-09-14 "Remote: GitHub deferred" | repo-creation plan superseded by QNAP-first remote |
| v1-026 | Context | row: Name | carried | DECISIONS D-18; v2 Versioning bullet | — |
| v1-027 | Context | row: Research timing | superseded | DECISIONS D-19 (tied to closed D-13) | — |
| v1-028 | Context | row: LAN access (M4) | moved | DECISIONS D-20, §5 threat model | — |
| v1-029 | Context | row: Interim browsing | moved | DECISIONS D-21; v2 "Power view" row | — |
| v1-030 | Context | row: Guard design rules | moved | DECISIONS D-22; v2 "Guard design rules" section | — |
| v1-031 | Context | row: Git identity | moved | DECISIONS D-23 | — |
| v1-032 | Context | row: Python version | carried | v2 tech-stack Runtime row; DECISIONS D-24 | — |
| v1-033 | Context | row: Database engine | carried | v2 choices row "Storage"; DECISIONS D-25 | D-25 records the 2026-09-16 drift correction (plain modules, not a port) |
| v1-034 | Context | row: Version control | moved | DECISIONS D-26 | GitHub-as-remote language superseded by QNAP-first (2026-09-14) |
| v1-035 | Context | row: Reference corpus | moved | DECISIONS D-27; v2 "Reference corpus and memory routing" | — |
| v1-036 | Context | row: Operator surface | carried | v2 choices row "UI"; DECISIONS D-28 | — |
| v1-037 | Context | paragraph (Assumptions) | reduced | v2 tech-stack table; DECISIONS D-06/D-11 | drops the standalone summary paragraph; facts distributed |
| v1-038 | Architecture | heading | carried | v2 "Architecture" | — |
| v1-039 | Architecture | fenced block (diagram) | reduced | v2 architecture diagram | "daily" → "scheduled"; drops "(later) JSONL → Claude" wording (replaced, milestone-tagged) |
| v1-040 | Architecture | paragraph | carried | v2 same paragraph | near-verbatim |
| v1-041 | Tech stack | heading | carried | v2 "Tech stack" | — |
| v1-042 | Tech stack | table | carried | v2 tech-stack table | v2 adds build-state detail in prose |
| v1-043 | Tech stack | row: Runtime | carried | v2 Runtime row | — |
| v1-044 | Tech stack | row: Reddit | carried | v2 Reddit row | v2 adds pinned-major detail (G53) |
| v1-045 | Tech stack | row: Storage | carried | v2 Storage row | — |
| v1-046 | Tech stack | row: CLI | carried | v2 CLI row | — |
| v1-047 | Tech stack | row: Config | carried | v2 Config row | v2 adds `extra="forbid"` |
| v1-048 | Tech stack | row: Web | carried | v2 Web row | — |
| v1-049 | Tech stack | row: Rules | carried | v2 Rules row | — |
| v1-050 | Tech stack | row: Tests | carried | v2 Tests row | cassette detail moved to Testing-strategy section |
| v1-051 | Tech stack | row: Quality | carried | v2 Quality row | import-linter named explicitly |
| v1-052 | Tech stack | row: Scheduling | carried | v2 Scheduling row | — |
| v1-053 | Tech stack | paragraph (Why SQLite/Postgres exit) | carried | v2 same paragraph; DECISIONS §4 | explicit "SearchIndex port" phrase dropped per 2026-09-16 drift fix |
| v1-054 | Repo layout | heading | carried | v2 "Repository layout" | — |
| v1-055 | Repo layout | fenced block (tree) | reduced | v2 repo tree | drops `CONTRIBUTING.md`; adds `.claude/`, `.ratchets/`, `memory-snapshot/`, `tools/` (not in v1) |
| v1-056 | Reference corpus | heading | carried | v2 same heading | — |
| v1-057 | Reference corpus | paragraph (Wes's earlier projects) | carried | v2 opening paragraph | reworded |
| v1-058 | Reference corpus | fenced block (docs/ tree) | reduced | v2 prose paragraph (no tree diagram) | ASCII tree dropped; folders restated in prose with the doc-contract mechanism added |
| v1-059 | Reference corpus | paragraph (Routing: CLAUDE.md...) | carried | v2 paragraph | adds doc-policy/G55 mechanism |
| v1-060 | Module map | heading | carried | v2 same heading | — |
| v1-061 | Module map | paragraph (Layers...) | carried | v2 paragraph | "web is read-mostly, never imports praw" → "web never imports cli"; mypy scope widened to whole tree |
| v1-062 | Module map | table | carried | v2 module map table | v2 adds a "State" column |
| v1-063 | Module map | row: core.normalize | carried | v2 row | adds crosspost-reduction note |
| v1-064 | Module map | row: core.deletion | carried | v2 row | — |
| v1-065 | Module map | row: core.paging | carried | v2 row | — |
| v1-066 | Module map | row: core.milestones | carried | v2 row | — |
| v1-067 | Module map | row: core.themes | carried | v2 row | adds `rules_hash` |
| v1-068 | Module map | row: core.budget | carried | v2 row | — |
| v1-069 | Module map | row: core.retry | carried | v2 row | drops rate-limit-wait-planning/defer-run clause (KI-025 removed the defer rule) |
| v1-070 | Module map | row: core.digest | carried | v2 row | tagged "built, not yet assembled from the DB (M1d)" |
| v1-071 | Module map | row: adapters.reddit_praw | carried | v2 row | tagged "tranche B" |
| v1-072 | Module map | row: adapters.reddit_fake | carried | v2 row | tagged "built"; moved above reddit_praw in table order |
| v1-073 | Module map | row: adapters.notify | carried | v2 row "notify, clock" | merged with a clock row |
| v1-074 | Module map | row: db.* | carried | v2 row | adds "schema dump" |
| v1-075 | Module map | row: services.* | carried | v2 row | tagged "built; trees, revisit, reconcile, scrub, tag, report, export follow" |
| v1-076 | Module map | row: cli | carried | v2 row | tagged with which subcommands are built |
| v1-077 | Module map | row: web.* | carried | v2 row | tagged "M2" |
| v1-078 | Data model | heading | carried | v2 "Data model (SQLite)" | — |
| v1-079 | Data model | paragraph (Conventions) | carried | v2 Conventions paragraph | adds AUTOINCREMENT and `EXPLAIN QUERY PLAN` test detail |
| v1-080 | Data model | paragraph (Table-to-writer map) | carried | v2 same paragraph | adds `db/ownership.py` file reference |
| v1-081 | Data model | table | carried | v2 Data model table | v2 adds `workspaces` and `backups` rows (new; see § New) |
| v1-082 | Data model | row: subreddits | carried | v2 row | adds `workspace_pk` |
| v1-083 | Data model | row: searches (M3) | carried | v2 row | adds `workspace_pk` |
| v1-084 | Data model | row: posts | reduced | v2 row | itemized flag columns condensed to "flair and flags"; `comments_harvested` renamed `comments_captured` (review-pass correction) |
| v1-085 | Data model | row: comments | carried | v2 row | column list condensed, same fields |
| v1-086 | Data model | row: comment_more | carried | v2 row | — |
| v1-087 | Data model | row: post_sources | carried | v2 row | adds "through several workspaces" |
| v1-088 | Data model | row: item_snapshots | carried | v2 row | — |
| v1-089 | Data model | row: authors | carried | v2 row | — |
| v1-090 | Data model | row: themes/theme_rules/post_themes | carried | v2 row | adds `workspace_pk`, unique-within-workspace, `origin` field (M2) |
| v1-091 | Data model | row: runs/run_subreddits | carried | v2 row | adds `network` status, `violations_json`, `settings_fingerprint` (rev 0002) |
| v1-092 | Data model | row: raw_rejects | carried | v2 row | retention value moved to config reference |
| v1-093 | Data model | row: ui_state | carried | v2 row | — |
| v1-094 | Data model | row: posts_fts/comments_fts | reduced | v2 row | "delete-old on update/delete" trigger phrasing dropped, replaced by persistent secure-delete (rev 0004) |
| v1-095 | Data model | paragraph (Raw JSON policy) | carried | v2 same paragraph | — |
| v1-096 | Data model | paragraph (Content-state machine) | carried | v2 same paragraph | adds terminal `gone` state and KI-021 bodyless-return exception |
| v1-097 | Data model | paragraph (Scrub) | carried | v2 same paragraph | adds index `optimize` step and "edits are an event" sentence |
| v1-098 | Data model | paragraph (Corrections from test-strategy panels) | reduced | v2 "SQLite facts the design rests on" paragraph | AUTOINCREMENT reasoning, backups-table mention, and UI-panel findings (maintenance-only mode, mode=ro engine, Host check, stale-run threshold, exports, operator-complete gate) moved into their own Web-UI/gates rows rather than restated here |
| v1-099 | Collector algorithm | heading | carried | v2 same heading | — |
| v1-100 | Collector algorithm | list item: step 0 (Order matters) | carried | v2 step 0 | adds "a run with no collectable source is refused loudly (KI-017)" |
| v1-101 | Collector algorithm | list item: step 1 (Sweep /new) | carried | v2 step 1 | adds cadence-comfort note (D-30) |
| v1-102 | Collector algorithm | list item: step 2 (Harvest comment trees) | carried | v2 step 2 | hardcoded budget numbers (1,500/16/40) replaced by config-key references |
| v1-103 | Collector algorithm | list item: step 3 (Revisit ladder) | reduced | v2 step 3 | explicit "1d→3d→7d→30d" dropped for a `revisit_ladder_days` config reference; adds 365-day stage note |
| v1-104 | Collector algorithm | list item: step 4 (Reconcile) | carried | v2 step 4 | cost estimate updated (2,400 → "about two and a half thousand"), tied to D-30 |
| v1-105 | Collector algorithm | list item: step 5 (Tag themes) | carried | v2 step 5 | — |
| v1-106 | Collector algorithm | list item: step 6 (Finish) | reduced | v2 step 6 | "VACUUM INTO" phrasing replaced by online-backup-API wording (2026-09-16 drift fix); digest-content detail (per-theme ranking, deep links, untagged/rising sections) moved to "From data to insight" |
| v1-107 | Collector algorithm | paragraph (Budget reality) | reduced | v2 "Budget reality" paragraph | drops "~10 minutes" / "~1 hour" numeric detail; exit-code list expanded (adds 1, 3, 4, 5, 130) |
| v1-108 | Collector algorithm | paragraph (Search source M3) | carried | v2 same paragraph | — |
| v1-109 | CLI commands | heading | carried | v2 same heading | — |
| v1-110 | CLI commands | table | carried | v2 CLI table | v2 adds a "State" column |
| v1-111 | CLI commands | row: doctor | carried | v2 doctor row | expanded with the full named check list |
| v1-112 | CLI commands | row: db init/upgrade/... | carried | v2 db rows (split into two) | split into "init/upgrade/current" and "downgrade/backup/.../reprocess" |
| v1-113 | CLI commands | row: run | carried | v2 run row | adds `--gateway fake` |
| v1-114 | CLI commands | row: fetch/comments/revisit/reconcile/tag/search-run | carried | v2 same row | — |
| v1-115 | CLI commands | row: report | carried | v2 report row | — |
| v1-116 | CLI commands | row: export | carried | v2 export row | — |
| v1-117 | CLI commands | row: subs/themes/config validate/show/export/import | carried | v2 rows (split: config row, subs/themes row) | reorganized into two rows, no content dropped |
| v1-118 | CLI commands | row: probe | carried | v2 probe row | — |
| v1-119 | CLI commands | row: serve | carried | v2 serve row | — |
| v1-120 | Web UI | heading | carried | v2 same heading | — |
| v1-121 | Web UI | paragraph (Old-Reddit density...) | carried | v2 same paragraph | adds "the workspace is the top-level switch" |
| v1-122 | Web UI | table (Design rules) | carried | v2 Design rules table | v2 adds a "Writes" row (new) |
| v1-123 | Web UI | row: Same URL, page or fragment | carried | v2 row | — |
| v1-124 | Web UI | row: Comment tree | carried | v2 row | — |
| v1-125 | Web UI | row: Honest coverage | carried | v2 row | — |
| v1-126 | Web UI | row: Tombstones | carried | v2 row | — |
| v1-127 | Web UI | row: Content safety | carried | v2 row | adds explicit CSP header line |
| v1-128 | Web UI | row: Mutations | carried | v2 row | — |
| v1-129 | Web UI | row: Security | carried | v2 row | adds "threat model in DECISIONS §5" pointer |
| v1-130 | Web UI | row: Process model | reduced | v2 Process model row | "single uvicorn worker" generalized to "single worker" |
| v1-131 | Web UI | row: Styling | carried | v2 row | — |
| v1-132 | Web UI | row: Power view | carried | v2 row | — |
| v1-133 | Web UI | row: Operator-first | carried | v2 row | — |
| v1-134 | Web UI | table (Routes) | carried | v2 Routes table | — |
| v1-135 | Web UI | row: `/` | carried | v2 row | — |
| v1-136 | Web UI | row: `/r/{sub}` | carried | v2 row | — |
| v1-137 | Web UI | row: `/t/{slug}` | carried | v2 row | — |
| v1-138 | Web UI | row: `/r/{sub}/comments/{id}/{slug}` | carried | v2 row | — |
| v1-139 | Web UI | row: comment permalink `/{cid}` | carried | v2 row | — |
| v1-140 | Web UI | row: `/search` | carried | v2 row | — |
| v1-141 | Web UI | row: `/u/{name}` | carried | v2 row | — |
| v1-142 | Web UI | row: `/settings/subreddits` | carried | v2 row | — |
| v1-143 | Web UI | row: `/settings/themes` | carried | v2 row | — |
| v1-144 | Web UI | row: `/settings/searches` | carried | v2 row | — |
| v1-145 | Web UI | row: `/settings/appearance` | carried | v2 row | — |
| v1-146 | Web UI | row: `/runs`, `/runs/{id}` | carried | v2 row | — |
| v1-147 | Web UI | row: `/export` | carried | v2 row | — |
| v1-148 | Web UI | row: `/setup` | carried | v2 row | adds "loopback-only unless a password is set" |
| v1-149 | Web UI | row: `/system` | carried | v2 row | adds no-network-default checkbox detail |
| v1-150 | Web UI | row: `/system/backups` | carried | v2 row | — |
| v1-151 | Web UI | row: `/system/maintenance` | carried | v2 row | — |
| v1-152 | Web UI | row: `/healthz` | carried | v2 row | — |
| v1-153 | Web UI | paragraph (Curation controls) | reduced | v2 Curation controls paragraph | explicit schema-rev-2 column list restated less fully; adds "which curation records survive a failed restore... decided at M2" |
| v1-154 | Web UI | fenced block (Wireframe, feed) | absent (retired with a home) | — | v2 Version history: "the two UI wireframes (git history; the feed sketch is in `docs/reference/reviews/2026-09-12-ui-design-review.md`)" |
| v1-155 | Web UI | fenced block (Wireframe, post page) | absent (retired with a home) | — | same retirement note; no separate named home for the post-page sketch beyond git history |
| v1-156 | Testing strategy | heading | carried | v2 same heading | — |
| v1-157 | Testing strategy | paragraph (Principle) | carried | v2 Principle paragraph | adds `ProcessRunner` protocol and `vanish` scenario method |
| v1-158 | Testing strategy | table (Layer) | carried | v2 Layer table | v2 adds "Deploy" and "Gates" rows; points at `docs/TEST_STRATEGY.md` |
| v1-159 | Testing strategy | row: Unit (core/) | carried | v2 row | — |
| v1-160 | Testing strategy | row: Collector e2e | carried | v2 row | — |
| v1-161 | Testing strategy | row: Adapter | carried | v2 row | tagged "tranche B" |
| v1-162 | Testing strategy | row: Migrations | carried | v2 row | adds migration-checklist/KI-014 reference |
| v1-163 | Testing strategy | row: Web | carried | v2 row | tagged "M2" |
| v1-164 | Testing strategy | row: E2E (optional) | reduced | v2 Web row / Deploy row | no standalone Playwright row; folded into the Web row's tools column |
| v1-165 | Testing strategy | row: Live smoke (opt-in) | carried | v2 row | — |
| v1-166 | Testing strategy | row: Workflow | carried | v2 row | — |
| v1-167 | Testing strategy | row: Sweeps (scheduled, in production) | reduced | v2 "Sweeps in production" row | parenthetical "(freshness anchor, stress scenario, weekly notifier proof cut/downgraded)" dropped; that content now lives only in DECISIONS N-08/N-11/N-16 |
| v1-168 | Testing strategy | paragraph (lead-in: "Failure-mode matrix") | carried | v2 same lead-in | — |
| v1-169 | Testing strategy | table (Failure-mode matrix) | carried | v2 Failure-mode matrix table | v2 drops one v1 row (Uniform staleness, see v1-197) and adds two new rows (KI-015, KI-016) |
| v1-170 | Testing strategy | row: 429 with Retry-After | reduced | v2 row | `min(retry_after,300)` specific formula dropped, generalized to "the bounded wait" |
| v1-171 | Testing strategy | row: 401 at token endpoint | carried | v2 row | — |
| v1-172 | Testing strategy | row: 401 invalid_token mid-run | carried | v2 row | reworded shorter, same behavior |
| v1-173 | Testing strategy | row: 403 private subreddit | carried | v2 row | adds KI-017 reference |
| v1-174 | Testing strategy | row: 404 banned subreddit | carried | v2 row | — |
| v1-175 | Testing strategy | row: Nonexistent subreddit | carried | v2 row | "auto-disabled after N runs" → explicit "three runs" |
| v1-176 | Testing strategy | row: Casing/identity change | carried | v2 row | — |
| v1-177 | Testing strategy | row: 5xx/timeout mid-page | reduced | v2 row | explicit retry-ladder numbers "(30s→2m→5m)" dropped |
| v1-178 | Testing strategy | row: Crash between pages | carried | v2 row | — |
| v1-179 | Testing strategy | row: Crash mid comment-tree | carried | v2 row | — |
| v1-180 | Testing strategy | row: Overlapping run | carried | v2 row | adds `skipped_locked` row detail |
| v1-181 | Testing strategy | row: DB locked by another writer | carried | v2 row | — |
| v1-182 | Testing strategy | row: Stale `running` row | carried | v2 row | — |
| v1-183 | Testing strategy | row: Malformed/missing fields | reduced | v2 row | explicit fixture-example list ("edited false/float, absent author_fullname") dropped |
| v1-184 | Testing strategy | row: Deleted/removed content | carried | v2 row | "FTS empty" reworded "index entry and bytes gone" |
| v1-185 | Testing strategy | row: Account deletion | carried | v2 row | — |
| v1-186 | Testing strategy | row: Missing from `info()` | reduced | v2 row | "fake omits id twice" specificity dropped; adds KI-021 bodyless-return exception |
| v1-187 | Testing strategy | row: Config validation errors | reduced | v2 row | explicit bad-input example list dropped |
| v1-188 | Testing strategy | row: DB missing/behind head | carried | v2 row | — |
| v1-189 | Testing strategy | row: Disk write failure | carried | v2 row | — |
| v1-190 | Testing strategy | row: Clock skew ±1 day | reduced | v2 row | "±1 day" magnitude dropped, generalized |
| v1-191 | Testing strategy | row: Empty subreddit/zero new | carried | v2 row | — |
| v1-192 | Testing strategy | row: Cloudflare HTML 403 | carried | v2 row | — |
| v1-193 | Testing strategy | row: Overlapping listing pages | carried | v2 row | — |
| v1-194 | Testing strategy | row: Quarantined subreddit | carried | v2 row | — |
| v1-195 | Testing strategy | row: Budget exhausted mid-run | carried | v2 row | — |
| v1-196 | Testing strategy | row: Column silently 100% NULL | carried | v2 row | reworded "the field nested elsewhere" |
| v1-197 | Testing strategy | row: Uniform staleness | superseded | DECISIONS N-08 | freshness-anchor row cut entirely from v2's failure matrix; v1 itself already flagged it "(freshness anchor cut 2026-09-13, N-08)" |
| v1-198 | Testing strategy | row: A gate that has gone inert | carried | v2 row | — |
| v1-199 | Testing strategy | row: Source freshness | carried | v2 row | — |
| v1-200 | Testing strategy | row: Test suite pointed at the real data dir | carried | v2 row | — |
| v1-201 | Testing strategy | row: Repeated reruns churn primary keys | carried | v2 row | — |
| v1-202 | Testing strategy | row: Same post normalizes differently via two paths | carried | v2 row | — |
| v1-203 | Testing strategy | row: Subreddit recovers after an error | carried | v2 row | — |
| v1-204 | Testing strategy | row: Dry run or no-network mode touches network/DB | carried | v2 row | — |
| v1-205 | Testing strategy | row: Deleting a workspace removes data another reaches | carried | v2 row | — |
| v1-206 | Testing strategy | row: Re-tagging removes a manual tag | carried | v2 row | — |
| v1-207 | Testing strategy | row: A watched thread falls off the ladder | carried | v2 row | — |
| v1-208 | Testing strategy | paragraph (Gates: `make check` = ...) | carried | v2 same paragraph | wording updated for added gates (code health, ratchet compare, hooks line, memory audit, green stamp) |
| v1-209 | Robustness | heading | carried | v2 "Robustness, enforcement and portability" | — |
| v1-210 | Robustness | paragraph (The failure pattern...) | carried | v2 same paragraph | adds "inventoried on `docs/INSIGHTMINER_HARNESS.md`... ledger row in `docs/runbook/GUARDS.md`" |
| v1-211 | Robustness | heading "Guard design rules" | carried | v2 same heading | — |
| v1-212 | Robustness | paragraph (Source: WHY_THE_GUARDS_EXIST.md) | reduced | v2 same paragraph | specific counts ("29 guards... 2,250 grandfathered suppressions") generalized to "an audit found that half the guards had never fired" |
| v1-213 | Robustness | table (Guard design rules) | carried | v2 same table | — |
| v1-214 | Robustness | row: Scan a structural shape | carried | v2 row | — |
| v1-215 | Robustness | row: Key on the invariant, not a proxy | carried | v2 row | — |
| v1-216 | Robustness | row: A gate that cannot fail is not a gate | carried | v2 row | — |
| v1-217 | Robustness | row: Structural markers, not comment proximity | carried | v2 row | adds N-05 |
| v1-218 | Robustness | row: Assert on the delivery surface | carried | v2 row | — |
| v1-219 | Robustness | row: Fail, never skip, inside the required gate | carried | v2 row | — |
| v1-220 | Robustness | row: Zero-suppression baseline | reduced | v2 row | "start at zero" weakened to "started at the measured baseline with no backlog" |
| v1-221 | Robustness | row: Hold the count | carried | v2 row | — |
| v1-222 | Robustness | row: Derive state, never narrate it | carried | v2 row | adds status page/harness inventory to the list of derived surfaces |
| v1-223 | Robustness | row: Show the denominator | carried | v2 row | — |
| v1-224 | Robustness | heading "TDD policy by layer" | carried | v2 same heading | — |
| v1-225 | Robustness | table (TDD policy) | carried | v2 same table | — |
| v1-226 | Robustness | row: core/ | carried | v2 row | — |
| v1-227 | Robustness | row: services/ | carried | v2 row | — |
| v1-228 | Robustness | row: adapters/reddit_praw.py | carried | v2 row | adds "one credentialed probe day precedes M1b" |
| v1-229 | Robustness | row: db/migrations/ | carried | v2 row | — |
| v1-230 | Robustness | row: web/ | carried | v2 row | — |
| v1-231 | Robustness | row: Bug fixes | carried | v2 row | expanded to name the `harden` skill (new mechanism, not in v1) |
| v1-232 | Robustness | heading "Gates and ratchets" | carried | v2 same heading | — |
| v1-233 | Robustness | table (Gates and ratchets, 29 rows) | reduced | v2 "Gates and ratchets" table | v2 consolidates to ~19 rows; several v1 rows merged (see below) |
| v1-234 | Robustness | row: pre-commit | carried | v2 row | adds dmypy whole-tree, no-commits-on-main |
| v1-235 | Robustness | row: `make check` | carried | v2 row | adds code health, ratchet compare, memory audit, green stamp |
| v1-236 | Robustness | row: Required CI on `main` | superseded | DECISIONS 2026-09-14 "Remote: GitHub deferred" | no "Required CI" row in v2; GitHub/branch-protection plan superseded by QNAP-remote decision |
| v1-237 | Robustness | row: Coverage ratchet | carried | v2 row | — |
| v1-238 | Robustness | row: Skip/xfail ratchet | moved | v2 merged row "Skip, suppression, assert-count, and collected-test floors" | consolidated with two other rows |
| v1-239 | Robustness | row: Suppression ratchet | moved | v2 same merged row | — |
| v1-240 | Robustness | row: Test-count floor | superseded | DECISIONS N-09 | v2's merged row states the floor is kept only under the loosening protocol, "a contradiction recorded in DECISIONS" |
| v1-241 | Robustness | row: import-linter | carried | v2 row | adds G04/G05 |
| v1-242 | Robustness | row: Network block | carried | v2 row | adds G06 |
| v1-243 | Robustness | row: Schema snapshot | moved | v2 merged row "Schema snapshot; models == DDL" | — |
| v1-244 | Robustness | row: Models == DDL | moved | v2 same merged row | — |
| v1-245 | Robustness | row: Runtime schema fingerprint | carried | v2 row | — |
| v1-246 | Robustness | row: Portability job | carried | v2 row | adds "once a remote exists" |
| v1-247 | Robustness | row: Mutation testing | superseded | DECISIONS N-10; HARNESS §7 | no row at all in v2's shipped gate table (only referenced as declined) |
| v1-248 | Robustness | row: Post-run invariants | carried | v2 row | — |
| v1-249 | Robustness | row: Dead-man switch | carried | v2 "Dead-man ping" row | — |
| v1-250 | Robustness | row: Restore drill | carried | v2 row | — |
| v1-251 | Robustness | row: Guard reachability | moved | v2 Post-run invariants row (merged, cites G30) | — |
| v1-252 | Robustness | row: `DATA_DIR` isolation | carried | v2 row | adds subprocess-seam refusal detail (G19) |
| v1-253 | Robustness | row: Connection chokepoint | carried | v2 row | adds G31, ruff TID251 |
| v1-254 | Robustness | row: Destructive-operation gate | reduced | v2 row | explicit backups-table column list (sha256, size, integrity) moved to the Data-model `backups` row |
| v1-255 | Robustness | row: No bypass flags | carried | v2 row (N-06) | — |
| v1-256 | Robustness | row: Size ratchets | moved | v2 Code-health ratchets row | folded into the code_health family |
| v1-257 | Robustness | row: Code-health ratchets | carried | v2 row | — |
| v1-258 | Robustness | row: Freshness anchor | superseded | DECISIONS N-08 | no row in v2's shipped gate table |
| v1-259 | Robustness | row: Coverage counters | moved | v2 Silent-failure-controls "Coverage counters" bullet | moved out of the gates table into prose |
| v1-260 | Robustness | row: Stress scenario | superseded | DECISIONS N-11 | no row in v2's shipped gate table; `EXPLAIN QUERY PLAN` assertions retained via the Conventions paragraph instead |
| v1-261 | Robustness | row: Hard-block hooks | carried | v2 row | expanded to cover the third hook (read-before-touch, added 2026-09-14) |
| v1-262 | Robustness | row: Doc currency | moved | v2 "Documentation gates" row | expanded into the consolidated G33/G34/G35/G39/G40/G44/G45/G47/G50/G52/G54 row |
| v1-263 | Robustness | heading "Silent-failure controls" | carried | v2 same heading | — |
| v1-264 | Robustness | bullet: Exception policy | carried | v2 same bullet | adds KI-010 |
| v1-265 | Robustness | bullet: Warnings are errors in tests | carried | v2 same bullet | — |
| v1-266 | Robustness | bullet: Post-run invariants | carried | v2 same bullet | restructured into "built" vs "planned with their stages" |
| v1-267 | Robustness | bullet: Structured logs | carried | v2 same bullet | "notifies on non-zero" → "maps the exit code to an operator action" |
| v1-268 | Robustness | bullet: Typed boundaries | carried | v2 same bullet | — |
| v1-269 | Robustness | bullet: No mocking of internals | carried | v2 same bullet | adds N-17 |
| v1-270 | Robustness | bullet: Cross-platform and environment controls | carried | v2 same bullet | "Linux as primary CI from day one" qualified "once a remote exists" |
| v1-271 | Robustness | bullet: Two-gate discipline for semantics | carried | v2 same bullet | — |
| v1-272 | Robustness | bullet: Notifier proof (downgraded 2026-09-13) | moved | v2 "Alerts" bullet | downgrade narrative moved to DECISIONS/retired-claims table; substance kept plainly |
| v1-273 | Robustness | heading "Known AI-assisted-development failure patterns" | carried | v2 same heading | — |
| v1-274 | Robustness | table (12 rows) | carried | v2 same table (13 rows) | v2 adds one new row (hook present but never installed) |
| v1-275 | Robustness | row: Assertion loosened or test deleted | carried | v2 row | adds `xfail_strict` |
| v1-276 | Robustness | row: Tests skipped/xfailed to unblock | carried | v2 row | — |
| v1-277 | Robustness | row: Mocks that mock the thing under test | carried | v2 row | — |
| v1-278 | Robustness | row: Broad `except … pass` hiding failures | carried | v2 row | — |
| v1-279 | Robustness | row: Hallucinated library APIs or fields | carried | v2 row | adds "the pinned major" |
| v1-280 | Robustness | row: Model edited without a migration | carried | v2 row | — |
| v1-281 | Robustness | row: "Works on my machine" | carried | v2 row | — |
| v1-282 | Robustness | row: Time-dependent flaky tests | carried | v2 row | adds "(gated)" |
| v1-283 | Robustness | row: Partial run reported as success | carried | v2 row | — |
| v1-284 | Robustness | row: "Tests pass" claimed on a subset | carried | v2 row | adds "the green stamp names the tree" |
| v1-285 | Robustness | row: Over-abstraction | carried | v2 row | adds N-20 |
| v1-286 | Robustness | row: Docs drift | carried | v2 row | adds "the documentation gates above" |
| v1-287 | Robustness | heading "Working agreement" | carried | v2 same heading | — |
| v1-288 | Robustness | paragraph (Never weaken, skip, or delete...) | moved | `CLAUDE.md` (repo working agreement) | v2's paragraph states plainly "the plan does not repeat it" |
| v1-289 | Robustness | heading "Workflows, cadence and verification points" | carried | v2 same heading | — |
| v1-290 | Robustness | table (7 rows) | carried | v2 table (8 rows) | v2 adds a new "Guard review" row |
| v1-291 | Robustness | row: Daily run | superseded | DECISIONS D-30 | v2's "Scheduled run" row: twice-weekly, not daily |
| v1-292 | Robustness | row: Config change | carried | v2 row | — |
| v1-293 | Robustness | row: Code change | carried | v2 row | "PR CI → human merge" replaced by "make check stamps the tree → fast-forward into main" (GitHub-PR flow superseded by local-merge flow) |
| v1-294 | Robustness | row: Schema migration | carried | v2 row | — |
| v1-295 | Robustness | row: Dependency bump | carried | v2 row | adds fixture-replay-on-major detail |
| v1-296 | Robustness | row: Compliance reconcile | carried | v2 row | cadence updated "weekly" → "every scheduled run" |
| v1-297 | Robustness | row: Restore/rollback drill | carried | v2 row | — |
| v1-298 | Robustness | heading "Portability targets" | carried | v2 same heading | — |
| v1-299 | Robustness | bullet: Fresh machine in under 10 minutes | carried | v2 same bullet | drops "portability CI job proves it weekly" clause (moved to gates table) |
| v1-300 | Robustness | bullet: 12-factor config | carried | v2 same bullet | adds timezone-validation detail (KI-011) |
| v1-301 | Robustness | bullet: Docker image is the portable artifact | carried | v2 same bullet | — |
| v1-302 | Robustness | bullet: Move data | carried | v2 same bullet | — |
| v1-303 | Robustness | bullet: Each person registers their own Reddit app | carried | v2 same bullet | — |
| v1-304 | Robustness | bullet: `CLAUDE.md`, `CONTRIBUTING.md`, `RUNBOOK.md` | reduced | v2 "the working agreement, the runbook, and the harness page" bullet | explicit `CONTRIBUTING.md` filename dropped |
| v1-305 | Robustness | heading "QNAP as a service host (M4)" | carried | v2 same heading | — |
| v1-306 | Robustness | paragraph | carried | v2 same paragraph | "runs/jobs tables" → "runs table" |
| v1-307 | Robustness | heading "Adversarial review: what changed (2026-09-13)" | superseded | DECISIONS §3 and the 2026-09-13 entries | v2 Version history explicitly lists this section as retired with that home |
| v1-308 | Robustness | paragraph (The adversarial reviewer's central charge...) | superseded | DECISIONS §3 intro | content now lives as the N-xx settled-negatives framing |
| v1-309 | Robustness | bullet: Gates cut or downgraded | superseded | DECISIONS N-06, N-07, N-08, N-09, N-10, N-11, N-13, N-16 | each cut/downgrade now has its own numbered row |
| v1-310 | Robustness | bullet: Positive controls, split honestly | moved | DECISIONS D-22 / guard design rules | — |
| v1-311 | Robustness | bullet: Enforcement stated honestly | moved | DECISIONS D-11, D-17; 2026-09-14 "Remote: GitHub deferred" | GitHub/branch-protection plan superseded entirely |
| v1-312 | Robustness | bullet: CSRF on the LAN | carried | v2 Web-UI Security row | — |
| v1-313 | Robustness | bullet: Isolation across the subprocess seam | carried | v2 Process-model row (`ProcessRunner` port) | — |
| v1-314 | Robustness | bullet: State machine shape locked, predicates unlocked | moved | v2 Content-state-machine paragraph | v1's provisional framing resolved; "predicates re-confirmed against real captures on the probe day" |
| v1-315 | Robustness | bullet: Compliance bounds written down instead of over-claimed | moved | DECISIONS §2 Compliance bounds | — |
| v1-316 | Robustness | bullet: The #1 priority pulled forward | moved | v2 "From data to insight"; DECISIONS 2026-09-13 late section | — |
| v1-317 | Robustness | bullet: Smaller fixes | reduced | scattered (Collector step 0 flock rule; N-14 bot detection; Destructive-gate `Confirmation` object; TID251; suppression-ratchet mypy overrides; 365-day ladder stage) | consolidated bullet dropped as one unit; facts distributed piecemeal, LAN "operator error" wording moved to DECISIONS §5 |
| v1-318 | Robustness | bullet: From the enforcement panel (adopted) | moved | DECISIONS (ratchet 3-way compare, coverage floor, dmypy whole-tree, hooks count); v2 Gates table; HARNESS page | — |
| v1-319 | Robustness | bullet: Disputed or deferred, for Wes | moved | DECISIONS §6, §7 "Pending Wes" | JSONL sidecar cut confirmed; `reddit.request()` question deferred to M1b |
| v1-320 | Release practices | heading | carried | v2 same heading | — |
| v1-321 | Release practices | bullet: Schema | carried | v2 same bullet | "FTS count equals live count" → "index membership equals live rows" (terminology update) |
| v1-322 | Release practices | bullet: Safety | reduced | v2 Safety bullet | explicit backup-path naming pattern dropped; adds KI-015 restore-order fix |
| v1-323 | Release practices | bullet: Connections | carried | v2 same bullet | adds minimum-SQLite-version check (rev 0004) |
| v1-324 | Release practices | bullet: Reprocessing | carried | v2 same bullet | — |
| v1-325 | Release practices | bullet: Versioning | reduced | v2 Versioning bullet | SemVer minor/patch rule and `CHANGELOG.md`/git-tags detail dropped (N-19: no changelog ceremony beyond the version string) |
| v1-326 | Release practices | bullet: Startup checks | carried | v2 same bullet | — |
| v1-327 | Release practices | bullet: Containers (M4) | carried | v2 same bullet | — |
| v1-328 | Deployment path | heading | carried | v2 same heading | — |
| v1-329 | Deployment path | table (4 rows) | carried | v2 Deployment path table | rows reordered (MB before M4); cadence and TCC/login-session notes updated |
| v1-330 | Milestones | heading | carried | v2 same heading | — |
| v1-331 | Milestones | table (11 rows) | carried | v2 Milestones table | v2 adds "Built-versus-planned is stated on STATUS.md, not here" intro line |
| v1-332 | Milestones | row: D0 | reduced | v2 D0 row | drops the itemized walk-status list; one summary sentence instead |
| v1-333 | Milestones | row: M0 | reduced | v2 M0 row | drops the long "brew install uv gh..." step-by-step recap |
| v1-334 | Milestones | row: M1a | reduced | v2 M1a row | drops the detailed tranche-A recap paragraph (moved to DECISIONS 2026-09-13 night section) |
| v1-335 | Milestones | row: M1b | carried | v2 row | — |
| v1-336 | Milestones | row: M1c | carried | v2 row | adds migration-checklist tests (KI-014) |
| v1-337 | Milestones | row: M1d | reduced | v2 row | explicit seed-theme name list (Crashes, Export failures, ...) dropped |
| v1-338 | Milestones | row: M2 | carried | v2 row | adds "the curation migration" and "rev-2 design items" |
| v1-339 | Milestones | row: M3 | carried | v2 row | — |
| v1-340 | Milestones | row: M4 | carried | v2 row | — |
| v1-341 | Milestones | row: MB | carried | v2 row | — |
| v1-342 | Milestones | row: M5 | carried | v2 row | — |
| v1-343 | Milestones | paragraph (M0 foundation tranche) | moved | DECISIONS 2026-09-13 night section; `docs/recent/STATUS.md` | v2 drops the long recap paragraph, points at STATUS.md instead |
| v1-344 | Things only Wes can do | heading | carried | v2 same heading | — |
| v1-345 | Things only Wes can do | item 1: Create dedicated Reddit account | carried | v2 item 1 | adds Responsible Builder Policy access-request step |
| v1-346 | Things only Wes can do | item 2: Register the script app | moved | v2 item 1 (merged) | merged into the expanded item 1 |
| v1-347 | Things only Wes can do | item 3: Approve installing uv/gh; create GitHub repo | superseded | DECISIONS 2026-09-14 "Remote: GitHub deferred" | no GitHub-repo-creation item in v2's list |
| v1-348 | Things only Wes can do | item 4: Prior-learnings material (8 documents) | moved | DECISIONS 2026-09-13 late section; `EARLIER_PROJECT_REFERENCE.md` | — |
| v1-349 | Things only Wes can do | item 5: Optional test subreddit | carried | v2 item 4 | — |
| v1-350 | Things only Wes can do | item 6: Later — search queries, optional subreddits | carried | v2 item 5 | adds "whether and when a second workspace, or a second instance, is wanted" |
| v1-351 | Verification | heading | carried | v2 same heading | — |
| v1-352 | Verification | item 1: `make check` passes | carried | v2 item 1 | adds "and stamps the tree" |
| v1-353 | Verification | item 2: `doctor` auth OK | carried | v2 item 2 | tagged "(tranche B)" |
| v1-354 | Verification | item 3: `run --budget 200` | carried | v2 item 3 | — |
| v1-355 | Verification | item 4: Compliance drill | carried | v2 item 4 | "grep the data directory" → "scan the data directory, the index bytes" |
| v1-356 | Verification | item 5: `serve` → UI checks | reduced | v2 item 5 | explicit export-zip content list (`posts.jsonl`, `comments.jsonl`, ...) dropped |
| v1-357 | Verification | item 6: Migration drill | carried | v2 item 6 | — |
| v1-358 | Verification | item 7: Scheduler | carried | v2 item 7 | adds "sleep the Mac through a slot and confirm the run fires on wake" |
| v1-359 | Decisions table (retired) | heading "Decisions taken on the reviewers' open questions" | moved | DECISIONS §6 "Decisions on the reviewers' open questions" | v2 Version history names this retirement explicitly |
| v1-360 | Decisions table (retired) | table (10 rows) | moved | DECISIONS §6 table | — |
| v1-361 | Decisions table (retired) | row: Raw JSON policy | moved | DECISIONS §6 row | — |
| v1-362 | Decisions table (retired) | row: Reconcile cadence | superseded | DECISIONS D-30 | cadence changed from D-16's daily-era wording to twice-weekly |
| v1-363 | Decisions table (retired) | row: Banned/private subreddit content | moved | DECISIONS §6 row | — |
| v1-364 | Decisions table (retired) | row: Cassettes with third-party content | moved | DECISIONS §6 row | — |
| v1-365 | Decisions table (retired) | row: Tree JSON shape | moved | DECISIONS §6 row | "disputed" flag retained, decision still pending at M1b |
| v1-366 | Decisions table (retired) | row: Initial backfill | moved | DECISIONS §6 row | — |
| v1-367 | Decisions table (retired) | row: Score snapshots | moved | DECISIONS §6 row | — |
| v1-368 | Decisions table (retired) | row: Regex rules in UI | moved | DECISIONS §6 row | — |
| v1-369 | Decisions table (retired) | row: Digest persistence | superseded | DECISIONS §2 "Digests" bound | "files kept 14 days" explicitly superseded by the route-based digest (D-30 era) |
| v1-370 | Decisions table (retired) | row: Timezone | moved | DECISIONS §6 row | — |
| v1-371 | Decisions table (retired) | row: Secrets in Docker | moved | DECISIONS §6 row | — |
| v1-372 | Remaining open items (retired) | heading | moved | DECISIONS §7 "Pending Wes"; `docs/recent/STATUS.md` | v2 Version history: "the D0 open-items list and walk status (DECISIONS § 7 and the status page)" |
| v1-373 | Remaining open items (retired) | paragraph (Approved 2026-09-13...) | moved | DECISIONS §7 intro | — |
| v1-374 | Remaining open items (retired) | bullet: Enforcement panel delivered | moved | DECISIONS Robustness-section adoptions | — |
| v1-375 | Remaining open items (retired) | bullet: For Wes, raised by adversarial review | moved | DECISIONS §7 items 1, 2, 4, 5 | — |
| v1-376 | Remaining open items (retired) | bullet: Owner questions raised by the panels | moved | DECISIONS §6 rows (backup retention, purge semantics, loopback-only, archive import, Playwright local, `[NEW]` badge, no-network default) | most resolved as settled decisions there and in the 2026-09-14 entries |
| v1-377 | Remaining open items (retired) | sub-heading "D0 section walk status" | reduced | v2 Milestones D0 row | v2's D0 row is one condensed sentence, not the per-section table |
| v1-378 | Remaining open items (retired) | table (7 rows) | reduced | v2 Milestones D0 row (single sentence) | per-section status/decisions-recorded detail not preserved row-by-row |
| v1-379 | Remaining open items (retired) | row: Data model and state machine | reduced | v2 D0 row (summary only) | "Locked" status and its itemized decisions dropped from the summary |
| v1-380 | Remaining open items (retired) | row: Collector algorithm and budgets | reduced | v2 D0 row (summary only) | itemized ladder/budget defaults dropped from the summary |
| v1-381 | Remaining open items (retired) | row: UI routes and design rules | carried | v2 D0 row ("the UI routes, which Wes was reviewing") | explicitly named as one of the two sections left open |
| v1-382 | Remaining open items (retired) | row: Wes's prior database learnings | reduced | v2 D0 row (summary only) | itemized appendix pointer dropped from the summary |
| v1-383 | Remaining open items (retired) | row: Reference corpus and memory routing | reduced | v2 D0 row (summary only) | — |
| v1-384 | Remaining open items (retired) | row: Test-strategy panels | reduced | v2 D0 row (summary only) | "5 of 5 delivered" detail dropped from the summary (panel outcomes live in `docs/TEST_STRATEGY.md`) |
| v1-385 | Remaining open items (retired) | row: Milestones and sequencing | carried | v2 D0 row ("the milestone sequencing... overtaken by the milestones as executed") | — |
| v1-386 | Appendix: retrospectives | heading | superseded | v2 Version history: "the appendix of retrospective changes (`docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` and `LEARNINGS_TRANSFER.md`)" | explicitly retired with a named home |
| v1-387 | Appendix: retrospectives | paragraph (How these were assessed) | moved | `docs/learnings/LEARNINGS_TRANSFER.md` | — |
| v1-388 | Appendix: retrospectives | paragraph (The earlier system...) | moved | `LEARNINGS_TRANSFER.md`; `EARLIER_PROJECT_REFERENCE.md` | — |
| v1-389 | Appendix: retrospectives | table (17 rows) | moved | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` | whole table's content is stated to live in the named learnings document (not itself in the INPUTS list, so its content was not independently re-verified) |
| v1-390 | Appendix: retrospectives | row: launchd/TCC finding | moved | `DB_LEARNINGS_APPLIED_2026-09-12.md` | — |
| v1-391 | Appendix: retrospectives | row: Guards audited (14 of 29 never fired) | moved | same document; DECISIONS D-22 | — |
| v1-392 | Appendix: retrospectives | row: A gate unit-tested and called by nothing | moved | same document | — |
| v1-393 | Appendix: retrospectives | row: Tests overwrote live artifacts twice | moved | same document; v2 `DATA_DIR` isolation gate | — |
| v1-394 | Appendix: retrospectives | row: `INSERT OR REPLACE` burned rowids | moved | same document; DECISIONS N-04 | — |
| v1-395 | Appendix: retrospectives | row: Two producers of one record shape drifted | moved | same document | — |
| v1-396 | Appendix: retrospectives | row: Everything uniformly stale for two weeks | moved | same document; DECISIONS N-08 | — |
| v1-397 | Appendix: retrospectives | row: Opt-in write guard bypassed | moved | same document | — |
| v1-398 | Appendix: retrospectives | row: Silent accept of unknown enum values | moved | same document | — |
| v1-399 | Appendix: retrospectives | row: Boolean off-switch disabled a safety mechanism | moved | same document; DECISIONS N-06 | — |
| v1-400 | Appendix: retrospectives | row: Half-built DB promoted to live | moved | same document | — |
| v1-401 | Appendix: retrospectives | row: Ratchets ran only in the full suite | moved | same document | — |
| v1-402 | Appendix: retrospectives | row: Small-input tests hid a 90-minute merge | moved | same document; DECISIONS N-11 | — |
| v1-403 | Appendix: retrospectives | row: `python3` resolved to 3.9 | moved | same document | — |
| v1-404 | Appendix: retrospectives | row: Fixed-template notifications lied | moved | same document | — |
| v1-405 | Appendix: retrospectives | row: Process outran the product (~74 ADRs) | moved | same document; HARNESS §7 | — |
| v1-406 | Appendix: test-strategy panels | heading | superseded | v2 Version history: "the proposed-panels appendix (executed; `docs/TEST_STRATEGY.md` and the panel reports)" | panels were executed, not merely relocated |
| v1-407 | Appendix: test-strategy panels | paragraph (Five focused reviewers...) | moved | `docs/TEST_STRATEGY.md`; `docs/reference/reviews/` panel reports | — |
| v1-408 | Appendix: test-strategy panels | table (5 rows) | moved | `docs/TEST_STRATEGY.md` | — |
| v1-409 | Appendix: test-strategy panels | paragraph (Estimated cost) | moved | `docs/TEST_STRATEGY.md` (outcome fulfilled) | the specific cost-estimate sentence itself is not restated verbatim anywhere found |
| v1-410 | Appendix: research brief | heading | superseded | DECISIONS D-13 "closed... never arrived"; v2 Version history | — |
| v1-411 | Appendix: research brief | paragraph (Title) | absent | — | "Engineering controls for AI-assisted codebases: preventing silent failures..." |
| v1-412 | Appendix: research brief | paragraph (Context) | absent | — | single-developer Python project description written for the brief |
| v1-413 | Appendix: research brief | list item: Q1 (mechanical controls with documented effectiveness) | absent | — | — |
| v1-414 | Appendix: research brief | list item: Q2 (ratchet design) | absent | — | — |
| v1-415 | Appendix: research brief | list item: Q3 (post-run data invariants) | absent | — | — |
| v1-416 | Appendix: research brief | list item: Q4 (working agreements for coding agents) | absent | — | — |
| v1-417 | Appendix: research brief | list item: Q5 (mutation testing cadence) | absent | — | — |
| v1-418 | Appendix: research brief | list item: Q6 (SQLite production failure modes) | absent | — | — |
| v1-419 | Appendix: research brief | list item: Q7 (known anti-patterns in AI-generated Python) | absent | — | — |
| v1-420 | Appendix: research brief | paragraph (Deliverable) | absent | — | "a prioritized list of controls with cost, what each catches..." |
| v1-421 | Appendix: research brief | bullet (Reddit-side behaviors marked unverified) | carried | v2 Content-state-machine / TDD-policy probe-day language | "closed in M1a with the probe command and become fixtures" |
| v1-422 | Review harness | heading | carried | v2 "Review harness (agentic panels at critical points)" | — |
| v1-423 | Review harness | paragraph (Wes will lean on Claude and on agent panels...) | reduced | v2 opening paragraph | model-name-specific phrasing dropped (no-model-names rule); adds register-row requirement (G50) |
| v1-424 | Review harness | table (5 rows) | carried | v2 table (6 rows) | v2 adds a new "A milestone or a design freeze" row (see § New) |
| v1-425 | Review harness | row: New module/service/migration | carried | v2 row | — |
| v1-426 | Review harness | row: A big change/new phase plan | carried | v2 row | — |
| v1-427 | Review harness | row: Every ordinary PR | reduced | v2 "Every ordinary change" row | explicit `/code-review` tool-name/flag detail dropped |
| v1-428 | Review harness | row: Large PRs, milestone merges | reduced | v2 "Large changes and milestone merges" row | explicit `/code-review ultra` command name dropped |
| v1-429 | Review harness | row: A decision Wes must make | carried | v2 row | — |
| v1-430 | Review harness | paragraph (Mechanics: a `tools/review/` script...) | reduced | DECISIONS 2026-09-14 "External reviewers" entry | the automated multi-provider runner described here was not built; DECISIONS records the actual mechanism built instead (manual packet + external chat/Codex review) |
| v1-431 | Review harness | paragraph (Round construction, added 2026-09-13...) | carried | v2 closing paragraph after the Review-harness table | near-verbatim |
| v1-432 | Agent model tiers | heading | carried | v2 same heading | — |
| v1-433 | Agent model tiers | paragraph (Wes's rule...) | reduced | v2 opening paragraph | historical "until 2026-09-13 every sub-agent inherited..." narrative dropped |
| v1-434 | Agent model tiers | table (4 rows) | carried | v2 same table | — |
| v1-435 | Agent model tiers | row: The main session | carried | v2 row | — |
| v1-436 | Agent model tiers | row: Opus | carried | v2 row | — |
| v1-437 | Agent model tiers | row: Sonnet | carried | v2 row | — |
| v1-438 | Agent model tiers | row: Haiku | carried | v2 row | — |
| v1-439 | Agent model tiers | paragraph (Rules: a Sonnet stage...) | reduced | v2 closing paragraph | "review panels mix providers once `tools/review/` (M1) can call one that is not Anthropic" sentence dropped — no automated multi-provider runner was built |
| v1-440 | Workspaces | heading | carried | v2 "Workspaces: expanding to other domains" | — |
| v1-441 | Workspaces | paragraph (Wes expects to point the same system...) | reduced | v2 "The design unit" / "Direction" paragraphs | "for a consulting practice" framing dropped per D-32 (no business application; both domains restated as personal interest) |
| v1-442 | Workspaces | paragraph (Workspace lifecycle decided 2026-09-13) | carried | v2 "Lifecycle" paragraph | — |
| v1-443 | Resilience to outages | heading | carried | v2 same heading | — |
| v1-444 | Resilience to outages | paragraph | carried | v2 same paragraph | cadence language updated (daily → twice-weekly); adds D-30/KI-024 references |

## New in version two

Units with no version-one ancestor found.

- **Front-matter contract** (purpose / update-policy / mirrors / verified-at) on every living document, including the plan itself — the document-policy mechanism (G55) built 2026-09-15.
- **"From data to insight"** section — a new mid-plan section stating the ranking, theming, and coverage philosophy as connected prose rather than scattered decisions-table rows.
- **Built-versus-planned "State" columns** on the Module-map and CLI-commands tables, and per-row build tags elsewhere (e.g. "tranche B", "M2") — reflects what is actually built, absent from the pre-build v1.
- **`workspaces` table row** in the Data model — schema support for a second domain, seeded 2026-09-13/14, not present in v1's schema.
- **`backups` table row** in the Data model, with its own columns (path, sha256, size, integrity result, kind, schema_rev, table_counts_json) — the destructive gate's record, added after v1 was written.
- **"Schema revisions (Alembic, zero-padded ids)"** paragraph — a built revision history (0001–0004) that did not exist when v1 was written.
- **D-31 backup-retention decision** (one online-backup copy per scheduled run, two post-reconcile copies kept) — reasoned out 2026-09-15, replacing v1's daily/weekly VACUUM INTO scheme rather than refining it.
- **Workspaces: "What is built and what is not"** — an honest built-vs-planned accounting of the workspace feature, a genre v1 does not use for this section.
- **Workspaces: "Leaving a domain"** — the archive/delete/instance disposal paths spelled out as a standalone paragraph.
- **Workspaces: "What a second domain should expect"** — volume-assumption limits and the two deferred levers (daily cadence, ingest filter) for a high-volume second domain.
- **`docs/OVERVIEW.md` and `docs/INSIGHTMINER_HARNESS.md`** named as companion documents throughout the plan — both pages were built after v1.
- **Version history table** — the retirement ledger for v1→v2 itself, a mechanism that only exists because a version two was cut.
- **Review-harness table row "A milestone or a design freeze"** (the external review round, packet-built, sent to more than one provider) — the actual external-review mechanism built 2026-09-14, distinct from v1's undelivered `tools/review/` plan.
- **Web-UI Design-rules row "Writes"** (one read-write engine behind the writer-map repository, N-07) — a design correction made after v1 was written (v1 proposed `mode=ro` for page routes; N-07 declined it).
- **Gates table row "Documentation gates"** (the consolidated G33/G34/G35/G39/G40/G44/G45/G47/G50/G52/G54 set) — the whole document/memory-policy enforcement layer, built through September 2026, after v1.
- **Gates table row "Dependency pins"** (G53) — pin-with-behavioural-contract enforcement, added with the PRAW-major-pin decision.
- **Gates table row "Schedule contract"** (`tests/deploy/`) — binds the plist schedule, staleness threshold, and doctor default to D-30; built after the cadence change and KI-024.
- **Gates table row "Review-only ceiling"** (`.ratchets/review_only_rules.txt`) — the ceiling on rules with no mechanical enforcer, part of the "every rule names its enforcer" mechanism built into `CLAUDE.md` and the plan's rules table.
- **Known-patterns table row "A hook present but never installed, or a script never registered"** — added after the incident where the read-before-touch hook shipped unregistered.
- **Workflows table row "Staleness check"** (hourly `doctor` under launchd) — split out as its own workflow row.
- **Workflows table row "Guard review"** (quarterly, ledger verdicts and firings) — new cadence row.
- **Milestones D0 row's framing** ("both were overtaken by the UI panel's specifications and by the milestones as executed, without a formal close") — an honest-status admission that the design lock-down was never formally closed, a statement v1 could not make about itself.

## Counts

Counted mechanically from the table's disposition column (`grep`/`awk` over this file, not hand-tallied):

- carried: 295
- moved: 69
- reduced: 48
- superseded: 20
- absent: 12 (10 plain `absent`, plus 2 rows marked `absent (retired with a home)` — the two Web-UI wireframes, which are gone from the plan's own text but have a named home outside the three searched documents: git history and a specific review record. They do not fit `moved`, whose definition is scoped to the decisions log, the overview, or the harness page, so they are counted under `absent` with the distinction kept visible in the disposition cell.)
- new (v2 units with no v1 ancestor): 22 (counted mechanically from the bullet list above)

Total: 295 + 69 + 48 + 20 + 12 = 444, matching the 444 rows v1-001 through v1-444 (verified: sequential, no gaps or duplicates).
