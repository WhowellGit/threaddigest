# Review register (machine-read by `tests/gates/test_review_register.py`)

> One row per review run, appended, never edited except to correct a typo. A commit on `main` dated on or after 2026-09-15 that touches a review-required surface (`src/insightminer/db/migrations/`, `src/insightminer/services/scrub.py`, `src/insightminer/core/deletion.py`, `src/insightminer/db/repo.py`, `tests/gates/`, `.ratchets/`, `tools/hooks/`, `CLAUDE.md`, `.claude/settings.json`) must be covered by a row's **Scope** (a commit hash, or a `first..last` range), and every **Record** must be a file in this folder. The gate names the uncovered commits; it cannot judge whether the review was adversarial enough, so the record says what the reviewer was given (the packet and its hash) and who gave the verdict.
>
> Triggers, in Wes's words (2026-09-14): a complex problem solved, a significant design plan finalised, a complex or risky fix confirmed, a module finished or started; and, from the harness protocol, any change to the enforcement surfaces, a migration, the intent block, or the irreversible four. Reviews are refute-framed; findings are weighed by independence and evidence, never tallied; a reviewer handed the prior verdict inherits its blind spots. An external provider (a reviewer outside this model family) is used at the moments `docs/decisions/DECISIONS.md` § 2026-09-14 lists; nothing but the clean current tree or a diff ever leaves this machine.
>
> Rows dated before the baseline are the planning-day panels, listed for provenance; their scope is `pre-baseline`.

| Date | Trigger | Scope | Provider / tier | Verdict | Record |
|---|---|---|---|---|---|
| 2026-09-13 | plan lock-down: five test-strategy panels and one adversarial pass | pre-baseline | in-family, Opus, fresh context | adopted per `docs/PLAN.md` § Adversarial review | `2026-09-13-adversarial-review.md` |
| 2026-09-13 | the earlier project's harness and documentation practices | pre-baseline | in-family, Opus, fresh context | adopted per `docs/decisions/DECISIONS.md` | `2026-09-13-documentation-practices-assessment.md` |
