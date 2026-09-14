# External review brief: {project} at commit `{commit}` ({date}; packet `{packet_hash}`)

You are reviewing the design and the current implementation of a small personal system that
harvests Reddit discussion about a video-editing product every day, stores it locally, honours
deletions, and helps its one operator see what people are struggling with. The packet holds the
committed tree at one commit: the plan, the decisions log, the working agreement and everything
that enforces it, the source, and the tests. `00-README.md` gives the reading order and
the file index at its end maps every file to the upload part that holds it; use it before searching.
`02-CLAIMS.md` lists the claims the project stakes its correctness on.

## Intent, success, and acceptance

**Why this review exists.** The owner is one person building this system with an agent, and
the project's own rule is that same-model builders agreeing is not confirmation. This review is
the first look by a different model family before the next stages (comment trees, reconcile
and scrub, the daily digest) are built on the current design. Its purpose is to find the errors
that would cost data, compliance, or a milestone while they are cheap to fix. It is not a
request for validation, a summary, a redesign, or a comparison with other tools.

**What a successful review looks like.** Findings that survive the owner's triage: each one is
re-checked by running the cheapest check you name, and a finding that survives changes the
code, a test, a document, or the plan. Three findings that survive are worth more than fifteen
that do not. Saying that an area holds as far as you can tell, and why, is a valid result; a
confident finding that fails its own check is the failure to avoid.

**Acceptance criteria for your report.** It is accepted for triage when every finding carries a
verbatim quote with part, path, and line; a mechanism (why, with evidence); a cost and a
confidence on the scales below; and a cheapest check the owner can run in under an hour. A
finding without a quote or a check is dropped unread. The report ends with the cannot-judge
list and at most five questions, and contains no summary of the system and no restatement of
the plan.

Three facts about the packet that change how you read it:

- **There is no real Reddit adapter yet.** Tranche B waits on credentials. The fake gateway's
  behaviour summary (`src/insightminer/adapters/reddit_fake/__init__.py`) is a *specification*
  of what the real adapter must reproduce; judge it as a spec against Reddit as it is today.
- **Every line in the parts carries its line number** in the left margin, the same number
  the file has in the repository. Cite a finding as part, path, line number, and the verbatim
  quoted line, for example ``2-harness-1.md › tools/hooks/no_bypass_git.sh › 141 › "case
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
- Themes, digest, schedule, notifications as a daily product. State: Not built (M1d); the core modules render, nothing schedules or ships them. Where to look: `core/themes.py`, `core/digest.py`.
- Web UI, saved searches, containers. State: Not built (M2, M3, M4). Where to look: plan sections only.
- The harness: hooks, ratchet families, gates, code-health analysis, this packet builder. State: Built and live. Where to look: `tools/`, `tests/gates/`, the hook settings and rule files, the ratchet files.

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
   the author from a removal by a moderator, what do the rate-limit headers report, and what
   do the API terms require of a personal, read-only collector that stores content? Cite.
   Start here: `core/deletion.py`, the collector design review under `docs/reference/reviews/`
   (its section 1.4 is the source of the deletion predicates), the decisions log's compliance
   bounds, `config/settings.yaml`. Search for: "removed_by_category", "reconcile", "Limits",
   "user agent".
2. **Compliance inside the store.** Where could deleted or removed content survive: the row
   store, the search index, exports, backups, the digest, logs, the raw JSON? Which transition
   in the content state machine (plan § Data model; `src/insightminer/core/deletion.py`) is
   wrong or missing? What does a run that dies mid-reconcile leave behind? Start here:
   `core/deletion.py`, the search-index triggers in `db/schema.sql`, `db/fts.py`,
   `db/backup.py`, the error columns written by `services/sweep.py`. Search for: "scrub",
   "tombstone", "raw_json", "VACUUM INTO", "last_error".
3. **Data integrity.** SQLite in write-ahead mode, FTS5 with external content, Alembic batch
   migrations, upserts, identity rules, backups and restore: which of the plan's rules are
   wrong for the engine's actual behaviour, and which failure is not covered by a test?
   Start here: `db/engine.py`, `db/repo.py`, `db/migrate.py`, `db/migrations/`, the
   database learnings under `docs/learnings/`, `tests/db/`. Search for: "ON CONFLICT",
   "posts_fts", "render_as_batch", "wal_checkpoint", "AUTOINCREMENT".
4. **Enforcement.** Given `.claude/settings.json` and `tools/hooks/*.sh` in the harness part,
   write the literal command line an agent with shell access could run to (a) change a value
   under `.ratchets/`, (b) commit with verification off, or (c) push to `main`, that the
   hooks' matching does not catch; quote the matching code you defeated. Then: which rule in
   the working agreement's rules table names an enforcer that does not actually enforce it,
   and which gate or ratchet is unfalsifiable or self-serving? Also: what actually stops a
   red tree from being merged into `main` today, given that there is no remote and the check
   runs on push? Start here: the hook settings file, `tools/hooks/`, `tools/ratchet.py`, the
   rules table in `CLAUDE.md`, `tests/gates/test_hooks.py`. Search for: "READ_ONLY",
   "GIT_ALLOWED", "Enforced by", "ff-only".
5. **Test strategy.** Using `docs/TEST_STRATEGY.md` and the tests parts: which class of bug
   passes this suite? List the behaviours asserted only by the fake gateway's summary that no
   shipped test could detect as wrong if Reddit's real behaviour differed, and name the three
   you would probe first, with the call. What does the coverage figure hide? Search for:
   "Behaviour summary", "hypothesis", "golden". Start here: `docs/TEST_STRATEGY.md`,
   `tests/adapters/test_fake_gateway.py`, `tests/e2e/`, `tests/gates/test_invariants_planted.py`.
6. **The analytic product.** `core/digest.py`, `core/themes.py`, and `core/normalize.py` ship
   with a golden digest at `tests/unit/golden/digest_example.md`. Where does the ranking
   mislead: ties, one loud author, a theme rule that over- or under-matches, a coverage
   denominator printed beside a number it does not cover? Search for: "distinct", "rising",
   "author_fullname".
7. **Cost of the enforcement surface.** For one operator: which guards in the ledger are
   unfalsifiable, which restate another, and which three would you delete outright? Name the
   failure each would stop catching. Search for: "UNPROVEN", "Positive control".
8. **Abandonment.** The system depends on three recurring human duties (read the digest,
   acknowledge alerts, label tags). Which design choices break silently rather than loudly
   when the operator skips a week: coverage, the freshness window, alert acknowledgement,
   deletion reconcile? Search for: "FRESHNESS_WINDOW", "acknowledge", "partial".
9. **Sequencing and scope.** For a tool run by one person, what should be cut, deferred, or
   built earlier than the milestone table says? What in the plan is complexity without a
   failure mode behind it?
10. **Anything else**, ranked the same way.

## Output

At most fifteen findings, each under 150 words, as a numbered list ranked by cost times
confidence, one block per finding with these labelled lines: Cost (3/2/1); Confidence (3/2/1);
Location (part, path, line); Quote; Claim attacked; Why; Cost if right; Cheapest check. No
tables anywhere in the report. Then the "cannot judge" items, each with the missing context
named. Then at most five questions for the owner. No preamble, no summary of the system, no
closing encouragement.
