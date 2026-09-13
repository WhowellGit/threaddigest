# Insight Miner reference corpus — INDEX (the router)

> Purpose: one line per document and *when to read it*. Keep this file short. Everything below moves into the repo as `docs/` at setup (M0); until then it lives here in `~/Desktop/Reddit/insightminer-docs/`.
> Update policy: add a line when a document is added; remove it when the document is retired. A currency test will check INDEX ↔ folder in both directions once the repo exists.

## How the corpus is organized

| Folder | What lives here | Update policy | Read when |
|---|---|---|---|
| `insights/` | Dated captures of strategy discussions and the reasoning behind decisions | Append-only, dated entries | Starting a new phase, or when a decision is being questioned |
| `learnings/` | Hard-earned lessons: the canonical `LEARNINGS.md` plus dated "applied" notes | Append-only; canonical file curated | Before touching the area the lesson is about (router lines below say which) |
| `decisions/` | `DECISIONS.md`: settled choices and settled negatives with triggers for revisiting | Append-only; each entry has a date and a "revisit when" | Before proposing an alternative to something already decided |
| `reference/` | External material: research reports, prior-project retrospectives, reviewer reports, API notes | Immutable copies; add, never edit | When the source of a claim is needed |
| `runbook/` | `RUNBOOK.md`, `KNOWN_ISSUES.md`, `GUARDS.md`, `DATA_DICTIONARY.md` | Prune-stale; generated where possible | Operating, debugging, or adding a guard |
| `recent/` | `STATUS.md`: what is in flight and what is next | Rewritten, never appended | Start of every working session |

## Routing table (task → read first)

| If you are about to… | Read |
|---|---|
| Start a session | `recent/STATUS.md` (not yet created; will hold in-flight work) |
| Touch the database schema, migrations, upserts, FTS, backups | `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §1–§2, then `runbook/RUNBOOK.md` § migrations (repo) |
| Touch deletion, scrubbing, reconcile, or anything compliance-related | Plan § Data model (content-state machine), `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §2, `runbook/KNOWN_ISSUES.md` (repo) |
| Add or change a gate, ratchet, invariant, or test policy | Plan § Robustness → "Guard design rules", `reference/reviews/2026-09-12-db-learnings-review-A.md` §B, `runbook/GUARDS.md` (repo) |
| Change the collector's fetch, budget, revisit, or search behavior | Plan § Collector algorithm, `reference/reviews/2026-09-12-collector-design-review.md` §1 |
| Change the web UI | Plan § Web UI, `reference/reviews/2026-09-12-ui-design-review.md` |
| Wonder why something was decided the way it was | `insights/INSIGHTS_2026-09-12.md`, then `decisions/DECISIONS.md` (repo) |
| Evaluate a new approach or library | `decisions/DECISIONS.md` § settled negatives first (do not rebuild a killed lever) |

## Documents in this corpus today

- `insights/INSIGHTS_2026-09-12.md` — the strategy discussion of 2026-09-12: priorities, honest-take points, every decision and its reasoning, principles worth keeping.
- `learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` — the exact plan changes made after reading the earlier project's database retrospectives, with sources; decisions raised; lessons that did not transfer; the living follow-up list for evolving the database implementation.
- `reference/reviews/2026-09-12-collector-design-review.md` — independent design review of the collector, data model, PRAW behavior (verified against upstream), failure-mode matrix, migration practices.
- `reference/reviews/2026-09-12-ui-design-review.md` — independent design review of the Reddit-style local web UI.
- `reference/reviews/2026-09-12-db-learnings-review-A.md` — reviewer A's extraction from `KEY_LEARNINGS.md`, `DEAD_ENDS_AND_RULED_OUT.md`, `VALUE_STAGE_KEY_LEARNINGS.md`.
- `reference/reviews/2026-09-12-db-learnings-review-B.md` — reviewer B's extraction from `SYSTEM_ARCHITECTURE_AND_REBUILD.md`, `PROJECT_JOURNEY.md`.
- `../Database_Key_Learnings/` — the earlier project's eight retrospective documents (source material, immutable copies).
- `../compass_artifact_…_text_markdown.md` — the Compass research report on building a rules-compliant Reddit miner (source material).
- `~/Desktop/InsightMiner-Plan.html` — the current rendered plan (regenerated after each revision; the markdown source is the plan file managed by Claude Code).
