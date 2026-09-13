# Prior-project retrospectives → plan: reviewer A — 2026-09-12

> Raw, lightly de-entitized report from a reviewer agent asked to read `KEY_LEARNINGS.md`, `DEAD_ENDS_AND_RULED_OUT.md`, and `VALUE_STAGE_KEY_LEARNINGS.md` in full and map them onto the Insight Miner plan. Treat as one perspective: it had the documents and the plan, not the conversation. Disposition of its recommendations is in `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md`.

**Abbreviations.** KL = `KEY_LEARNINGS.md`, DE = `DEAD_ENDS_AND_RULED_OUT.md`, VS = `VALUE_STAGE_KEY_LEARNINGS.md`, Plan = the Insight Miner plan. **G** = general lesson for any SQLite/Python pipeline; **D** = specific to the old system's domain or to a mistake the new plan already structurally avoids.

**What the old system was** (inferred from the docs): a Mac-first, later multi-machine, Python script collection ("[earlier-project]") fetching Jira, GitHub PRs, Sentry crash events and release notes into JSONL archives + per-item JSON "sidecar" files, feeding a downstream store ("[earlier-project]") with a very large SQLite `crash_db.sqlite`, a vector store, and a Slack-driven triage layer. Schema was a *payload* version stamped on JSON artifacts (`NFS_SCHEMA_VERSION 2.x`), not Alembic DDL. Coordination was via state JSON files, PID/fcntl locks and a `/refresh` cadence check. DE and VS are ~90% about embedding/retrieval/routing levers and transfer only as method lessons; KL is where the database-side failures live.

---

## A. Failure catalogue

### A1. Schema / contract drift

| # | What happened | Root cause | Detected | Fix | G/D | Source |
|---|---|---|---|---|---|---|
| 1 | Schema version was an inline literal in 6+ producers; a bump updated some, not others → 825K `cross_links` rows stamped `2.1.5` in a "v2.2.2" system | No single constant; "if a constant can be inlined as a literal, it WILL drift during a release bump" | Silent; found by audit weeks later | Central `contract/schema_versions.py` + drift detector | G | KL → "April 19-20, 2026" → "Magic-string drift is systematic" |
| 2 | Same anti-pattern three times (schema version, classifier enums, Jira project list): value lists hardcoded in N>1 producers drifted | "Already consolidated" mental model | Silent, production bugs | Rule: used in 2+ places → contract it; lock test scanning scripts for the canonical sentinel | G | KL → "2026-05-15 PM learnings" |
| 3 | The two worst schema drifts were MODIFY-in-place (field meaning redefined), which pass shape checks | Schema evolution treated as add/remove only | Silent; passed verifiers | Schema evolution modelled as ADD / MODIFY / REMOVE; "two-gate discipline": refactor = byte-identical golden; semantics change = separate commit + re-bless | G | KL → "2026-05-20→23" |
| 4 | `event_count_90d` held an all-time total; first ranking over-stated old items up to ~38× | Field name promised a window the value didn't have | Silent until a ranking looked wrong | Rename + companion field; "a field name is a contract" | G | KL → "2026-05-18→19" |
| 5 | Patch bump made the verifier flag every on-disk artifact as MUST-fail | Compatibility predicate inverted for "current freshness" | Loud | Three-way branch: major-mismatch fail / data-newer-than-code fail / older-same-major warn | G | KL → "2026-05-07" |
| 6 | 5 of 13 whitelisted provenance enum values had never been emitted | Enum declared before any producer existed | Silent for months | Verifier flags never-emitted whitelist members | G | KL → "April 19-20" → "Ghost contracts always decay" |
| 7 | Emission nested inside a loop that was permanently empty after the first run → 0 edges across a 5.47M-row graph | Code path gated by state that only held on first run | Silent | Hoist emission to an unconditional pass | G | KL → "v2.3.0" → "Ghost emitters" |
| 8 | Registering a new bundle before its producer existed would have marked all PRs "incomplete" | Completeness check demanded every registered bundle | Caught in design | Sequence: backfill → wire producer → register → lock test | G | KL → "2026-06-11" |
| 9 | Schema required a field nothing had written since v1.1; type too narrow; a field absent | Schema and writers evolved independently | End-to-end pilot | Pilot before release | G | KL → "v2.1.2" |
| 10 | Only 1 of 11 scored fields had matching entries in both reference docs | Human process | Audit | Machine-readable contract + doc integrity checker as hard FAIL | G | KL → "v2.1.2", "2026-05-04" |

### A2. Data integrity: wrong, empty, or stale values

| # | What happened | Root cause | Detected | Fix | G/D | Source |
|---|---|---|---|---|---|---|
| 11 | Two code paths emitted the same record (fat path vs hand-maintained stub path). Drifted **four times**: 50K of 53K sidecars empty; a column NULL on all 52,816 rows; fixture mismatch; 62% missing promotion | Duplicate producers for one shape | Silent each time; the NULL-everywhere case passed "every internal gate" | Shape-parity test + promote-or-fail test | G | KL → "2026-05-08", "2026-05-04" |
| 12 | Shape verifiers passed while a column carried no data | Verifiers check shape, not substance | Consumer-shaped coverage query found 3 real issues | Headline-coverage audit after every schema bump | G | KL → "2026-05-04" |
| 13 | Fields 100% null: code read top-level keys; the bulk endpoint nested them | Wrong key path assumed "no data" | Silent | Check other shapes before down-rating a null field | G | KL → "2026-05-18→19" |
| 14 | A parsing path passed all unit tests and recovered **zero** items in production for ~2 weeks | Fixtures used a wrong-but-plausible shape | Silent | Fixtures sampled from real on-disk artifacts | G | KL → "2026-05-18→19" |
| 15 | Enrichment markers appended into raw files; every re-harvest overwrote them (three times) | Derived data shared a file with raw input; orphaned harvester held no lock | Loud eventually | Raw immutable; derived output separate | G | KL → "2026-05-18→19" |
| 16 | PR `state` frozen at first capture; `dict.get("state", default)` never fired because the key was present with `""` | Absent-key vs empty-value confusion | Silent | Truthiness fallback; state in parity hash | G | KL → "2026-06-15" |
| 17 | Cross-links frozen for ~4 weeks while the corpus advanced; the freshness guard existed but was **dead** (table missing, recorder never wired, checker not in `/refresh`) | Guard written, never connected | Silent | Wire it | G | KL → "2026-06-15" |
| 18 | Terrifying cross-machine "divergence" (63,588 vs 46,775 rows) was `max(rowid)` vs `count(*)`; 16,813 rowids burned by INSERT-OR-REPLACE churn | Fingerprint compared unlike measures; **INSERT OR REPLACE deletes+reinserts so rowids climb** | Loud false alarm | Compare like-for-like | G — directly relevant to SQLite PK/FTS design | KL → "2026-06-15" |
| 19 | Full fetch wrote raw data and reported success, but enrichment + import never followed; everything sat ~2 weeks stale together; relative-currency checks passed | No absolute anchor | Silent; confident wrong triage output | Parity gate; absolute anchor ("newest on server vs newest in corpus") | G | KL → "2026-09-03" |
| 20 | Bulk fetch iterated a ~3-week-stale issue list and silently skipped ~12,560 new events | Work-list file was schema-valid but time-stale | Silent | Work-list gets its own freshness gate | G | KL → "2026-06-13" |
| 21 | Authoritative values captured at fetch silently replaced downstream by windowed/sampled/truncated versions | Both fields "looked populated" | Silent | Keep both; name which one each consumer reads | G | KL → "2026-06-30" |
| 22 | Bodies capped ~500 chars downstream | Import-time truncation | Embeddings looked wrong | Read from the full raw store | G | KL → "Body/Description Truncation Risks" |
| 23 | Filter literal `RELEASE_QUERY = "*26.2*"` silently dropped 89% of issues | Bare literal filter | Silent until counts audited | Named flag piped into the data fingerprint | G | KL → "2026-05-03" |
| 24–30 | Domain-specific: narrow default filters, one carrier field assumed, misleading negative message, hand-curated roster errors, `integrity_check` over SMB `CANTOPEN(14)` (locking, not corruption), utf-8 mangling on Windows, key aliasing | — | — | — | mostly D, with G patterns (audit schema against data population; explicit encodings; never trust `integrity_check` over SMB) | KL various |

### A3. Concurrency, locking, process state

| # | What happened | Fix | Source |
|---|---|---|---|
| 31 | Leaked `active_operation` marker survived because PID recycling put a live unrelated process on the tracked PID | Max-age guard + `atexit` context manager | KL → "v2.3.0" |
| 32 | PID files orphaned on SIGKILL | fcntl locks | KL → "fcntl Locks vs PID Files" |
| 33 | Watchdog misread a rate-limit wait as a stall | Heartbeat carries state (`rate_wait:Ns`) | KL → "Heartbeat Files for Liveness" |
| 34 | A stall marker never cleared on clean completion | Explicit cleanup on success and failure | KL → "Refactoring Patterns" |
| 35 | Orphaned harvester ran with no lock so the "block if sync active" guard saw nothing | All writers register | KL → "2026-05-18→19" |
| 36 | A 10-hour standalone fetcher never updated global state | Any tool >5 min updates global state at checkpoints | KL → "2026-05-04" |
| 37 | Laptop deep-idle dropped DNS; 3 quick retries gave up in ~9 s; backfill died 43,651 items in | Patient retry ladder + `caffeinate`; idempotent per-item markers | KL → "2026-06-11" |
| 38 | Multiple terminals triggering overlapping syncs | Strict lock policy | KL → "Concurrent Pipeline Coordination" |

### A4. Silent failures and unenforced controls

| # | What happened | Fix | Source |
|---|---|---|---|
| 39 | 22 `except Exception: pass` blocks swallowed exactly the errors the monitoring existed to surface | Never `except: pass` in monitored code | KL → "Refactoring Patterns" |
| 40 | Per-item `except` swallowed a Windows `open()` failure → attachment dropped silently | Cross-platform tests | KL → "2026-06-13" |
| 41 | Truncated gzip raised `EOFError` not in the except clause | Add to handler | KL → "v2.1.2" |
| 42 | Contract loader defaulted `return True` for unknown `side_type`; 720K-edge drift for weeks | Raise on unknown; count as `parse_error`; full-scan verifier | KL → "v2.3.0" |
| 43 | Verifier sampled the first 5,000 of 5.47M rows; violations were after line 541K | `limit=None` | KL → "v2.3.0" |
| 44 | Write-refusal guard was opt-in (~30 of ~124 writers); the primary DB helper skipped it | Guard inside `get_db()` behind explicit `allow_live` | KL → "2026-09-03" |
| 45 | Promote swapped the DB but never re-stamped the active-DB marker; detector cried wolf until ignored | Refresh derived state at the op that mutates it | KL → "2026-09-03" |
| 46 | Fixed-template notification fired regardless of what ran | Compose from state at send time | KL → "v2.3.0" |
| 47 | Watchdog posted identical status every 5 min for hours | Post only on change | KL → "Status Notification Hygiene" |
| 48 | A HARD gate ran a 120 s network op even under `--dry-run` | Test asserting the gate is not called when `dry_run=True` | KL → "2026-05-11" |
| 49 | Five bugs in one shell wrapper in two days | Postcondition test per phase | KL → "2026-05-08" |
| 50 | A failing test sat in the "pre-existing failures" bucket for weeks; it was a real regression | Never carry pre-existing failures | KL → "v2.3.0" |
| 51 | A shared utility extracted with zero consumers for 36 h | Wire ≥1 consumer in the same change | KL → "Refactoring Patterns" |
| 52 | Gated rules must report offender counts, not be silenced | Two-layer guard pattern | KL → "2026-05-08" |

### A5. Testing gaps and test isolation

| # | What happened | Fix | Source |
|---|---|---|---|
| 53 | Tests stamped phantom PIDs into the **live** state file | Detect test context → temp state dir; precedence rule | KL → "2026-05-03" |
| 54 | Integration test with a 2-bug temp data root silently **overwrote the real** corpus index; reads respected the test root, writes did not | All derived writes via `DATA_ROOT`; only a floor test caught it | KL → "2026-05-09" |
| 55 | Small-input tests passed; production merge took 90 min | Stress tests at three scales with wall-time budgets | KL → "April 19-20" |
| 56 | Data merges lacked before/after checks | Named pre/post invariants | KL → "April 19-20" |
| 57 | 8 bugs passed unit tests, caught only by an end-to-end pilot | Pilot before release | KL → "v2.1.2" |
| 58 | Module split kept function copies for `@patch` compatibility; path hacks made patches miss | Thin wrappers; patch where consumed | KL → "Refactoring Patterns" |
| 59 | Decomposing a 1,134-line module succeeded only because 32 tests were written first | Tests first, then split | KL → "Refactoring Patterns" |
| 60 | Chaos-testing and zero-context assessment agents found gaps the working session missed | Post-refactor fresh-eyes review | KL → "Multi-Agent Chaos Testing" |

### A6. Tooling / environment / portability

| # | What happened | Fix | Source |
|---|---|---|---|
| 61 | `python3` on stock macOS is 3.9.6; 70 subprocess argvs silently ran under 3.9 | `sys.executable`; AST-scan test with empty allowlist | KL → "2026-05-08" |
| 62 | Second OS joined and a **cluster** surfaced: silent (utf-8, dropped attachment, lost paths, wrong machine tag) vs loud (`import fcntl`, `SIGHUP`, `os.rename`, hardcoded `mps`, `python3` literal) | Cross-platform portability test; `os.replace`; guarded POSIX imports; explicit codec | KL → "2026-06-13" |
| 63 | `tqdm` progress unreadable in captured logs | Line-based progress; structured JSON log | KL → "Long-Running Job Observability" |
| 64 | Exit-only monitors left the operator blind for hours | Streaming progress filtered to step transitions | KL → "2026-05-16" |
| 65–68 | VPN drops, secondary rate limits, pagination stopping after one page, newest-first-only pagination vs retention | Preflight + mid-run re-check; per-request delay + `Retry-After`; follow cursors until exhausted; accept retention ceilings | mostly D | KL various |

### A7. AI-agent behaviour, claims, and drift

| # | What happened | Fix | Source |
|---|---|---|---|
| 69 | A claim cited results that had never tested that signal; reached the operator twice | Claim-provenance check before banking; adversarial review; "the operator should NEVER be the first to question a load-bearing claim" | KL → "2026-06-27"; VS → KL-12 |
| 70 | Agent repeatedly assumed VPN was down and skipped live fetches | "Attempt the operation; report failure if it fails" | KL → "Long-Running Job Observability" |
| 71 | Agent declared a capability blocked after testing the wrong credential | Exhaust the credential chain before "blocked" | KL → "2026-05-20" |
| 72 | Guessed identities produced 49 dead roster entries | Never guess identifiers | KL → "2026-05-20/21" |
| 73 | Narrow metrics propagated as system-wide capability | "Scope before you weigh"; state denominator | KL → "2026-06-06" |
| 74 | Eval leakage: 69% collapsed to 3.4% on a time-aware split | Leak-free temporal eval before any ranker | KL → "2026-05-20→23" (M5 only) |
| 75 | Blind file copy between branches silently reverted newer fixes twice | `check_bank_safety.py`; "zero net-new content" test before deletion | VS → KL-18 |
| 76 | Human-in-loop caught the highest-impact bugs — no test would have | Operator review of real output is a first-class check | KL → "Human–AI Collaboration Patterns"; VS → KL-11 |
| 77 | Research synthesis re-proposed two levers already banked negative | Grep the dead-ends index first; hand any synthesis to a fresh adversarial reviewer | KL → "2026-06-21"; DE header |

### A8. Process and planning

- 11 docs needed updating on a schema bump; a human missed half; encoded as a hard-FAIL checker (KL 2026-05-04).
- "Backward-look" (why is it this way) and "forward-look" (what breaks if I change X) are different artifacts (KL 2026-05-15).
- Centralisation often needs a navigation pointer, not a refactor (KL 2026-05-08).
- Doc-sync rule: new failure mode → smallest unit test + doc update in the same session; "guard the condition, not the conclusion" (KL "Doc Sync Rule"; 2026-06-14).
- Write formulas/criteria down before coding (KL v2.1.2).
- Maximal capture up front so downstream work is local (KL "PR Fetch Completeness").
- Deliverables for a human who acts: action + confidence first (VS KL-17).
- Every measured result must land a 3-line learning (WHY / OUTCOME / IMPLICATION) (VS header).

---

## B. Guards the previous project adopted, and whether they worked

| Guard | Worked? | Evidence |
|---|---|---|
| Central constants + drift detector | Yes, once in place | KL 2026-05-03 |
| Consolidation lock test (scan for canonical sentinel outside allowlist) | Yes | KL 2026-05-15 |
| Doc integrity / currency checkers as hard FAIL | Yes | "caught drift on its own first run that I would have missed" (KL v2.1.2) |
| Shape-parity test + promote-or-fail test | Yes, but only after the class hit **four** times | KL 2026-05-08 |
| Verifier flags never-emitted enum members | Yes ("caught all 5") | KL April 19-20 |
| Full-scan (not sampled) verifier | Adopted after a miss | KL v2.3.0 |
| Headline-coverage audit after each schema bump | Yes: 3 real findings all verifiers had passed | KL 2026-05-04 |
| fcntl locks (not PID files) | Yes | KL |
| Heartbeat with state | Yes | KL |
| Max-age guard on stale markers + `atexit` | Yes | KL v2.3.0 |
| `sys.executable` + AST-scan test | Yes; needed code-side and process-side layers together | KL 2026-05-08 |
| Cross-platform portability test | Yes | KL 2026-06-13 |
| Wrapper postcondition test | Adopted after 5 bugs | KL 2026-05-08 |
| `--dry-run` not-called test | Yes | KL 2026-05-11 |
| Test-context detection redirecting state writes | Partial: closed one escape; another escaped via a different root constant | KL 2026-05-03 vs 2026-05-09 |
| Floor test on a derived artifact | Yes — the only thing that caught the test-isolation escape | KL 2026-05-09 |
| Freshness guard | **No** until wired | KL 2026-06-15 |
| Opt-in write-target guard | **No**: bypassed by the main helper | KL 2026-09-03 |
| Manual active-DB re-stamp | **No** (cry-wolf) | KL 2026-09-03 |
| Evidence-based notifications; post only on change | Yes | KL v2.3.0 |
| Stress tests with wall-time budgets | Yes; budget miss documented honestly | KL April 19-20 |
| Named pre/post invariants for merges | Yes | KL April 19-20 |
| End-to-end pilot before release | Yes: 8 bugs | KL v2.1.2 |
| Idempotent per-item markers + patient retry ladder + `caffeinate` | Yes: laptop death cost ~10 min, not data | KL 2026-06-11 |
| Adversarial/zero-context agent review at critical points | Yes, when actually run; the failure was running it occasionally | VS KL-9/10/12 |

Pattern: guards worked when they sat **inside the operation** (the connection helper, the loader, the promote op, the CI gate) and had a behavioral test; they failed when they were opt-in, scheduled by a cadence, or dependent on a human remembering.

---

## C. Dead ends explicitly ruled out (transferable)

| Ruled out | Why | Use instead |
|---|---|---|
| PID-file locking | Orphaned on SIGKILL | fcntl/flock |
| Liveness by PID-alive alone | PID recycling | Heartbeat age + max-age |
| Sampling verifiers | Late-emitted violations missed | Full scan when cheap |
| Fixed-template notifications; posting on a timer | Lie eventually; noise | Compose from state; post on change/failure |
| Exit-only monitors for >1 h ops; `tqdm` in captured logs | Operator blind | Line-based, filtered progress |
| Enrichment written into the raw file | Overwritten on re-fetch | Raw immutable; derived elsewhere |
| Bare `python3` literal; platform-default codec; `os.rename` for overwrite | 3.9 / mangled text / Windows failure | `sys.executable`; `encoding="utf-8"`; `os.replace` |
| Hand-curated lists without a validator | Silent drift | Canonical source + read-only audit + override layer |
| Hand-picked threshold seeds | Broke on first real data | Compute from corpus |
| Carrying "pre-existing" test failures | Hid a real regression | Fix/update/delete immediately |
| Extracting a utility without a consumer | Dead code with a lying name | Wire ≥1 consumer in the same change |
| Blind branch file copies to "bank" work | Silent reverts | Real merge; "zero net-new content" test |

Domain-only (relevant only at M5): dense embeddings for identifier-heavy text; equal-weight score fusion; unsupervised re-clustering; assembled risk scores; "make more results HIGH confidence"; a field whose container is present but content empty on 100% of rows. Moral for M5: FTS/keyword baseline first, a named binding test before any model, and a do-not-rebuild index from day one.

---

## D. Mapping to the new plan (abridged; priorities as the reviewer assigned them)

| Lesson | Covered? | Gap / refinement | Priority |
|---|---|---|---|
| INSERT OR REPLACE burns rowids; PK must be stable for FTS and FKs | Partly | Specify `INSERT … ON CONFLICT DO UPDATE`; PK-stability invariant after 3 reruns | High |
| Two producers for one record shape drift in lockstep | Not covered; the plan introduces two raw shapes | One canonical dict before normalize; shape-parity test via `probe` | High |
| Test isolation escapes into the real data dir | Partly | Autouse fixture; settings refuse default data dir under pytest; grep for repo-root-built paths | High |
| Uniform staleness passes relative checks | Partly | Absolute anchor vs live `/new?limit=1`; `partial` when a sub yields zero new items for K runs while live | High |
| Enforce at the operation boundary; opt-in guards get bypassed | Mostly | One connection factory (import-linter); behavioral pragma test; scrub one function | High |
| Shape verifiers pass while columns empty | Partly | Coverage counters on run row + digest; amber on drops vs trailing median | High |
| Silent accept on unknown values | Partly | Store raw + count; no ghost enums test | Medium |
| Named, fingerprinted settings | Partly | `settings_fingerprint` on runs | Medium |
| Field names are contracts | Mostly | `num_comments` ≠ `comments_harvested`; `more_skipped_reason` | Medium |
| MODIFY-in-place passes DDL snapshot | Partly | Data dictionary currency; two-gate discipline | Medium |
| Registering a requirement before its producer exists | Partly | Scope new invariants by `normalizer_version` | Medium |
| Every writer registers and locks | Mostly | State it for every mutating command; test per command | Medium |
| Heartbeat says what it is doing | Mostly | `rate_wait:<s>`; stale threshold 30–45 min | Low |
| Clear transient state on success | Not explicit | Failure-matrix row for recovery | Medium |
| `--dry-run`/`--no-network` make zero writes/calls | Partly | Add rows | Medium |
| Wrapper/deploy artifacts need structural tests | Partly | plist argument tests; forbid `"python3"` literal | Medium |
| Cross-OS silent members | Partly | ruff PLW1514; `os.replace`; guarded `fcntl` | Low |
| Verify compressed archive before deleting original | Partly | Re-read and compare line count | Low |
| Backup verification proof | Mostly | Compare row counts between live and copy | Low |
| Scale/stress tests with budgets | Not covered | `-m slow` scenario at ~50K/500K; `EXPLAIN QUERY PLAN` assertions; missing indexes | Medium |
| Never carry pre-existing red; every failure becomes a test | Yes | Add `KNOWN_ISSUES.md` | Low |
| Evidence-based digest | Mostly | Render "no run since", "N subs zero new" explicitly | Low |
| Human QA on real output | Partly | Wes reads seven digests against Reddit | Low |
| Claim provenance; adversarial review at critical junctures | Partly | Numbers cite their test/query; zero-context review for critical PRs | Medium |
| Verify before irreversible ops | Partly | `--yes` and counts printed | Low |
| Config precedence documented and tested | Mostly | Docstring + test | Low |
| Do-not-rebuild index before M5 | Not covered | `DECISIONS.md` for negatives | Low |
| Theme keyword base rates | Partly | Show "% of all captured posts" per rule | Low |
| Laptop sleep kills long runs | Partly | `caffeinate -i` for backfills | Low |
| Skip ratchet vs credential-gated live tests | Yes | Count static markers, not runtime skips | Low |

---

## E. Reviewer's top 10 concrete changes

1. Pin the upsert to `INSERT … ON CONFLICT DO UPDATE` and add a PK-stability invariant/test.
2. Collapse the two raw shapes into one normalizer input and add a shape-parity test.
3. Make test isolation of `DATA_DIR` structural.
4. Add an absolute freshness anchor and "zero new items" detection.
5. Add substance (coverage) counters to the run row and digest.
6. Route every DB connection through one factory enforced by import-linter; make scrub a single function.
7. Treat unknown enum values as counted anomalies, and prove no ghost enums.
8. Stamp a `settings_fingerprint` on each run; two-gate discipline for semantic changes.
9. Add a production-scale fake-gateway stress scenario with wall-time budgets and index assertions.
10. Require every mutating command to take the flock and write a `runs` row; add `KNOWN_ISSUES.md` and a data-dictionary currency check.

## F. Reviewer's questions for the owner

1. How were rows written in the old SQLite store — `INSERT OR REPLACE`?
2. Did the old DB have DDL migrations at all?
3. `DATABASE_SYSTEM_AND_INTEGRITY_REFERENCE.md` and `KNOWN_ISSUES.md` were not in the folder; can they be shared?
4. Were tests run against the live data directory by default?
5. How much of the adversarial-panel / claim-provenance process to carry into a single-developer project?
6. Is Windows ever in scope?
7. What is a realistic "zero new posts" alarm threshold per subreddit?
8. Was the old multi-writer setup the source of cross-project contract drift?
9. Should `doctor --post-run` be the only invariant surface, or also a `make check`-time data test against a seeded fixture DB?
10. How heavy should the institutional-memory layer be? Suggested minimum: `CLAUDE.md`, `KNOWN_ISSUES.md`, `DECISIONS.md`, `RUNBOOK.md`, `DATA_DICTIONARY.md`, with one currency test.
