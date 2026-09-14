# Insight Miner reference corpus — INDEX (the router)

> Purpose: one line per document and *when to read it*. Keep this file short. The corpus lives in the repo at `docs/` since M0 (2026-09-13) and travels with the code.
> Update policy: add a line when a document is added; remove it when the document is retired. The doc-currency test checks INDEX ↔ `docs/**/*.md` in both directions, so every file under `docs/` must appear below exactly once.

## Start here: which of these are you about to do?

| I am about to… | Read | Then |
|---|---|---|
| Start a session | `recent/STATUS.md` | `CLAUDE.md` § The irreversible few |
| Touch the schema, migrations, upserts, search index, backups | `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §1–§2 | `runbook/RUNBOOK.md` § migrations; `.claude/rules/db.md` loads automatically |
| Change the collector (fetch, budget, revisit, reconcile, invariants) | `PLAN.md` § Collector algorithm | `decisions/DECISIONS.md` 2026-09-13 entries; `.claude/rules/services.md` |
| Touch deletion, scrubbing, or anything compliance-related | `PLAN.md` § Data model (state machine) | `runbook/KNOWN_ISSUES.md` |
| Change the web UI | `PLAN.md` § Web UI | `reference/reviews/2026-09-12-ui-design-review.md`; `.claude/rules/web.md` |
| Add or change a gate, ratchet, invariant, or test policy | `PLAN.md` § Robustness → Guard design rules | `runbook/GUARDS.md` (birth incident, positive control, verdict) |
| Write a brief for a sub-agent | `reference/AGENT_BRIEF.md` | the rows above for the task |
| Decide whether to adopt a practice from the earlier project | `reference/reviews/2026-09-13-documentation-practices-assessment.md` | `reference/reviews/2026-09-13-harness-assessment.md` § 7 |
| Run a retrospective or score a prediction | `learnings/LEARNINGS_TRANSFER.md` §5 | `learnings/DOC_DRIFT_FINDINGS_2026-09-13.md` |
| Wonder why something was decided | `insights/INSIGHTS_2026-09-12.md` | `decisions/DECISIONS.md` (settled negatives first) |

## How the corpus is organized

| Folder | What lives here | Update policy | Read when |
|---|---|---|---|
| `docs/` (root) | `PLAN.md` (the plan; canonical for design and decisions), `TEST_STRATEGY.md` (router into the test specs), this file | Plan revised in place with dated corrections; strategy rewritten per version | Plan: before any design change. Strategy: before writing or changing tests |
| `insights/` | Dated captures of strategy discussions and the reasoning behind decisions | Append-only, dated entries | Starting a new phase, or when a decision is being questioned |
| `learnings/` | Hard-earned lessons: dated "applied" notes now; a canonical curated learnings file is added when the first project-native lesson lands | Append-only; canonical file curated | Before touching the area the lesson is about (routing table says which) |
| `decisions/` | `DECISIONS.md`: settled choices, settled negatives, compliance bounds, Postgres-exit triggers, threat model, each with a "revisit when" | Append-only; dated entries | Before proposing an alternative to something already decided |
| `reference/` | External and immutable material: the research report, the earlier project's retrospectives, reviewer and panel reports | Add, never edit | When the source of a claim is needed |
| `runbook/` | `RUNBOOK.md`, `KNOWN_ISSUES.md`, `GUARDS.md`; a data dictionary generated from `schema.sql` joins at M1a | Prune-stale; generated where possible | Operating, debugging, adding a guard, fixing a bug |
| `recent/` | `STATUS.md`: what is in flight and what is next | Rewritten, never appended | Start of every working session |

## Routing table (task → read first)

| If you are about to… | Read |
|---|---|
| Start a session | `recent/STATUS.md`, then the row below that matches the task |
| Write or change any test, or decide what to test first | `TEST_STRATEGY.md` (spec table and status), then the panel report it points at |
| Touch the database schema, migrations, upserts, FTS, backups | `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §1–§2, `reference/reviews/2026-09-13-panel-db-integrity.md` (§A specs, §C migration checklist, §D fingerprint), `runbook/RUNBOOK.md` § 4 |
| Touch deletion, scrubbing, reconcile, or anything compliance-related | Plan § Data model (content-state machine), `decisions/DECISIONS.md` § 2 (compliance bounds), `reference/reviews/2026-09-13-panel-ingest.md` §B.6–B.7, `runbook/KNOWN_ISSUES.md` |
| Add, change, loosen, or retire a gate, ratchet, invariant, or hook | Plan § Robustness → "Guard design rules" and "Adversarial review: what changed", `reference/reviews/2026-09-13-panel-enforcement.md` §B–§D, `runbook/GUARDS.md`, `runbook/RUNBOOK.md` § 6 |
| Change the collector's fetch, budget, revisit, reconcile, or search behavior | Plan § Collector algorithm, `reference/reviews/2026-09-13-panel-ingest.md` §A (fake API) and §B, `reference/reviews/2026-09-12-collector-design-review.md` §1 |
| Change the web UI, middleware, or an operator flow | Plan § Web UI, `reference/reviews/2026-09-13-panel-ui.md` (§A specs, §B operator checklist, §C setup threat model), `reference/reviews/2026-09-12-ui-design-review.md` |
| Fix a bug | `runbook/KNOWN_ISSUES.md` (add the row; failing test first) |
| Deploy, migrate, restore, or run the quarterly review | `runbook/RUNBOOK.md` |
| Wonder why something was decided the way it was | `insights/INSIGHTS_2026-09-12.md`, then `decisions/DECISIONS.md` |
| Evaluate a new approach, library, or "just add a check" | `decisions/DECISIONS.md` § 3 settled negatives first; `reference/reviews/2026-09-13-adversarial-review.md` §C (over-engineering cut list) |
| Question a Reddit-side behavior | `reference/2026-09-11-compass-research-report.md`; `reference/reviews/2026-09-13-panel-ingest.md` §C (probe plan) |

## Documents in this corpus

### Root

- `PLAN.md` — the plan: context and decisions table, architecture, module map, data model, collector algorithm, CLI, web UI, testing strategy, robustness and enforcement (with the panel corrections and the adversarial changes), release practices, deployment, milestones, open items, appendices. Read when: any design question; it is canonical.
- `TEST_STRATEGY.md` — v1 router into the five panel reports: layered policy, kinds of tests and sweeps, every spec ID with layer/phase/priority/status (cut list applied), the M0 gate set and M1a invariants, guard design rules, open owner questions. Read when: writing tests or deciding test order.
- `INDEX.md` — this router.

### `insights/`

- `insights/INSIGHTS_2026-09-12.md` — the kickoff strategy discussion: Wes's priorities, insights, every decision and its reasoning, the 2026-09-13 additions, principles worth keeping. Read when: a decision is questioned or a new phase starts.

### `learnings/`

- `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` — ranked adoption of the earlier project's database lessons with confidence/importance/value/cost, the guard design rules, what was declined, decisions raised, lessons that did not transfer, the living follow-up list. Read when: touching `db/`, migrations, test isolation, or invariants.
- `learnings/LEARNINGS_TRANSFER.md` — what Insight Miner took from the earlier project beyond the database (guard philosophy, testing and operational methodology, documentation and memory structure, agent practice), the interpretive layer on the database adoptions, what was declined and why, and dated predictions to score at the retrospective. Read when: starting a retrospective, judging whether a transferred lesson held, or starting the next project's transfer.
- `learnings/DOC_DRIFT_FINDINGS_2026-09-13.md` — the documentation drift found in our own corpus on 2026-09-13 (retired gates still listed as live, self-contradicting counts, schedules of cut items, narrated status, dangling register ids), each with a way to scan for it in another system. Read when: sweeping documents after a decision, or auditing another project's corpus.

### `decisions/`

- `decisions/DECISIONS.md` — settled choices (D-nn), compliance bounds, settled negatives (N-nn), Postgres-exit triggers, LAN threat model, reviewer-question decisions, and the pending-Wes list. Read when: before proposing an alternative or claiming compliance.

### `runbook/`

- `runbook/RUNBOOK.md` — setup, daily operation from the UI, deploy, migrate, restore drill, quarterly guard review; steps known so far, later-milestone steps marked. Read when: operating or deploying.
- `runbook/KNOWN_ISSUES.md` — fixed bugs with root cause and the regression test node id (currency-checked). Read when: fixing a bug or seeing a familiar symptom.
- `runbook/GUARDS.md` — the guard ledger: Active (M0 shipped set with birth incident, mechanism, positive-control node, verdict), external controls with "last seen red", Retired, Loosenings. Read when: adding, loosening, or reviewing a guard.

### `recent/`

- `recent/STATUS.md` — what is in flight on the stated date, what is deferred, what waits on Wes, next steps. Read when: every session start.

### `reference/`

- `reference/2026-09-11-compass-research-report.md` — the Compass research report on building a rules-compliant Reddit miner: OAuth/PRAW constraints, rate limits, deletion handling, IP considerations, the minimal-start recommendation. Read when: a Reddit-side rule or limit is in question.
- `reference/AGENT_BRIEF.md` — the template every sub-agent brief follows (purpose, tier, read-first rows, rules that bite, scope, contract, verification, don'ts). Read when: writing or reviewing a brief.

`reference/earlier-project-retrospectives/` — three of the earlier database project's eight retrospective documents, kept redacted as narrative source material (the other five live only in the archive at `~/repos/insightminer-desktop-archive/Reddit/Database_Key_Learnings/`, readable by agents on this machine; disposition decided 2026-09-13, see `REDACTION_NOTE.md` there and `learnings/LEARNINGS_TRANSFER.md` §7):

- `reference/earlier-project-retrospectives/INDEX.md` — what each retrospective covers and the shared meta-lesson. Read when: choosing which retrospective to open.
- `reference/earlier-project-retrospectives/REDACTION_NOTE.md` — what was redacted in the three kept files, which five files moved to the archive and why, and the history rewrite. Read when: sharing the repo, or looking for one of the moved files.
- `reference/earlier-project-retrospectives/CRITICAL_FAILURES_RETROSPECTIVE.md` — the ranked ~15 failures; a number that was real but measured wrong, scoped wrong, or asked the wrong question. Read when: designing a metric or invariant.
- `reference/earlier-project-retrospectives/WHY_THE_GUARDS_EXIST.md` — what incident birthed each guard, what it caught since, and the design rule separating guards that work from ones that only look like they work. Read when: adding or reviewing a guard.

`reference/reviews/` — independent reviewer and panel reports (raw, unedited):

- `reference/reviews/2026-09-12-collector-design-review.md` — collector, data model, PRAW behavior verified against upstream, failure-mode matrix, migration practices. Read when: changing fetch, paging, or the adapter.
- `reference/reviews/2026-09-12-ui-design-review.md` — the Reddit-style local web UI design review: routes, wireframes, nested comments, settings UX, Run now, export, search, testing, styling. Read when: changing the UI.
- `reference/reviews/2026-09-12-db-learnings-review-A.md` — reviewer A's extraction from `KEY_LEARNINGS`, `DEAD_ENDS_AND_RULED_OUT`, `VALUE_STAGE_KEY_LEARNINGS` (failure catalogue cited as "A #nn"). Read when: an "A #nn" citation needs its source.
- `reference/reviews/2026-09-12-db-learnings-review-B.md` — reviewer B's extraction from `SYSTEM_ARCHITECTURE_AND_REBUILD`, `PROJECT_JOURNEY` (cited as "B Snn/Fnn/Inn/Tnn"). Read when: a "B …" citation needs its source.
- `reference/reviews/2026-09-13-panel-db-integrity.md` — database panel: 55 specs (DB-01…55), three empirical SQLite corrections, fixture-DB plan, migration checklist, `schema.sql` and fingerprint design, judgements, owner questions. Read when: touching `db/`.
- `reference/reviews/2026-09-13-panel-ingest.md` — ingest panel: `FakeRedditGateway` scenario-builder API, 60 specs (SW/SS/TE/TR/RV/RC/SC/FR/PA/NM/RL/JS/TH/DG/CF/AD/GT-nn), probe plan (P-01…17), judgements (D-1…18), owner questions. Read when: touching the collector or the fake.
- `reference/reviews/2026-09-13-panel-enforcement.md` — enforcement panel: CI design, 38 gates (G01…38) with positive controls, ratchet file format and one-way protocol, hooks, cut list, compensating controls, `GUARDS.md` structure, owner questions. Read when: touching CI, ratchets, hooks, or `tests/gates/`.
- `reference/reviews/2026-09-13-panel-ui.md` — UI panel: 55 specs (UI-01…55), operator-complete checklist, setup-wizard threat model, plan judgements, owner questions. Read when: touching `web/`.
- `reference/reviews/2026-09-13-adversarial-review.md` — the adversarial pass: unfalsifiable gates, gaps against the failure catalogue, over-engineering cut list, contradictions, unverified claims, disagreements with the ranked learnings, risks, top 10 changes. Read when: tempted to add a gate, or when a plan claim needs a second opinion.
- `reference/reviews/2026-09-13-harness-assessment.md` — the evidence-first assessment of the earlier project's personal harness (memory and context model, documentation system, enforcement, agent discipline): a mechanism catalogue with birth incident, evidence, cost, and a transfer call each; what to keep and what to simplify with high confidence; what only Wes can settle; revised after a steelman pass that defended the original harness. Read when: deciding whether to adopt a practice from the earlier project, or pruning the reference material.
- `reference/reviews/2026-09-13-documentation-practices-assessment.md` — which of the earlier project's documentation and memory practices to adopt, adapt, or leave, from a usage census of 1,127 transcripts and a reading of its documentation system: the day-one set for any new project, the skip list with the measured costs, and eight decisions. Read when: adding a document class, a register, or a memory mechanism.
- `reference/reviews/2026-09-13-harness-questions-answered.md` — the 26 harness questions answered from the earlier project's repository backup, transcripts, and never-committed material (19 at high confidence): what fired versus what redirected work, installed versus written, read versus written, used versus defined; the catalogue rows the evidence moves; grounded recommendations for the earlier repository; ten decisions for Wes. Read when: re-scoring a harness catalogue row, or deciding whether an advisory mechanism is worth building.
