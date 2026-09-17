# Review record: the known-issues rows the gate could not see (2026-09-16)

**Scope.** `docs/runbook/KNOWN_ISSUES.md` and the gate that reads it,
`tests/gates/test_known_issues_cite_collected_tests.py` (G40), which is a review-required
surface; the ledger row, the test-strategy row and the decisions entry that mirror it. Landed as
commit 9182a2c (the move and the widening), commit d1ee7a1 (the follow-up the independent seat
asked for) and commit 72090f2 (the follow-up the landing seat asked for). Issue: KI-034 in
`docs/runbook/KNOWN_ISSUES.md`.

**What happened.** The runbook's known-issues table is followed by an HTML comment that holds a
one-line format example, whose regression test is deliberately a ghost. Over 2026-09-14 to
2026-09-16 sessions appended thirteen real rows, KI-015 to KI-027, after the last row they could
see, which was the example, inside the comment; three more, KI-028 to KI-030, were placed below a
blank line that ends the table, and KI-029 was written onto the end of KI-028's own physical
line. The gate strips comments before parsing and parses rows only under a header, so it resolved
nothing for sixteen rows, the page rendered none of them, and the rule that every fixed bug lands
a row pointing at its test was unenforced for every one. Nothing compared the rows a reader could
see with the rows the parser returned.

**The fix.** The thirteen rows moved out of the comment byte for byte, the blank line went and the
doubled line was split, so KI-028, KI-029 and KI-030 join the table; the comment keeps only the
`KI-0XX` example. The gate widened rather than gaining a sibling (the ledger's hold-the-count
rule; a parser that skips a row is G40's own class, a register that reads as complete, one level
down): every line shaped like a register row must be one the parser returned for the
regression-test column, the single placeholder inside the comment being the one exception; every
parsed row must in turn match the shape, so a shape that quietly stops matching real ids is red
rather than blind; and every id written onto a line that already carries a row is named on its
own, because the first two checks are keyed on the line and can only ever have an opinion about
the first row on it.

**How reviewed.** The failing test was written first and run against the unfixed file; it named
the hidden rows with their line numbers:

```
30: KI-028 is outside every table that declares 'Regression test (node id)'
33: KI-015 sits inside an HTML comment, where the gate cannot see it
34: KI-016 sits inside an HTML comment, where the gate cannot see it
(KI-017 to KI-023 likewise, lines 35 to 45)
```

Then an independent seat in a fresh context was given the first commit and a refute brief (attack
the byte-identity of the move, the escapes from the new check, the control's reach, any
narrowing, and the documents), never the conclusion. What it proved held: the move is
byte-identical; the failing-test reproduction and its numbers; no existing check lost reach (two
hunks, a docstring sentence and a pure addition); the old fact lived in three live places and all
three were swept; the verdict wording is the ledger's; widening was the right call. What it
refuted:

- The widened check could be narrowed to blindness. With the row shape reduced to a single digit
  it matched one line of the real file, the parser returned every row, and the check passed
  seeing nothing, the failure `test_the_registers_cite_at_least_one_node_each` exists to prevent
  one level up. Closed in d1ee7a1 by the floor: the same mutation, re-run against the landed
  tree, names all thirty-four parsed rows (`narrowed shape: missed [] | unshaped rows: 34`).
- A bold or backticked id, a blockquoted row, a lowercase placeholder, and a row written after
  text on the comment opener's line were seen by neither the parser nor the check. Closed in
  d1ee7a1: the shape tolerates each and the control plants each.
- The control's planted ids resembled no real row, which is what let the first finding through.
  Closed: three-digit ids.
- The first commit's message miscounted the node ids the rescued rows carry. Corrected; the
  resolution claim itself held, by the gate's structural check and by a real pytest collection of
  every id.

**What the landing seat found.** A third seat, in a fresh context, rebased the branch onto `main`
and reviewed it to land it. What it proved held: the widened check is a real widening and not a
weakening anywhere (run against `main`'s own file it named fifteen of the sixteen hidden rows,
and every check that existed before still resolves what it resolved); the "row shape floor" is a
structural check in the gate, not a hand-written number in `.ratchets/`, so it needs no ratchet;
the move is byte-identical against `main` as well as against the branch point (all thirty-four
rows `main` carried compare equal id for id, and only KI-034 is new). What it refuted:

- The widened check named fifteen of the sixteen hidden rows and was silent about the sixteenth.
  KI-029, written onto the end of KI-028's line, is rendered by Markdown as extra columns of
  KI-028, returned by `cells_under` under KI-028's line number, and matched by `KI_SHAPED` only
  as KI-028 — so all three checks, being line-keyed, could only have an opinion about KI-028.
  Closed in 72090f2 by `rows_sharing_a_line`, which names every id past the first on any line,
  inside a table or outside it, with a control that drives the two real rows both ways.
- The branch's own row and the branch's own decisions entry claimed KI-029, which `main` had
  given to the `probe` exit-78 fix while this work was in hand, and the ledger and record
  counted fourteen hidden rows where the landing tree has sixteen. Renumbered to KI-034 and
  recounted in every mirror.

**Left open, named rather than fixed here.** A `fixed` row with an empty regression-test cell
passes everything (the citation rule, not the visibility rule; the register is clean today, the
one empty cell belongs to the `open` KI-014). `duplicate_ids` in the same file is blind both to a
decorated id, the way the shape was, and to a second row sharing a line, the way all three
visibility checks were. The guards ledger, the claims list and the test strategy are parsed by
the same code and can lose a row to a comment the same way; a hidden guard row named by a `gate`
marker is still caught, a hidden hook or ratchet row is not. Recommendation: close the first as a
one-assertion widening of this gate at the next touch of the file (confidence high that it is
cheap; medium that it is worth a commit of its own), point `duplicate_ids` at the same shape in
the same pass, and generalise the visibility check over an id shape per register when a second
register loses a row, as the decisions entry says.

**What the seats did not run, and what stands in for it.** The independent seat did not run
`make check` (it writes the stamp, which would have changed the tree under review); the sessions
ran it green on the working tree before each commit and on the final tree before the merge, and
the merge hook accepts only the stamped tree. The escape analysis is empirical, the shapes probed
one at a time, not a proof over Markdown.

**What an independent seat should attack next.** Whether the shape's tolerance now over-matches
prose inside a comment (a false red fails closed, but a reader would need to rewrite a sentence);
whether a row can be parsed and still be wrong in a way no check names; and the open items above.
