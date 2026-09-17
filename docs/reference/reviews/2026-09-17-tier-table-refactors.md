# Review record: structural refactors move to the Opus tier (2026-09-17)

**Scope.** The agent model tier table in `docs/PLAN.md` § Review harness → "Agent model tiers",
the matching paragraph in `CLAUDE.md` § Agent model tiers, and the tier memory in the private
snapshot. The working agreement is a review-required surface, which is why this record exists.
No code, no test, no gate changed.

**What changed.** Structural refactors (reducing a function's complexity, splitting a module,
moving a boundary) are named as Opus work in both homes, with two conditions that hold whatever
the tier: characterization tests are pinned first wherever the function or module lacks direct
tests, and a fresh-context review of the diff judges readability rather than the metric, asking
of every extracted function whether its name stands for a real step. Refactors whose
specification fully determines the result (renames, moves, codemods) stay Sonnet work.

**Why.** The first code-health pass is due before the birth relaxations in the code-health
ratchet expire on 2026-09-27, over the nine functions above the complexity ceilings. Those are
the hardest functions in the tree: the collector, the sweep, the doctor, the invariants. Where
to cut and what to name the pieces is design; a metric can be satisfied by three functions that
each pass the ceiling while the caller reads worse than the original, and no ratchet can see
that. The main session recommended the move and Wes agreed on 2026-09-17; the reasoning is in
`docs/decisions/DECISIONS.md` under that date.

**How reviewed.** In-family: the main session wrote the change and checked the three homes
against each other; not an independent seat, which is this record's weakness, mitigated by the
change being wording in two documents and a memory file, with no behaviour behind it. Three
things were checked rather than assumed: that the plan's table and the working agreement's
paragraph state the same rule and the same two conditions; that the memory file's description
and body name the same rule, and that `make memory-export` carried it to the private snapshot;
that `make check` is green with the doc-policy gate, which resolves every backticked identifier
in the rewritten sections.

**Not claimed.** That the two conditions are enforced: a brief carrying them is review-only
until a refactor brief template exists, and the review-only ceiling was not moved by this change
because the tier table was already review-only.
