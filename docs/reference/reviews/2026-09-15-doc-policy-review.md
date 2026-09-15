# The document-contract mechanism: the refute pass (2026-09-15)

After the document contract (`tools/doc_policy.py`, gate G55, the `docs` ratchet family, the memory
rules under G47, the process section of the runbook, the `docs-sweep` skill, and front matter on
every living document) was built on Wes's ask to mechanize the document update process, one
fresh-context seat at the Opus tier, read-only, was asked to break five claims: that every check can
go red on the state it names and has a control proving it; that no check passes vacuously; that the
process documents state what the tools do and no more; that nothing conflicts with an existing
gate; and that each document's declared policy and mirrors match how it is actually edited. The
seat worked in a sandbox beside its findings file; nothing in the repository was touched. Every
finding was re-checked by the main session before it was acted on. The raw findings stay outside
the repository.

## Verdict

All five claims failed. The seat found sixteen bypasses or vacuous passes, two of them critical,
eight positive controls that proved a pure function rather than the report the gate runs, twelve
overstatements in the documents, nine conflicts with existing gates or with the corpus's own
editing habits, ten of fourteen front-matter declarations that the last three days of edits
contradicted, and eight design risks. The three that mattered most: the append-only rule compared
against `HEAD`, so a deleted line was green as soon as it was committed; the accretion ceiling
counted the dated verdict cells the guards ledger requires by design, so adding a guard would have
needed a ratchet loosening, and it was already red by one; and three documents promised a
mechanical mirror sweep while the tool checked only that the declared mirror paths existed.

## What changed, the same day

- **The append-only baseline is the merge base with `main`**, not `HEAD`, so committing a deletion
  does not launder it; a lost, moved, hidden, or rewritten line is a loss; a dated parenthetical
  may be inserted anywhere in a line and a suffix appended; the policy that governs the diff is
  the one declared at the base, so a document cannot exempt itself by editing its own front
  matter; `exempt-sections` names a table column filled at milestones; outside a git repository
  the check reports a problem rather than passing.
- **Records are checked.** Under `docs/reference/` a file that existed at the base must be
  byte-identical, the review register is append-only, and the templates are reviewed like code;
  "add, never edit" is now a check rather than a sentence.
- **The accretion count excludes table rows** and counts parentheticals (one nested level),
  brackets, and dash-delimited asides; the ratchet was re-bumped to the honest measurement; the
  count is described everywhere as a pressure the milestone pass reads, not a proof.
- **Vacuous passes closed:** the `generated` policy is gone from the vocabulary (a generated block
  is a region inside a prune-stale page); an absent, empty, or unparsed live-facts table is a
  problem; a document stamped ahead of the status page is a problem; mirror and home searches
  ignore code fences and HTML comments; markdown links are parsed as well as backticked paths; the
  status page carries one stamp, the `milestone` the contract reads; `make check` runs the tool
  with `--check`, so its own invocation exits non-zero on a problem.
- **Mirrors bite a little and are described honestly.** Mirroring between living documents must be
  declared from both sides, and every declaration was corrected against the seat's table (the
  decisions log, the guards ledger, and the known-issues register now name the documents that
  restate them; the plan names its configuration and launchd homes). The working agreement, the
  runbook, the skill, the harness page, and the ledger row now say that the declared mirrors and
  the live-facts table are the list the sweep reads, that the facts table is the mechanical check
  for the facts it holds, and that the rest of the sweep is review.
- **Every positive control plants its bad state on a real git tree and reads it through the
  report the gate runs**, including the committed deletion, the policy flip, the future stamp, the
  one-sided mirror, the edited record, the empty facts table, and the command line's exit code.
- **Test strategy** is declared prune-stale (its rows flip in place); the learnings-transfer
  document exempts its outcome column; the status page's title no longer contradicts its policy.

## Held, by design

The milestone clock is the status page's own front matter, advanced when a milestone is recorded
as done in the decisions log; the seat noted it is self-declared, and it is: the lag gate makes the
heavy pass mandatory once the clock moves, and moving the clock is a recorded decision. Short
literals in the facts table (`5d`, `UTC`) are weak as substring checks; their homes are
configuration and code, where the value is compared exactly, and the prose mirrors are the honest
limit. A bare file name with no directory is not judged by the dangling-reference check, and the
documents say so. Documents outside `docs/` carry no contract.

## Lesson

A mechanism built to stop a habit is itself the first thing the habit will bend: the seat's
sharpest finding was that the tool's own status line named this record before it existed, and the
tool caught it. The second lesson is the one the plan's refute pass taught the same morning: a
review seat that executes the code and reproduces each bypass in a sandbox finds what reading
finds not.
