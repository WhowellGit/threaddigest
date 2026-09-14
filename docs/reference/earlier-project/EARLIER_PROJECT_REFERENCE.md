# The earlier project: one reference

> **Update policy:** prune-stale for the judgements (a call settled by new evidence is corrected in
> place, dated); append-only for the dated notes at the end of § 8. `last-verified: 2026-09-14 — every
> number below was read from the source named beside it in this pass; nothing was carried from memory.`
>
> **Audience:** a future project, or an agent working on this one, that wants to know how a real
> solo-operator-plus-agents data system and its harness worked, what failed and why, what was measured,
> and what Insight Miner took from it — without opening any of that project's files.

---

## 1. What this is, and how to read it

*This is the entry point for everything Insight Miner learned from Wes's earlier project; the assessments
that produced it are now its appendices (§ 10). It is a synthesis of six analysis passes over that
project's documents, repository, transcripts and measurements, abstracted so that none of its
identifiers cross over.*

### Provenance: what was read, when, and by what method

| Pass | When | What was read | Where the record is |
|---|---|---|---|
| The retrospective bundle | 2026-09-12 | Eight point-in-time documents (~700 KB) the earlier project wrote about itself: a ranked failure retrospective, a guards record, a settled-negatives log, an engineering key-learnings log, a value-stage learnings log, a project-journey narrative, an architecture-and-rebuild guide, and their index | `docs/reference/earlier-project-retrospectives/` (three kept, redacted); the rest in the archive |
| Two reviewer digests | 2026-09-12 | Two agents read six of the eight in full and mapped them onto the Insight Miner plan | `docs/reference/reviews/2026-09-12-db-learnings-review-A.md`, `-B.md` |
| Ranked adoption | 2026-09-12 | 26 database and process lessons ranked by confidence, importance, value and cost, with the declined and scoped items | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` |
| Adversarial review of the transfer | 2026-09-13 | The applied set itself, challenged | `docs/reference/reviews/2026-09-13-adversarial-review.md` |
| The harness assessment, then a steelman pass | 2026-09-13 | Every mechanism in the harness catalogued in four parts, each with its birth incident, evidence, cost, scale-dependence and transfer call; then every recommendation put to a defence argued from the same documents | `docs/reference/reviews/2026-09-13-harness-assessment.md` |
| The archive pass: 26 open questions answered | 2026-09-13 (night) | The earlier project's full backup — its repository with history, its session transcripts, its predecessor repositories, folders never in git, under a full-text index — read by eight agents and synthesised | `docs/reference/reviews/2026-09-13-harness-questions-answered.md` |
| The documentation and memory census | 2026-09-13 | A usage census over the transcripts against a universe of documents taken from the final snapshot, plus a practice-by-practice read of the documentation system and of the guides as documents | `docs/reference/reviews/2026-09-13-documentation-practices-assessment.md` |

Everything was read-only. The raw findings behind the last two passes — thirteen agent reports — live in
the archive outside this repository (§ 10) and were consulted here where an in-repo summary was too thin.

### The limits every number below inherits

1. **Shell reading is invisible.** Only dedicated file-tool calls were counted, and the structured
   search tool was invoked exactly once across all transcripts, so essentially all searching went
   through shell commands the method cannot see. **Every read count is a floor, not a ceiling.**
2. **The transcript window is about ten weeks**, not the project's life. "Never read" means "never
   opened with the read tool in a captured transcript inside that window".
3. **Absolute transcript counts are inflated roughly threefold** — the same tool call is written to the
   transcript once per file that replays the turn. What survives is set membership and ratios.
4. **The repository history was squashed** to a single root commit partway through, so no
   repository-side "this never happened" can see behind that date. The predecessor repositories partly
   repair this.
5. **"Active hours" means harness-engagement time**, derived from gaps between timestamped messages
   capped at ten minutes, and nearly all of it sits in two long-lived sessions kept alive by scheduled
   wake-ups. It is not hands-on-keyboard time.
6. **Verdicts are judgements over measurements**, and are labelled as such. Every "adopt / skip / defer"
   below is reasoning; the numbers are the evidence it reasons over.

### The sensitivity rule

Nothing project-specific crosses over from the earlier project: no codenames, register or decision
numbers, ticket keys, hosts, channels, people, service accounts, file or script names, or the name of
the employer whose product this project monitors. Its artifacts are named by role — *its issue
register*, *its architecture guide*, *a session-end hook*, *its fetch stop-rule module*. This is a rule
about **conflation** as much as confidentiality: two systems must stay distinct, and a lesson that
crosses over is stated abstractly or not at all. `tests/gates/test_no_imported_identifiers.py` enforces
it on every tracked file.

### The stance: verify before reuse

Three findings from the earlier project's own evidence govern how this document should be used.

- **A guard's clean record is not evidence.** Six of its twenty-eight blocking checks had a defect found
  *in the check itself*, and in every case the check's own record read clean while it was broken.
- **A red is not a catch.** At least half of its reconstructable red-to-green transitions were closed by
  editing the test.
- **Birth is not evidence.** Almost every guard was born after an incident that a human, an agent
  investigation or a hand comparison found — not the guard. The honest question is only what it caught
  since, and for roughly half the answer is nothing.

So: a mechanism described here as having worked *there* is a hypothesis *here* until this project has
seen it go red on a constructed bad state. That is the whole content of the "verify before reuse"
stance, and it is why every gate in this repository ships a positive control.

---

## 2. The earlier project in one page

*A solo operator plus agents built a bug-intelligence pipeline over about six months, ending with a very
large SQLite store, a two-to-three machine fleet, and a harness of guards, registers and hooks that grew
larger than the product path it protected.*

**What it did.** It answered "which reported product defects actually matter, and who should fix them"
by pulling four upstream sources — an issue tracker, pull requests, crash events, and release notes —
into an enrichment pipeline and a single searchable store, then surfacing ranked triage cards to the
operator through a chat tool.

**Its shape.** Raw payloads were fetched to disk as line-delimited JSON plus per-item sidecar files, run
through a twenty-two-step pure-Python enrichment ladder, and imported into one SQLite database of
roughly thirty-six tables and eight views (~815 lines of DDL), with a full-text index, dense embeddings,
a keyword ranker, and the card layer on top. Schema was a *payload version* stamped onto artifacts,
not database migrations. Coordination between processes was through state files, advisory locks and a
periodic health command. A second and third machine joined later, bridged through a chat channel because
they had no direct socket to each other.

**Its scale.** Millions of raw crash events condensing to tens of thousands of distinct crashes, tens of
thousands of tracked bugs and pull requests, a crash store in the hundreds of gigabytes, and a document
tree in the low thousands. The figures, and the places two sources disagree about them, are in § 5.1.

**Its lifecycle.** It began as "can I get my own bug data out of the tracker?", had **no version control
at all** until a merge sprint in its third month, and is described by its own index as a project that
"did NOT start from a clearly defined spec" and whose "defining trait became catching and correcting its
own rosier story". Every crisis produced a safeguard: a data-loss event produced atomic writes, a schema
drift produced a single-source contract module, a leaking evaluation produced leak-free measurement.
Its journey document's own summary is that "the safeguards are arguably the real product".

**Why it matters as a source.** Three reasons, and they are unusual together.

1. **It is audited, not remembered.** It ran an audit over its whole guard estate and published the
   verdict that roughly half of its guards had never caught anything. It kept a ledger of numbers it had
   believed and later disproved. Documents that grade themselves this harshly are rare and are worth
   more than documents that describe a design.
2. **It is measured.** The archive pass and the census turned opinions into counts: which documents were
   opened, which commands were ever invoked, which nudges were ever acted on, how many hours went where.
3. **It is the same shape as this project, one size up.** One operator, agents doing the building, a
   laptop doing long network work, one SQLite file, a local operator surface. The scale, the fleet, the
   embeddings and the evaluation-leak lessons do not transfer. The integrity, migration, silent-failure,
   two-producer and agent-behaviour lessons transfer almost verbatim.

---

## 3. Its harness, in four parts

*The harness had one organising principle — "capture is reliable by mechanism, not by anyone
remembering" — instantiated in four cooperating layers, each of which solved a problem the others
created. Each part below gives how it worked, what it cost, what the evidence says it achieved, and its
characteristic failure.*

### 3.1 Memory and context loading

**How it worked.** Context survived in four mechanisms split by *scope and load-timing*, not by topic: a
parent instruction file holding rules shared across projects; a per-project instruction file holding
read-order and rules; a per-machine automatic memory store (a one-line index plus per-topic files)
holding operator judgement that existed nowhere else; and the in-repo durable documents. The first three
are always loaded; the fourth must be read. That asymmetry *is* the design — always-loaded space is the
scarce resource, so everything else has to be reachable rather than present. The memory index's entries
were deliberately **routing hooks** ("what this is and why you would open it"), never summaries, under a
hard byte budget, with a standing write gate: *never save what the repository already records; point at
a document for any number that can move.* Five hooks sat on session boundaries: session start,
pre-compaction, session end, pre-tool-use and post-tool-use. A script archived session transcripts so
they could be searched after the client's own retention window.

**What it cost.** The smallest editing bill of the three document-facing layers and by far the largest
*context* bill (§ 5.2): an always-loaded instruction layer measured in tens of thousands of tokens
before any work began, multiplied by every non-fork sub-agent, plus a comparable block of authored
routing metadata in the topic files — for a recall path that did not exist.

**What the evidence says it achieved.** Memory outperformed every other channel in the harness. 176 of
211 memory files were referenced at least once by agent-authored text; **no memory was ever observed
being overridden**; and the single largest behavioural intervention in the whole corpus is a memory, not
a hook — an agent refused to overwrite 49,343 shared files because the go-ahead had come from a peer
session rather than from the operator. A second delivery channel mattered as much: 77 memories were
pasted into dispatched sub-agent briefs, which is how a discipline reached a context that never
auto-loaded it. The memories that changed behaviour were **standing prohibitions and epistemic
disciplines**; the ones that got *opened* were operational facts expensive to rediscover. Those are two
different jobs.

**Its characteristic failure: write-mostly and unreachable.** The recall mechanism the design assumed
did not exist — topic files are not loaded at startup, and there was no description matching, no
embedding, no semantic surfacing. **127 of 166 files were reachable only through a second-tier index
that had been opened 6 times in 629 sessions.** The two-tier split optimised against a budget that was
never binding: the always-loaded index used 42 lines and 6.8 KB of a 200-line / 25 KB limit, so those
127 files were demoted into invisibility to reclaim context that was never scarce. Three further defects
cluster here: the memory store was keyed to the repository *path* and not in git, so merging two
repositories stranded ~58 files silently; the export script mirrored deletions until it was fixed to
add-or-update only, having nearly committed away a day-old operator directive whose substance survived
nowhere; and its
restore path counted files copied rather than asserting completeness, which produced a live failure
found the day after the final commit — a path containing a space or an underscore made restore write
into a directory nothing reads **and exit 0**. Finally, obedience without freshness is its own failure:
two memories that were obeyed were stale, and both produced near-misses.

### 3.2 The documentation system

**How it worked.** Capture routed by **shape, not judgement**: an architectural decision to a decision
record, a calibrated number to a calibration register, a data bug to the issue register, a harness fix
to a fix log, deferred work to a backlog, each session's changes to a session changelog. Two maintenance
rules kept the prose from lying: an update policy declared per document class (append-only for logs,
registers and journals; prune-stale for routers, status and specs), and *a fact changed in one place
propagates to every mirror in the same pass*. Counts were generated, never typed, marked with a
derive-live tag naming the command. Every figure that could move had **one home**, and every other
document pointed at it. Documents carried a `last-verified` line with an honesty clause naming what had
*not* been re-checked. A router table mapped "question a reader has → path", checked by a lint. Agent
reports were separated from curated documentation in their own tree. Two documents held negatives: one
for killed approaches (a build-time "do not rebuild" check) and one for refuted beliefs and numbers (a
measurement-time "do not re-quote" check) — separated deliberately, by *consumption moment*.

**What it cost.** Four fifths of all harness maintenance time, and within that a single dominant line
item — the session changelog plus pre-compaction handoffs, a top-three harness mechanism in 8 of the 10
measured weeks (§ 5.2). The document tree also grew into an obstacle to its own answers: "superseded
answers outnumber current ones by roughly two orders of magnitude", and the corrective was itself a
document — a 67-line file whose whole job was to say which eleven of roughly four thousand documents
were current.

**What the evidence says it achieved.** The register layer is why the corpus is auditable at all:
roughly 2,900 issue-register references, 950 decision references and 370 fix-log references are embedded
directly in the Python, so you can grep a number and find the incident or decision that justifies the
line. The registers split cleanly on use, and the consulted ones were consulted repeatedly (§ 5.5).
Routing by shape held — across 459 combined register entries, exactly **one** had to cite the taxonomy
decision to justify its classification, and the boundary was never once deliberated in the transcripts.
And the derive-state rule, where it was applied, held: hand-editing the generated headline was forbidden
and the health command failed on drift.

**Its characteristic failure: the second copy.** Every documentation artifact a machine checked stayed
true, and every artifact only a convention checked drifted. The per-module document sets are the
cleanest natural experiment: **three of eleven module prose READMEs drifted into actively misleading
territory while the machine-readable manifest beside them stayed correct in every one of those three
cases.** The router itself grew to 72,394 bytes and 205 rows, with rows running to full paragraphs, and
it sat in the fed-but-rarely-opened group (§ 5.5) — "a router that grows becomes another thing to
search", as a sibling document in the same corpus warned. And freshness became a declaration rather than
a fact: the tree was, by its own words, "kept honest about being stale rather than actually current".

### 3.3 Enforcement: guards, gates, ratchets, hooks, lints

**How it worked.** Twenty-nine guards were registered in a blocking tuple (twenty-seven blocking lints
plus two advisory by design, plus an in-process contract check: twenty-eight checks that actually
block). Structural invariants were held by lint **ratchets** with shrink-only per-file baselines, which
is what let the debt be called "known and bounded" rather than "unknown". A documentation checker held
roughly sixty-four checks that *check but never edit*, so staleness could not hide while document edits
stayed agent-driven. One health command answered "is everything current?" and a second sweep asked "is
anything slipping?". Five design rules were derived by auditing the estate rather than assumed, and they
are the single most valuable thing in the corpus:

1. **A guard that scans the whole tree for a structural shape earns its keep; a guard that polices a
   hand-maintained list does not** — because the curator is also the enforcer. Corollary: key on the
   **invariant**, never on a surface token.
2. **A gate that cannot fail is not a gate.** Every gate ships a constructed-bad-state positive control.
3. **The marker window is part of the contract.** A check a comment rewrap can defeat measures
   formatting, not risk; justifications belong in syntax.
4. **Probe each item the way a real record would present it.** A guard's input shape is part of its
   contract.
5. **Assert on the artifact the user receives, and never let two guards mandate contradictory truths.**

Plus an admission test before adding any guard — structural shape or hand-maintained list; can you watch
it go red; is the class recurring; does an existing guard cover it with a widened rule, because
**widening beats adding**.

**What it cost.** Cheap to maintain and expensive to get wrong. Enforcement was the smallest of the
three harness buckets by editing hours (§ 5.2), but the ratchet lints ran to more lines than the
delivery path they protected (§ 5.1), and the real cost was suppression that only ever grew (§ 5.4).

**What the evidence says it achieved.** One mechanism in the whole harness reliably redirected work, and
it is the one that **blocked a push**: when a gate blocked, agents overwhelmingly treated the finding as
their own debt and fixed it, with no guard ever disabled and no baseline re-baked to swallow new debt
(§ 5.3). Against that, every warn-only channel was read and walked past. Two lints have repeat
attributed post-birth catches — an unreachable-code lint (one of its catches blocked a push on a real
routing mis-scoring defect) and a silent-exception lint — and one documentation-integrity check caught
real drift on its own first run.

**Its characteristic failure: detection outgrew remediation, and the checks lied about themselves.**
Roughly half the estate registered clean and never fired; one guard was self-serving, its only two reds
both closed by adding a registry row while the motivating defect stayed live (§ 5.4). The commonest
self-defect was a **dead scope fence** — one lint "reported a clean 138-site baseline while never
opening 138 files". And written was not installed: the push gate was version-controlled, documented and
tested for fourteen days
before it was ever installed, and its test "passes against a hook whose entire body is `exit 0`, because
the comment text alone satisfies every assertion". Three lints sat unwired for seven weeks, twenty-nine
days and twenty-one days; three of five global session-end hooks were never registered at all; five
lints existed on disk in no gate. And enforcement sat on a clock rather than on the operation: the
project's own last operator-flagged learning is *"move enforcement to the operation boundary —
event-triggered at the op it protects — not a clock or a human's memory"*.

### 3.4 Agent discipline and collaboration

**How it worked.** Panels were the standing method on high-stakes questions — diverse lenses, an
explicit refute mandate, independent verification — **stacked**, so a later round was aimed at the
earlier round's conclusion, and made a *requirement* rather than an occasional extra after a claim
citing evidence that never existed reached the operator twice. Zero-context agents were dispatched after
any structural change. Sub-agents were read-and-investigate shaped; writes stayed in the driving
session. Parallel and dispatched sessions were required to **stage only**, with one integration thread
doing all the committing. Every dispatched agent got a written brief with a fixed set of headings and a
hard rule zero ("never commit"). Every number a sub-agent produced was re-derived. And the human was the
other half, named precisely: *"the model's characteristic failure is confident-wrongness it cannot
self-detect … while the human brings domain intuition and a felt sense that something is off"*, ending
in the sentence that is the most quoted line in the whole corpus — **"the operator's corrections
mattered more than the operator's approvals."**

**What it cost.** Panels are not free and not self-correcting. A same-model three-agent panel reinforced
a keyword bias in a labelling gold set; the fix was the operator's independent blind pass plus an outside
review, and the repaired agreement statistic went *down* (0.635 → 0.559 → 0.519), with "the lower number
is the honest one". Parallelism cost real coordination at the concurrency levels in § 5.1 — including
nine recorded events where one session took a singleton listener from another, and the operator's own
"I put 12 commits on main today while it worked — my velocity was the problem, so I stopped."

**What the evidence says it achieved.** This is the most concretely evidenced practice in the corpus.
A four-lens panel caught a false headline, and an independent verification *of that panel* caught that
the panel's own correction was partly circular and found two items it had missed. A ten-agent panel
found two of five "actionable" research levers were already banked negatives — "the adversarial pass
paid for itself by preventing two re-builds of already-killed work". Five adversarial review lenses run
*before* the architecture guide was drafted found four whole missing subsystems and corrected several
numbers; two verification agents then confirmed sixteen of sixteen load-bearing claims. And
re-grounding 120 review-comment labels in the real threads and the real source flipped 34.8% of them
(16 of 46), cutting across panel-unanimous, spot-check-ratified and operator-adjudicated labels alike.

**Its characteristic failure: the method worked when it was a requirement and failed when it was
occasional.** The operator's own reframe: *"our agentic reviews keep catching these … the method works;
the failure was running it occasionally / after-the-fact instead of as a requirement."* The rule that
follows is the one this project adopted verbatim: **the operator should never be the first to question a
load-bearing claim.** Two structural hazards travel with it. Same-model agreement is not corroboration —
"N same-model build-agents are correlated". And doctrine is not behaviour: worktree self-isolation
before editing was mandatory, with a one-step launcher, and measured usage was 7 of 264 sessions (2.7%),
while the *other* half of the same doctrine — "conflict-gated, not count-gated, about five sessions
comfortable" — matched measured behaviour almost exactly.

---

## 4. What failed, and why

*Eleven failure classes, each stated as a mechanism rather than a symptom. The one-sentence lesson the
project drew about itself is that almost every expensive failure was a number, label or field that was
real but measured wrong, scoped wrong, or asked the wrong question — not a broken algorithm.*

**1. Silent failure, the governing class.** The mechanism is always the same: an operation that produces
nothing returns the same signal as an operation that produces everything. Concretely: an empty table
read through a left join as "absent" rather than "missing", so a half-built database promoted to live
looked healthy; twenty-two `except Exception: pass` blocks swallowing exactly the errors the monitoring
existed to surface; filters failing *open* on malformed input; a truncated scan reporting a clean
partial; per-item parse failures counted by silent-failure counters that themselves all read zero
because the swallow paths never incremented them. The worst case is the shape a collector reproduces
exactly: **a total wipe was the maximally green run that harness could produce.**

**2. A rule written in prose does not execute.** The sharpest sentence in the corpus is that *a rule
written in three places was violated for months and obeyed from the moment it became a hook*. The
mechanism is that an advisory channel imposes no cost for ignoring it, so it is ignored at a rate that
does not depend on how good its content is. The measured form of this is § 5.3.

**3. Unfalsifiable gates.** Nine of about twenty audited gates could not fail. The mechanisms vary and
are all worth recognising: a write-ahead-log guard asking a connection opened immutable for its journal
mode, which could never report the mode it was checking; a comparator whose 541-entry history was
entirely test artifacts, so the live table could fall from 2,086,542 rows to 457,500 with nothing going
red; a recall gate whose baseline was frozen 27 seconds before its own run, every delta exactly 0.0, and
that green sat cached as its verdict for 34 days. The remedy is the second design rule, and the archive
pass extended it: the positive control must be planted **inside the guard's own scope fence**, because
the commonest self-defect was a scope path that had stopped existing.

**4. Guards that lie about themselves.** Beyond a dead fence: two guards on one field mandating
*opposite* nouns, both green for the whole period the delivered line printed the wrong quantity —
"contradictory contracts that never meet are worse than one guard, because the pair reads as double
coverage while guaranteeing nothing". Marker checks keyed on a one-line lookback, found six times in a
single day across two machines working independently, because the obvious way to write one is a one-line
lookback: *the check did not fail because code changed, it failed because a comment got longer.* And
binding tests pinned to a live defect, which argue against their own remediation — four instances in one
day, including a test requiring one call within 2,000 characters of another and measuring 2,392 after
someone added a comment. Rule: **assert what the code must do, never how it is written.**

**5. Narrated state.** A number typed into prose is a lie waiting to happen, and the mechanism is
arithmetic drift: the headline test count was silently off by 57 because it was maintained by adding to
the previous figure. A derive-live *marker* is not a derive-live *gate*: one command count carried the
marker and still printed 48 when the live count was 52. Three current documents stated three different
sizes for the same documentation gate. And a status claim with no commit, test or output behind it is
the same failure in the tense that matters most — a past-tense claim about work that had not happened.

**6. Two producers of one record.** One conceptual constant held as a literal in six or more producers:
a bump updated some and 825K rows were stamped a stale version. The same anti-pattern shipped production
bugs four separate times. A "fat" path and a hand-maintained stub path emitting the same record drifted
four times — 50K of 53K sidecars silently missing fields in one instance, and in another a column left
NULL on every row while every internal gate passed (§ 7.1). Two text builders for one artifact drifted
latently. The mental model that causes it is stated exactly: *"it's just one thing, how could it
drift"* — which is why it drifted. The rule that followed: **before adding the second usage of any
constant, factor it into one home.**

**7. A correction in a document is not a correction in the code.** A metric was correctly relabelled in
a document while the scripts kept emitting the old label — and inverted the bound — for weeks
afterwards, on the operator-facing surface. Propagation is not optional and it does not stop at the
prose layer.

**8. Tests touching live data.** Twice. First, tests stamped phantom process ids into the *live* state
file. Then an integration test with a two-item temporary data root silently overwrote the real corpus
index, because **reads honoured the test root and writes did not** — caught only by a floor test on a
derived artifact, not by anything designed to catch it.

**9. The harness outgrew the product.** Roughly 270 documents and 74 decision records accumulated before
code moved; once attention shifted, modules relocated within a day. About 12% of commits were pure
process-state churn the project's own rules forbade; documents outnumbered code commits about 1.5 to 1
and test commits about 10 to 1. The operator's frustration was the governing signal — *"we're spinning
wheels — real work, not analysis"*, *"you keep asking me to commit — stop"*, *"is the overhead worth
it?"* — and that last question was left honestly open, because there is no counterfactual. The measured
share is § 5.2; the important framing is that every adopted counterweight was an absolute cap while the
failure is a **ratio**.

**10. Documents describing a target state as if built.** The mechanism is that an agent writing a README
from a plan describes the plan. All eleven modules were mid-extraction, so their READMEs described a
public interface that did not exist yet; one cited three different line counts for one file; another
described about twelve files for a one-file directory; a third omitted an entire subsystem. The
precedence rule the project adopted in response — *when the prose and the code disagree, the code wins* —
is honest and is a reading rule, not a fixing rule.

**11. The remedy can cost more than the defect.** A pre-compaction hook was made a hard block on stale
documents and stranded a session that had no command line to run the fix — against a written decision a
month earlier that said "we want remind, not gate", with the blocking machinery left in place and a note
explaining how to enable it. A prose-style guard forced a rewrite of a draft already rendered on the
operator's screen, so every enforcement shipped as a visible near-duplicate reply. Both are the same
lesson: **design the remedy, not only the detection**, and treat "the machinery is here if a future use
case wants it" as a hazard.

---

## 5. What was measured

*The numbers that matter, each stated once, with the pass that is its home. Where two sources give
different figures for the same thing, § 5.8 says so rather than picking one.*

### 5.1 Scale and shape (reviewer digests; the archive pass)

| Quantity | Figure |
|---|---|
| Repository at backup | 4,287 commits; final commit 2026-09-06; history squashed to one root commit on 2026-06-09 |
| Session transcripts | **1,127 files** = 264 top-level + 863 nested sub-agent transcripts; ~1 GB; 406,050 JSON lines |
| Substantive sessions | 249 of the 264 top-level transcripts are under 100 lines (median 27) — scheduled runs that load, drain, log and exit. Real work lives in **15** sessions, five of which carry most of it |
| Store | one SQLite database, ~36 tables + 8 views, ~815 lines of DDL; the crash store grew 574 GB → 747 GB |
| Corpus | ~1.5M raw crash events → ~85K distinct crashes; ~49K bugs; ~85K pull requests; ~230K review comments |
| Code | ~680K lines of Python; tests 47% of all authored source lines; ratchet lints 16,373 lines against a 15,450-line delivery path |
| Concurrency | 4+ concurrent top-level sessions on 39 of 69 days (57%), peak 8, mode 5; only 9 single-session days; up to 256 sub-agents under one parent |

### 5.2 What the harness cost (the time-and-workflow finding, ten weeks)

604.9 measured active hours, of which **158.4 (33.6%) went to maintaining the harness rather than the
product**: documents 127.9 h, memory 22.7 h, enforcement 7.7 h (agent reports 25.1 h and unclassified
108.4 h sit outside the ratio). Weekly harness share ran 25–42% with one low outlier at 11% and one
final week at **56.3%** — the only week where harness work outweighed product work. The single largest
mechanism was the session changelog plus pre-compaction handoffs at **~49.1 hours**, 31% of harness time
and 8% of all active time. A second instrument, measuring bytes rather than hours, names a different
winner: ~41,592 tokens of authored routing metadata for a recall mechanism that does not exist — "the
largest single block of wasted authoring effort in the system" — plus one style rule duplicated across
four instruction files at ~1,525 tokens every session while already being enforced by a hook.

### 5.3 Detection versus remediation (the transcript-behaviour pass)

Every detection half fired; every prescription half was inert.

| Channel | Fired | Acted on |
|---|---:|---:|
| Compaction sweeps | 151 | carry-forward referenced in **1 of 9** sessions; a mechanical audit of the following turns found **zero** follow-through |
| Post-compaction re-orient command | nudged 9 sessions (151 fires) | **0** |
| Memory-consolidation command | nudged 144 | **0** |
| Worktree-integration command | nudged 130 | **0** |
| Stale-documents warning → its remediation command | 5 loud warnings | **1** invocation in the whole 264-transcript corpus |
| The one remediation that is a plain shell command | nudged 43 | **8** |
| Gate reds (a blocked push) | 236 across 6 sessions | **24 of 26** episodes fixed rather than bypassed; zero disables, zero re-bakes |

Four session-end signals were cut in one commit as "90% of all noise", measured across 629 transcripts:
19,274 fires across 43 sessions; 14,422 fires across 527 of 629 sessions with "0 of 10 genuinely stale
today"; 13,187 fires across 20 sessions from a check that compared a lifetime count against one
session's output and so "could never clear". The three signals kept, for cause, fired in **1, 3 and 5**
sessions out of 629. Separately, one tripwire was retired with "238 fires and zero true positives across
640 transcripts". And a pre-compaction critical subset produced **140 reports and zero failures ever**,
with the same finding 130 of 151 times — a threshold sitting below the normal working state, which is a
steady-state readout, not a detector.

### 5.4 Guards (the guards record; the archive pass's two audits)

14 of 29 registered clean and never fired. 1 was self-serving. 2 lints have repeat attributed post-birth
catches (five and two respectively). **6 of 28 checks had a defect found in the check itself while
reading clean** (the unfalsifiable-gate count is in § 4). At least half of reconstructable red-to-green
transitions were closed by editing the test; 555 of 795 test files (69.8%) have neither gone red in 36
recorded runs nor been named in a register entry. Only **1 of 22** guards pointed at the surface a human
actually reads. When reds were classified by cause: 30.5% were pins on exact counts over legitimately
moving data, **29.7% was the harness policing its own conventions**, 12.1% machine state, and 27.6%
candidate product defects; 41% of the commits touching only test files were the guard machinery catching
the guard author. Suppression: 2,250 grandfathered entries across 13 files, the largest holding 1,319
against 2 documented real defects, and of 18 such files only four ever shrank — two of those because
debt was actually paid.

### 5.5 Documents and registers (the usage census)

- **572 of 783 curated documents (73%) were never opened** with the read tool in the captured window;
  536 show no activity at all. Four named meta-documents about how to run the harness show zero reads
  *and* zero writes.
- Read-to-write ratios split the register set cleanly. **Consulted:** the decision record 15:1, settled
  negatives 4:1, the results ledger 2.6:1, the breakage-pattern catalogue 1.7:1, the guard-rationale
  document 1.5:1, the issue register 1.4:1. **Fed and rarely opened:** the session changelog 0.44 (and
  the heaviest-touched file in the set), the backlog 0.66, the script manifest 0.35, the doc router 0.33,
  the compound-insights file 0.25. One named register was never touched at all.
- Genre read rates: the journey narrative (4,326 lines across eight files) was read in 7 of 1,201
  sessions (0.6%), the least-read genre measured; the per-module governing document in 10 of 1,201
  (0.8%); the architecture guide in 50 of 1,201 (4.2%) and its companion set in one session in
  seventy-five. Of the architecture guide's 18 recorded reads, **one was top-level and seventeen were
  inside sub-agent transcripts**.
- The natural experiment on intent documents: a document fusing product intent with the live phase plan
  was the fourth most-read document in the whole universe (75 reads, 134 writes, 71 commits); a document
  holding **intent alone** shows 0 reads and 0 writes. So does the document describing the project's own
  working method — whose content was among the most valuable in the corpus, and whose single rewrite cut
  it from 550 lines and corrected **31 claims verified stale in that pass**.
- Session handoffs: 46 of them, independently converging on seven headings; consumed at most once each
  and often never (24 reads against 108 writes across 42 files). What was actually read was the resume
  breadcrumb pinned at the top of the changelog — present in 427 of 1,201 sessions (36%) — while the
  1,381-entry, ~6.2 MB body beneath it is what cost the 49 hours.
- Agent reports: at the one deliberate retirement pass, **713 cited against 2,487 orphaned (22%/78%)**.
  The policy was then corrected five times by measured problems, the worst being a shipped index naming
  584 files of which only 36 were tracked — **93% of its own entries unopenable by a recipient**.
- Documentation overwhelm has two dates: the first delegated census and a 26-item judgement queue at
  **~120 files in one repository**, four months before the tree reached its peak. The honest answer to
  "when did the curated set stop fitting in your head" is the earlier one — and the binding constraint
  was never the corpus count but the always-loaded slice.

### 5.6 Commands and memory (the archive pass)

52 commands defined; **50 were never invoked as a slash command anywhere**; combining literal invocation
with direct file reads, only 10 of 52 show any evidence of use. The client's own usage counter,
recovered from disk, records **197 invocations across 17 distinct names in five months**, and the
single most-used command in the whole project was a built-in. The dispatch command — the central artifact
of the agent-discipline layer — **was never invoked once**, while dispatch waves demonstrably happened;
it functioned as a written playbook followed by hand. Memory: 140 of 174 live files (80%) have zero
logged reads; 51% of all logged reads are one cross-machine handoff file and 19% the index; only 34
distinct topic files were ever read, and 13 of those 34 are on the deliberate tombstone list; 71 of 154
topic files have body text appearing in no transcript at all. The index's own rule caps a routing line
at ~120 characters and 19 of its 20 lines exceed it (mean 275, longest 787).

### 5.7 The measurement culture's own scoreboard (the results ledger)

**13 numbers once believed and later disproved**, and across **192 measured results roughly four in five
did not survive honest re-measurement.** The guards are described as "the machine that produces the one
in five". The headline reversals: a scorer at ~69% accuracy was a train/test leak and was ~3.4% under a
leak-free temporal split; a retrieval recall of ~96.8% was identity-leaked and was honestly ~49.9%; an
area-under-curve of 0.97 was a co-temporal leak and is 0.41 leak-free; a prioritisation model at 0.811
was impeccably measured and answered the wrong question, because its label was "engineering already
filed a bug for it"; two real-but-narrow figures (~2.9% and ~80.5%) were weighed as system-wide and drove
a wrong priority across ~40 documents; one crash-impact count swung 393 → 918 → 2,303 on counting
convention alone; a windowed count that was silently a lifetime total inflated rankings up to ~38×.

### 5.8 Where the sources disagree

Recorded rather than reconciled, because the disagreements are themselves informative.

| Quantity | The disagreement | Reading |
|---|---|---|
| Guard count | 29 guards audited versus 22 blocking ratchets named elsewhere — and the top-earning lint does not appear in the 22 at all | Reconcilable if the 29 includes non-blocking guards; the archive pass settles on 28 checks that actually block. Two audits two days apart also differ: 14 of 29 never fired versus 12 of 28 with an attributed catch, because the later one counted the newest cohort's same-week catches |
| Test count | ~17K tests (a reviewer digest) versus 13,005 (the architecture guide) versus 15,386 reported by the daily runner on one day | Different denominators at different dates; none is wrong, and the drift is the point — this is the project whose headline test count was once silently off by 57 |
| Document corpus | ~4,300 / ~4,330 markdown files with ~81% agent exhaust; a tracked tree running 1,160 → 4,286 at peak → 1,005 after a purge → 1,962; a census universe of 838 with 783 curated | The curated figure is quoted as "~700–820" by the project and measured as 783 by the census. Both are point-in-time |
| Router coverage | "138 of 140 routed" (the project's own claim) versus "137 reference documents, 136 routed" (the census) | Adjacent tiers measured on different dates |
| Architecture guide length | 3,385 lines versus 3,380 | Two reads days apart of a live document |
| Were the ratchets in the commit path? | One document said a pre-push hook ran them; two others said the fast gate was not wired into the commit path | **Settled by the archive:** both are true — the hook was pre-*push*, there was no pre-*commit* hook, and a third cited line was written two days before the hook existed. So the widely quoted "the only thing between a regression and the corpus was someone remembering" is stale, and the enforcement story is stronger than the retrospectives suggest |
| Operator hours | "roughly 1,000 hours" as the assessment's framing of the whole practice versus 604.9 measured active hours | Different things: the second is harness-engagement time inside a ten-week transcript window, not the project's life and not hands-on-keyboard |
| Memory corpus size | 166 / 174 / 179 / 211 / 214 files, depending on the pass | A corpus that grew and was consolidated repeatedly; ratios within one pass are safe, absolutes across passes are not |
| Suppressions | 2,250 across 13 files at one stamp; ~2,612 across 18 at the final commit; its own registry quotes 918 with 866 in three lints | Three dates, one direction: up |

---

## 6. What Insight Miner adopted, skipped, and deferred

*The transfer was made with a deliberate bias toward adopting, because the sources are audited failures
with numbers attached rather than opinions — and the adversarial review then measured the cost of that
bias at about a third of the resulting gates. What follows is the settled state, with the ruling dates.*

### 6.1 The day-zero set

Installed because a greenfield project gets these for free, and that is the only cheap moment.

| Adopted | Where it lives here | Ruled |
|---|---|---|
| The five guard design rules and the four-question admission test | `docs/PLAN.md` § Robustness → "Guard design rules"; `docs/runbook/GUARDS.md` header | 2026-09-12 (D-22) |
| A constructed-bad-state positive control per gate, and the verdict vocabulary (earned / earned-at-birth / unproven / self-serving) | `tests/gates/` with a `gate` marker; the `GUARDS.md` ledger; Active rows lacking a control are a ceiling that only goes down | 2026-09-12, scoped 2026-09-13 into three honest classes after the adversarial review |
| Enforcement in the path every change takes | pre-commit on every commit; `make check`; a pre-push stage; hard-block hooks that fail closed | 2026-09-12 |
| Justifications in syntax, never in a comment window | `N-05`: no comment-proximity markers — stronger than the earlier project's fix, which widened the window rather than removing it | 2026-09-12 |
| Zero grandfathering; every suppression printed with file and line every run | `.ratchets/suppressions.txt` at ceiling zero per key, written only by the ratchet tool | 2026-09-12 |
| Derive state, never narrate it | the `make check` block is pasted, never described; counts come from one function with a denominator; the status page is gated against restated counts | 2026-09-12 |
| One home per number; propagate to every mirror in the same change | `CLAUDE.md` § "Every mirror in the same change"; `G34` fails any live line restating a retired claim | 2026-09-13 |
| Separation of append-only learnings from rewritten status | `docs/learnings/`, `docs/insights/` append-only; `docs/recent/STATUS.md` the one rewritten surface, capped and gated (`G45`) | 2026-09-12, capped 2026-09-13 |
| Three registers with a sharp bar, not seven | `DECISIONS.md`, `KNOWN_ISSUES.md`, `GUARDS.md`; everything smaller goes in the commit message | 2026-09-13 |
| A settled-negatives section that rows *point* rather than copy, each carrying its status | `DECISIONS.md` § 3 | 2026-09-12 |
| A router whose rows a script checks, in both directions | `docs/INDEX.md` + `tests/gates/test_doc_currency.py`; routing pointers resolve (`G44`) | 2026-09-12, extended 2026-09-14 |
| Hermetic tests; a guard whose precondition is missing FAILS, never skips | `--block-network`; skip ratchet at zero; runtime-skipped must be zero | 2026-09-12 |
| Test isolation of the data directory, structurally and across the subprocess seam | `G19`: settings refuse the default directory under pytest | 2026-09-12 |
| Claim provenance; the operator is never the first to question a load-bearing claim | `CLAUDE.md` § "Practices carried from the earlier project"; the review pass checks that the cited test asserts the claim | 2026-09-13 |
| Swept-and-clean: a suspicion found to be nothing gets a written home | `KNOWN_ISSUES.md` § Swept | 2026-09-13 |
| Partial findings early, not only finished artifacts | `CLAUDE.md`; workflows emit an interim note after the reading phase | 2026-09-13 |
| Sub-agents tiered by model; nothing inherits the planner's | `CLAUDE.md` § Agent model tiers | 2026-09-13 |
| Memory as an index of routing hooks, with an integrity check and an add-or-update-only snapshot whose restore asserts completeness | `tools/memory_snapshot.py`, `G47` — with the earlier project's two gaps closed at birth | 2026-09-13/14 |
| Nothing in the development gate is advisory | `D-29` — the correct reading of the zero-remediation rows in § 5.3 | 2026-09-13 |
| Installed-ness is a separate fact from existence | `doctor` and `make check` report whether hooks are installed; the settings test requires the registered set to equal the scripts on disk | 2026-09-13/14 |

Four more were carried from the archive pass on 2026-09-13/14 and are worth naming separately because
they were *corrections* to the first transfer: the date-stamped identifier as the default (a
max-plus-one allocator read from a file is the mechanism that produced the earlier project's duplicate
numbers, and staging without committing is exactly the window it fails in); the `last-verified` stamp
adopted as a **writer's** discipline only, with no reader-side alert; the session-start carry-forward
reduced to writing the state and nothing prescriptive; and the never-hard-block rule at any unavoidable
boundary.

### 6.2 The skip list, with the measured cost that justifies each skip

| Skipped | The measurement behind the skip |
|---|---|
| Session changelogs and pre-compaction handoff documents | The single largest harness line item, for at most one later reader per artifact, with a resume mechanism that changed behaviour once (§ 5.2, § 5.3, § 5.5). `git log` is the changelog and `STATUS.md` is the resume surface. Re-confirmed 2026-09-14 against a live compaction: the automatic summary carried the state and the status page had drifted, so the fix was a contract on the status page, not a new genre |
| A standalone document for the project's working method | Zero reads *and* zero writes in the whole transcript window, while its content was among the most valuable in the corpus (§ 5.5). The content became a section of `CLAUDE.md`; the container did not transfer |
| A standalone intent document | The same zero, against a heavily-read version fused with the plan (§ 5.5). Intent lives in `PLAN.md` § Context and as `D-28` |
| The journey narrative and the per-module README/journal set | The two least-read genres measured (§ 5.5), and the module prose drifted while its machine-readable twin held (§ 3.2). The module docstring is the README; `git log` is the design journal |
| Semantic search over the documents | The authors' own words: "a reliability layer, not a rescue … deliberately kept light until real use proves it helps", with one recorded catch in total. At a few dozen documents the query it answers does not exist |
| A second-tier index and authored routing metadata | Effectively inert as a routing surface, for a recall path that does not exist (§ 3.1) |
| A memory read census, and a collision-free number allocator | Machinery built to answer questions a solo project answers by looking. Neither trigger should fire at this size |
| A large slash-command surface | Almost nothing defined was ever invoked (§ 5.6). **A door built but never opened is a maintenance surface pretending to be an interface** |
| The fleet apparatus: a chat bridge, keepalive chain, orphan watchdog | Scoped out by the earlier project itself — "operational topology, not core logic; a rebuilder can run the whole system on one machine and skip this entirely" |
| A prose-style guard | 1,187 detection events and 2,219 violations in 18 days that nothing consumed; 56% of events flagged nothing but ordinary capitalised English, and its own remedy shipped duplicate replies to the operator |
| Grandfathered per-file baselines | Suppression that only ever grew (§ 5.4). This project starts at the measured baseline with no backlog, and a loosening pauses for approval |
| Mutation testing as a gate; a production-scale stress corpus; a runtime schema fingerprint that refuses to run; a launchd dead-man | Cut or downgraded by the adversarial review on 2026-09-13 (`N-10`, `N-11`, `N-13`, `N-12`), each for a stated reason recorded in `DECISIONS.md` |

The adversarial review of the transfer itself cut or downgraded about a third of the ~28 gates and 15
invariants the transfer had produced. **That review is the single most valuable step in the whole
transfer**, and it is the first entry in this project's own candidate canon: a transfer step needs
adversarial review before its gates are built.

### 6.3 Deferred, with the trigger that adopts it

Nothing is thrown away. Each row keeps its birth incident and a trigger that is a recurrence class, a
scale, or a second maintainer — never a feeling that it might be time. The full table is in the harness
assessment § 7; the rows most likely to fire here:

| Deferred | Trigger | First step when triggered |
|---|---|---|
| A measured-results ledger and pre-registered decision criteria | The first number that drives a decision (a coverage rate, a dedup rate) | Three fields only: denominator, operating point, status |
| A blind labelling packet with a pre-registered rule | The first question only Wes's judgement can settle | A stratified, self-contained sample and the pass bars written **before any label is seen**, with "unsure" kept in the denominator and results never collapsed to one accuracy figure. Note the realistic cadence: the earlier project ran this twice in three months, and both runs were accepted without recorded disagreement — so write the rule down cheaply and build no machinery around it |
| A confidence register for heuristic weights | Any output is ranked, scored, deduplicated or filtered by a weight a human then acts on | A twenty-line convention, not a system |
| A do-not-quote lint | A corrected number is actually re-quoted at least once | Key it on the invariant, never a proximity window |
| Parity / syntax-tree lock tests | Two code paths produce the same artifact (a page view and an export assembling the same row) | Lock the key set *and* the value promotion; the earlier project's parity test locked only the key set |
| A delivery-surface guard | The operator surface reads a cached derived value instead of recomputing | Make the trigger a check, not a remembered condition |
| An alert-path delivery canary, plus a genuine-versus-routine alert ledger from day one | The first notification Wes would rely on to learn a run failed | Verify delivery, not that a send returned. The earlier project deleted an alerting path defensibly because its own ledger recorded **zero genuine alerts** across its whole life |
| An interleaved-write probe | Two processes can touch the store at once — a run writing while the operator surface reads | One agent forcing interleaved writes, one verifying invariants afterwards |
| A written architecture guide | M2, when the module set has stopped moving — or sooner if a second person or a plan-less agent must change the code | One capped file with a trust header, a canonical-source table, one diagram, the invariants, what a clone does not contain, and a generated block. Writing it earlier documents a target state, which is precisely the failure that made three of eleven module documents misleading |
| A forward-time "what breaks if I change this" note; a per-domain data-traps page; characterisation pins before splitting a file; a shim guard | Each named in the assessment's trigger table | — |

---

## 7. The database layer

*The database lessons were the first thing transferred and are the best-evidenced, because each has a
dated incident and a row count attached. Most transferred verbatim; a few were reinterpreted because
this store's shape differs; the scale, fleet and embedding lessons did not transfer at all.*

### 7.1 Transferred verbatim

**Upsert semantics.** Never `INSERT OR REPLACE`: it deletes and re-inserts, so row identifiers climb,
delete triggers do not fire as expected, and rows in an external-content search index detach from their
content. In the earlier project this burned **16,813 row identifiers** and then produced a terrifying
false cross-machine divergence alarm — 63,588 against 46,775 — which turned out to be the maximum row
identifier compared against a row count. Two rules follow: upsert with `INSERT … ON CONFLICT DO UPDATE`,
and **never compare unlike measures** when checking two stores for agreement. Here: repository upserts
only, with a primary-key stability invariant (the primary key and first-seen timestamp unchanged across
three reruns of the same input) proven through the real run path.

**Fail closed on unknown values.** A contract loader that returned `True` for an unknown category caused
a 720K-edge drift over weeks. Here, deletion state never defaults to "live", unknown enumerated values
are stored raw and counted, and the scheduling column is `NOT NULL`.

**Population floors and coverage counters.** A column was NULL on all **52,816** rows while every gate
passed; another field was 97% empty because the code read a top-level key that the bulk endpoint
nested; an extractor recovered *zero* real values for about two weeks behind a passing test. Shape
verifiers pass on empty substance. Here: structural population floors per column, and — from the archive
pass — the **across-epoch** form as well as the per-run delta, because a per-run canary catches a field
that *stopped* being populated and only the across-epoch form catches one that was never populated,
which is the likelier failure in a young collector.

**Test isolation is structural, not conventional.** See § 4 item 8. Here: an autouse temporary data
directory, settings that refuse the default directory whenever pytest is loaded, and the same refusal
carried across the subprocess seam.

**One connection chokepoint, and the guard inside it.** The earlier project's write-refusal guard was
opt-in and called by roughly 30 of ~124 writers — and the primary database helper was one of the ones
that skipped it. The fix it reached, and the form to copy, is: **put the guard inside the chokepoint
every writer already passes**, behind an explicit opt-in for the live store. Here, only one module
creates engines (enforced by import-linter and a ruff banned-symbol rule) and a behavioural test asserts
the pragmas on a real pooled connection rather than grepping for them.

**One scrub function.** Deletion scrubbing mutates the content tables, the search index and the tags in
a single call, because two code paths that must agree will not.

**Destructive operations require a recorded verified backup.** A half-built database was promoted to
live, and a partial append wiped 30,000+ rows. Here, a backups table ships in the first schema revision
and every destructive door checks it.

**Never sample when the cheap full scan is affordable.** A verifier sampled the first 5,000 of 5.47M
records and the violation first appeared after row 541K.

**Operational hygiene for long network work on a laptop**, all four adopted: velocity throttling (a
secondary rate limit arrives as a rejection *with budget remaining*, so per-request delays and honouring
the retry header are needed, not just a budget check); advisory file locks rather than process-id files,
because they self-heal on process death including a kill signal; a heartbeat that distinguishes alive
from doing useful work, since a process waiting on a rate-limit reset is alive but idle; and status
messages that post only when something changed. Plus the three-layer answer to a laptop sleeping through
a long run — keep the machine awake for the process lifetime, a patient retry ladder with loud log
lines, and per-item idempotent resume markers. The resume layer is what turned a death 43,651 items into
a backfill from a data loss into ten lost minutes.

### 7.2 Reinterpreted, then verified here

**The external-content search index.** The earlier project's lesson was general — two copies of one
truth diverge silently unless a lock or a parity test makes divergence impossible. Here the two copies
are the content tables and the full-text index, and the mechanism is local and was verified empirically
rather than inherited: live-only views with gated triggers on the base tables; index membership counted
from the size shadow table, because a plain count over an external-content table can never go red; and
an integrity check that actually exercises the index. Two of the three findings from that verification
corrected the plan's first draft.

**Migrations.** Their lesson was a schema version literal copied into six producers, with the seam
between two processes as the number-one hot zone. Here there is one migration head; batch operations
drop and recreate the search views and triggers **inside the same migration**; each migration runs in
its own transaction; a fixture database is kept per prior revision; a golden schema file with generated
column comments is compared on every check; and the runtime fingerprint is derived by one normalizer
from both the live schema and the packaged golden — **never a stored constant**, because a stored
constant is exactly how their literal drifted. A second ordering rule came with it: **the blocking gate
goes last, not first** — theirs was moved after it refused the very imports that would have satisfied it.

**Freshness.** Their axis was the *work list*: a three-week-stale issue list hid 12,560 crash events
while every run reported success, and a fetch chain that was uniformly stale passed every relative
check. The general form is that **no relative check can catch uniform staleness**; their fix was one
live "newest on the server versus newest in the corpus" spot-check. Here it became per-source freshness
tracked separately from run status plus zero-new detection; the live anchor itself was adopted on
2026-09-12 and cut on 2026-09-13 (`N-08`) as spending requests on a rare failure, because this
collector's sweep *is* the live listing in the same run. That is a recorded judgement call with a
prediction attached (P5 in § 8).

**Guard reachability.** Their unit-tested-but-never-called gate became the rule that a post-run
invariant is proven only by driving the real command with the fake gateway planting the violation and
watching the run status flip.

**Ratchets.** Their per-file shrink-only baselines suited a large codebase with a backlog to drain.
Here there is no backlog, so the measured baseline of a greenfield tree *is* the floor, floors are
compared three ways on every check so a stale or hand-edited floor is red, and every move in the wrong
direction is a recorded loosening that pauses for approval. The most likely recurrence here is
"grandfathered forever"; the loosening ledger is the counter.

### 7.3 What did not transfer

Embedding and retrieval lessons, evaluation-gold discipline and leak guards, ownership routing,
per-server object identity after a host migration, upstream cadence rules, and every fleet operation.
The problem class is different: this system stores what a public forum says and tags it with rules the
operator writes; nothing is learned, ranked by a model, or measured against a gold set. Also not
transferred: hundreds of gigabytes making raw data irreplaceable (this store grows 1–2 GB a year, and
deliberate scrub-ability is a requirement rather than a loss), and the multi-machine divergence
apparatus (one writer, one machine). The one surviving echo of the retrieval work is "gated promotion
beats fusion", which here means a tagging-rule change is previewed against the corpus with denominators
before it is saved.

---

## 8. Predictions to score

*Thirteen falsifiable predictions were written on the dates below, each naming the mechanism under test
and the milestone at which it is scored. A failed prediction is a lesson for the canon, not a fault —
and the earlier project supplies the cautionary case: it set one falsifiable prediction with a due date
and never checked it.*

| # | Written | Prediction | Mechanism under test | Score at |
|---|---|---|---|---|
| P1 | 2026-09-13 | At least one positive control catches a gate that would otherwise have passed vacuously | Positive controls in `tests/gates/` | M2 |
| P2 | 2026-09-13 | The suppression ratchet reaches 5 or fewer `noqa` and zero type-ignores, or a loosening row explains why not | The ratchet ledger | M2 |
| P3 | 2026-09-13 | Wes reading seven daily digests against the live source finds at least one mismatch no test caught | User-as-QA | M1d |
| P4 | 2026-09-13 | The primary-key stability invariant never fires in production; if it fires, the upsert rule was insufficient | Upsert discipline | 3 months of runs |
| P5 | 2026-09-13 | Per-source freshness flags a quietly failing source before the operator notices, and uniform staleness — the case the cut live anchor covered — does not occur | The freshness design after the adversarial cut | 3 months of runs |
| P6 | 2026-09-13 | The two-shape parity test fails at least once during early probing | Shape parity | M1b |
| P7 | 2026-09-13 | The corpus stays under about 40 curated documents with no agent exhaust committed, and the currency test is never disabled | Hold the count, for documentation | M2, then quarterly |
| P8 | 2026-09-13 | Lower-tier sub-agent stages rarely need a higher-tier verifier's catch; no class of stage is promoted twice | Model tiers — with a comparison point: the earlier project's measured skip rate for an agent-chosen step was about **one in five** | M2 |
| P9 | 2026-09-13 | The cross-stage workflow layer catches at least one ordering bug the unit layer missed | Cross-stage tests — their first such wave caught three real defects, two of them vacuous tests passing against an empty directory | M1d |
| P10 | 2026-09-13 | The shipped gate count at M2 is at or below the M0 menu, and every gate has a birth incident or is cut at the first quarterly review | Hold the count, for guards | M2, first quarterly review |
| P11 | 2026-09-13 | The compliance canary is never found in a backup or export inside the retention bounds | Scrub plus the retention sweep | M1c, then monthly |
| P12 | 2026-09-13 | The apparatus-to-product ratio (enforcement and test lines against source lines; documents added against modules shipped) falls after M1 and never exceeds its M0 value | Hold the count, measured as a **ratio** — the gap the earlier project's own evidence identified, since every counterweight it adopted was an absolute cap while the failure is a ratio | M1d, M2, then quarterly |
| P13 | 2026-09-14 | With the status-page contract in place, no resuming session re-does merged work | The resume surface, in place of a handoff genre | M1d |

---

## 9. How to use this for the next project

*The order below is by the cost of installing each thing late, not by value — the two differ, and the
earlier project's most expensive gaps were all cheap things installed after the damage.*

**Day zero, in this order.**

1. **A short always-loaded floor: the three to five rules whose late arrival is unrecoverable.** The
   selection criterion is not "important rules" — it is specifically *rules where the rule arriving late
   means the damage is already done*. The earlier project's floor existed because raw data was destroyed
   accidentally twice. Twenty lines. And know which instruction files load *when*: a directory-scoped
   rule file does not load at session start, and for a sub-agent it never arrives at all unless that
   agent reads a file under that directory.
2. **One home per number, with a derive-live check — not just a marker.** The earlier project had the
   marker and never had the gate, and a marked count still printed the stale figure (§ 4 item 5).
   Installing this late means auditing every document already written.
3. **Document classes with declared update policies, and a one-line honest stamp.** Retrofitting means
   re-reading every file to decide which mode it was always under. Adopt the stamp as a *writer's*
   discipline — one line naming what was **not** checked — and build no reader-side alert: five loud
   warnings produced one remediation in a whole corpus.
4. **One register with all five reliability properties**: a sharp binary inclusion bar, a mechanical
   ritual giving each entry a citable identity, exactly one home per record kind, enforcement, and a
   frequent unambiguous trigger. Missing any one, it degrades to disposition-dependent and rots. This
   was *derived* by comparing a register that held for the life of the project against ones that did
   not. Cite the identifier from the code, so a line can be traced to the incident that justifies it.
5. **Mechanise rather than restate — and measure a check's true-positive rate before keeping it.**
6. **The memory index as the recall mechanism** (hooks, never summaries; a stated ceiling; a door table
   routing outward), its integrity check, and an add-or-update-only snapshot into the repository whose
   **restore asserts completeness against a manifest** rather than printing a copy count.
7. **Propagate-to-all-mirrors as a same-pass rule, with a check.** Flagging a stale mirror is not fixing
   it.
8. **The guard admission test and the verdict vocabulary.** Free at day zero; a retrofit otherwise.

**The cheapest moments.** Two things are nearly free once and expensive later. The first is the guard
design rules, which let a project skip roughly half the guards the earlier project built before
discovering they were useless. The second is *ordering*: review adversarially **before** drafting — the
review lenses run ahead of the architecture guide's first draft are what found its missing subsystems
(§ 3.4), and that practice transfers at any size and costs nothing but sequence.

**Wait for a trigger.** The architecture guide (until the module set stops moving), a separate router
file, the consolidation cadence, a measured-results ledger, session handoffs, agent-report indexing, a
methodology document, semantic search, a number allocator. Each waits on a recurrence class or a scale,
written down now so the decision is mechanical later. **Order matters here too**: the earlier project
built its report index and its orphan lint *before* auditing the corpus, and the audit then found that
most of the corpus had never been referenced by anything (§ 5.5).

**The three sentences to carry if nothing else survives.**

- *Every documentation artifact a machine checked stayed true, and every artifact only a convention
  checked drifted — so write only what a check can hold, and generate the rest.*
- *An advisory channel will be read and walked past regardless of how good its content is; if something
  must happen, it belongs at a boundary that stops.*
- *A guard's clean record is not evidence, a red is not a catch, and birth is not evidence — the only
  honest question about a guard is what it has caught since.*

---

## 10. Related documents

*This file is the entry point. The assessments below are its appendices: each holds the full working for
one pass, and each is the home for the numbers this document cites from it.*

**In this repository.**

- `docs/reference/reviews/2026-09-13-harness-assessment.md` — the eighty-mechanism catalogue in four
  parts, each row with its birth incident, evidence, cost, scale-dependence, transfer call and
  confidence; the steelman pass that downgraded thirteen calls, withdrew seven claims and added
  twenty-two missing mechanisms; the adoption-trigger table; the twenty-six open questions.
- `docs/reference/reviews/2026-09-13-harness-questions-answered.md` — those questions answered from the
  archive: nineteen at high confidence, three at medium, one only Wes can settle, three about this
  project. Its § 5 holds the cross-cutting findings and its § 4 the catalogue rows that moved.
- `docs/reference/reviews/2026-09-13-documentation-practices-assessment.md` — the usage census and the
  practice-by-practice adopt / adapt / skip rulings, with the day-one set ordered by the cost of
  installing late.
- `docs/learnings/LEARNINGS_TRANSFER.md` — provenance, what transferred and how it was interpreted, what
  the transfer cost, the predictions of § 8, and how to evolve this genre across future projects.
- `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` — the twenty-six database and process lessons
  ranked by confidence, importance, value and cost, with the declined and scoped items and their
  reasons.
- `docs/reference/reviews/2026-09-12-db-learnings-review-A.md` and `-B.md` — the two reviewer digests
  behind that ranking: a failure catalogue of roughly eighty numbered incidents, and an
  architecture-decision catalogue with the replacement each pain produced.
- `docs/reference/reviews/2026-09-13-adversarial-review.md` — the review that cut or downgraded about a
  third of the gates the transfer produced.
- `docs/learnings/DOC_DRIFT_FINDINGS_2026-09-13.md` — the same drift classes found in *this* project's
  own corpus, written as a scan list any project can run against itself.
- `docs/reference/earlier-project-retrospectives/` — three of the earlier project's own narrative
  documents, kept deliberately and redacted under the redaction note in that folder, plus their index.
  They are the only first-person voice left in the repository; everything else here is analysis of them.
- `docs/decisions/DECISIONS.md` (the 2026-09-13 and 2026-09-14 entries) and `CLAUDE.md` §§ "How this
  project uses its agents" and "Practices carried from the earlier project" — the binding form of every
  adoption in § 6.

**Outside this repository.** An archive folder holds the material that is deliberately dirty: the eight
original retrospective documents unredacted, the repository bundles, the thirteen raw agent findings
behind the archive pass and the census, and the session transcripts with their search index. Its role is
to be the one place where the earlier project's identifiers may exist on this machine, so that nothing
in this repository has to carry them. Read findings there when this document is too thin on a point;
carry their lessons over abstracted, never their names. Its path is recorded in `DECISIONS.md`; it is not
under version control and never will be.
