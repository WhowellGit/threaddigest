# Internal panel on the round-one fixes (2026-09-15)

After the round-one fixes, the twice-weekly cadence, and KI-011 landed on `main`, a three-seat
panel reviewed the change set `a0d8e8a..HEAD`, refute-framed, each seat with fresh context and no
session history, at the Opus tier. Every finding was re-run against the tree before it was acted
on; nothing was believed on assertion.

## Seats

- **Test-methodology (Opus).** Reverted seven fixes one at a time in a throwaway worktree and
  confirmed each cited test went red, then restored: KI-015, KI-016, KI-017, KI-018, KI-021,
  KI-022, KI-023 all have genuine positive controls. All 21 cited node ids collect. No stale
  tests, no tautologies. Three enforcement-reach gaps, all cheap.
- **Adversarial correctness (Opus).** Attacked all nine correctness fixes; five were robust
  against its attacks (KI-015 ordering, KI-018 cap boundary, revision 0004, KI-022, the rank
  tie-break), and it raised four findings plus a docstring nit, each reproduced or traced.
- **Hooks and migration adversarial (Opus).** Confirmed the ff-only merge algorithm and revision
  0004 are sound, and found four accidental-class hook holes, one of which (a line continuation)
  defeated the whole git hook end to end, actually advancing `main` with an unstamped tree.

## What was confirmed and fixed the same day

Every finding below was reproduced by the reviewer and re-reproduced by the main session before
the fix; all fixes landed as green commits with tests.

- **Hook line continuation (highest severity).** A backslash-newline continuation split a git
  word, flag or refspec across lines; the hook split on raw newlines and never joined them, so a
  `--no-verify`, a push to `main`, or an unstamped merge hid on the next line. Both hooks now join
  continuations before parsing.
- **`--config-env core.hooksPath` (separated form).** The `-c` form was blocked; the separated
  value went unscanned. Now every value-taking global is scanned for a hooksPath override.
- **A doubled slash and case-variant protected paths.** A doubled slash in the settings path, and
  `.Ratchets` / `.CLAUDE` on the case-insensitive filesystem, named the protected paths while a
  single-slash, case-sensitive match let them through. Protected-path matching is now slash-tolerant
  and case-folded.
- **KI-016 non-mapping crosspost entry.** A list-in-list `crosspost_parent_list` entry stored the
  parent's text and author verbatim; it is now reduced to an empty pointer like any other entry.
- **KI-017 forbidden-enabled sources.** A private or gone source stays enabled (it never
  auto-disables) while collecting nothing, so the hourly `doctor` stayed green. The check now counts
  *collectable* sources, so an all-forbidden workspace goes red at once.
- **KI-023 single large subtree.** The fake reveals one `more` child's whole subtree in a single
  request even when it exceeds a hundred instances; the fake cannot split a cascade. Pinned and
  documented as a known fidelity limit to validate against the real adapter on the probe day, and
  the KI-023 wording corrected.
- **KI-021 non-consecutive omissions.** `[omit, bodyless-return, omit]` reaches `gone`; the two
  omissions are not strictly consecutive. This is the safe direction and now the documented
  behaviour (the "consecutive" wording is softened) with a pinning test.
- **KI-015 docstring.** The "microseconds" characterisation of the restore window was wrong (a
  full fsync runs inside it); corrected, no code change.

Enforcement-reach gaps closed: the twice-weekly schedule and staleness are now checked without
macOS tooling (`tests/deploy/test_schedule_contract.py`), so Linux CI enforces D-30; the
`praw>=8,<9` pin has a control (G53); and the test-strategy citations are gated like the other
registers.

## Held as out of scope, by design

The reviewers' deliberate-bypass gaps (a variable resolving to a wrapper name, an interpreter
reading its program from stdin or a written file, a protected path split across variables that
dodge the fragment scan, `git --exec-path`) are the documented limit of a text-parsing hook
(G23): mistake prevention for the agent, not a security boundary. The trust boundary against a
deliberate bypass is pre-commit, CI once a remote exists, review, and the remote's branch
protection.

## Verdict

No landed fix was reverted. The panel's value was concentrated in the two seats that executed the
code: the hook line-continuation hole would have let an unstamped tree reach `main`, and it was
found only because a reviewer ran the bypass rather than reasoning about it. That is the standing
argument for keeping an execute-the-code seat in every review round.
