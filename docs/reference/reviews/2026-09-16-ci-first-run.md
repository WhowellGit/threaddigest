# The first CI run on the remote, and the three defects it found (2026-09-16) — record

Record for commits `e463bb7`, `d22de60` and `c54f683`. Surface touched: `tests/gates/`
(`test_dependency_pins.py`, `test_known_issues_cite_collected_tests.py`, `test_code_health.py`),
which is review-required; the workflow commit that follows them touches no such surface. Seat:
the session that made the change, under a bounded brief, working from the failed run's logs. That
is this record's weakness and it is stated here rather than implied: no independent seat read it.

## What happened

`make check` was green on the owner's Mac and the first run on the remote was red in three jobs.
Every cause turned out to be a real defect rather than a difference CI should have been taught to
tolerate, and none of them could have been found on a machine that had already been running the
suite for days. That is the finding worth keeping: a second kind of machine is a reviewer.

## The three defects

1. **The zone database was undeclared (KI-031).** `core/digest.py` resolves a display timezone
   with `zoneinfo`, which reads the host's IANA database. macOS and the hosted runner have one;
   a slim Ubuntu container has none, so a name every developer machine knows was unknown there.
   The database was a dependency the machines had been supplying silently. It is now declared,
   as a runtime dependency rather than a dev one, because the digest renders wherever the
   schedule runs. The gate that held the PRAW pin widens to hold it, and proves the resolution
   with the host's database taken away — a child interpreter whose `zoneinfo` search path points
   at a directory that is not there — in both directions, the second half hiding the package to
   reproduce the container's failure exactly.

2. **The hash map's gate asked a question about one machine (KI-032).** The map a history rewrite
   leaves is a reference record, added once and never edited, because the append-only logs, the
   register and the other records cite hashes and may not be edited to follow a rewrite. The gate
   over its right-hand column demanded that every recorded successor be a commit this repository
   has. A rewrite moves unmerged local branches too, and a branch nobody has pushed is in no
   other clone, so a row for such a commit is red in CI and in every fresh checkout for as long
   as the branch is unpushed — while the record may not be edited to drop the row. Existence is
   now demanded of the rows a citation is actually followed into, chains included.

   The alternative considered and rejected: prune the uncited rows from the map and keep the full
   map in the archive outside the repository. It was rejected because the map is a reference
   record by its own header and by the tool that reads it, and the working agreement forbids
   editing one; the brief itself made this the tie-breaker. The narrowing loses nothing that
   matters, because a row no document cites cannot make a citation fail, and the day a document
   cites it the citation is followed into the row and both this gate and the cited-hash gate go
   red. That is not an argument on paper: writing the defect's own row into `KNOWN_ISSUES.md`
   with the two hashes in backticks turned the cited-hash gate red on the spot, which is how the
   row came to be worded without them.

3. **A duplicate block was named by the wrong file (KI-033).** pylint emits `duplicate-code` from
   its closing pass, with no node left to attach the message to, so the row carries whichever
   module the run finished on — directory-read order, which differs between filesystems. The
   planted control's block lives in two modules and pylint named one of them on APFS and an
   unrelated third module on ext4. The count was right on both; only the location was wrong, and
   the gate reads the location. The hit now names every module the message body lists, sorted.

## The workflow

Two differences between the informational 3.14 job and the required job, neither of them about
Python 3.14: it ran plain `pytest`, which takes only the `not live` selection from the pytest
configuration and therefore also ran the launchd tests, which need `plutil` and fail rather than
skip so a broken plist cannot pass unnoticed; and it checked out at depth one, which leaves the
two gates that resolve a cited commit hash and the gate that matches a review row's scope with no
history to resolve against. It now makes the Makefile's off-Darwin marker selection and takes
full history. Nothing is skipped and no marker changed.

## Evidence

`make check` green on the branch tip, its block pasted in the pull request body. The container's
failure is reproduced on macOS by pointing `PYTHONTZPATH` at a directory that is not there, which
is what the new control does in-suite. `actionlint` could not be run on this machine (the job runs
it through a container image and neither that image nor the binary is installed here); the
workflow file was parsed and the two changed keys are forms already used elsewhere in it, and the
`actionlint` job, green on the failed run, is the check that matters.

## What an independent seat should attack

That the hash-map gate's narrowing is a weakening dressed as a correction; that a defect found
only because a second operating system ran the suite argues for a macOS job rather than for
confidence; and that three defects hiding behind one machine is an argument for the portability
job running on every push rather than on a file list.
