# Database learnings applied — 2026-09-12 (ranked)

> What changed in the Insight Miner plan after reading the earlier project's retrospectives, ranked by how much each item deserves to drive our work. Append dated sections below as the implementation evolves; do not rewrite history.

## How this was assessed (provenance and caveats)

- **Sources:** eight documents in `~/Desktop/Reddit/Database_Key_Learnings/` (point-in-time copies of the earlier project's `framework/docs/…`). `INDEX.md`, `WHY_THE_GUARDS_EXIST.md`, and `CRITICAL_FAILURES_RETROSPECTIVE.md` were read directly by Claude. `KEY_LEARNINGS.md`, `DEAD_ENDS_AND_RULED_OUT.md`, `VALUE_STAGE_KEY_LEARNINGS.md` were read by reviewer A and `SYSTEM_ARCHITECTURE_AND_REBUILD.md`, `PROJECT_JOURNEY.md` by reviewer B. Their raw reports are in `reference/reviews/` and are the audit trail for every citation below.
- **Who decided:** the adoption verdicts are Claude's, made the same day. There was a deliberate bias toward adopting, because the sources are audited failures with numbers attached rather than opinions. Several recommendations were declined or scoped (section 3), and a few reviewer claims were discounted for lacking context (section 4).
- **What has not happened yet:** an adversarial review of the *applied set* itself. Reviewer feedback was scrutinized by one reader, not challenged by an independent one. Until that pass runs (proposed as part of the test-strategy panels), treat the confidence column as one informed judgment, not a consensus.
- **Scoring key.** *Confidence*: is the lesson real and does it apply to this system (H/M/L)? *Importance*: damage if ignored here. *Value*: leverage for ongoing work beyond the immediate fix. *Cost*: effort to adopt. *Phase*: when it lands. Ranking is by confidence × importance × value, with cost as the tiebreaker.

The earlier system, for transfer judgement: a solo-operator-plus-agents bug-intelligence pipeline over Jira, GitHub PRs, Sentry crash events, and release notes; raw JSONL/JSON sidecars on disk; a 22-step Python enrichment ladder; one SQLite database (~36 tables; a crash store that grew from 574 GB to 747 GB); FTS5, embeddings, Slack triage cards; a 2–3 machine fleet with data on the QNAP. Its scale, fleet, embedding, and eval-leak lessons mostly do not transfer. Its SQLite integrity, migration, silent-failure, two-path-drift, and agent-behavior lessons transfer almost verbatim.

## 1. Ranked: what to leverage, in order

| Rank | Item | Conf. | Import. | Value | Cost | Phase | Verdict | Source finding |
|---|---|---|---|---|---|---|---|---|
| 1 | **Test isolation of the data directory is structural**: autouse fixture pointing every test at a temp dir, and settings that refuse the default data dir when pytest is loaded unless explicitly opted in | H | H | H | low | M0 | Adopt now | Tests overwrote live artifacts twice; reads honored the test dir, writes did not (A #53–54) |
| 2 | **Runtime lives outside TCC-protected folders** (`~/Desktop`, `~/Documents`, `~/Downloads`, `/Volumes/*`); `doctor` checks the path; launchd invokes the venv interpreter by absolute path | H | H | M | low | M0 | Adopt now; folder decision pending with Wes | launchd silently denied access; observed directly (B E1, ARCH §5.2) |
| 3 | **Upsert is `INSERT … ON CONFLICT DO UPDATE`, never `INSERT OR REPLACE`**, with a PK-stability invariant (`pk`, `first_seen_at`, `max(pk) == count(*)` unchanged across reruns) | H | H | M | low | M0/M1a | Adopt now | 16,813 rowids burned; false divergence alarm; would detach FTS rows here (A #18) |
| 4 | **Fail-closed state machine**: unknown `removed_by_category`/malformed bodies never default to `live`; unknown enum values stored raw and counted; `next_check_at NOT NULL` | H | H | H | low | M1a | Adopt now | Silent accept on unknown caused a 720K-row drift; filters failing open (A #42, B F2) |
| 5 | **Population floors and coverage counters** per column over recent live rows, with an amber alarm against the trailing 7-run median | H | H | H | medium | M1a | Adopt now | A column NULL on all 52,816 rows while every gate passed; shape verifiers pass on empty substance (A #11–12, B I1) |
| 6 | **Freshness anchor and zero-new detection**: compare the stored watermark with one live listing item per subreddit; per-source freshness tracked separately from run status | H | H | H | low | M1a | Adopt now | Uniform staleness for two weeks with relative checks green; a stale source list hid 12,560 events (A #19–20) |
| 7 | **A positive control for every gate** in `tests/gates/`: construct the bad state, assert red. A gate never seen failing is a hypothesis | H | H | H | medium, grows with each gate | M0 | Adopt now | 9 of ~20 gates unfalsifiable; one blessed an emptied database (WHY_THE_GUARDS_EXIST rule 2) |
| 8 | **Enforcement in the path every change takes**: pre-commit plus required CI; human review on enforcement surfaces via CODEOWNERS | H | H | H | low | M0 | CI now; CODEOWNERS pending Wes | Ratchets outside the commit path drifted; "the only thing between a regression and the corpus was someone remembering to run the full suite" (B T1) |
| 9 | **Guard reachability**: every invariant and failure-matrix row is proven through the real `run` path with the fake planting the violation, never by calling the guard directly | H | M | H | medium | M1 | Adopt | A unit-tested gate called by nothing; a predicate that fired zero times; a "lock" test that was a source grep (B F3–F5) |
| 10 | **Connection chokepoint and single scrub function**: only `db.engine` creates engines (import-linter); behavioral pragma test; scrub mutates DB, FTS, tags, and JSONL in one call | H | M | M | low | M0/M1c | Adopt | Opt-in guard bypassed by the main helper; freshness guard written but never wired (A #44, #17) |
| 11 | **No bypass flags**: nothing can skip reconcile or scrub; `--budget` hard-capped; dry-run and no-network modes proven to make zero calls and zero writes | H | H (compliance) | M | low | M1 | Adopt | A boolean off-switch silently disabled a safety mechanism fleet-wide; a hard gate ran under `--dry-run` (B B6, A #48) |
| 12 | **FTS-aware migrations**: batch operations recreate triggers and rebuild FTS in the same migration; per-revision fixture asserts FTS count equals live count; `transaction_per_migration=True`; new invariants scoped by `normalizer_version` | H | H | M | low–medium | M1a | Adopt | Imports before DDL; diverging view migrations; gates placed first; plus SQLite batch mode's real behavior (B S2–S6) |
| 13 | **Every mutating command takes the lock and writes a run row**; heartbeat carries stage (`rate_wait:37s`); 45-minute stale threshold; wall-clock ceiling; recovery clears error state | H | M | M | low | M1 | Adopt | PID recycling, orphaned harvesters, rate-limit waits misread as stalls, stale markers never cleared (A #31–36) |
| 14 | **One canonical raw shape before normalize**, shape-parity test via `probe`, per-path field-ownership table | M | M | M | medium | M1a | Adopt as the cheap proof | Two producers of one record drifted four times (A #11, B B5). Confidence M because our single normalizer boundary may already suffice; the parity test settles it |
| 15 | **Single `normalizer_version`, `settings_fingerprint` on runs, two-gate discipline** (refactor keeps the golden byte-identical; semantic change is its own PR) | H | M | M | low | M1a | Adopt | Version literal copied into 6+ producers; a one-character filter literal dropped 89% of data; MODIFY-in-place passed shape checks (A #1–3, #23) |
| 16 | **Destructive-operation gate**: restore, downgrade, reprocess, delete-captured-data, container init, and retention sweeps require a recorded verified backup plus an explicit confirmation; web reads and Datasette open read-only | H | M now, H later | M | medium | M1c basic, M3 full | Adopt in two steps | Half-built DB promoted to live; any script could write the crash DB; a partial write wiped 30,000 PRs (B B8, I1, I2) |
| 17 | **Cross-platform controls**: utf-8 on every text open (ruff PLW1514), `os.replace`, guarded `fcntl`, absolute interpreter, Linux as the primary CI matrix | H | M | M | low | M0 | Adopt | `python3` was 3.9 and silently corrupted output; a second OS surfaced a cluster of silent bugs (A #61–62) |
| 18 | **The operator reads real output**: Wes reads seven daily digests against Reddit before M1d closes; zero-context second review for changes to deletion, scrub, migrations, and the upsert repository | H (process) | M | H | low / medium | M1d | Adopt, scoped | The highest-impact bugs were caught by the operator; the AI's "ship it" was overruled by a third review that found a security hole (B D3, A #76, #69) |
| 19 | **Metrics as single functions with denominators**; "top issue" ranked by distinct authors; bot-authored items flagged and excluded by default | M | M | H | low | M1d | Adopt | Counts swung 393 → 918 → 2,303 on convention alone; bots nearly doubled a "human" corpus (CRITICAL #3, B I8, P3) |
| 20 | **Reference corpus with a router**, append-only learnings and insights, prune-stale status, `KNOWN_ISSUES`/`DECISIONS`/`GUARDS`/`RUNBOOK`, agent reports never committed, one currency test | M | M | H | low | M0 | Adopt | Process outran product; 81% of 4,300 docs were agent exhaust; doc currency had to be enforced, not remembered (B A10, A #78–81) |
| 21 | **Notifier proof**: weekly test notification with delivery recorded; digest composed from state, never a template | H | M | M | low | M1d | Adopt | Fixed-template notifications lied; an alert path could itself be broken (B F9, A #46–47) |
| 22 | **Hold the count and cap the apparatus**: size ratchets, two-day time box for scaffolding, widen before adding, `GUARDS.md` pedigree reviewed quarterly | M | M | M | low | M0 | Adopt | 14 of 29 guards never fired; the reflex to answer every incident with a new lint is itself a failure mode (WHY_THE_GUARDS_EXIST) |
| 23 | **Stress scenario at a two-year scale with wall-time budgets**; `EXPLAIN QUERY PLAN` assertions on three or four hot queries | M | L–M | M | medium | M1d/M3 | Adopt lightly, weekly | Small-input tests hid a 90-minute merge (A #55). Our data is small; the value is in the indexes being real, not in scale itself |
| 24 | **Hard-block hooks**, at most three (`--no-verify`, writes to the production DB, edits to ratchet files outside a PR) | M | M | M | low | M0 | Adopt lightly | A reminder hook was insufficient and became a block; but hooks are path-fragile per the same source (B L5, E6) |
| 25 | **Compressed raw files verified before deletion**; a partial trailing JSONL line tolerated on read; the DB is authoritative after a crash | H | L | L | low | M1c | Adopt | Truncated gzip raised an unhandled error; two stores can disagree after a crash (A #41, B E11) |
| 26 | **Monthly mutation testing** on the state machine, paging, and normalizer | M | L | M | medium | M3 | Optional, not a gate | Not validated by the retrospectives; kept because it is the only direct test of whether tests test anything |

## 2. Guard design rules adopted (from `WHY_THE_GUARDS_EXIST.md`)

1. A guard that scans the whole tree for a structural shape earns its keep; a guard that polices a hand-maintained list does not, because the curator is also the enforcer.
2. Key on the invariant, not a surface token: five green guards missed a 42-point gap that one invariant-keyed measurement found.
3. A gate that cannot fail is not a gate; every new gate ships with a constructed-bad-state positive control.
4. The marker window is part of the contract: a check a comment rewrap can defeat measures formatting, not risk. Justifications live in syntax.
5. Probe each item the way a real record would present it: input shape is part of the contract.
6. Assert on the artifact the user receives; two guards on one field must agree and be single-sourced.
7. Birth is not evidence: track what each guard has caught since; hold the count until one has a fired-in-anger record; widening beats adding.
8. Suppression must stay visible: a large baseline is a permanent exemption wearing a ratchet's clothes.

## 3. Declined, deferred, or scoped (with reasons)

| Recommendation | Verdict | Reason |
|---|---|---|
| Windows fallback for the lock (`msvcrt`) | Declined | Windows is out of scope unless a coworker needs it; `fcntl` stays behind a clear error |
| `caffeinate` for scheduled runs | Scoped | Only wraps the interactive first backfill; the daily run is about ten minutes |
| Reimplement PRAW's more-children expansion to get wire-only JSON for trees | Deferred | The parity test (rank 14) is the cheap proof; reimplementation is a later provenance upgrade |
| Zero-context review for every PR | Scoped | Only for deletion, scrub, migrations, and the upsert repository; elsewhere CI is the gate |
| A `jobs` table for multi-service coordination now | Deferred to M5 | One writer today; the flock plus `runs` rows suffice |
| Presence floors stored as ratchet files in `.ratchets/` | Changed | Floors are properties of the data, so they live in settings and post-run invariants, not in code-metric ratchets |
| `authors` as a view instead of counters | Changed | Counters with a `COUNT(*)` invariant keep author pages fast |
| Blind human-labeling packet per theme | Deferred to M3 | High value for the #1 priority; needs a few weeks of captured posts first |
| A grep for repo-root-built paths in `src/` | Replaced | List-policing in spirit; the settings refusal and autouse fixture are the structural control |
| Mandatory operator sign-off on every merge | Not adopted | Wes chose agent-merges-when-green; human review is proposed only for enforcement surfaces |

## 4. Where reviewer feedback was discounted or needs context

- **CODEOWNERS on enforcement surfaces** (reviewer B) reintroduces some review friction Wes explicitly disliked in the earlier project. Scoped to a handful of paths and left to Wes to decide rather than adopted outright.
- **The TCC/launchd block** is documented and was observed directly, but it will be verified on this Mac during M0 with a two-minute test job regardless of the folder decision.
- **Stress testing at 50k posts / 500k comments** reflects the earlier system's scale, not this one's; adopted lightly for the sake of real indexes and query plans.
- **"Docs may not restate counts"** is correct, and it applies to the reference corpus Wes asked for: the corpus must stay curated and routed, or it becomes the exhaust the retrospectives warn about.
- **Both reviewers assumed a developer operating through the CLI.** Wes requires the UI to be the operator surface, so every gate and destructive confirmation must exist as a UI control with a typed confirmation, not only as a CLI flag.
- **Reviewer A's questions about how the old rows were written and whether tests ran against live data** are still worth answering; the answers change how strongly ranks 1 and 3 should be weighted, though both are cheap enough to adopt regardless.

## 5. Decisions raised for Wes

| Question | Recommendation |
|---|---|
| Project location vs launchd/TCC | **Decided 2026-09-13:** `~/repos/insightminer`; `~/Desktop/Reddit` stays for documents |
| Human review on enforcement surfaces | **Declined 2026-09-13** by Wes; compensating controls: positive controls, hard-block hooks, PR bodies listing changed tests, adversarial review, quarterly guard review |
| "Top issue" ranking | **Decided 2026-09-13:** distinct authors, then comments, then score; never raw post count |
| "Zero new posts" alarm threshold | Per subreddit; start at 3 consecutive runs and tune |
| Windows in scope? | No, unless a coworker needs it |
| Additional source documents | its issue register, its database integrity reference, its breakage-pattern catalogue, and its update-semantics note would sharpen the database side further |

## 6. Lessons that did not transfer (and why)

- Embedding, retrieval, and eval-leak lessons (69% → 3.4% under a leak-free split; circular gold): no model or ranker exists here until M5. Kept as an M5 note: FTS/keyword baseline first, a named binding test before any model, a do-not-rebuild index from day one.
- Multi-machine fleet coordination, Slack bridge, copies of the DB behind live: one canonical DB and one collector here.
- Hundreds of gigabytes and 90-day upstream retention making raw data irreplaceable: Reddit's `/new` window plus gap detection makes our raw data reconstructable within limits, and deliberate scrub-ability is a requirement rather than a loss.
- Domain-specific data quirks (Jira assignee bias, Sentry bucketing, crash-signature normalization).

## 7. Living follow-up list for the database implementation

Add dated entries; strike through when done, with the commit or test that closed it.

- [ ] M0: schema rev 1 with integer PKs, `reddit_id UNIQUE`, `next_check_at NOT NULL`, `comment=` on every column, declared indexes; `schema.sql` golden; runtime schema fingerprint.
- [ ] M0: `tests/gates/` positive controls for every ratchet and invariant in the plan's gates table; `GUARDS.md` with birth incident and control for each.
- [ ] M0: data-directory isolation fixture and settings refusal under pytest; verify the launchd/TCC behavior on this Mac with a two-minute test job.
- [ ] M1a: `probe` fixtures for deleted post, removed post, deleted comment with children, leaf-deleted comment, crosspost, "continue this thread" chain; close every Reddit-behavior unknown listed in the collector design review.
- [ ] M1a: shape-parity test (listing vs tree shape) and per-path field-ownership test.
- [ ] M1a: PK-stability invariant; population floors; coverage counters; freshness anchor; unknown-enum counters.
- [ ] M1c: compliance canary through the full run; JSONL rewrite verified; `secure_delete` behavior confirmed; "last reconcile within 48 h + grace" invariant.
- [ ] M1c: FTS-aware migration checklist exercised by the first batch migration; per-revision fixture DB test.
- [ ] M1d: stress scenario at production scale with wall-time budgets; `EXPLAIN QUERY PLAN` assertions; notifier proof.
- [ ] M2: web write surface limited to the table-to-writer map; read paths `mode=ro`; destructive gates as UI controls with typed confirmation.
- [ ] M3: reconcile fallback thresholds tuned against the observed corpus; per-subreddit zero-new threshold; blind labeling packet per theme.
- [ ] M4: `doctor` check that the data directory is a local filesystem on the QNAP; backups recorded with row-count verification.
- [ ] Quarterly: restore drill; guard pedigree review; prune guards that never fire and are cheap to lose.
- [ ] Pending: adversarial review of this applied set (proposed panel).
