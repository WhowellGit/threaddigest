# Prior-project retrospectives → plan: reviewer B — 2026-09-12

> Raw, lightly de-entitized report from a reviewer agent asked to read `SYSTEM_ARCHITECTURE_AND_REBUILD.md` and `PROJECT_JOURNEY.md` in full and map them onto the Insight Miner plan. Treat as one perspective: it had the documents and the plan, not the conversation. Disposition of its recommendations is in `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md`.

Legend: **[G]** general lesson (any SQLite/Python pipeline) · **[D]** specific to the old system's domain or its particular mistakes. Citations: `ARCH` = `SYSTEM_ARCHITECTURE_AND_REBUILD.md`, `JOURNEY` = `PROJECT_JOURNEY.md`, `PLAN` = the Insight Miner plan.

## A. What the old system was

The earlier project (formerly two separate projects, a collector and a downstream store) was a solo-operator-plus-AI-agents bug-intelligence pipeline. Four REST sources (issue tracker, pull requests, crash events, release notes) were fetched to disk as JSONL/JSON sidecars, run through a 22-step pure-Python enrichment ladder, then imported into one SQLite database (~36 tables + 8 views, ~815 lines of DDL, a crash DB that grew 574 → 747 GB), with FTS5, bge-m3 embeddings, BM25, and Slack triage cards on top. Scale: ~1.5M raw crash events → ~85K distinct crashes, ~49K bugs, ~85K PRs, ~230K review comments, ~680K LOC Python, ~17K tests, ~4,300 markdown docs (81% agent-report exhaust). It ran on a 2–3 machine fleet coordinated through a Slack channel, with data on the same QNAP NAS the new plan targets. It began March 2026 as "can I get my bug data out of Jira?", had no version control until the May monorepo merge, and was "born out of necessity, not planning" (JOURNEY §1, §5; ARCH Part 0). **Transfer judgement:** the scale, multi-machine fleet, embeddings, and eval-leak lessons mostly do *not* transfer; the SQLite integrity, migration, silent-failure, two-path-drift, and agent-behavior lessons transfer almost verbatim.

## B. Architecture decisions that caused pain, and what replaced them

| # | Decision that hurt | Pain | Replacement + rationale | Source |
|---|---|---|---|---|
| B1 [G] | Schema version and enums hand-copied as literals across writers/readers | One missed literal stamped **825K rows** with a stale version; a version bump without a reader catch-up silently dropped fields | `contract/` typed leaf: every writer imports the constant, every reader asserts it; drift verifier merge-blocking. "Import it; never trust a transcribed literal." | ARCH M1; Part 4 row 1; §5.3 |
| B2 [G] | Two processes joined by a file handoff with no contract | "The most expensive seam in the system": three handoff cycles dropped silently | Handoff manifest (schema pin + fingerprint) + a pre-embed gate; count reconciliation manifest-vs-`COUNT(*)` | ARCH Part 3 |
| B3 [G] | Several scripts each (re)writing the same view; ad-hoc migration scripts | Competing view migrations diverged | `schema_migrations` applied-ledger: each id recorded once, chain **aborts on first failure** rather than committing a half-migrated DB | ARCH "The data model" |
| B4 [G] | `LEFT JOIN … issues` with NULL read as "absent" | Empty table ⇒ zero cross-source links, silently; the 2026-06-27 DB-integrity crisis | Presence floor at the bless boundary; gate asserting the table is populated; cross-epoch field-collapse alarm | ARCH data-model callout; §5.9 |
| B5 [G] | Same decision implemented on two code paths | ~50K of 53K sidecars silently lost fields when only one path was updated; a guard ran on one path only; text builders drifted | Shape-parity and AST-lock tests; the durable fix: one shared function + **value-level** parity | ARCH Stage 2; Part 4 row 8 |
| B6 [G] | Boolean off-switch for a safety mechanism | Found to have silently disabled saturation fleet-wide | Deleted; cost control expressed as a **ceiling**, not a boolean; non-saturating paths must register a written reason or raise | ARCH Stage 1a |
| B7 [G] | Non-atomic JSONL appends | **30,000+ PRs wiped** by a partial write | Write-then-rename; resume treats missing/zero-byte/unparseable as corrupt-and-refetch | JOURNEY §2; ARCH PR Stage 1 |
| B8 [G] | Any script could open the crash DB writable | Un-reproducible data one bad script away from loss | Read-only by default (~37 scripts flipped to `mode=ro`); a pre-ingest gate on all ~26 write doors: recent verified backup exists + no live fetch + per-table sufficiency, else exit non-zero | ARCH Part 3 |
| B9 [G] | God-objects/functions | 1,509-line function; 5,359 LOC script | Characterization goldens, then incremental extraction | ARCH Part 4 row 2 |
| B10 [G] | Back-compat shims after relocation | "Editing the name-matching file changes nothing"; five files with one name | Shim resolution rule; stated as debt | ARCH §5.8 |
| B11 [G] | Stored derived value used instead of live recompute | Stored team 27–30pp less accurate than the live engine | Lint forbids reading the stored column | ARCH ownership routing |
| B12 [G] | Field names that lie | Mislabeled twice, came back once | Kept the names, added a test requiring the meaning stated at every site | ARCH Stage 3 |
| B13 [G] | ~72 scattered hardcoded paths | Relocation stranded parts of the harness silently | Single loud-fail front door; re-point ritual | ARCH M9; §5.2 |
| B14 [G] | Live status restated inline in docs | Rotted "twice in one week" | LIVE state in exactly ONE place; "derive state, never narrate it" | ARCH Part 0 |
| B15 [G] | Evidence captured into a catch-all JSON column | Read by nothing | "Put every captured evidence blob into the importer's field maps on day one" | ARCH crash path |
| B16 [D] | Enrichment auto-ran after sync | Built off a half-synced corpus | Manual trigger; hard-blocks while the sync lock is held | ARCH §5.3 |
| B17 [D] | Rebuild runbook "re-fetch raw" | Sentry retains 90 days | Raw tree ranked #1 un-reproducible asset | ARCH §5.1 |
| B18 [G] | Dense embeddings assumed to be the retrieval tool | Keyword/BM25 won ~3–11× on identifiers | "Route the method to the task" — validates FTS5-first | ARCH PR Stage 6 |

## C. Failure catalogue (database-side first)

Detection: **H** human noticed; **G** gate caught; **S** silent until measured later.

### C.1 Schema / migrations
| # | What happened | Root cause | Det. | Fix |
|---|---|---|---|---|
| S1 | 825K rows stamped with a stale `schema_version` | One un-updated literal | S | `contract` module |
| S2 | Importer silently skipped fields whose columns did not exist yet; embed later crashed | DDL not run before import | G (late) | "DDL before imports" build-order rule |
| S3 | Diverging view migrations | Multiple writers of one object | H | Applied-ledger, abort-on-failure |
| S4 | Full re-import wiped a derived table | Coupled steps without an enforced order | G | Ordered steps registry |
| S5 | Loader run before its inputs produced **zero** links silently | Step ordering | G | Ordering rule + gate |
| S6 | Verification gate refused the imports that would satisfy it | Gate placed first | H | Gate moved last |
| S7 [D] | Code schema vs embedded corpus schema mismatch | Additive filter-only columns | by design | Explicit intent module + completeness test |

### C.2 Data integrity
| # | What happened | Root cause | Det. | Fix |
|---|---|---|---|---|
| I1 | **Crisis:** half-built DB promoted to live; empty table read as "absent"; 57,273 issues recovered | No presence floor; promotion not gated | H | Presence floor; populated assertion; supervised rebuild |
| I2 | 30,000+ PRs wiped by a partial JSONL write | Non-atomic write | H | Write-then-rename; chaos test |
| I3 | Inconsistent key convention + `int()` in `try/except: continue` with no counter — worked by accident; "cleaning up" would silently zero the feature driving 84% of picks | Swallowed parse failure + synthetic fixtures | S | Shared parse helper, failure counter, per-provenance nonzero-load canary |
| I4 | Pass rewrote every sidecar unconditionally; mtime bumps cancelled pending re-enrichment | Unconditional write | S | Diff before write |
| I5 | Tested-but-wrong fixture recovered zero signatures for ~2 weeks; an "event count" field was an all-time total (~38× inflation) | Assumed field semantics | S | Probe and measure |
| I6 | Reader keyed one name; writer used another (0.0% vs 38.8% populated) — highest-weight signal discarded | Key-name drift | S | Contract |
| I7 | Cross-OS cluster: utf-8 mismatch; a colon in a filename made `open()` raise and the attachment was dropped silently | Single-OS assumptions | S then H | Explicit encodings; validators |
| I8 [D] | Seven build-bot accounts nearly doubled the "human" review corpus | Generic `[bot]` filter insufficient | S | Project-specific bot list |
| I9 | Stale key wins over fresh token whenever non-empty | Credential precedence | H | Documented trap |
| I10 | Setting a "secret" salt silently repartitions every scrubbed identifier | Salt in the hash key | H | Locked UNSET |
| I11 | A regex silently drops strings that do not match its shape | Silent set-drop | S | Documented hazard |
| I12 | Snapshot manifest reported a stale count; only the file was current | Two update paths, one manifest | H | Read the artifact, not the manifest |
| I13 [D] | Fault address in exception text made near-identical crashes read as distinct; a cap applied before stripping boilerplate discarded signal | Normalize-before-cap ordering | H | Parse full, classify, then cap |

### C.3 Concurrency / locking / environment
| # | What happened | Fix |
|---|---|---|
| L1 | Enrichment could run while a sync held the corpus half-written | Advisory lock; enrich refuses while sync active |
| L2 | Session-bound watchers died on suspend while the work survived | Durable state + on-demand checks |
| L3 | Progress cursor advanced before the batch was durably emitted → lost messages | Advance cursor only after flush |
| L4 | `PRAGMA integrity_check` over SMB reports false corruption | Never trust over SMB; data on local volume |
| L5 [D] | Backgrounded listener orphaned — "#1 recurring fleet failure"; a REMIND hook was insufficient | Hard-BLOCK hook |
| L6 [D] | Serving DB on any machine is a copy behind live | One canonical DB |

### C.4 Silent failures
| # | What happened | Fix |
|---|---|---|
| F1 | Truncated scan reported a clean partial; the corpus is not re-fetchable | `FetchResult(items, meta{truncated})` + `ensure_complete()` |
| F2 | Filters failing open on malformed input; a declared filter was a never-applied no-op; a leak-guard printed "leak-clean" on a `None` anchor | Fail closed; "a filter you have not tested with a malformed input is untested" |
| F3 | A corroboration gate was implemented, unit-tested, and **called by nothing**; enabling the feature shipped the un-approved rule for a day | "Test reachability, not just behavior" |
| F4 | Wrong-product predicate fired **zero** times across 2,693 rows | Repair |
| F5 | A "lock" test was a source-grep that never called the function bypassing the gate | Behavioral test |
| F6 | First cross-stage workflow tests found a mis-ordered step, a swallowed crash, two "canonical" tests passing against an empty directory | Workflow-test layer |
| F7 | Silent-failure counters all read 0 — the swallow paths never incremented them; ~285 silent-ok sites | Counter on every parse-failure path |
| F8 | Vector count fell 25.5% between epochs; the one check was warning-only, measured churn not net loss | Per-modality epoch-delta gate |
| F9 | Alert path itself could be silently broken, making every "all clear" unverifiable | Delivery canary |
| F10 | Two render sites read a field nothing populates | Retire dead reads |
| F11 | Duplicate-post guard failed open but its token lacked read scope → duplicate incident | Verify the guard's dependency |
| F12 | A cap compared against on-disk total → every capped run a silent no-op | Count `written_this_run` |
| F13 | Denominator/container confusion: a "coverage hole" that was a filter drop-rate; a bogus P1 across ~40 docs; a field 91% "present" with 0% content | "Scope before you weigh"; "a container existing is not data existing" |
| F14 [D] | 95.5% of bugs read `crash_type=unknown` for ~18 months while the data sat inline | Pure regex fix |
| F15 | Reader helpers return `None` on parse error, masking malformed as absent | Flagged as debt |
| F16 | A quality field hard-coded so a gate would pass; then embedded as if true | Call the real classifier |

### C.5 Testing gaps
| # | Gap | Consequence |
|---|---|---|
| T1 | Ratchet lints ran only in the full suite, **not in the commit path** | "The only thing between a regression and the corpus was someone remembering to run the full suite — meaning the AI being prompted" |
| T2 | Shape-parity test locked key **set**, not values | Drift invisible |
| T3 | Tests used synthetic fixtures | Latent bomb invisible |
| T4 | Hand-typed test count was silently off by 57 | Machine-set headline |
| T5 | The rule that directly caused the vector swing had zero tests | Highest-value gap |
| T6 | Backtest harness could not reproduce its own baseline | Numbers not promotable |
| T7 | Hand-curated data had no semantic validators; refactor guards proved code *moved*, not that data was *correct* | Quietly-wrong data shipped |

### C.6 AI-agent behavior / drift
| # | Observed |
|---|---|
| A1 | An MCP tool "reported success but wrote nothing to disk" (day one) |
| A2 | Agents skipped a required grounding step ~1 in 5 → converted to a script |
| A3 | Agents edited shims that change nothing |
| A4 | Docstrings contradicted code; READMEs described target state as built |
| A5 | Corrected label re-introduced by new code |
| A6 | "Narrating 'relaunched' without running it breaks the chain" |
| A7 | AI recommended shipping after two review rounds; the operator's third round found five blockers including a security hole |
| A8 | A finding cited an audit that never ran the test it claimed; reached the operator twice |
| A9 | Shallow-pass labels flipped 34.8% when re-grounded in real code |
| A10 | Process outran product: ~74 ADRs + 530 process docs before code moved; ~12% of commits pure process churn; docs:code commits 1.5:1; ~81% of 4,300 docs agent exhaust; operator: "we're spinning wheels", "stop asking me to commit" |
| A11 | Stale error-message remediation pointed at a pre-merge path |
| A12 | Provisional weights "to be tuned after first measurement" were never measured; the 8-feature rubric was net-negative vs a one-line baseline |

### C.7 Tooling / environment
| # | Observed |
|---|---|
| E1 | **launchd is blocked by TCC for repos under `~/Desktop`, `~/Documents`, `/Volumes/*`** |
| E2 | Bare `python3` resolved to 3.9/3.11 and silently corrupted output → lint-locked pin |
| E3 | Unguarded `import fcntl` poisoned the import chain on Windows (139 test hits) |
| E4 | Space-containing directory name broke globs/shell paths |
| E5 | Credential backup files leaked → content secret-scan ratchet |
| E6 | Auto-memory and hooks path-keyed; a repo move strands them silently |
| E7 [D] | Hardcoded `"mps"` device; runaway memory |

### C.8 Process / planning
| # | Observed |
|---|---|
| P1 | No version control until the merge sprint |
| P2 | 69% accuracy → 3.4% under a leak-free split; ~40% self-synthesized "gold" |
| P3 | Same count swung 393 → 918 → 2,303 on counting convention → every metric one tested function + definition hash |
| P4 | "Is the overhead worth it?" left honestly open — no counterfactual |

## D. Process lessons about working with an AI coding agent

1. **Mechanism, not discipline.** Every costly lesson was converted into a lint, regression test, register entry, derive-live tool, hook, or skill. A REMIND hook for the #1 fleet failure was insufficient and became a hard BLOCK.
2. **Enforcement must sit in the path every change takes.** Ratchets outside the commit path drifted red between runs.
3. **The two intelligences fail differently.** The model's characteristic failure is confident-wrongness it cannot self-detect; the human's contribution is domain intuition and "something is off". "The operator's corrections mattered more than the operator's approvals."
4. **Adversarial, independent review is a requirement**, aimed at the previous round's conclusion, with teeth to retract; same-model builders agreeing is not confirmation.
5. **Provisional until the binding test — including negatives.**
6. **Denominator discipline.**
7. **Derive state, never narrate it.** "A manual number is a lie waiting to happen."
8. **Test the guard's reachability and its behavior on malformed input**, assert values not shapes, fail closed.
9. **Ceilings, not booleans**, for anything safety-related.
10. **Make agent-skipped steps into scripts**, never leave shims, keep one canonical door per workflow.
11. **Apparatus is its own drift.** The operator's "are we spinning wheels?" was the governing signal.
12. **Docs: code wins.** APPEND-ONLY for logs, PRUNE-STALE for status; no mirrors.
13. **For questions with no deterministic gold, a small blind human-labeling packet with a pre-registered decision rule** beats another automated pass.
14. **What the human had to do:** create accounts/credentials, adjudicate ambiguous data, run blind labeling passes, push for extra review, notice numbers the gates missed, override the AI's "ship", stop process churn, keep the AI running the full suite.

## E. Mapping to the new plan (reviewer's priorities)

| # | Lesson | Gap / refinement | Priority |
|---|---|---|---|
| E1 | launchd cannot read `~/Desktop` under TCC | Move repo+data before the scheduled-runs milestone; `doctor` check | **High** |
| E2 | Empty table / NULL read as absent | Presence floors and populated-rate floors per column with a cross-run alarm | **High** |
| E3 | Same value produced by two paths must match | Value-level parity test across ingest paths; per-path field-ownership table | **High** |
| E4 | Guards tested in isolation but unreachable | Guard-reachability rule; every invariant proven via the real run | **High** |
| E5 | Enforcement outside the path changes take; the model cannot self-detect | CODEOWNERS requiring Wes's review on `tests/`, `.ratchets/`, migrations, `schema.sql`, `CLAUDE.md`, `.github/` | **High** |
| E6 | Migrations must be all-or-nothing and ordered; batch mode drops FTS triggers | FTS rebuild in the same migration; `transaction_per_migration=True` | Medium |
| E7 | Fail closed on malformed input | Unknown never defaults to `live`; `next_check_at NOT NULL` | Medium-High |
| E8 | No boolean bypass of a safety mechanism | No flag may skip reconcile/scrub; cap `--budget`; invariant "last full reconcile ≤ 48 h + grace" | Medium-High |
| E9 | Destructive writes need a gate | Backup recorded in a `backups` table + `--yes` on every destructive door; UI and Datasette `mode=ro` | Medium |
| E10 | Truncation must be named in the return value | `Page`/`TreeResult` carry `complete`; consumed by the service layer | Medium |
| E11 | Atomic writes; ordering between two stores | DB authoritative after a crash; tolerate partial trailing JSONL line; compression write-verify-rename | Medium |
| E12 | Two writers to one DB need a writer map | Table → writer map; web repo exposing only its allowed writes | Medium |
| E13 | Metrics are one tested function | Define now; rank themes by distinct authors; UI and digest share functions | Medium |
| E14 | Derived counters drift | `authors` counts by view or invariant | Medium |
| E15 | Alert path must prove delivery | `notify --test` weekly; `doctor` records last delivery | Medium |
| E16 | Runs that hang hold the lock forever | Wall-clock ceiling; launchd `ExitTimeOut` | Medium |
| E17 | Apparatus outran code | Agent reports never committed; docs may not restate counts; size ratchets | Medium |
| E18 | Bot contamination | Flag moderator-distinguished and known bots | Low-Medium |
| E19 | Hard-block hooks for the most damaging agent actions | 2–3 `PreToolUse` hooks; keep tiny | Low-Medium |
| E20 | Field names must not lie | `comment=` on every column | Low |
| E21 | Explicit encodings, POSIX-only imports, safe filenames | ruff PLW1514; Windows out of scope | Low |
| E22 | Interpreter pin | launchd invokes the venv interpreter by absolute path | Low |
| E23 | Human blind-labeling for non-deterministic quality | 30-post packet per theme labeled by Wes; precision per theme in the digest | Low-Medium |
| E24 | Keyword beats dense for identifier-heavy text | Keep FTS as the retrieval arm at M5 | Low |
| E25 | Data never on SMB/[earlier-project] | `doctor` checks `DATA_DIR` is local | Low |
| E26 | Non-re-fetchable data protected above the DB | Covered; scrub-ability is by design | Low |

## F. Reviewer's top 10 changes

1. Move the runtime out of `~/Desktop` before scheduled runs; `doctor` check for TCC-protected paths.
2. Human-only merge on enforcement surfaces via CODEOWNERS.
3. Presence-floor and populated-rate invariants with a cross-run alarm.
4. Value-level parity across ingest paths and a per-path field-ownership table.
5. Guard-reachability discipline.
6. Fail-closed state machine and NOT NULL scheduling columns.
7. Destructive-operation gate; web and Datasette read-only.
8. FTS-aware migration checklist; `transaction_per_migration=True`.
9. Metric definitions as named tested functions shared by digest and UI, with denominators; "top issue" by distinct authors.
10. Cap the apparatus and the flags: size ratchets, no shims, agent reports not committed, no flag skips reconcile/scrub, `--budget` hard-capped, 2–3 hard-block hooks.

## G. Reviewer's questions for the owner

1. Is `~/Desktop/Reddit` negotiable? Was the launchd/TCC block observed on this Mac?
2. Will the new DB live on the same QNAP as the old system's data, and is that a local volume from Container Station's perspective?
3. Willing to be the required reviewer on the enforcement surfaces?
4. Which of the old system's guards were worth their cost?
5. Is 30-day JSONL plus scrub-able `raw_json` enough as the "irreplaceable tier"?
6. Exclude AutoModerator/mod-distinguished posts from theme counts by default?
7. "Top issue" definition: post count, comment count, distinct authors, or score?
8. Should `--budget` have a hard maximum?
9. Claude Code `PreToolUse` hard-block hooks in this repo?
10. Can `KNOWN_ISSUES.md`, `DATABASE_SYSTEM_AND_INTEGRITY_REFERENCE.md`, `UPDATE_SEMANTICS.md`, and `RF_BREAKAGE_PATTERNS.md` be shared?

**Overall verdict:** the plan is already unusually well aligned with the old system's hardest lessons. The gaps are concentrated in five places: an environment conflict (Desktop + launchd), who merges enforcement changes, presence/populated-rate floors, multi-path parity, and proving guards are reachable rather than merely present.
