# External review brief: {project} at commit `{commit}` ({date}; packet `{packet_hash}`)

You are reviewing the design and the current implementation of a small personal system that
harvests Reddit discussion about a video-editing product every day, stores it locally, honours
deletions, and helps its one operator see what people are struggling with. The packet holds the
committed tree at one commit: the plan, the decisions log, the working agreement and everything
that enforces it, the source, and the tests. Read `00-README.md` for the reading order and
`02-CLAIMS.md` for the claims the project stakes its correctness on.

## Your job

Find what is wrong, what it would cost, and how sure you are. Do not summarise the plan, praise
it, or restate it in your own words. Assume the authors know what they wrote; they do not know
what they got wrong.

For every finding give, in this order:

1. **The claim or choice you are attacking**, quoted, with the file and line (or section) in
   the packet.
2. **Why it is wrong or fragile**, with evidence: a public fact with its source, a code path,
   a counterexample, a documented behaviour of the API or the database engine.
3. **What it would cost if you are right**: data loss, a compliance breach (content kept after
   its author removed it), wrong conclusions in the digest, a wasted build, an operator
   surprise.
4. **Your confidence** (high, medium, low) and what evidence would change your mind.
5. **The cheapest check** that would settle it: a test to write, a query to run, a document to
   read, a call to make.

Rank findings by cost times confidence. Where you lack the context to judge, say "cannot judge"
and why, instead of guessing; a guess presented as a finding costs the owner more than silence.

Ground rules:

- The decisions log lists settled choices and settled negatives (levers deliberately not
  pulled), each with the reason and a revisit trigger. Attack a settled choice only with
  evidence that its reason is false or its trigger has fired; do not propose tools, services,
  frameworks, or infrastructure the negatives already decline unless a finding requires it.
- Prefer the concrete over the general. "Consider adding monitoring" is not a finding;
  "the dead-man ping fires on success only, so a run that hangs after the ping is invisible
  until the next day, see `services/collect.py` line N" is.
- Treat the claims list as load-bearing: for each claim, either say how you would falsify it
  and whether the cited test actually asserts it, or say it holds as far as you can tell.
- Numbers: when you cite a limit, a rate, a cap, or a date, name the source.

## Questions, in priority order

1. **Reddit reality.** Which assumptions in the collector algorithm (plan § Collector algorithm)
   and in the fake gateway's behaviour summary (`src/insightminer/adapters/reddit_fake/__init__.py`)
   are false about Reddit's API today: listings and their caps, `more` stubs and tree expansion,
   `info()` semantics for deleted and removed items, the signals that distinguish a deletion by
   the author from a removal by a moderator, rate limits and the headers that report them, and
   what the API terms require of a personal, read-only collector? Cite.
2. **Compliance.** Where could deleted or removed content survive: the row store, the search
   index, exports, backups, the digest, logs, the raw JSON? Which transition in the content
   state machine (plan § Data model) is wrong or missing? What does a run that dies mid-reconcile
   leave behind?
3. **Data integrity.** SQLite in write-ahead mode, FTS5 with external content, Alembic batch
   migrations, upserts, identity rules, backups and restore: which of the plan's rules are
   wrong for the engine's actual behaviour, and which failure is not covered by a test?
4. **Enforcement.** The working agreement's rules table names an enforcer per rule. Which
   enforcer does not actually enforce its rule? Which gate or ratchet is unfalsifiable,
   bypassable by an agent operating the repository, or self-serving? Which hook can be defeated
   by a command it does not recognise?
5. **Test strategy.** Which class of bug passes this suite? Where is the fake gateway the only
   witness, and where would the real adapter diverge from it? What does the coverage figure
   hide?
6. **Sequencing and scope.** For a tool run by one person, what should be cut, deferred, or
   built earlier than the milestone table says? What in the plan is complexity without a
   failure mode behind it?
7. **Anything else**, ranked the same way.

## Output

First a ranked findings table with the columns: rank, cost, confidence, file and line, the
claim attacked, why, cost if right, cheapest check. Then the "cannot judge" items with the
missing context named. Then at most five questions for the owner. No preamble, no summary of
the system, no closing encouragement.
