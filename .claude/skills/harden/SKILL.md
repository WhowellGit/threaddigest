---
name: harden
description: Harden a fix or a resolution so it cannot quietly regress - failing test first, register row, the strongest mechanical enforcer that fits, a positive control, a ledger row, mirrors swept, installed-ness checked, proof pasted. Use whenever a bug, a failure, a near miss, or a rule violation has just been fixed or is about to be, or when Wes says "harden this", "make sure this is enforced", or "use the harden methodology".
---
# Harden a fix

Purpose: turn "we fixed it" into "it cannot come back unnoticed". Run every step in order and
report each with its evidence, or say which step does not apply and why. The steps produce
artifacts the gates already check (a register row must cite a test that exists; a gate file must
have a ledger row; the review-only ceilings only go down), so skipping one shows up red.

1. **Reproduce first.** A failing test that fails for the reason the incident happened, not a
   similarly named one. For a documentation or process failure the "test" is a gate that would
   have gone red on the artifact.
2. **Register the incident.** A row in `docs/runbook/KNOWN_ISSUES.md` (a defect) or a birth
   incident in `docs/runbook/GUARDS.md` (a guard), citing the test's node id. A suspicion that
   turned out not to be a bug goes under § Swept with how it was checked.
3. **Choose the enforcer, the strongest that fits.** A hook (an agent must not do it; sits in the
   path of every action) → pre-commit (must never be committed) → a gate in `make check` and CI
   (must never merge) → a runtime invariant (must never ship a bad run) → a ratchet (must never
   grow) → review, last, with the reason nothing mechanical can, knowing the review-only
   ceiling in `.ratchets/review_only_rules.txt` only goes down.
4. **Positive control.** Plant the bad state and assert red; the same tree without it is green.
   A guard never seen failing is a hypothesis.
5. **Widen before adding.** Check whether an existing guard can take the case (the ledger is the
   list); hold the count.
6. **Sweep the mirrors.** Every document that states the old fact changes in the same commit; a
   replaced mechanism's phrase goes into the retired-claims table in `docs/decisions/DECISIONS.md`.
   A build that deviates from a mechanism the plan names is a changed fact: the plan's sentence
   changes in the same commit, with the reason there or in the decisions log, never only in a
   docstring.
7. **Check installed-ness, not existence.** A hook or a config that is present but not installed
   has never run (`make check` prints the hooks line; `doctor` reports it).
8. **Prove it.** Paste the check output (the `make check` tail or the gate's own run); a claim of
   "fixed" names the test that proves it.
9. **Record.** A `DECISIONS.md` entry if a choice was made; a drift-findings row if it was drift;
   `make ratchet-bump` if a floor moved.

Rules that bite here: never weaken a test to get green; never touch `.ratchets/` or the hook
settings by hand; no model names, attribution trailers, or another system's identifiers in
anything written.
