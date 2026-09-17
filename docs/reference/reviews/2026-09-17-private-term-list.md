# Review record: the private term list widening of G35 (2026-09-17)

**Scope.** `tools/private_terms.py` (new), `tests/gates/test_no_imported_identifiers.py` (the
shared file set moved into the tool and imported back, plus the real-tree check and seven
positive controls), the `check` recipe in `Makefile`, and the rules table in `CLAUDE.md`.
Landed as `ecb0902`. A gate file and the working agreement are review-required surfaces, which
is why this record exists.

**Why now.** The birth incident, stated here exactly as it is stated in the ledger and the
known-issues row: 2026-09-17: a term on the operator's private list was found in tracked text;
nothing mechanical had been checking for it. The standing rule is the operator's own — sensitive
material never reaches the repository, and where the repository can check that mechanically it
builds the check. G35 checked fixed classes only.

**Why the list is not in the tree.** This repository is public. A file listing the terms it must
not carry would be the leak the rule exists to prevent, and a gate whose patterns are its own
disclosure cannot be widened this way. So the list sits in the private folder beside the memory
snapshot, reached through the one definition of that folder in `tools/memory_snapshot.py`; the
tool holds no term, a finding names the pattern that matched by its ordinal in the list, and the
accepted file identifies an occurrence by the hash of its line rather than by its text.

**How reviewed.** In-family, the session that built it under a bounded brief, the controls
watched red before the scan existed; not an independent seat, which is this record's weakness.
Five things were checked rather than assumed.

1. *That the controls were red first.* The scan has one seam, `hits_on`, and the module was
   written with that function returning nothing. Three controls failed against it, the first
   with `assert [] == ['docs/SUSPECT.md:3: private term (pattern 1)', 'docs/SUSPECT.md:4:
   private term (pattern 2)']`; one line of implementation turned all three green.
2. *That the guard was widened rather than added.* The harden skill's "widen before adding" step
   and the ledger's "hold the count" rule both point the same way: G35 already scans exactly
   this population, so it takes the new rule, the guards count does not move, and the file set
   both readers share now has one definition instead of two. It lives in the tool because a tool
   run by `make check` cannot import a test module, and the gate imports it back.
3. *That an acceptance covers what it should and no more.* It is the hash of the offending line
   under one repository-relative path: a control moves the line down its file and it stays
   accepted, edits the line and it is flagged again, and writes the same line into a second file,
   where it is flagged. An acceptance list keyed on `path:line` would have gone stale on the
   first paragraph inserted above it, and one keyed on the term would have had to hold the term.
4. *That the two absent-state answers are the right way round.* No list at all is a verbatim note
   and green: CI and a fresh clone have no private folder and never will, and a permanent red
   there teaches nothing while hiding the real failures. A list that is present and cannot be
   used — unreadable, a pattern that does not compile, no pattern at all, an accepted file that
   is not in the format — is red, because a check that cannot run must never be quietly green.
   Each of those four shapes has its own control.
5. *That the real tree is green for the right reason.* The occurrences the operator had already
   accepted are accepted by the format this tool reads, which is what the real-tree check proves
   by passing; the same check against the list with the accepted file ignored finds them, so the
   list is not vacuous and the green is not the green of a scan that matches nothing. The
   `make check` line prints the number of files it scanned for the same reason.

**Refutations attempted.**

- *That the terms could live in the tree as hashes.* Refused: a hash list in a public repository
  still says how many there are and invites a dictionary attack on short strings, and the
  operator could no longer read back what the repository is enforcing.
- *That a finding should name the pattern's text so a fix is obvious.* Refused: findings are
  pasted into pull requests and kept in CI logs. The ordinal names the line of the private list,
  which the operator has open when fixing.
- *That the check belongs in a pre-commit stage, the stronger rung of the enforcer ladder.*
  Not taken here, and named rather than dismissed: `make check` already runs at the pre-push
  stage and this check runs inside it twice over, once in the gate and once as its own line. A
  per-commit stage would be strictly stronger on the operator's machine and is the obvious next
  tightening if a term ever reaches a commit again.
- *That a missing list should be red whenever the private folder itself exists* (the asymmetry
  the memory tool draws, where a missing snapshot home with live memory present is red).
  Considered and left to the operator: it would be strictly stronger on the machine that has the
  folder, at the cost of a red on a machine that keeps the folder for the snapshot alone.

**Left open, named here rather than papered over.**

- Only tracked text is scanned. A commit *message* is not: the message hook refuses attribution
  trailers and nothing else, so a term in a message is unchecked.
- The gate half reads the folder at its tracked default path, because pytest strips every
  `THREADDIGEST_*` variable before a test runs; a folder moved with that variable is honoured by
  the `make check` line only. A bare `pytest` on such a machine checks nothing and says so.
- The check reads the working tree, never history. A term added to the list is not applied
  backwards, and what is already committed stays committed.
