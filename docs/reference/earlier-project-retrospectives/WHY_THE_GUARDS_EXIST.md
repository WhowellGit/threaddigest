# Why the guards exist, and which ones have earned it

> **Intent:** the reasoning behind our tests and ratchets - what incident birthed each one,
> what it has caught SINCE, and the design rule that separates the ones that work from the
> ones that only look like they work. Written because an agent reading 29 lint files learns
> what they check and never learns why, or which to trust.
> **Subject:** testing philosophy · **Doc-type:** canonical guide. **last-verified: 2026-09-01**
> (added THE FIFTH RULE: assert on the delivery surface, and never let two guards mandate
> contradictory truths, from the reach devices-vs-sessions two-guard conflict, X-01 sig #8,
> DPI phase-2 gap #8; body otherwise not re-attested).

## The shape of our test estate

Tests are **47% of all authored source lines** here, and the ratchet lints are **16,373
lines** - larger than the 15,450-line card path they protect. That is a deliberate bet,
and it has paid: this project's own ledger records **13 numbers it once believed and later
disproved**, and across 192 measured results roughly **four in five did not survive honest
re-measurement**. The guards are the machine that produces the one in five.

But scale is not the point, and more guards is not the goal. What follows is the part that
actually matters.

## THE DESIGN RULE (the single most useful thing on this page)

**A guard that scans the whole tree for a STRUCTURAL SHAPE earns its keep. A guard that
polices a HAND-MAINTAINED LIST does not.**

Measured across 29 guards. Every repeat earner - `unreachable_code_lint`,
`silent_except_lint`, `silent_empty_dict_lint`, `undefined_name_lint`,
`sqlite_fetchall_lint`, `direction_lint` - scans everything for a pattern. The unproven
ones cluster into two shapes:

- **The curator is also the enforcer.** A lint checking a registry that the same person
  maintains cannot catch that person's blind spot. It reports on what was remembered.
- **A baked zero on a class that never recurred.** Registered clean, still clean, no
  information ever produced.

**Corollary, learned expensively (R-77):** a guard must key on the INVARIANT, not on a
surface token. Five guards were live and green while the routing gold was 99.96% identical
to the router's own output for two months and DOUBLED in size. They checked an import
graph, a docstring substring, a row count, a tuple in a manifest, and a review cadence
that had not run in eight weeks. One invariant-keyed measurement found a **42-point gap**
that five surface guards missed.

## THE SECOND RULE: a guard that cannot fail is not a guard

**Nine of about twenty audited gates were unfalsifiable.** The worst blessed a rebuild
when the live side had been EMPTIED - a total wipe was the maximally green run that
harness could produce. Others:

- A WAL guard asked `PRAGMA journal_mode` over an `immutable=1` connection that could never
  report WAL. Both machines quoted its green as proof.
- A comparator's history file held 541 entries, **every one a test artifact**. Its baseline
  was synthetic for its entire life. The live events table went from 2,086,542 rows to
  457,500 with nothing anywhere going red.
- A recall gate's baseline was frozen **27 seconds** before its own run, every delta
  exactly 0.0, and that green sat in the cache as its verdict for 34 days.

So: **every new gate ships with a constructed-bad-state positive control**, and
`gate_positive_control_lint` enforces it. Ask of any gate: *when did it last go red, and
has anyone ever seen it fail?* A gate never observed failing is a hypothesis.

## THE THIRD RULE: the marker window is part of the contract

**Found SIX times in a single day (2026-08-16) across two machines working independently,
which is why it is a rule and not an anecdote.** Three were found on Studio, three on MBP,
neither knowing the other was looking. Every one was a context detector reading exactly one
line:

1. **`silent_except_lint`** - a `# silent-ok:` reason reflowed onto a second line stopped
   counting, and the handler reappeared as net-new debt with its reason sitting two lines
   above, unread. **Nine live handlers repo-wide** were being counted that way.
2. **A `P2_OK` marker** placed three comment lines above its gate, putting it four lines
   above the `skipTest` and outside the detector's three-line window. Self-inflicted, by
   the person who had fixed instance 1 an hour earlier.
3. **`check_superseded_claims`** - the worst, because it inverted the guard's meaning. A
   correction is a SECTION, not a sentence: a heading reading `### De-staling the old
   "57.7% unmapped" number`, and every paragraph under it explaining why the figure is
   retired, were all flagged as live RE-ASSERTIONS of that figure. Widening the window to
   the preceding lines plus the nearest heading took it from **25 live flags to 5**, and
   the five survivors are real.

4. **`empty_population_lint`** (MBP) - same one-line lookback.
5. **`silent_empty_dict_lint`** (MBP) - same.
6. **`phantom_cited_test_lint`** (MBP) - same.

**WHY SIX AND NOT ONE: this is a house style, not six mistakes.** The obvious way to write a
marker check is a one-line lookback, so everyone writes it that way, and every one of them
silently stops justifying the moment a comment wraps. Six independent instances in a single
day is what a shared default looks like when it is wrong. The fix is therefore a rule about
how marker checks are written, not six patches.

**THE SHARPEST STATEMENT OF IT** came from a seventh case the same evening, where a
proximity check failed and the commit it blamed (`555b3e8b`) had only reworded an abort
message: *the check did not fail because code changed, it failed because A COMMENT GOT
LONGER.* A guard keyed on a proxy eventually fires on something that is not the thing it
cares about - and widening the window only moves the next false alarm further out. That is
the argument for keying on the invariant (does the justification EXIST for this handler)
rather than on the proxy (is it within N lines).

**A guard a comment rewrap can defeat is measuring formatting, not risk.** Worse, in case
3 the noise was the reason nothing ever got cleaned: the lint sat REMIND-only with a
backlog that could not clear, because there was nothing cleanable in it. **A detector
whose hits are mostly the fix trains everyone to ignore it - the same outcome as having no
detector, bought at the price of running one.**

Markers now walk the contiguous comment block (`silent_except_lint`) or the enclosing
block plus heading (`check_superseded_claims`). Both carry negative controls: a marker
separated by code or a blank line still does NOT justify, and an ordinary heading cannot
launder a genuine re-assertion - only a heading that itself reads as correction context
clears the flag.

## A SWEPT-AND-CLEAN RESULT, recorded so nobody re-runs it

**Question (2026-08-17): is anything in the pre-push gate silently inert?** A module listed in a
gate but decorated `@slow_test` would SKIP when the runner does not set `NFS_RUN_SLOW_TESTS` -
present in the list, doing nothing, reading as coverage. The concern was real enough to check:
`critical_subset.py` does NOT set that flag, and I nearly added a `@slow_test` module to it
before noticing.

**Swept: clean.** Of the 17 modules in `CRITICAL_GROUPS`, exactly one file carries a
`@slow_test` decorator - `test_gate_positive_control_lint` - and it is **not** inert. The
decorator sits on ONE class (`TestLiveBaselineHonest`), not the module, so 20 of its 22 tests
run in the gate. Verified by running it the way the gate does rather than by reading the
decorator: `Ran 22 tests ... OK (skipped=2)`.

The one skipped class is the whole-tree LIVE baseline scan, and its coverage is not lost - it is
deliberately duplicated at the `run_ratchets` gate (which the same pre-push hook runs first) and
in the daily `--slow` sweep. Deliberate, documented at the decorator, and load-bearing coverage
intact through a different path.

**Why this is written down at all:** a refuted concern that leaves no trace gets re-investigated.
The rule that keeps costing time here is *check whether it is already decided before
investigating* - so a clean sweep is worth the four lines it takes to record.

## THE FOURTH RULE: probe each item the way a REAL record would present it

**Established 2026-08-17 by getting the same measurement wrong three times in twenty minutes,
inside the sweep built to find that class of error.** The question was simple: which of the
operator's no-owner rulings actually reach a triage card?

| Probe | Answer | Why it was wrong |
|---|---:|---|
| Harvest ruling blocks by the key name `NO_CLEAR_OWNER` | **1** | TOO LOW. One ruling is keyed `import_mode_and_workspaces_are_unowned` and was invisible to that pattern. One naming convention, one blind spot. |
| Widen the key pattern | **8** | TOO HIGH. Fed ruling LABELS (`AAF`, `interchange import/export`) to the router as COMPONENTS. Zero bugs carry those as a component, so "misses" meant *not a component*, not *unwired*. |
| Validate against the 157 real component values | **1** | Right number, WRONG REASONING. It silently DROPPED every label-shaped area rather than testing it another way. |
| Re-probe the labels as SUMMARY text | **4** | Correct. AAF, FCP-XML, Premiere XML and OTIO all reach a card that way; EDL, Dalet-XML and Import mode do not. |

**1, 8, 1, 4.** Each confident, each wrong in a different direction, for a different reason: a
naming convention, a type confusion, a silent exclusion. Note that probe 3 produced the *number*
a naive reader would call correct while being unable to justify it - a right answer with wrong
reasoning is not a measurement, it is a coincidence with good PR.

**The rule: a component must be tested as a component and a keyword as a keyword.** Feeding
heterogeneous items down one code path answers a question nobody asked, and it fails SILENTLY -
every one of those probes returned a clean-looking number with no error.

**This is the authoring-time twin of the third rule above.** That one says a guard's window is
part of its contract; this one says a guard's INPUT SHAPE is too. Both fail the same way: the
check runs, reports, and measures something adjacent to what you meant.

## THE FIFTH RULE: assert on the artifact the user receives, and never let two guards mandate contradictory truths

**Established 2026-08-18 by the reach "devices vs sessions" case (X-01 signature #8), the same
mislabel this project has corrected twice and had come back once.** The card's `Reach:` line had
been printing an event COUNT under the project's canonical word for crash SESSIONS. Two guards were
live and green the whole time, and they mandated OPPOSITE nouns for the one field:

- `framework/tests/test_reach_is_labelled_sessions.py` required every site that defines or feeds
  `reach_devices` to call it **sessions** (an upper bound on devices, `count_unique([internal-symbol])`).
- `policy/[company]/dqs/tests/test_card_reach_is_devices_not_volume.py` required the card's Reach line to
  call the value **devices**.

Both passed, because each policed a DIFFERENT surface: the first scanned the enrichment/definition
sites, the second scanned the render site, and neither compared its noun against the other's. A field
had two guards, two contradictory contracts, and zero red. Reconciled this session to **sessions**
everywhere (the correct meaning), and the render guard was renamed in spirit to
`test_reach_is_labelled_crash_sessions_not_devices`.

**Two lessons, both about WHERE a guard points:**

1. **Assert on the artifact the user receives, or on the input immediately before the transform,
   never on a surface merely adjacent to it.** The bug was in the rendered Slack line the operator
   reads; a guard that only checked a definition site upstream could be green while the delivered line
   lied. The reach guard now source-anchors the exact render EXPRESSION (`devices = data.get("reach_devices")`
   and the `*Reach:* ... sessions/90d` shape) and a phantom-cite guard checks that `gather()` still
   SELECTS the column, so the render can actually fire.
2. **Two guards on one field must agree, and something has to check that they do.** Contradictory
   contracts that never meet are worse than one guard, because the pair reads as double coverage while
   guaranteeing nothing. When you add a guard to a field that already has one, reconcile the nouns and
   make the invariant single-sourced (here: the canonical reach definition lives in framework
   `CLAUDE.md` § Data Parameters / Sentry, and both guards must cite it, not restate it).

**This is the delivery-surface twin of the third and fourth rules.** The third says a guard's WINDOW
is part of its contract; the fourth says its INPUT SHAPE is; this one says its TARGET SURFACE is, and
adds that a field's guards must not disagree with each other.

## HOW TO READ A GUARD'S PEDIGREE

**Birth is not evidence.** Almost every guard here was born AFTER an incident that a human
review, an agent investigation, or a hand comparison found - not the guard. The honest
question is only *what has it caught since*. For roughly half, the answer is nothing.

Verdict vocabulary used in the audit, worth reusing:

- **EARNED** - independently attributed catches after birth. The two strongest are
  `unreachable_code_lint` (four post-birth catches, including blocking a push on a real
  routing mis-scoring defect) and `silent_except_lint` (two, both self-reported by the
  author as "it was right").
- **EARNED AT BIRTH ONLY** - a real birth scan, nothing since. Keep if the failure class is
  catastrophic and the runtime is cheap.
- **UNPROVEN** - registered clean, never fired. Fourteen of twenty-nine.
- **SELF-SERVING** - both reds resolved by allowlisting rather than a fix, and the
  motivating defect still live and uncaught. One of twenty-nine.

## THE HONEST LEDGER OF SUPPRESSION

**2,250 grandfathered entries across 13 baseline and allowlist files.** The largest,
`silent_except_baseline`, holds **1,319** - against 2 documented real defects. A baseline
that size is a permanent exemption wearing a ratchet's clothes. Suppression is legitimate
and it must stay VISIBLE, which is what `baseline_vintage_lint` reports on every run.

Two allowlist statuses, and the difference matters:
- `accepted` - legitimately standalone, nothing owed.
- `open` - a REAL finding, triaged, awaiting a decision. Suppressed from FAIL so the gate
  runs green, but PRINTED every run so it stays visible. **Check this before investigating
  anything a ratchet flags** - it is the project's memory of what it already decided.

## WHEN TO ADD A GUARD, AND WHEN NOT TO

The reflex of answering every incident with a new lint is itself a failure mode. Before
adding one:

1. Would it scan a structural shape, or police a list you also maintain? If the latter, do not.
2. Can you construct the bad state and watch it go red? If not, you have a hypothesis.
3. Is the class recurring, or did it happen once and get fixed at the source?
4. Does an existing guard cover it with a widened rule? Widening beats adding.

**The current count is 22 blocking ratchets and the recommendation is to hold there** until
one has a fired-in-anger record. Only 1 of the 22 guards the card path - the surface a
human actually reads - which is the real imbalance, not the total.

## Related

`DATA_EXPLORATION_TRAPS.md` (the data-side twin of this page) · `WHERE_THE_TRUTH_LIVES.md`
(what is current vs archive) · `KNOWN_ISSUES.md` and `SYSTEM_FIX_LOG.md` (the incidents
these guards were born from) · `RESULTS_LEDGER.md` (the reversals that justify the estate).
