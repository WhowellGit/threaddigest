# External review brief: {project} at commit `{commit}` ({date}; packet `{packet_hash}`)

You are reviewing the design and the current implementation of a small personal system that
harvests Reddit discussion about a video-editing product every day, stores it locally, honours
deletions, and helps its one operator see what people are struggling with. The packet holds the
committed tree at one commit: the plan, the decisions log, the working agreement and everything
that enforces it, the source, and the tests. `00-README.md` gives the reading order, and the
file index at its end maps every file to the upload part that holds it; use it before searching.
`02-CLAIMS.md` lists the claims the project stakes its correctness on.

## Intent, success, and acceptance

**Why this review exists.** The owner is one person building this system with an agent, and
the project's own rule is that same-model builders agreeing is not confirmation. This review is
the first look by a different model family before the next stages (comment trees, reconcile
and scrub, the daily digest, the web UI) are built on the current design. Its purpose is to find
the errors that would cost data, compliance, or a milestone while they are cheap to fix. It is
not a request for validation, a summary, a redesign, or a comparison with other tools. An
internal panel has already reviewed this tree; what it found is recorded in
`docs/runbook/KNOWN_ISSUES.md` (the open rows) and in the hardening queue on
`docs/recent/STATUS.md`, both in the packet. You are asked for what an outside vantage and a
different model family can add, not for a second pass over those.

**Where your input is worth most, in this order.**

1. Reddit as it is today, against the fake gateway's behaviour summary, which is the project's
   specification of Reddit and has never been checked against a real response.
2. What a scrub leaves on disk: the search index, the write-ahead log, backups, error columns,
   logs, raw JSON; and the SQLite behaviours the design relies on.
3. Unattended operation over months: the failures between runs (a schedule that stops, backups
   and retention, disk, signals, credentials, a subreddit gone private), as opposed to the
   failures during a run, which are the best-tested part of the tree.
4. The test methodology's blind spot: assertions that read the system back through the same
   abstraction that wrote it, which artifacts have no witness at all, and what the fake alone
   attests.
5. Operator workflows: what each routine action needs to be complete, and the practical
   breakages tools like this suffer (reset, delete, undo, cancel, re-tag, restore, configuration
   drift).
6. The enforcement machinery itself: hooks that judge command text, ratchets, gates, the review
   register; where it is bypassable, unfalsifiable, or costs more than it prevents.

Anything else is welcome after the ranked findings, under a separate heading, and is judged the
same way.

**What a successful review looks like.** Findings that survive the owner's triage: each one is
re-checked by running the cheapest check you name, and a finding that survives changes the
code, a test, a document, or the plan. Three findings that survive are worth more than fifteen
that do not. A successful review has at least one finding in each of the first four areas that
is not already in the known-issues rows or the hardening queue, or a reasoned statement that
the area holds as far as you can tell. A confident finding that fails its own check is the
failure to avoid.

**Acceptance criteria for your report.** It is accepted for triage when every finding carries a
verbatim quote with part, path, and line; a mechanism (why, with evidence); a cost and a
confidence on the scales below; and a cheapest check the owner can run in under an hour. A
finding without a quote or a check is dropped unread. A finding that restates an open
known-issue row or a queued hardening item is marked "known" in one line and not expanded; a
new angle on a known item is a finding. The report ends with the cannot-judge list and at most
five questions, and contains no summary of the system and no restatement of the plan.

Three facts about the packet that change how you read it:

- **There is no real Reddit adapter yet.** Tranche B waits on credentials. The fake gateway's
  behaviour summary (`src/insightminer/adapters/reddit_fake/__init__.py`) is a *specification*
  of what the real adapter must reproduce; judge it as a spec against Reddit as it is today.
- **Every line in the parts carries its line number** in the left margin, the same number
  the file has in the repository. Cite a finding as part, path, line number, and the verbatim
  quoted line, for example ``2-harness.md › tools/hooks/no_bypass_git.sh › 141 › "case
  \"$cmd\" in"``. A finding whose quoted line is not at the cited number is dropped, so quote
  what you see rather than what you remember.
- **Earlier reviews are recorded, not withheld.** The dated review reports are excluded, but
  the plan and the decisions log record what was adopted from them and the authors' rulings
  ("that charge is correct", "adopted from the enforcement panel"). Treat every such recorded
  conclusion as a claim under review, not as settled. A finding that contradicts an adopted
  conclusion is worth more, not less.

## Your job

Find what is wrong, what it would cost, and how sure you are. Do not summarise the plan, praise
it, or restate it in your own words. Assume the authors know what they wrote; they do not know
what they got wrong.

For every finding give, in this order:

1. **The claim or choice you are attacking**, quoted verbatim, with the part, path, and line.
2. **Why it is wrong or fragile**, with evidence: a public fact with its source, a code path,
   a counterexample, a documented behaviour of the API or the database engine.
3. **Cost if you are right**, on this scale: **3** = irreversible data loss, or content kept
   after its author removed it; **2** = wrong conclusions in the digest, or a wasted
   milestone; **1** = operator friction or wasted effort short of a milestone.
4. **Confidence**, on this scale: **3** = high (you can point at the evidence), **2** = medium
   (a strong inference), **1** = low (a suspicion worth a check). Say what evidence would
   change your mind.
5. **The cheapest check** that would settle it: a test to write, a query to run, a document to
   read, a call to make.

Rank findings by cost times confidence and show both numbers. Where you lack the context to
judge, say "cannot judge" and why, instead of guessing; a guess presented as a finding costs
the owner more than silence.

A worked example of the shape wanted: "`3-source-2.md › src/insightminer/services/invariants.py
› 314 › \"window = repo.recent_sweeping_runs(ctx.conn, current_run_pk=ctx.run_pk,
limit=FRESHNESS_WINDOW)\"`: with `FRESHNESS_WINDOW = 2`, a source that stops appearing is
invisible until it has been missing from two sweeping runs, so a two-day outage of one
subreddit is silent on day one. Cost 2, confidence 3. Cheapest check: a test that plants a
source absent from exactly one run and asserts the digest names it."

Ground rules:

- The decisions log lists settled choices and settled negatives (levers deliberately not
  pulled), each with the reason and a revisit trigger. Attack a settled choice only with
  evidence that its reason is false or its trigger has fired; do not propose tools, services,
  frameworks, or infrastructure the negatives already decline unless a finding requires it.
- Prefer the concrete over the general. "Consider adding monitoring" is not a finding; the
  worked example above is.
- Treat the claims list as load-bearing: for each claim, either say how you would falsify it
  and whether the cited test actually asserts it, or say it holds as far as you can tell. The
  project's own gate checks only that each cited test exists, not that it asserts the claim;
  that judgement is yours.
- Numbers: when you cite a limit, a rate, a cap, or a date, name the source.
- Spend at most a quarter of your effort on public API facts (questions 1a and 1b); the rest
  of the questions are about this code and cannot be answered from the web.

## What exists at this commit, and what does not

Read this before spending effort: several questions below touch code that is designed but not
yet built, and the packet's index confirms the absences.

- Pure logic: deletion state machine, paging and stop rules, revisit ladder, budget, theme rules, normalisation, digest rendering, retry ladder. State: Built, test-first, as `core/` modules; some have no caller yet (see below). Where to look: `src/insightminer/core/`, `tests/unit/`.
- Schema, migrations, upserts, search index over live views, backups table. State: Built (revision 2). Where to look: `src/insightminer/db/`, `tests/db/`.
- Posts ingestion: lock, run lifecycle, sweep with one transaction per page, post-run invariants, doctor, migrate and seed commands, the `run` command. State: Built and proven end to end against the fake gateway. Where to look: `src/insightminer/services/`, `src/insightminer/cli.py`, `tests/e2e/`, `tests/services/`.
- The fake Reddit gateway. State: Built; the only gateway that exists. Where to look: `src/insightminer/adapters/reddit_fake/`.
- The real Reddit adapter, wire captures, the `probe` command. State: Not built (tranche B waits on credentials); no real Reddit response has been captured yet. Where to look: nothing under `adapters/` for it.
- Comment trees and their budget accounting. State: Not built (M1b); the fake and the paging rules model them. Where to look: `core/paging.py`, the fake's tree methods.
- Reconcile, revisit, scrub as run stages. State: Not built (M1c); `core/deletion.py` decides, nothing in a run calls it yet. Where to look: `core/deletion.py`, `db/fts.py` (scrub of the index exists).
- Themes, digest, schedule, notifications, the dead-man ping, scheduled backups, retention pruning. State: Not built (M1d); the core modules render, nothing schedules or ships them; the backup primitives exist and only the migration path calls them. Where to look: `core/themes.py`, `core/digest.py`, `db/backup.py`, `services/migrate.py`.
- Web UI, saved searches, containers. State: Not built (M2, M3, M4). Where to look: plan sections only.
- The harness: hooks, ratchet families, gates, code-health analysis, this packet builder, the green-stamp merge rule. State: Built and live. Where to look: `tools/`, `tests/gates/`, the hook settings and rule files, the ratchet files.

For questions about unbuilt stages, judge the design and the pure logic that exists, say so,
and do not spend effort confirming absences the list above already states.

## Questions, in priority order

1a. **Reddit listings and trees.** Which assumptions in the collector algorithm (plan
   § Collector algorithm) and the fake gateway's behaviour summary are false about Reddit's
   API today: listing pagination and its caps, `more` stubs and tree expansion, `info()`
   semantics for deleted and removed items, and the shape of what comes back? Cite. Search
   for: "iter_new_pages", "fetch_tree", "more_limit", "LISTING_CAP". Start here: the
   plan's Collector algorithm section, the fake's behaviour summary, `services/sweep.py`,
   `core/paging.py`, the research report under `docs/reference/`.
1b. **Reddit compliance signals and terms.** Which signals actually distinguish a deletion by
   the author from a removal by a moderator, what happens to `info()` for a subreddit that has
   gone private, what do the rate-limit headers report, and what do the API terms require of a
   personal, read-only collector that stores content? Cite.
   Start here: `core/deletion.py`, the collector design review under `docs/reference/reviews/`
   (its section 1.4 is the source of the deletion predicates), the decisions log's compliance
   bounds, `config/settings.yaml`. Search for: "removed_by_category", "reconcile", "Limits",
   "user agent".
2. **Compliance on disk.** Where could deleted or removed content survive after a scrub: the
   search index's segments until an `optimize`, the write-ahead log after a checkpoint that
   found a reader, backups made by copy or by `VACUUM INTO`, error columns, logs, raw JSON and
   rejects? Which transition in the content state machine (plan § Data model;
   `src/insightminer/core/deletion.py`) is wrong or missing? What does a run that dies
   mid-reconcile leave behind? Start here: `core/deletion.py`, the search-index triggers in
   `db/schema.sql`, `db/fts.py`, `db/backup.py`, `db/engine.py`, the error columns written by
   `services/sweep.py`. Search for: "scrub", "tombstone", "raw_json", "VACUUM INTO",
   "last_error", "wal_checkpoint", "secure_delete".
3. **SQLite as it actually behaves.** Write-ahead mode and checkpointing, pragmas set per
   connection, FTS5 external content over live-only views with triggers on the base tables
   (including what those triggers do on a routine upsert whose text has not changed),
   `AUTOINCREMENT` and the sequence table across an Alembic batch-mode copy, batch mode with
   views, triggers, and FTS in one migration, the backup API against `VACUUM INTO`, integrity
   checks after a migration: which of the plan's rules are wrong for the engine's documented
   behaviour, and which failure has no test? Start here: `db/engine.py`, `db/repo.py`,
   `db/migrate.py`, `db/migrations/`, the database learnings under `docs/learnings/`,
   `tests/db/`. Search for: "ON CONFLICT", "posts_fts", "render_as_batch", "wal_checkpoint",
   "AUTOINCREMENT", "sqlite_sequence".
4. **Unattended months.** The failures during a run are the best-tested part of the tree;
   judge the failures between runs: a schedule that stops (agent unloaded, machine moved, not
   logged in), backups and retention, disk full at run-finish, a process signal at shutdown,
   credentials revoked, a subreddit gone private for days, clock and daylight-saving changes,
   configuration drift between the YAML and the database. Which of these produce silence
   rather than a loud signal, what does the operator see after a failed night, and which
   designed-but-unbuilt controls must precede the daily schedule? Start here: plan
   § Deployment path and § Resilience to outages, `services/invariants.py`,
   `services/doctor.py`, `services/runs.py`, `deploy/launchd/`, `settings.py`. Search for:
   "FRESHNESS_WINDOW", "acknowledge", "partial", "retention", "log_path", "crashed".
5. **The suite's blind spot.** Using `docs/TEST_STRATEGY.md` and the tests parts: which
   assertions read the system back through the same abstraction that wrote it (a count from
   the writer's connection, a query answer rather than the stored bytes), which artifacts have
   no witness at all, and which behaviours are asserted only by the fake gateway's summary
   with no shipped test able to detect a real divergence? Name the three you would probe
   first, with the call. What does the coverage figure hide, and what runs at a milestone
   boundary that does not run per commit? Start here: `docs/TEST_STRATEGY.md`,
   `tests/adapters/test_fake_gateway.py`, `tests/e2e/`, `tests/db/test_fts.py`,
   `tests/gates/test_invariants_planted.py`. Search for: "Behaviour summary", "hypothesis",
   "golden", "_docsize", "read_bytes".
6. **Operator workflows.** For each routine action (first-run setup; add or remove a source;
   create a theme, preview, save, re-tag; act on the digest; correct a tag by hand and keep it
   through a re-tag; run now, cancel, and a schedule firing meanwhile; recover from a failed
   run; reconcile and see what was scrubbed; export, back up, restore, move machines; archive
   or delete a workspace; change configuration; rename or merge themes; reset), what is
   required for it to be complete, what is the classic breakage in tools like this, and does a
   spec row or test exist? Start here: plan § Web UI (the routes table and the curation
   controls), § Operator surface, § Workspaces, `src/insightminer/cli.py`,
   `docs/runbook/RUNBOOK.md` section 2, `docs/TEST_STRATEGY.md`. Search for: "origin",
   "watch_until", "Confirmation", "cancel", "import".
7. **Enforcement.** Given the hook settings file and `tools/hooks/*.sh` in the harness part,
   write the literal command line an agent with shell access could run to (a) change a value
   under `.ratchets/`, (b) commit with verification off, (c) push to `main`, or (d) merge into
   `main` a tree the check has not stamped, that the hooks' matching does not catch; quote the
   matching code you defeated. Then: which rule in the working agreement's rules table names
   an enforcer that does not actually enforce it, which gate or ratchet is unfalsifiable or
   self-serving, and which three guards would you delete, naming the failure each would stop
   catching? Start here: the hook settings file, `tools/hooks/`, `tools/ratchet.py`,
   `tools/check_stamp.py`, the rules table in `CLAUDE.md`, `docs/runbook/GUARDS.md`,
   `tests/gates/test_hooks.py`. Search for: "READ_ONLY", "GIT_ALLOWED", "Enforced by",
   "ff-only", "UNPROVEN".
8. **The analytic product.** `core/digest.py`, `core/themes.py`, and `core/normalize.py` ship
   with a golden digest at `tests/unit/golden/digest_example.md`. Where does the ranking
   mislead: ties, one loud author, a theme rule that over- or under-matches, a coverage
   denominator printed beside a number it does not cover? Search for: "distinct", "rising",
   "author_fullname".
9. **Sequencing and scope.** For a tool run by one person, what should be cut, deferred, or
   built earlier than the milestone table says? Should real Reddit captures come before
   comment trees rather than after reconcile? What in the plan is complexity without a
   failure mode behind it?
10. **Anything else**, ranked the same way, and general observations under their own heading
    at the end.

## Output

At most fifteen findings, each under 150 words, as a numbered list ranked by cost times
confidence, one block per finding with these labelled lines: Cost (3/2/1); Confidence (3/2/1);
Location (part, path, line); Quote; Claim attacked; Why; Cost if right; Cheapest check. No
tables anywhere in the report. Then the "cannot judge" items, each with the missing context
named. Then at most five questions for the owner. Then, if you have them, general observations
under their own heading, at most 200 words. No preamble, no summary of the system, no closing
encouragement.
