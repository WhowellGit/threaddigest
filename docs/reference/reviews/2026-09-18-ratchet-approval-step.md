# Review record: the loosening approval step (2026-09-18)

**Scope.** `93ee41f..05ef38f`. Review-required surfaces moved: `tests/gates/`
(`test_ratchet.py`, `test_hooks.py`), `tools/hooks/enforcement_files_script_only.sh`, and
`CLAUDE.md` (the rules table, PR-protocol steps 4 and 5, the commands line). The behaviour is new:
`tools/ratchet.py` gains an `approve` command and the comparison gains a verdict it did not have.

**The gap this closes.** The gate round of 2026-09-17 carried the first ratchet loosening in this
repository that was not a birth relaxation, and it could not land. Comparison 3 reads the floors on
the working tree against the floors committed on `main`, so a loosening keeps firing until the
loosened value is itself on `main`; the merge hook refuses any tree `make check` has not stamped;
and the stamp is written as the last step of `make check`, after the comparison. The three
mechanisms are each correct and together they form a circle with no exit. Every loosening before
this one was a birth relaxation, written into `.ratchets/` on the same commit that introduced the
family, where the branch and `main` agree and comparison 3 never fires — which is why four days of
green checks hid it.

What the documents said existed did not. `docs/runbook/RUNBOOK.md` § 4 listed a
`ratchet-loosen-approval` continuous-integration job as *planned*; the guards ledger said a
loosening "pauses for approval" without naming what ends the pause; `CLAUDE.md` PR-protocol step 4
said the same. Three sentences described a step nobody had built, and each of them read as a
description of something that worked.

**What was rejected, and why it matters more than what was chosen.** Three ways out were on the
table when the gap was reported.

- *Write the green stamp by hand.* Rejected. The stamp exists to certify that the check passed;
  writing it while the check is failing would make the merge guard a comment. That guard has a
  birth incident behind it (2026-09-14, a red tree fast-forwarded into `main`), and hollowing out a
  guard to land the change that tripped it is the exact failure this project is built against.
- *Switch off the baseline comparison for one run.* Attempted, and a gate refused it:
  `tests/gates/test_ratchet.py::test_compare_without_any_main_baseline_is_red` holds the rule that
  a run with no baseline is red. The harness caught the shortcut before a person did.
- *Build the planned job on the remote.* Not rejected, deferred, and it would not have unblocked
  this: a job on the remote approves after a push, and the refusal here is before a merge. The
  runbook still names it as planned, and the local step is now recorded as the near half of a gate
  whose far half is still owed.

**What was built.** `make ratchet-approve KEY=<key>` records one approval per ratchet key: the key,
the value on `main`, the value here, the day it was granted, and the day it stops covering
anything. Four properties were deliberate.

1. *Narrow.* An approval names one move. Loosening the same key further afterwards is a different
   move and red again — watched, not assumed
   (`::test_an_approval_does_not_authorise_a_different_value`).
2. *Bounded.* Fourteen days by default, ninety at most, and `bump` removes an approval once it has
   expired. Without this, an approval granted today would silently authorise a repeat of the same
   move months later, when the ceiling had been tightened back and loosened again. The ledger row
   is the permanent record, so removing a spent permission loses no history.
3. *Attached to its reason.* The command refuses unless `make ratchet-loosen` has already written
   the reason into the guards ledger, and it prints that reason rather than restating it, so the
   operator approves against the text the record will carry. One home per fact.
4. *Not available to the agent.* The confirmation is a line typed at a terminal, and the command
   refuses when stdin is not one.

**Widened, not added.** The approval file lives inside `.ratchets/`, which
`tools/hooks/enforcement_files_script_only.sh` already refuses every hand edit to, so the
permission inherits the guard that protects the floors. No guard id was created; two rows were
added to that hook's own control table instead, proving the file tools are refused on the new path.
The hook's allowed-target list gained `ratchet-approve` so that it agrees with the tool's actual
commands — a list that disagrees with the thing it describes is the kind of drift this hook exists
to prevent.

**How reviewed.** In-family, the main session, which found the gap and built the fix; not an
independent seat, which is this record's weakness. What stands in for one is that the gap was found
by the harness refusing the session's own work, and that every control was seen red before the
implementation existed: nine tests failing with the command and its output recorded, then green.
Two further things were checked rather than assumed. The refusal was exercised on the real tree,
not only in a temp tree — `make ratchet-approve KEY=code_health.dead_code` printed the move, the
ledger's reason and the phrase to type, and then refused the session with "an agent cannot approve
its own loosening". And the terminal path itself is proven, not merely the refusal: the controls
drive the command through a real pseudo-terminal, because a refusal that nothing can satisfy is a
dead end rather than a gate.

**The honest limit, stated plainly.** This is not a security boundary and it is not claimed as one.
A process that wants to can open a pseudo-terminal, and any agent with file access could write the
approval file directly. The hooks have never claimed more than they hold (G23 says so in its own
row), and the same sentence belongs here. What the step provides is the difference between a
permission somebody granted and a permission the work granted itself, and a record of which it was.
The mechanism that would close the remaining distance is the approval job on the remote, where the
approval is a click by an account the agent does not hold; that is still owed.

**Two findings recorded rather than fixed.**

1. `docs/reference/AGENT_BRIEF.md` states in its own prose that it is prune-stale and revised in
   place, and the document-contract gate refuses to let it be revised at all, because everything
   under `docs/reference/` is treated as a record that is never edited. The mechanism for the
   exception exists (`REFERENCE_EDITABLE` in `tools/doc_policy.py`, which already carries the
   review templates) and the brief template arguably belongs in it, being a template rather than a
   record of anything. Not changed here: it is a second enforcement surface and a second question,
   and D-46's rule reached its readers through `CLAUDE.md`, which is loaded in every session, so
   nothing was lost by leaving it. The contradiction is real and should be settled deliberately.
2. The guards ledger now carries two Loosenings rows for `code_health.dead_code`, `0 -> 29` and
   `0 -> 25`, because the first was written before the comment-tree stage landed and made four of
   the counted symbols live. The table is append-only by design, so the superseded row stands; a
   reader should know the second row is the one that was approved. The approval file names `25`,
   so the tooling cannot confuse them even though a reader might.
