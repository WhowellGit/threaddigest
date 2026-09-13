# Key learnings + failure modes to avoid (copies, 2026-09-12)

Duplicates of the docs that capture the major failures, the key learnings, and the failure modes to avoid
repeating, from building and evolving the data system. Point-in-time COPIES; the living versions are in the
repo at the source paths below. The recurring meta-lesson these docs share: we did NOT start from a clearly
defined spec, we evolved and iterated aggressively, and the project's defining trait became catching and
correcting its own rosier story.

## The core "failures + what we learned, so we do not repeat them" set

- **CRITICAL_FAILURES_RETROSPECTIVE.md** - the single RANKED list of the ~15 failures that mattered most
  (wrong assumptions, bad-data episodes), tied to the arc, honest that several "different" failures are the
  same failure wearing different clothes. The one-sentence lesson: almost every expensive failure was a
  number/label/field that was REAL but measured wrong, scoped wrong, or asked the wrong question. This is the
  "reference in the future to avoid the same problems" doc.
  Source: `framework/docs/reference/CRITICAL_FAILURES_RETROSPECTIVE.md`
- **DEAD_ENDS_AND_RULED_OUT.md** - the "do NOT rebuild this" index: every lever we tested and proved does
  not work, so a future session never re-derives a settled negative. The build-time companion to the
  retrospective (which is the measurement-time "do not re-quote" check).
  Source: `framework/docs/reference/DEAD_ENDS_AND_RULED_OUT.md`
- **KEY_LEARNINGS.md** - the curated engineering-reliability log: silent-failure swallowing, rate-limit
  handling, schema drift, credential resolution, sync orchestration. The durable "things we fought and
  fixed" patterns.
  Source: `framework/docs/reference/KEY_LEARNINGS.md`
- **WHY_THE_GUARDS_EXIST.md** - the reasoning behind our tests and ratchets: what incident birthed each
  guard, what it has caught since, and the design rule separating the guards that work from the ones that
  only look like they work. This is the "failure mode -> the guard we built to prevent it" map.
  Source: `framework/docs/reference/WHY_THE_GUARDS_EXIST.md`

## The evolution + limitations context

- **PROJECT_JOURNEY.md** - the honest narrative arc of the whole project over time (the "no upfront spec,
  evolved and iterated aggressively, kept correcting its own story" theme, in narrative form).
  Source: `framework/docs/journey/PROJECT_JOURNEY.md`
- **SYSTEM_ARCHITECTURE_AND_REBUILD.md** - how the system/database is built and was evolved, where the
  technical debt concentrates (the hot zones = the limitations), and how to rebuild it from zero.
  Source: `framework/docs/SYSTEM_ARCHITECTURE_AND_REBUILD.md`
- **VALUE_STAGE_KEY_LEARNINGS.md** - the key-learnings companion for the value/retrieval stage (where a deep
  investigation becomes a measurable routing gain); the anti-silent-failure "capture the lesson, not just the
  number" rule lives here.
  Source: `framework/docs/value_stage/VALUE_STAGE_KEY_LEARNINGS.md`

## If you want the granular sources
The two consolidated retrospectives above draw from point-in-time agent reports under
`framework/docs/agent_reports/db-integrity/` and `.../schema/` (silent-disconnect, silent-failure-panel,
silent-divergence, silent-staleness). Say the word and I will add those too.
