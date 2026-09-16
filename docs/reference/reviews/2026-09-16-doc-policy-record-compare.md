# Review record: the reference-record comparison (2026-09-16)

**Scope.** `tools/doc_policy.py`, the reference-record half of the append-only check, and its
gate `tests/gates/test_doc_policy.py`, which is a review-required surface. Landed as b686eb9
on top of the D-35 history rewrite. Issue: KI-028 in `docs/runbook/KNOWN_ISSUES.md`.

**What happened.** The rewrite's hash map is a reference record that is not Markdown, and it is
the first such file in the tree. The check read the baseline through `git show`, which decodes
to text, and the working file through `read_bytes().hex()`, which does not, so for that record
the two sides could never be equal and the gate reported it edited although it was
byte-identical to the commit that added it. `main` was red on every run.

**Why the rehearsal did not catch it.** The check skips a file that does not exist at the
baseline, and the baseline is the merge base with `main`. On the branch that adds a record the
file is new, so the comparison never runs; it runs for the first time once the branch is merged
and the baseline carries the file. The rehearsal on a throwaway clone ran the gate on the branch
and was green. Running the gate on `main` after the fast-forward is what found it, and that is
the lesson worth keeping: for a check whose baseline is the merge base, a branch-only run is not
evidence about `main`.

**How reviewed.** In-family, the session that ran the rewrite; not an independent seat. The
failing test was written first and watched go red against the unfixed tool, with the message
quoted in the commit: it commits a tab-separated record, moves the baseline onto it so the file
exists there, and asserts silence. Its second half is the positive control in the other
direction — a real edit to that same record is still reported — so the fix cannot have bought
silence by making the check see nothing. The existing control on an edited Markdown record was
re-run unchanged and stayed green.

**The fix.** `base_blob` reads the baseline as bytes and the comparison is bytes against bytes.
The append-only register still needs decoded text for its line-by-line diff, so that branch is
taken first and reads both sides as text. Nothing was narrowed: every record the check used to
judge, it still judges.

**What an independent seat should attack.** Whether reading a record as bytes hides a change
that only a text comparison would have called a change (a line ending, an encoding), and whether
any other check in this tool shares the shape of comparing a decoded baseline against an encoded
working file.
