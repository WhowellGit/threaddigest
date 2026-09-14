# Documentation and memory practices from the earlier project: adopt, adapt, or leave

> **Update policy:** prune-stale — correct in place; this is an assessment, not a log.
> **Status:** draft for the planning session to review and move into `docs/reference/reviews/`.
> `last-verified: 2026-09-13`
>
> **What this is.** Wes's earlier project — a much larger, multi-machine, agent-operated system — evolved
> a documentation and memory system over months and ended with a rich corpus. It worked there, and the
> apparatus also grew too big. This assesses each practice on its own evidence and says whether Insight
> Miner should adopt it now, adopt it at a named trigger, adapt it, or leave it.
>
> **Two systems, kept separate.** Nothing here imports the earlier project's mechanisms, names,
> numbering schemes, check engine, router, or corpus. Only the abstracted practice crosses over, and
> every "Shape here" paragraph names a fresh Insight Miner mechanism. Several say the right answer is
> "nothing". No identifiers from the earlier project appear below; its documents are referred to by
> role.
>
> **Enforcement-first rule.** Every recommendation names what would enforce it. A written rule with no
> mechanical check is labelled **review-only**, which is the weakest column.

---

## 1. How this was assessed, and what the method cannot see

Three passes over a read-only archive of the earlier project, each answering a different question.

**Pass one — the usage census.** Which documents were actually *opened*, as opposed to written and left
alone. A script streamed **1,127 session transcripts** (264 top-level sessions plus 863 nested
sub-agent transcripts; 406,050 JSON lines; zero parse errors) and counted every file-read and file-write
tool call against a universe of **838 documents** taken from the final repository snapshot. It also
pulled git commit counts and file sizes for the sixty most-read documents, and scanned the two failure
registers for sentences blaming or crediting a named document.

**Pass two — the documentation system, read practice by practice.** Twenty-three distinct practices were
identified from the system's own governing documents. Each was assessed for the problem it solved, the
incident that created it, the evidence it worked, the evidence it cost more than it returned, and
whether its value depends on scale.

**Pass three — the guides, read as documents.** The system architecture guide and its ten companions,
the workflow guides and the commands attached to them, the session handoffs and changelogs, the
project-journey narrative, and the per-module document set — each read, measured for size, commit count
and read rate, and compared against what it cost.

Five supporting passes provided the evidence: transcript-derived usage counts; a time-and-workflow
reconstruction; a behavioural pass asking what agents actually *did* when a mechanism fired; a
memory-and-hooks pass; and passes on registers, on documents and commands, and on guards.

### What the method cannot see, stated plainly

1. **Shell-based reading is invisible.** Only the dedicated file tools are counted. The structured
   search tool was invoked **exactly once** across all 1,127 transcripts, which means essentially all
   searching went through shell commands this method cannot observe. **Every read count below is a
   floor, not a ceiling.**
2. **The window is ten weeks, not the project's life.** Tool activity spans a ~10-week period. "Never
   read" precisely means "never opened with the read tool in a captured transcript inside that window".
   Several process documents were demonstrably written and repaired before the window opened, then
   stopped being opened.
3. **Deleted documents are invisible.** The universe was built from the final snapshot, so a document
   that existed and was removed earlier cannot appear anywhere, including in "never read".
4. **The blame/credit tally is a keyword heuristic** over free-text engineering prose, not a labelled
   dataset; its own confidence is low-medium.
5. **The hour figures rest on stated assumptions.** Active minutes are inter-message gaps capped at ten
   minutes, split across buckets in proportion to that week's file-touch counts; almost all measured
   time comes from a handful of long-lived sessions kept alive by scheduled wake-ups, so "active hours"
   means harness-engagement time, not hands-on-keyboard time.
6. **Pass three's counts are upper bounds** — a "hit" means a string appeared somewhere in a session.
   They are comparable to each other, which is what the argument needs.
7. **The two projects differ in working mode, not only in size.** The earlier project ran 4 or more
   concurrent top-level sessions on **57% of days**, peaking at 8, with up to 256 sub-agents under one
   parent. Insight Miner is one operator, one repository, sequential sessions. Where a practice's value
   comes from concurrency, the verdict says so; where it does not, scale is not used as an argument.
8. **The verdicts are judgements.** The numbers are measurements; "adopt / adapt / skip" is reasoning
   over them. Each carries a confidence.

---

## 2. The answer, in one paragraph

The practices worth carrying are the cheap ones that govern **where a fact lives** — one home per
number, derive rather than restate, change every mirror in the same pass, one register with a sharp bar
and an id you can cite from code, a router whose rows a script checks, an always-loaded floor holding
only the rules whose late arrival is unrecoverable, and a memory index whose one-line entries *are* the
recall mechanism, protected by a byte budget, an integrity check, and an add/update-only snapshot into
the repository. Those cost tens of lines each, and in the earlier project every one of them that a
machine checked stayed true while every one that only a convention checked drifted. The practices to
leave are the ones that produce a **second copy of something already true elsewhere**: per-session
changelogs and handoffs (~49 hours, 31% of all harness time, against at most one later reader per
artifact), the journey narrative (read in 0.6% of sessions), the per-module README/journal set (0.8%),
the companion document set (one session in seventy-five), a separate approach document (0 reads and 0
writes in 1,127 transcripts), and every mechanism whose only justification is parallel writers. Between
those sits a third group that is genuinely valuable but not yet: the system architecture guide, the most
expensive document in the corpus and the least-read of the major genres (4.2% of sessions), which
Insight Miner should write once at M2, capped, with its facts generated rather than typed. The single
strongest transferable finding is not a document at all: across 264 transcripts, **every warn-only
channel was read and walked past, and only the mechanism that blocked reliably redirected work** — the
named remediations fired 0 times out of 151, 0 of 144, 0 of 130, and once in the whole corpus. So: write
only what a check can hold, generate the rest, and label any written rule with no check as review-only.

---

## 3. The practices

Each entry gives the practice in plain English, the evidence for and against with numbers, a verdict, a
confidence, and the shape it should take here — naming the file or mechanism and what enforces it.

---

### 3.1 The approach document — "how this codebase uses its AI harness"

**What it is.** One document recording the load-bearing decisions about *working method*, deliberately
separate from the always-loaded operating-rules file and from the register that records decisions about
the code.

**Evidence for.** Its content was genuinely good. Its core was a six-row table mapping each class of
failure to the kind of mechanism that catches it — a recurring bug class becomes a lint, a production
drift becomes a regression test, a decision becomes a numbered register entry, a verifiable fact becomes
a derive-don't-narrate tool, a session boundary becomes a hook, a repeated procedure becomes a named
door — closing with "don't trust judgment to remember; wire the mechanism that makes forgetting loud".
It also holds the sharpest sentence in the whole corpus: *a rule written in three places was violated
for months and obeyed from the moment it became a hook.* And writing it caused corrections — one rewrite
cut it from 550 lines and corrected **31 claims verified stale in that pass**, including two that
asserted checks which had never been built.

**Evidence against.** It was **never opened**: 0 reads and 0 writes across all 1,127 transcripts. It had
no guard and said so — the written trigger was the only guard, "which is why thirty-one claims went
stale between audits". It had to warn itself against growth twice in its own body, and it appears twice
in the earlier project's fix log as the named cause of a problem, once because a duplicated section had
drifted into naming a mechanism deleted 55 days earlier.

**Verdict: ADAPT — keep the content, kill the container.** The value came from the act of writing and
auditing it, not from anyone reading it afterwards. A document nobody opens cannot route behaviour; the
same twelve lines placed where they auto-load can.

**Confidence: high** on the content transferring; **medium-high** on the container being unnecessary
(read counts are floors, but 0 reads *and* 0 writes over four months is close to untouched).

**Shape here.** No `METHOD.md`. The mechanize-don't-restate table becomes a ~12-line section of
`CLAUDE.md` titled "What turns a lesson into a mechanism", beside the "Rules and what enforces them"
table it already rhymes with; the depth stays in `docs/learnings/LEARNINGS_TRANSFER.md` § 6, which is
already the evolving canon and is already re-read at retrospectives. **Enforcement: review-only** — no
check is possible for prose of this kind, and its real guard is the existing enforcement column in the
`CLAUDE.md` rules table, where any row without a mechanical enforcer is visibly labelled "review".

---

### 3.2 Memory

The area with the strongest and most counter-intuitive evidence, in five parts.

#### 3.2.1 The memory index as the recall mechanism (hooks, door table, budget)

**What it is.** One always-loaded index whose one-line entries are the *only* thing that makes a
per-topic memory file findable. Entries are routing **hooks** ("what this is and why you would open
it"), never summaries; the index opens with a small **door table** routing by task; the file lives under
a hard byte budget.

**Evidence for.** The design was measured, and the measurement reframed the system: of **179 topic
files, only 28 had ever been opened, and the "most-read" one had been opened once**. Read correctly,
the value lives in the always-loaded hooks, not the bodies — the hook *is* the memory in practice, and
moving content to retrieval-only would have deleted its influence. Behaviourally, memory outperformed
every hook in the corpus: **176 of 211 memory files were referenced at least once** by agent-authored
text, **no memory was ever observed being overridden**, and the single largest behavioural intervention
in 264 transcripts was a memory — an agent refused to overwrite **49,343** shared files because the
go-ahead had come from a peer session rather than the operator. A second channel matters here: **77
memories were pasted into dispatched sub-agent briefs**, which is how a discipline reached a context
that never auto-loaded it. And the value is *higher* for a solo operator, in the earlier project's own
words: in a team the people hold the context; in a solo human-and-AI project the AI's memory is the only
shared brain.

**Evidence against.** The budget is a cliff, not a guideline — past the ceiling, content **silently
fails to load** — and the corpus repeatedly hit it, once sitting at ~240% of its file ceiling with 112
"owed" markers. Maintaining memory cost **~21.7 measured hours** over ten weeks (18.1 on topic files,
3.6 on the index itself). And obedience without freshness is its own failure: two memories were obeyed
while stale, and both produced near-misses.

**Verdict: ADOPT NOW — the architecture exactly, the size not at all.**

**Confidence: high.** The 28-of-179 measurement points the same way at any scale: build the index as
though the bodies will rarely be opened.

**Shape here.** The index already exists in the project's auto-memory directory with 8 hook lines and 8
topic files, and already follows the hooks-route-never-summarise rule. Three additions: a stated ceiling
of **25 index lines / 8 KB**, written into the index's own first line so the number is mechanical rather
than a feeling; a 3-row door table at the top ("changing the collector? / changing the store or a
migration? / changing enforcement or docs?") pointing into `docs/`, so the index routes outward and not
only into itself; and the standing write gate, stated in the index — *never save what the repo already
records; point at a repo document for any number that can move.* **Enforcement:** the ceiling and link
integrity are checked by `tools/memory_check.py` inside `make check` (§3.2.2). The write gate is
**review-only**.

**One live finding, verified on this machine on 2026-09-13.** There are currently **two** memory
directories holding the same eight topic files — one keyed to a Desktop working directory, one keyed to
`~/repos/insightminer`. The eight topic files are byte-identical, but **the two indexes have already
diverged**: one hook line differs in wording between the copies. The index is the recall mechanism, so
this is the earlier project's number-one drift bug reproduced inside Insight Miner's own memory on day
one. Pick one home, delete the other, and let the snapshot be the only mirror.

#### 3.2.2 The memory integrity check (orphan / dangling / budget)

**What it is.** A small read-only script that fails when a memory file exists but nothing links to it
(unreachable), when the index links a file that does not exist (dangling), or when the index is over
budget — grading the git-tracked mirror rather than the machine-local directory, so it cannot pass by
having no subject.

**Evidence for.** Both failure modes happened, and both are silent. Measured on one date, **127 of 166
memory files were reachable only through a second-tier index that had itself been opened 6 times in 629
sessions**, and **28 index links pointed at files that no longer existed**, repaired by hand in a single
pass. Neither surfaces as an error anywhere: nothing crashes, the memory is simply, quietly, gone. An
independent audit reached the same conclusion from the other direction — the dominant defect was
*effectively orphaned by index structure*, not *memory duplicating the repo*. The check is also what
made a wholesale index rewrite safe: the consolidation procedure required zero unreachable and zero
dangling before export. Its anti-vacuity design deserves copying verbatim: a guard pointed only at a
machine-local directory "silently passes by having no subject".

**Evidence against.** Essentially none — a few hundred lines, read-only, writes nothing. Its one
weakness is that it must actually be run, and in the earlier project it was not a blocking gate.

**Verdict: ADOPT NOW.** The cheapest high-value guard in the catalogue.

**Confidence: high.**

**Shape here.** ~60 lines in `tools/memory_check.py`: every file in the snapshot directory has exactly
one index line; every index line resolves; the index is under its stated ceiling; and — the fix for the
live finding above — **exactly one memory home exists**. **Enforcement:** run inside `make check`,
hard-failing, with a positive control in `tests/gates/` that plants an orphan and an unresolvable link
and watches both go red, matching the convention already required by `docs/runbook/GUARDS.md`.

#### 3.2.3 The git-tracked snapshot, with a completeness assertion

**What it is.** A mirror of the machine-local agent memory into the repository, so it survives a repo
move, a fresh machine, or a reset — with export deliberately **add/update-only**, so one session's
deletion cannot silently propagate.

**Evidence for.** Both halves have a recorded incident. The memory directory is per-user, per-machine,
and keyed to the repository *path*, and is not in git — which stranded roughly **58 memory files** when
two repositories were merged. Then the mirror itself became the hazard: when one session's
reconciliation removed a live file, the next export staged a deletion into the shared index and "nearly
rode into a commit, silently dropping a day-old operator directive whose substance survived nowhere".
That is the origin of the add/update-only default, and it is the specification to copy — not the
original design.

**Evidence against.** One verified gap, and it is the one to close at birth: **restore is never checked
for completeness.** The restore path prints a count of files copied — "a count, not a completeness
check. There is no checksum, no manifest comparison, no 'expected N files, got N' assertion anywhere."
There is also no dedicated positive-control test proving the add/update-only guard can actually fail.

**Verdict: ADOPT NOW, with the earlier project's gap closed at birth.**

**Confidence: high.** This is the one asset in the setup that cannot be regenerated from code or data,
and it currently lives only outside git, in two diverging copies.

**Shape here.** ~60 lines in `tools/snapshot_memory.py` with `--export` (add/update only, never
deletes), `--restore` (never clobbers a newer live file), and `--check` (exit 1 on drift), mirroring
into `docs/memory/` so memory travels with the repository. `--restore` asserts an expected file count
from a manifest line and fails loudly on a mismatch, so "restored" means complete. **Enforcement:**
`--check` in `make check`; a positive control in `tests/gates/` deletes a live file and asserts the
export does not stage a deletion, and corrupts the manifest count and asserts restore fails.

#### 3.2.4 The consolidation pass and its cadence

**What it is.** A periodic reflective sweep over the memory corpus — merge duplicates, make relative
dates absolute, retire what shipped, tighten the index back under budget, verify, export — triggered by
a size threshold rather than by intention.

**Evidence for.** The need is real and was diagnosed honestly: a nudge fired because the index had
tipped over its line limit, "which silently drops the last entries on load", and the cause was
"accretion, not this session's doing … what was missing was a periodic consolidation cadence. Like
garbage collection, it needs a sweep, not a one-time fix." Two techniques were paid for and work:
grouping index lines took an index from **151 to 124 lines, −12% bytes, with zero routes lost**, and a
full pass trimmed **25,151 → 18,773 bytes** via 9 merges, 3 route-outs and ~23 re-points with no entries
dropped and the integrity gate at 0/0. One rule is worth its weight: **a merge is not done until the
source file *and* its index line are gone** — a content-merge that leaves the source doubles the corpus,
which is how one pass grew the corpus by ~45 files instead of shrinking it.

**Evidence against.** The cadence itself rotted, and the project said so: "a manual cadence rots. Decay
must be automated … or it becomes a New Year's resolution." The mechanisation to fix that was still owed
at archive time. The consolidation procedure's own definition file was opened **exactly once in 1,127
transcripts**; the corpus grew back to **214 files** after consolidation; and — the sharpest number —
the session-start nudge recommending the consolidation command fired in **144 sessions and the command
was invoked 0 times**.

**Verdict: ADOPT AT A NAMED TRIGGER — and make the trigger mechanical, not a calendar.** The trigger is
the integrity check reporting the index over its ceiling, or the memory directory passing 20 files.
Until then, consolidate inline at write time: the write gate ("search for an existing file that covers
this and update *that*") does the same work with no ceremony.

**Confidence: medium-high** on the trigger form; **high** on the two rules to carry (a merge is not done
until the source and its index line are gone; tighten hooks rather than thinning bodies).

**Shape here.** No custom code — when the trigger fires, run the packaged consolidate-memory skill, then
`tools/memory_check.py` and the snapshot export. **Enforcement:** the trigger is mechanical
(`tools/memory_check.py` fails the build when the index is over its ceiling, which is what forces the
pass). The pass itself is judgement work and is **review-only** by design; a script that edits memory
automatically is how the earlier project lost files.

#### 3.2.5 The memory read census

**What it is.** A script that scans transcripts for reads of memory files and logs them durably, so
"which memories are ever opened" survives the transcript retention window.

**Evidence for.** It produced the single most consequential measurement in the memory evidence — the
28-of-179 figure that reframed the whole design. It also caught a **3× counting error** in a prior
hand-measurement: a naive scan reported 532 reads where the true count of distinct tool calls was 179,
and a widely-quoted headline had been inflated by that factor.

**Evidence against.** It is machinery built to answer a question you can answer by looking when the
corpus is eight files, and it was built against 629-session-scale data. Its own docstring states the
limit that matters: it "measures RECALL (was the file opened), never USEFULNESS (did opening it change
the answer) … Treat a zero-read file as a routing question and a read file as unproven, not as proven
value."

**Verdict: SKIP the machinery; the *finding* is what transfers.** Build the index as though the bodies
will rarely be opened, because in the one project where this was measured, they were not.

**Confidence: medium-high.** What would change it: if the memory corpus ever passes ~30 files, a
five-line shell command over the transcript directory answers the same question without a script.

---

### 3.3 Routing for agents and sub-agents

Four distinct mechanisms that are easy to conflate.

#### 3.3.1 The router (question → file)

**What it is.** One table whose every row is "question a reader has → path", so a reader can tell what a
document is for without opening it, with a standing rule: when you add a document, add a row.

**Evidence for.** It works as an intent surface — each row's question *is* the document's purpose,
readable without opening it. Extracting the table out of the always-loaded instruction file made that
file **~31% lighter**. And it reached measured completeness on the tier it covered: **137 reference
documents, 136 routed, 0 unrouted, 0 dangling**.

**Evidence against.** Three costs, and together they are the clearest "grew past its value" case.
(a) **It was fed, not read**: **9 reads against 27 writes**, a 0.33 ratio, among the lowest in the entire
register set. (b) **It grew into the thing it replaced**: **72,394 bytes and 205 rows**, with individual
rows running to full paragraphs — while a sibling document in the same corpus warned that "a router that
grows becomes another thing to search". (c) **Its coverage rule was unguarded outside one directory**:
all ten documents in the architecture folder had **zero** router rows — "the gap is total, not partial".
The counter-example is instructive: a second, deliberately tiny router of **67 lines**, whose whole job
was to say which eleven of roughly four thousand documents were current, did more work per byte than the
205-row table.

**Verdict: ADAPT — already adopted here, and already in the better form.** `docs/INDEX.md` is the
router, it is 90 lines, and `tests/gates/test_doc_currency.py` checks it against `docs/**/*.md` in
**both** directions — which closes the exact hole the earlier project left open.

**Confidence: high.**

**Shape here.** No change to the mechanism; one rule added to the `INDEX.md` header: **a row is one
line. If a row needs a second sentence, the sentence belongs in the document it points at.** The current
"Documents in this corpus" section already has multi-line entries, and that section is the seed of the
205-row failure. **Enforcement:** extend `test_doc_currency.py` with a row-shape assertion and a total
cap (~120 lines) on `INDEX.md`, so growth fails the build rather than being noticed at a review.

#### 3.3.2 The "read before you touch" table

**What it is.** A different mechanism from the router, and the earlier project conflated them once: the
router is a lookup you consult when you want to *find* something; this is a lookup keyed by **what you
are about to change**.

**Evidence for.** This is the genre the census says was actually consumed. In the sixty most-read
documents, a striking number of rows have **zero top-level reads** — every recorded read happened inside
a dispatched sub-agent's transcript. Those are documents an investigating agent was *told to consult*,
not documents the operator or main thread ever opened. Separately, of the 1,702 recorded reads landing
on the 838-document universe, roughly **three out of four** read calls in the whole archive were on
something other than a document. The reading that mattered was targeted and instructed.

**Evidence against.** It is a mirror of the guard and document lists, so it inherits the mirror-drift
tax (§3.9). The earlier project's registers blamed its always-loaded instruction file **18 times** and
credited it once — which, read together with that file being among the most-consulted documents in the
tree, says "load-bearing and therefore worth fixing fast" more than "unreliable", but the drift is real.

**Verdict: ADOPT NOW — in place, and the highest-value routing mechanism of the four.** `CLAUDE.md` §
"Routing: read before you touch" already has 9 rows.

**Confidence: high.**

**Shape here.** Keep it, and add the one row the evidence says is missing: *"Dispatch a sub-agent →
§3.3.4's brief template."* **Enforcement:** every path named in the table must resolve on disk — a
ten-line extension to `test_doc_currency.py`. This is the check the earlier project explicitly
recommended and never built ("a lint that resolves each document's code-path bullets against disk …
recommended as a register item, not built here"), and it is the guard that would have caught all three
of its actively-misleading module documents. Build it.

#### 3.3.3 Path-scoped rules and the always-loaded floor

**What it is.** Knowing which instruction file actually loads *when*, and putting the rules whose late
arrival would be unrecoverable in the layer that is always present, with the mechanics in a deeper
manual that loads on demand.

**Evidence for.** The most transferable single mechanical insight in the archive, and it was verified by
an agent inspecting its own context: a subdirectory instruction file does **not** load at session start,
and for a sub-agent it does not arrive until that agent reads a file under that directory — "every
decision made before that first read, including a shell call that deletes something, is made without
it, and if a task never reads a file there it never arrives at all". The four rules promoted to the
always-loaded floor were all irreversible-action rules, and the first records its incident: **raw data
was destroyed accidentally twice**, so deletion had exactly one sanctioned tool and no ad-hoc shell
removal — and because the write gate was opt-in and could not catch a caller that skipped it, "this
rule, not the gate, is the protection". The split held: 121 lines of routes and hard rules always
loaded, against a 513-line manual loading on demand.

**Evidence against.** Almost none. The optional per-module instruction files the system allowed were
**never created once**, which the project correctly read as the lazy-creation policy working rather than
as a gap.

**Verdict: ADOPT NOW.** Partly in place: `CLAUDE.md` is 108 lines and holds the rules table, but has no
short *arrived-late* block — and the criterion for that block is not "important rules", it is
specifically "rules where the rule arriving late means the damage is already done".

**Confidence: high.**

**Shape here.** A 4-line block at the very top of `CLAUDE.md`, above the rules table, on that criterion.
Candidates here: never write to or delete the live SQLite store outside the sanctioned backed-up path;
never start a bulk collection pass without an explicit go; never background a long collector run in a
session-bound watcher; never rewrite git history. **Enforcement:** each line names its enforcer. Two
already have one (the destructive-operation gate inside the service, and the hard-block hooks in
`.claude/settings.json`); the other two are **review-only** until a `PreToolUse` matcher covers them,
and the block should say so on the line itself. The session-hygiene fact already recorded in
`docs/runbook/RUNBOOK.md` § 1 — project hook settings load only from the session's *starting* directory
— belongs in this block too, because it is the reason a hook can be never-loaded rather than
never-fired.

#### 3.3.4 The context packet for sub-agents

**What it is.** A standard brief handed to every dispatched agent: context, what to read first, scope,
acceptance criteria, what not to do, the integration ritual, and safety.

**Evidence for.** This is where routing actually bites. **77 memories were embedded in dispatched
sub-agent briefs** — described in the evidence as the strongest form of propagation, because it makes a
discipline binding on a context that never auto-loaded it. Several disciplines reached agents *only*
this way: one memory was propagated into five briefs across two sessions, another into sixteen. The
brief also carried a hard safety rule as its rule zero — a dispatched agent never commits; it stages,
and the driving session commits in batch — plus a prohibition on editing shared registers directly, with
per-branch deltas the driver merges. That staging rule is also the cheap answer to number collisions
(§3.7).

**Evidence against.** The template is only as good as its "read first" list, which is a mirror. And the
wider command surface it sat inside was mostly dead: of **52 command files, 50 were never invoked** as a
literal command, and combining literal invocation with direct file reads, **only 10 of 52 show any
evidence of use at all**. The template was used because it was *pasted into a prompt*, not because it
was a command.

**Verdict: ADOPT NOW — and treat it as the primary routing surface, not a secondary one.** The census
says sub-agents, not the main thread, are what read the corpus.

**Confidence: medium-high.** The zero-top-level-read pattern is measured; the inference that briefs
*caused* those reads is reasoning.

**Shape here.** A short brief template at `docs/reference/AGENT_BRIEF.md` (or a `CLAUDE.md` section)
with six fixed headings: **context · read first · scope · acceptance · what not to do · model tier and
why**. The "read first" line is taken verbatim from the matching row of the `CLAUDE.md` routing table,
so there is one source and not two, and the existing model-tier rule becomes a heading of the brief
rather than a separate convention. **Enforcement: review-only** for the prose; the one mechanical half
worth having is "a dispatched agent never commits", already covered by the hard-block hook on
`--no-verify` and direct pushes to `main`.

---

### 3.4 The North Star / intent document

**What it is.** A short document stating what the project is for and what "done well" means, so intent
survives context resets and a session can tell whether a proposal serves the goal.

**Evidence for, and the finding that matters.** The earlier project had **two** documents in this genre
and they behaved completely differently. The one that fused intent with the live phase plan was the
**fourth most-read document in the entire 838-document universe**: 75 reads across 5 sessions, 134
writes, 71 commits, 33 KB — and 4.0% of sessions on the upper-bound count, marginally ahead of the
3,380-line architecture guide. The one holding **intent alone** shows **0 reads and 0 writes** across all
1,127 transcripts. The lesson is sharp and not obvious: *intent on its own does not get opened; intent
attached to the thing people already open does.* It was also live rather than decorative — a
doc-currency audit on it recorded "three verified-stale corrections, each replaced in place rather than
annotated", and across 71 commits, 34 touched its verification stamp with **zero** stamp-only bumps,
i.e. it was actually re-read when it was re-stamped.

**Evidence against.** The reason it was read is also its defect: it carried live phase state, so it was
written 134 times against 75 reads (a 0.56 ratio) and accumulated 71 commits. Live state inside a
durable document is the thing the same corpus elsewhere names as having "rotted here twice in one week".
And the intent itself was not stable: one decision reworded a north star and was superseded by another
decision the same week.

**Verdict: ADAPT — adopt the intent statement, refuse it a file of its own, and keep live status out of
it.**

**Confidence: medium-high.** The 75-versus-0 contrast is a strong natural experiment, but it is two
documents in one project.

**Shape here.** Intent lives where it already does and already gets opened: `docs/PLAN.md` § Context,
with the one-paragraph product intent restated as **D-28** in `docs/decisions/DECISIONS.md`. What it
should contain: what the system is for in two or three sentences, the one ranked priority, the two or
three things that would mean it failed, and the named non-goals. What to keep **out**: every count,
status, date and milestone — those belong in `docs/recent/STATUS.md` (live status), `docs/PLAN.md` §
Milestones (plan), and the run data (numbers). **Enforcement:** G34
(`tests/gates/test_superseded_claims.py`) already catches a retired claim restated as live anywhere
under `docs/`, which is the enforcement that matters for an intent statement — it stops an old priority
from surviving a re-ranking. Giving intent a document of its own would add a new mirror with no check;
**do not**.

---

### 3.5 The system guide ("why not document how everything works?")

**What it is.** One deep reference describing how the whole system works, from conceptual architecture
to a from-zero rebuild blueprint, plus a short front-door map routing into it.

**Evidence for — six mechanisms worth taking.**

1. **The trust-precedence rule, stated before any content.** "This document will drift. When it
   disagrees with the live code, **the code wins**", followed by a five-row table naming the canonical
   source for each class of fact — schema to the typed contract, module paths to a machine-readable
   manifest, dependency rules to the linter that enforces them, active hooks to the settings file, and
   *any count* to the derive-live command given at the point of use. This converts a document from an
   authority (which rots) into an index (which only rots at its pointers), and it is the single most
   transplantable idea in the corpus.
2. **The canonical-source pointer map** — sixteen lines, one per fact class, each naming the file or
   symbol that owns it. It is what makes "code wins" actionable rather than a slogan.
3. **Derive-live markers used as discipline.** Volatile figures were progressively converted from pinned
   numbers into pointers; one commit title records the lesson directly: realign the corpus to the fixes,
   and stop restating numbers that move.
4. **The debt map with a guard column** — ten ranked debt zones, each carrying evidence, the risk if
   untouched, **the guard that caps it**, and a confidence. A debt list without the guard column is a
   wishlist; with it, it is a status report.
5. **The rebuild blueprint**, and its first truth: **"a clone is empty"** — everything load-bearing was
   gitignored and symlinked, so a fresh clone plus a pipeline run yields empty tables and fails at step
   one mysteriously. This was the project's single most expensive undocumented fact.
6. **The construction method.** Three waves of read-only agents: six extraction agents grounding claims
   in live code rather than in existing documents; five adversarial review lenses run *before* the
   draft, which found **four whole missing subsystems** and corrected several numbers; and two
   verification agents that confirmed **16 of 16** load-bearing claims.

**Evidence against.** It was the most expensive document in the corpus and the least-read of the major
genres. The spine is **3,380 lines / 377 KB with 49 commits over nine weeks**, plus ten companions of
~8,750 lines. It was touched in **50 of 1,201 sessions (4.2%)** and its companions in **one session in
seventy-five**, while the operational registers and the resume breadcrumb were read three to eight times
more often. In the tool-call census it shows 18 reads, of which **one was top-level and seventeen were
inside sub-agent transcripts**. It accumulated **seven** trailing revision stamps, five ending "rest of
body NOT re-attested this pass" — an honest confession that after nine weeks of currency passes most of
a 3,380-line document had not been re-checked. Its rendered HTML copy was recorded as deferred or owed
across three separate stamps and never regenerated. It carried only **11** derive-live markers in 3,380
lines, and a marker does not make a number regenerate: one command count carried a derive-live marker
and still printed **48 when the live count was 52**. And the whole companion set had **zero** router
rows, so it was mechanically undiscoverable.

**Verdict: ADAPT, shrink about six-fold, and write it at a named trigger — not now.** The answer to "why
not document how everything works?" is: because the part that stays true is the part a machine
generates, and the part that drifts is the part a human types.

**Confidence: high** on the shape and on the timing. The earlier project's worst documentation failure
was documents describing a *target* state as if built — three of eleven module documents drifted into
actively misleading territory. Writing an architecture guide at M1a would reproduce exactly that.

**Shape here.** One file, `docs/ARCHITECTURE.md`, hard-capped at ~600 lines, written at **M2** — when
the web UI and the daily run both exist and the module set has stopped moving. Earlier trigger: a second
person, or a fresh agent with no plan access, has to change the code. Six sections:

1. A five-line **trust header**: code wins, plus a 6–8 row canonical-source table (schema → the Alembic
   head; exit codes → `core/retry.py`; module set → the generated block; guards → `docs/runbook/GUARDS.md`
   and `.ratchets/`; config keys → `config/`; decisions → `docs/decisions/DECISIONS.md`).
2. **One diagram** of the data path — source → gateway port → collector → SQLite → digest → web UI —
   with the trust and process boundaries marked. One diagram, not six.
3. **The invariants** an agent will get wrong without reading them: scrub-and-tombstone on deletion;
   `raw_json` per row as the single raw store; distinct-author ranking; the exit-code contract; tests
   never write into live data; the UI mirrors the CLI and never the reverse.
4. **What a clone does not contain, and how to restore it** — the SQLite database, the credentials, the
   collected corpus. The highest-value section, because it is the earlier project's most expensive
   undocumented fact.
5. **The debt map with a guard column**, only while there is debt.
6. **Roads not taken as a pointer** to `DECISIONS.md` § 3, never a copy.

Drop outright: any companion set, a confidence-tag legend, a journey narrative, and anything restating a
number that moves.

**Enforcement — four cheap checks, all inside `make check`.**

| Check | What it does |
|---|---|
| Generated-section gate | `make arch` writes the module list (one-line purpose from each docstring), the CLI command table, the exit-code table, the schema summary, the guard/ratchet inventory and the config keys into one marked block; `make arch --check` fails when the committed file differs from a fresh generation |
| Path/symbol resolution | Every file path and symbol named in the prose resolves on disk (the §3.3.2 check, extended) |
| Currency gate | Fails when `ARCHITECTURE.md` is older than the newest migration or the newest module added |
| Stamp lint | Fails on more than one `last-verified` line, or on any "not re-attested" wording |

The generated-section gate is the derive-live idea **mechanised**: the earlier project marked volatile
facts by hand and then chased them by hand for nine weeks. Generate instead of mark. The stamp lint
replaces the "not re-attested" honesty convention, which was correct for a 3,380-line document nobody
could re-read; at 600 lines a full re-attest is a ten-minute job, so the rule becomes **re-verify the
whole file or do not stamp it**.

---

### 3.6 Workflow guides that evolve over time

**What it is.** Two distinct things the earlier project bundled: the **door** (one named command per
recurring task, where the obvious wrong route refuses and names the right one) and the **methodology
document** (a long per-task guide on how to think about it).

**Evidence for the door.** The argument for the genre is one sentence: "a recurring cost here was
re-answering the same question with a fresh ad-hoc grep each time, which is non-deterministic and drops
the accumulated guards". The design doctrine's best line defines the limit: "a pathway is not a document
telling people what to run. A pathway is: the obvious thing works, the wrong thing refuses, and the
right thing is reachable without private knowledge." And the real value was not the prose — it was **the
audit that writing the prose forced**. Designing it surfaced two live failures: the obvious entry point,
the script named after the thing you want, ran and printed a real-looking result rendered through a
renderer superseded two weeks earlier, with nothing warning the user (fixed by making it exit non-zero
and name the real route); and the sanctioned batch route failed with a module-not-found error from its
own documented working directory, working only for someone who already knew to set an environment
variable (fixed at the shared resolver and locked by a test that runs in a subprocess with the
environment scrubbed).

**Evidence against the methodology document.** The four methodology guides total ~5,600 lines across 52,
31, 17 and 13 commits. The most-read reached **6.4% of sessions** — 1.5× to 4× the system guide, so per
unit of maintenance this genre outperformed the architecture guide — but they earned those lines because
triage and crash investigation were judgement-heavy analytical tasks run by hand at full depth on data
with a dozen traps. Even the best-shaped of them, at 612 lines, still accumulated a 15-line stamp. And
the command surface the doors sat in decayed badly: 52 command files, 8 of them superseded pointers,
**42 of 52 with zero evidence of ever running**.

**Verdict: ADOPT the door pattern; SKIP the methodology-document pattern.** Insight Miner's recurring
tasks — daily run, digest reading, theme editing, restore drill, release — are **operational**, not
analytical. Four of the five have a single correct sequence; only theme editing and digest reading carry
judgement.

**Confidence: high** on both halves.

**Shape here.** One section per task in `docs/runbook/RUNBOOK.md`, capped at roughly a screen each, with
a fixed four-part shape: *the one command · what good looks like · the three ways it goes wrong · the
refusal you should see.* No separate per-task documents. Theme editing gets the only genuine "how to
decide" note — half a page on what makes a theme worth keeping and how to tell a real signal from a
wording artefact. The runbook already has the skeleton in six numbered sections; what is missing is the
fixed shape and the refusals.

**Enforcement — three checks.**
1. **Every task section names a command, and a test asserts the command exists and that `--help` exits 0
   from the repo root with no environment set up.** That is the earlier project's exact fix, and it is
   the difference between a documented route and a working one.
2. **Any obvious-but-wrong entry point exits non-zero and names the right one.** The earlier project
   called this "the single highest-value item" in its pathway document.
3. **The corpus-freshness refusal**, which the earlier project listed as owed and never built: "every
   one of these programs reads the serving DB. None of them currently checks whether it is stale. A card
   built off a month-old corpus looks identical to a fresh one." Insight Miner has exactly one operator
   surface reading exactly one SQLite file, so this is a few lines: the digest page shows the collection
   watermark, and a stale read is a visible banner plus a disabled action, not a silently old page.
   Build it at the same time as the page.

**On "evolves over time".** What makes a guide evolvable is the **update policy declared in its header**
(§3.8): all four methodology guides declared prune-stale — "wrong content is corrected in place; this is
not an append-only log" — plus a read-order telling the reader to read staleness first, the real flow
second, the operator's model third, known defects fourth. That read-order instruction is described in
the evidence as "the single cheapest quality feature in the set". Copy the header, not the length.

---

### 3.7 Record tiers and the five-part reliability recipe

**What it is.** The forensic finding that a record-keeping system is reliable **if and only if** it has
five things — a sharp binary inclusion bar, a mechanical numbering ritual giving each entry a citable
identity, exclusivity (exactly one home per record kind), enforcement, and a frequent unambiguous
trigger — and that a project should have a small number of such tiers rather than one catch-all or a
dozen.

**Evidence for.** This was *derived*, not assumed: by comparing a register that had been reliable for
the life of the project against ones that "survived only on the operator's constant insistence
(disposition-dependent → eventually slips)". The durable statement is worth carrying verbatim: missing
any one of the five ⇒ it degrades to disposition-dependent ⇒ it rots. The bar held in practice: across
**459 combined entries** in two registers, exactly **one** entry ever had to cite the taxonomy decision
to justify its classification, and the boundary between the two registers was **never once deliberated
as a question** across 264 transcripts — it fired once, as a one-line rule application with no visible
weighing. A topic that plausibly straddled both landed cleanly on one side (zero hits in one register,
dozens in the other). And the decision register is the most re-read-relative-to-written artifact measured
anywhere: **15 reads against 1 write**, with essentially no self-rereading. The bug register sits at
1.43:1, a measured-results log at 2.64:1, a settled-negatives register at 4:1.

**Evidence against — the tiering multiplied.** The decision register reached **91 headings**, of which
**23 were proposed and never promoted**, 3 were reserved and never written, and one number was reserved,
never written up, and yet cited from live code. Of 74 substantive decisions in the main window, **43%
are cited only in documents and never in code** — the best available proxy for "wrote a decision record
that did no work". Eight of the 74 were walked back or never spent. The sharpest case: one decision
built a monitoring detector "red-teamed by 3 reviewer agents … with 54 passing tests", and another
deleted it outright three weeks later because the notification cadence was "a constant, burdensome
stream not worth the signal" — with **no attempt recorded to tune it first**. Meanwhile the two
highest-volume records were fed and rarely reopened: the session changelog at **0.44** read:write
against 595 writes, and the backlog at 0.66.

**Verdict: ADAPT — take the recipe; take three tiers, not seven.** Insight Miner already has exactly the
right three: `docs/decisions/DECISIONS.md` (a choice a future session could plausibly reverse without
knowing why), `docs/runbook/KNOWN_ISSUES.md` (a fixed bug pointing at its regression test), and
`docs/runbook/GUARDS.md` (a guard with its birth incident and positive control). Everything smaller
belongs in the commit message, which git already makes durable and searchable.

**Confidence: high** on the recipe and on three tiers.

**Shape here.** No new register. Two gaps against the five properties.

**(a) Identity you can cite from code.** The earlier project embedded roughly **2,900** bug-register
references, **950** decision references and **370** fix-log references directly in the Python, so you
could "grep the number, find the incident or decision that justifies the line". That is the load-bearing
half of the whole register system, and its corollary is that a register entry with no code reference is
a diary entry.

**(b) The collision-free number allocator: SKIP.** It exists purely for concurrency — 4+ concurrent
sessions on 57% of days — and collisions recurred even with it, requiring a commit that renumbered seven
entries. With one operator, the next number is the last number plus one. If parallel agents ever write
the register, the cheaper fix is the earlier project's own staging rule (§3.3.4): dispatched agents never
edit shared registers, they stage a delta the driver merges.

**Enforcement:** `tests/gates/test_superseded_claims.py` (G34) already asserts that a cited decision id
exists. Add the reverse — **a lint that fails on a `D-NN`, `N-NN` or `KI-NNN` cited in a code comment
that does not exist in its register** — which closes the loop in both directions and is about fifteen
lines. The inclusion bar itself is **review-only**; the evidence says a sharp bar does not need
enforcement, because across 459 entries it produced no arguments.

---

### 3.8 Document classes, update policies, and stamps

**What it is.** Every document declares which of two update modes it is under: **append-only** (logs,
registers, journals — history is the value; when it grows, roll the oldest sections off to a dated
archive leaving a pointer) or **prune-stale** (routers, status snapshots, specs — outdated content here
is wrong-if-kept, so remove it in place). Plus a one-line `last-verified` stamp meaning "someone actually
re-read this body on this date".

**Evidence for the classes.** Without the distinction, an agent told to "update the docs" either
destroys a decision lineage or preserves a lie. The operational half is what matters for an agent-built
project: **when dispatching a doc-update agent, tell it which mode applies.** The cost is one line of
front matter per document, and the architecture guide names it as one of the two rules that "keep the
prose corpus from lying".

**Evidence for the stamp, and its limits.** The honesty rule was born when a cleanup pass found the
corpus's *worst-stale documents hiding under fresh backfilled stamps* — "a date alone reads as
attestation", and "an honest 'not actually verified' state must exist and be visible, **or the absence
of red reads as green**". It was used at scale: **1,391 files** carry a stamp, **167** contain "not
re-attested", and in a ten-document sample every stamp bumped with zero body change self-declared the
qualifier rather than silently claiming freshness.

**Evidence against.** Three costs. (a) **The convention held but the behaviour did not** — the mechanism
made stamp-bumping-without-reading "visible and tracked rather than eliminating it". (b) **Stamps grew
into chains**, one predecessor chain running to several thousand characters before being collapsed.
(c) The behavioural pass is decisive: **the stamp worked as a writer's discipline and failed as a
reader's trigger.** Zero assistant reasoning blocks in the four largest sessions contain the word
"re-attest" — every occurrence is inside a tool input, i.e. in what the agent *writes*, never in what it
*weighs*. When the stamp arrived as an alert ("24 documents owe a re-attestation", "9 documents stale
>30 days"), the agent read it and moved on: five loud warnings, and the named remediation command was
executed **exactly once in the entire corpus**. The qualifier even confused the checker, producing a
false loud alarm treating 12 documents stamped one day earlier as more than 30 days stale.

**Verdict: ADOPT the classes now; ADAPT the stamp to one line, and do not expect it to change a reader's
behaviour.** The stamp's genuine value is the "what I did **not** check" half, which converts a silent
assumption into a named limit and which drove real re-measurements when an agent was already editing a
stamped document.

**Confidence: high** on the classes; **medium-high** on the stamp — the writer-side value is well
evidenced, the reader-side failure is measured, and the residual uncertainty is whether a stamp ever
silently changed a trust decision, which leaves no trace.

**Shape here.** Insight Miner declares update policies at the **folder** level in `docs/INDEX.md` § How
the corpus is organized, which is the right start but is one hop from the agent editing the file. Add one
front-matter line to every document under `docs/`: `update-policy: append-only` or
`update-policy: prune-stale`, matching the folder table. Close every durable document with exactly one
line — `last-verified: YYYY-MM-DD — <what was actually checked>` — replaced and never appended; a
mechanical touch stamps `(unread)` and the checker counts `(unread)` as stale forever.
**Enforcement:** extend `tests/gates/test_doc_currency.py` to assert (1) every file under `docs/` has a
front-matter `update-policy` line matching its folder's declared policy, (2) at most one `last-verified`
line per file, and (3) no "not re-attested"-style multi-clause wording — at this size the rule is
*re-verify the whole file or do not stamp it*. Today only `LEARNINGS_TRANSFER.md` carries a stamp, so
this is a small sweep.

---

### 3.9 Number homes, derive-live, and propagate-to-mirrors

**What it is.** Three rules that work as one: every figure that can move lives in exactly **one**
canonical home; every other document points at that home rather than restating the value; any count a
command can produce is printed with the command rather than as a literal; and a fact changed in one
place is changed in **every** place in the same pass.

**Evidence for.** The highest-value practice in the catalogue, with the most expensive incidents. The
enforcement lint's own header names three wounds: a claim corrected in one document keeps being asserted
live in N others; a narrow figure "drove a bogus P1 across ~40 docs"; and scripts kept emitting the old
label after the document was re-labelled. The originating incident is precise: two *real* numbers — one
from a narrow telemetry path, one from a small recent sample — were weighed as a system-wide finding and
shaped strategy. The rules that came out of it are quotable: "derive every count in this table, never
restate it — three restated counts in this section were stale at audit"; "cite a headline number by its
ledger row, never restate it bare"; and for memory specifically, "movable numbers do not live in memory
bodies — point at the ledger and add a do-not-quote banner". The propagation half has three teeth: a
retirement procedure used the wrong version-control verb, and "the wrong verb was written in four places
and is the mechanism that put tracked files under a gitignored directory"; a module's onboarding
document presented a retired architecture as the live one for months; and a duplicated section in the
approach document "had drifted into naming a mechanism deleted 55 days earlier".

**Evidence against — it was right and under-enforced.** The advisory lint sat at **RED with 69 live
hits** and never went green, and it was also the corpus's worst-behaved guard: a heading reading
"de-staling the old X number" was flagged as a live re-assertion; widening its window took it from 25
flags to 5; and the honest verdict is that "a detector whose hits are mostly the fix trains everyone to
ignore it — the same outcome as having no detector, bought at the price of running one". The best worked
example of the failure the rule targets: **three current documents stated three different sizes for the
same doc-currency gate** — "~23", "43", and "22 + 16" — and none carried a derive-live marker. And the
marker alone does not regenerate a number: one command count carried a derive-live marker and still
printed 48 against a live 52.

**Verdict: ADOPT NOW, all three — and this is the one place to go further than the earlier project did,
by turning the marker into a gate.**

**Confidence: high.**

**Shape here.** Name the homes explicitly in `CLAUDE.md`: run counts and throughput live only in the run
rows and the digest function; schema facts live only in the migrations; module and test counts live only
in the generated block and the `make check` output. Everywhere else a figure appears as
`[derive: <command>]` or as a pointer, never as a bare literal. The propagate rule is already in
`CLAUDE.md` § "Every mirror in the same change" and should keep its second sentence: *flagging a stale
mirror does not count as fixing it.* Where a duplicate is genuinely justified, annotate it inline with
`(canonical: docs/… § …)` so the copy is detectable.

**Enforcement.** (1) `tests/gates/test_superseded_claims.py` (G34) already enforces the propagation rule
for retired claims and has already been seen red — the strongest position in this whole assessment,
because the earlier project never got this to a hard failure. (2) Add the **derive-live diff**: a check
that finds every `[derive: <command>]` marker under `docs/`, runs the command, and fails on a mismatch —
a few dozen lines, and it closes the earlier project's single biggest gap in its best practice.
(3) Keep the earlier project's own warning in view: key any such check on the invariant, never on a
proximity window — which `docs/decisions/DECISIONS.md` N-05 already states more strongly than the
earlier project ever managed.

---

### 3.10 Session handoffs and session changelogs

**What it is.** A dated document written just before a context compaction, capturing carry-forward
state; and an append-only log of what changed each session, with a resume breadcrumb pinned at the top.

**Evidence for.** The problem is real: context is lost three ways — a compaction compresses the window,
a new session starts cold, and parallel sessions hold context that never reaches the orchestrator. The
artifacts were genuinely high quality: **46 handoffs converged independently on seven headings** —
resume in one paragraph, state at compaction, resume in N steps, watch-outs, pointers, corrections a
resuming session must not undo, and uncommitted working-tree state. Those seven are the whole
transferable content. And the breadcrumb *was* read: the session changelog appears in **427 of 1,201
sessions (36%)**, the highest of any document measured.

**Evidence against — the best-measured finding in the set.**

- **Cost:** the changelog-and-handoff mechanism was the single largest harness-maintenance item at
  **~49.1 hours — roughly 31% of all harness time and 8% of all active project time** — and it was
  persistent, appearing as a top-3 harness mechanism in **8 of the 10 weeks**.
- **Volume:** four changelog files totalling **~6.2 MB and ~1,381 entries**; the primary file alone is
  12,379 lines / 314 entries, **546 writes against 225 reads**, and **1,111 commits**.
- **Consumption:** handoffs were consumed at most once and often never. Querying each individual handoff
  filename returns **0 to 3 sessions, typically 1 or 2**, and the family string appears in **44 of 1,201
  sessions for 46 files written**. In the tool census: **24 reads against 108 writes** across 42 files.
- **What was actually read:** not the log. The 36% figure is the **resume breadcrumb pinned at the top**;
  the 1,381-entry body below it is what cost the 49 hours and there is no evidence it was read. "The
  genre paid for a 6.2 MB archive to maintain one paragraph."
- **The resume mechanism did not fire either.** The compaction carry-forward block arrived **151 times**
  with real content every time — and in **8 of 9 sessions it was never referenced**. A mechanical audit
  of the 80 records after each of the 9 first carry-forwards found **zero** sessions that read a handoff,
  read the resume breadcrumb, or ran the health check — the three things the block named. The
  recommended re-orientation command was invoked **0 times out of 151**.
- The project's own retrospective reached the same verdict independently: documents outnumbered code
  commits ~1.5:1 and test commits ~10:1, and **~12% of commits were pure process-state churn the
  project's own rules forbade**.

**Verdict: SKIP both genres.** The context-reset problem is real; the artifact shape was wrong even at
the earlier project's size, and Insight Miner is one operator, one machine, one repository, sequential
sessions — against up to 8 parallel sessions across two machines there.

**Confidence: high.** 49 hours spent, at most one later reader per artifact, and a resume mechanism that
fired 151 times and changed behaviour once.

**Shape here.** `docs/recent/STATUS.md` is already the single resume surface and is already declared
"rewritten, never appended". Two changes. (a) Adopt the converged headings, because 46 independent
handoffs arrived at them: *in flight (with any process or log pointers) · next step, numbered ·
uncommitted state · what a resuming session must not undo.* (b) **Cap it.** Today's file is 36 lines but
already carries five sections including a "Decisions waiting on Wes" list and a "Known contradictions"
list — both register content living in the status file, which is exactly how a status file becomes a
changelog. **Enforcement:** a ~50-line cap and a staleness check (`STATUS.md` is red if it is older than
the newest commit) added to `tests/gates/test_doc_currency.py`. Durable "what changed and why" goes in
the commit message and the three registers, both already enforced and already searchable. **git log is
the changelog**, and it cannot drift from the code it describes.

**Trigger that changes this:** genuinely concurrent sessions or a second machine, at which point a
handoff becomes a *message between agents* rather than a note to the future.

---

### 3.11 The journey narrative and the per-module document set

**What it is.** A living retrospective narrative of how the project got here; and, per module, a
plain-English README, an append-only design journal, a machine-readable manifest, and a verification
stamp.

**Evidence against the journey.** **4,326 lines across eight files**, including three "living deep-dive"
narratives of 386, 533 and 2,684 lines — **read in 7 of 1,201 sessions (0.6%), the least-read genre
measured**, on six commits over two months. Its hand-maintained HTML companion illustrates the failure
mode exactly: it carries its own warning that it is a hand-maintained snapshot which has drifted, that
there is no generator, that its content was frozen on one date while both sources it visualises advanced
two weeks later, and that "they are not even the same shape any more" — with the proposed fix backlogged
and never built.

**Evidence for one part of it.** One section earned its keep, and it is not the narrative: a "what we
got wrong" calibration register of six named reversals, each with the inflated figure, the corrected
figure, and the mechanism that caused the error — an accuracy of ~69% that was a train/test leak and
collapsed to ~3.4%; a retrieval recall of ~96.8% that was identity-leaked (94% of it because an
identifier appeared verbatim in the source text) and was honestly ~49.9%; an AUC of 0.97 that was a
co-temporal leak and is 0.41 leak-free — with every one of those numbers **mechanically enforced as
do-not-quote** by a script that greps the live corpus for retired phrasings. The meta-lesson is one
line: *a number can be perfectly real and still mislead if it is weighed out of its context — its
denominator, its operating point, its purpose.*

**Evidence against the per-module set.** It was mechanised — a module-doc health check, three hooks
warning when a module's code changed without a journal update, five structural tests — and the intent is
exactly Insight Miner's: preserve per-module context before it evaporates. The measured outcome is the
argument against it: the governing document was read in **10 of 1,201 sessions (0.8%)** on three
commits, and **three of eleven module READMEs drifted into actively misleading territory while the
machine-readable manifest stayed correct in every one of those three cases**. Even a healthy pair split:
in one sampled module the README described two API surfaces that the module's own journal recorded as
"not yet in the package". So the genre produced one artifact that stayed true because a test checked it,
one that drifted because only a convention checked it, and one that was honest because it was
append-only and small.

**Verdict: SKIP both. Transplant three pieces.**

**Confidence: high** — 0.6% and 0.8% read rates, a drifted artifact with no generator, and the human
half drifting while the machine half held.

**Shape here.** (1) **The reversal register is already adopted** — `docs/decisions/DECISIONS.md` §
Retired claims, enforced by G34, which has already been seen red. Keep it as the *only* home for
reversals, and do not add a narrative beside it. (2) **The module docstring is the README**: it sits next
to the code, it is what an agent reads, and the generated module table in `ARCHITECTURE.md` (§3.5) pulls
from it, which makes it mechanically checked for existence and freshness. **git log is the design
journal**: append-only by construction, and it cannot describe a file that no longer exists. (3) **Cite
register ids in code comments**, with the dangling-id lint from §3.7. **Enforcement:** the generated
block gate and the dangling-id lint; no hand-maintained per-module prose, so nothing to check. A
retrospective is worth writing **once at the end of a milestone as an input to the next project**, not
maintained as a living document — and `docs/learnings/LEARNINGS_TRANSFER.md`, with predictions to score,
is already a better instrument than a narrative because it can be graded.

**Trigger that changes this:** a single module past roughly 1,000 lines, or one accumulating more than a
handful of non-obvious decisions, earns a design note — as a section in `DECISIONS.md` naming the module,
not a new folder.

---

### 3.12 Key criteria: the gates model

**What it is.** The evidence supports one specific practice under this name: **write the bar before you
see the result.** It appears in three places — the admission test for a new guard, the verdict
vocabulary for an existing one, and the pre-registered decision rule for a measurement.

**Evidence for.**

- **The admission test.** Before adding a guard: does it scan a structural shape or police a list you
  also maintain; can you construct the bad state and watch it go red; is the class recurring, or did it
  happen once and get fixed at the source; does an existing guard cover it with a widened rule — because
  *widening beats adding*. The reflex of answering every incident with a new lint is itself named as a
  failure mode.
- **The verdict vocabulary** — EARNED, EARNED AT BIRTH ONLY, UNPROVEN, SELF-SERVING — applied to 29
  guards produced **14 of 29 UNPROVEN** ("registered clean, never fired") and **1 SELF-SERVING** ("both
  reds resolved by allowlisting rather than a fix, and the motivating defect still live and uncaught").
  A second audit two days later, using a stricter per-commit evidence standard, found **12 of 28** with
  an attributed post-registration catch. Two audits, different denominators, same conclusion: roughly
  half the guards did no work.
- **Pre-registered decision rules.** Only two measurement packets were ever run under that name, and both
  stated their pass/fail bars before any label was seen — one as "proceed if credible correctness <70%
  **or** incorrect+unlabeled >40% on either slice". Both slices tripped and the operator accepted the
  forced conclusion with no recorded disagreement. The contrast is the proof: a structurally similar
  finding whose criteria were **not** pre-registered had to be retracted — "the operator caught it from
  the arithmetic alone", because two data sources had been graded on different versions and the join was
  invalid.

**Evidence against, and the finding that dominates everything.** Criteria without a blocking mechanism
changed nothing. **Every mechanism's detection half worked and its prescription half was inert** — 151
of 151 compaction sweeps fired, 268 session-start banners fired, every push-gate block landed; the named
remediations ran **0 of 151, 0 of 144, 0 of 130, and once in 264 transcripts**. "What did change
behaviour was a mechanism that BLOCKED, not one that warned … every warn-only channel was read and
walked past." And a guard whose warning becomes the steady state stops carrying information: one check
produced **140 reports and 0 failures**, and 130 of 151 carry-forwards flagged the same condition —
"nothing distinguished an ordinary night from a bad one". The other half of the cost is grandfathering:
**2,250 grandfathered suppressions across 13 files**, 1,319 in one lint alone, against two documented
real defects — "a baseline that only grows is a guard being SATISFIED, not obeyed". And when red events
were classified by cause: 30.5% were pins on exact counts over legitimately-moving data, **29.7% was the
harness policing its own conventions**, 12.1% machine state, and only 27.6% candidate product defects —
"we were enforcing conventions and not enforcing data integrity". Forty-one percent of the commits that
touched only test files were the guard machinery catching the guard author.

**The one genuinely encouraging finding.** When a gate *did* block, agents behaved well: across **236 red
events in 6 sessions** and 26 episodes read in detail, the agent treated the red as its own debt and
fixed it in **24 of 26**; **zero** episodes show a guard disabled, a baseline re-baked to swallow new
debt, or a finding argued away; the baseline-rebake flag was never invoked. Two guards produced genuinely
new knowledge rather than friction.

**Verdict: ADOPT NOW — already largely in place, and Insight Miner is ahead of the earlier project
here.** `docs/PLAN.md` § "Guard design rules" holds the admission test, `docs/runbook/GUARDS.md` holds
the verdict vocabulary and requires a birth incident and a positive control, `docs/runbook/RUNBOOK.md` §
6 schedules the quarterly review, and **D-29** states the rule the evidence most strongly supports:
*nothing in the development gate is advisory.* That decision is the correct reading of the 0-of-151
finding.

**Confidence: high.**

**Shape here.** Two additions the evidence supports and the corpus does not yet have. (a) **A status and
a review date on each of the 24 live suppressions** in `.ratchets/`, so a suppression is either
`accepted` (nothing owed) or `open` (a real finding still owed, printed every run) — twenty lines, and
the direct answer to the 2,250-suppression failure. (b) **Pre-registered criteria for the first
measurement that drives a decision** — theme precision being the obvious one, and `DECISIONS.md` already
reserves "precision" for a blind, stratified, pre-registered packet, which is exactly right.
**Enforcement:** the ratchet tool already writes `.ratchets/` and the hard-block hook already prevents
hand edits, so the status field is enforced by extending `tools/ratchet.py` and its gate test; the
pre-registration rule is **review-only** until the packet exists, at which point the bar is written into
the code that computes it.

---

## 4. For future projects: the day-one set, in order

Ordered by the **cost of installing them late**.

1. **A short always-loaded floor plus path-scoped rules** (§3.3.3). *Incident:* raw data was destroyed
   accidentally twice, and the file holding the rule against it was a subdirectory instruction file that
   does not load at session start and never arrives at all for an agent that reads nothing under that
   directory. Installing this late means discovering the gap the way they did. It costs twenty lines.
2. **The number-homes rule, with a derive-live check** (§3.9). *Incident:* a real but narrow figure was
   restated across ~40 documents and drove a wrong priority. Late installation means auditing every
   document already written. Build the *check*, not just the marker — the earlier project never got a
   gate on its best idea, and a marked count still sat wrong (48 against a live 52).
3. **Document classes with update policies, and one-line honest stamps** (§3.8). *Incident:* a cleanup
   pass found the corpus's worst-stale documents hiding under fresh backfilled stamps — a date alone
   reads as attestation. Retrofitting a policy means re-reading every file to decide which mode it was
   always under.
4. **One register with all five reliability properties** (§3.7). *Incident:* the register that had the
   five properties was reliable for the life of the project, while the ones that lacked them survived
   only on constant insistence and eventually slipped. Decisions made before the register exists are the
   ones you most want and cannot recover.
5. **Mechanise rather than restate** (§3.1, §3.12). *Incident:* a rule written in three places was
   violated for months and obeyed from the moment it became a hook — and, at corpus scale, every
   warn-only channel was read and walked past while the one blocking gate reliably redirected work.
   Install the corollary too: measure a check's true-positive rate before keeping it. One tripwire was
   retired with "238 fires and zero true positives across 640 transcripts", and four session-end signals
   that were "90% of all noise" were cut — one having fired **19,274 times across 43 sessions**.
6. **The memory index as the recall mechanism, plus its integrity check** (§3.2.1, §3.2.2). *Incident:*
   127 of 166 memory files were reachable only through a second-tier index opened 6 times in 629
   sessions, and 28 index links pointed at files that no longer existed — neither failure surfaces as an
   error anywhere. Late installation means an unreachable corpus you have already paid to write.
7. **The add/update-only memory snapshot, with a completeness assertion on restore** (§3.2.3).
   *Incident:* an export path mirrored one session's deletion into the shared index and nearly committed
   it, silently dropping a day-old operator directive whose substance survived nowhere — and the restore
   path still only ever counted files, never asserted completeness.
8. **Propagate-to-all-mirrors as a same-pass rule, with a check** (§3.9). *Incident:* a retirement
   procedure used the wrong version-control verb, "written in four places", and that is the mechanism
   that put tracked files under a gitignored directory. One sentence in the instruction file, one grep
   step in every doc task, and — the part the earlier project never reached — one gate.
9. **A "how to trust this document" header on the one architecture document** (§3.5). *Incident:* the
   corpus ended up "kept honest about being stale rather than actually current". The header is what makes
   that honesty usable rather than merely true.
10. **The guard admission test and the verdict vocabulary** (§3.12). *Incident:* 14 of 29 guards had
    never fired and one was self-serving. A greenfield project gets these rules for free at day zero,
    which is the only cheap moment to install them.

### Deliberately left for a named trigger

| Practice | Trigger |
|---|---|
| A separate router file beyond the instruction file's inline table (§3.3.1) | The corpus passes ~60 documents. The router *lint* goes in on day one against whatever table exists; only the separate file waits |
| The memory consolidation pass and its cadence (§3.2.4) | The memory index exceeds its stated ceiling, or the memory directory passes ~20 files |
| The system architecture guide (§3.5) | The module set stops moving, or a second person or a plan-less agent has to change the code. Writing it earlier documents a target state — the earlier project's worst documentation failure |
| A methodology document for one task (§3.6) | One analytical task grows judgement-heavy enough that two runs on the same data can legitimately disagree. Then one document, on the best-shaped model in the earlier corpus: routes, holds no numbers, prune-stale, capped at 300 lines |
| A measured-results ledger and pre-registered criteria (§3.12) | The first number that drives a decision. Three fields: denominator, operating point, status |
| Session handoffs (§3.10) | Genuinely concurrent sessions, or a second machine |
| Agent-report indexing (§3.11, §5) | The second time you re-investigate a question you already investigated. Until then findings go into a register, not into files. The ordering lesson is the one that costs money: the earlier project built the index and the lint *before* auditing the corpus, and the audit then found 78% of it had never been referenced |
| A collision-free number allocator; a memory read census (§3.7, §3.2.5) | Neither trigger should ever fire on a solo project of this size |

---

## 5. What the earlier project got right, and how the apparatus outgrew its value

### The four things it got right

1. **It identified forensically why some record systems hold and others rot — and it is not
   discipline.** A record type is reliable if and only if it has a sharp bar, a mechanical ritual giving
   each entry a citable identity, exclusivity, enforcement, and an unambiguous trigger; missing any one,
   it degrades to disposition-dependent and rots. This was *derived* by comparing a register that had
   worked for the life of the project against ones that had not.
2. **It concluded that prose cannot enforce anything, and acted on it.** "A rule written in three places
   was violated for months and obeyed from the moment it became a hook. Advisory prose is advisory; a
   mechanism is binding. When a rule keeps being ignored, the answer is to mechanize it or delete it,
   not to restate it a fourth time."
3. **It built honesty about ignorance into the format itself, in three separate places.** On documents:
   "an honest 'not actually verified' state must exist and be visible, **or the absence of red reads as
   green**." On guards: a check pointed at a directory that may not exist "silently passes by having no
   subject … a green guard proves nothing until you watch it go red." On measurement: the read census
   states outright that it "measures RECALL … never USEFULNESS … treat a zero-read file as a routing
   question and a read file as unproven, not as proven value."
4. **Its construction method.** The architecture guide was built by three waves of read-only agents,
   with five adversarial review lenses run *before* the draft — which found four whole missing
   subsystems and corrected several numbers — and two verification agents that confirmed 16 of 16
   load-bearing claims. Reviewing before drafting is why that document's factual base held for two
   months. That practice transfers at any size and costs nothing but ordering.

### The four ways the apparatus outgrew its value, with the numbers

1. **The corpus became an obstacle to the answer.** "If you are trying to find out how something works
   TODAY, reading more of it makes you slower and more likely to be wrong, because superseded answers
   outnumber current ones by roughly two orders of magnitude." The tracked document tree ran **1,160 →
   4,286 at peak → 1,005 after a purge → 1,962** at the end, and roughly **81%** of the peak was
   machine-generated agent-report exhaust, leaving a curated set of ~700–820. **The corrective was itself
   a document** — a 67-line file whose whole job was to say which eleven of roughly four thousand
   documents were current — which is an admission that the routing layer had failed and had to be
   rebuilt smaller.
2. **The routing layer became another thing to search.** The primary router stood at **72,394 bytes and
   205 rows**, with rows running to full paragraphs, and was written into three times more often than it
   was read (9 reads / 27 writes) — while a sibling document in the same corpus warned that "a router
   that grows becomes another thing to search". The same shape recurs across the harness: of 52 command
   definitions, **42 show no evidence of ever running**.
3. **Freshness became a declaration rather than a fact, and the bill came due anyway.** The architecture
   guide's own honest-limits paragraph concedes the corpus was "kept *honest about being stale* rather
   than actually current"; 167 files carry that qualifier; and the behaviour the mechanism was built to
   stop "kept recurring — the mechanism made it visible and tracked rather than eliminating it". The
   price is measured: **33.6% of all measured active hours went to maintaining the harness rather than
   the product** (158.4 of 604.9 hours), spiking to **56.3% in the final week**, with documents at
   127.9 h, memory at 22.7 h, enforcement at 7.7 h and agent reports at 25.1 h — and the single largest
   line item, session changelogs and handoffs, at **~49 hours**.
4. **Detection outgrew remediation.** This ties the other three together and is the pattern most worth
   carrying. Every diagnostic fired reliably — 151 of 151 compaction sweeps, 268 session-start banners,
   every push-gate block — while the named remediations ran 0 of 151, 0 of 144, 0 of 130, and once in
   264 transcripts; and a guard whose warning became the steady state stopped carrying information
   altogether (140 reports, 0 failures). By the end the operator said so directly: "we can't have these
   tests popping up regularly every day. It's too expensive, counterproductive, and wastes too much time
   … I'm also concerned if they're not enforced. What's the point of having a bunch of tests that are
   super noisy that we're always fixing that we don't even enforce?"

**The one sentence under all of it:** every documentation artifact a machine checked stayed true, and
every artifact only a convention checked drifted — so at Insight Miner's size, write only what a check
can hold, and generate the rest.

---

## 6. Decisions for Wes

Only genuine choices; everything else above is a recommendation with no live alternative.

| # | Decision | Recommendation | Confidence |
|---|---|---|---|
| D1 | **One memory home, and which one.** Two memory directories currently exist on this machine with the same eight topic files, and their indexes have **already diverged by one hook line**. Keep the repo-keyed directory and delete the other, or keep both and accept divergence | Keep the repo-keyed directory, delete the other, and let the snapshot into `docs/memory/` be the only mirror | **High** — this is the earlier project's number-one drift bug reproduced inside our own memory, and the index *is* the recall mechanism |
| D2 | **Build the memory snapshot and integrity check now, or at a trigger.** About 120 lines of Python plus two gate tests | Now. It is the only asset in the setup that cannot be regenerated from code or data, it currently lives in two diverging copies outside git, and the earlier project's one recorded incident here nearly destroyed an operator directive that survived nowhere else | **High** |
| D3 | **When to write `docs/ARCHITECTURE.md`** — now (M1a) or at M2 when the module set has stopped moving | M2, with the named earlier trigger (a second person or a plan-less agent has to change the code). Writing it at M1a documents a target state, which is precisely the failure that made three of eleven of the earlier project's module documents actively misleading | **High** |
| D4 | **Build the derive-live gate, or keep the convention review-only.** The check is a few dozen lines: find every `[derive: <command>]` marker under `docs/`, run the command, fail on a mismatch | Build it, at the same time as the first generated block. The earlier project had the marker and never had the gate, and a marked count still sat wrong (48 against a live 52) | **Medium-high** — small cost and a certain failure class, but until a generated block exists there is little to check |
| D5 | **Cap and de-scope `STATUS.md`.** It currently carries a "Decisions waiting on Wes" list and a "Known contradictions" list, both register content | Move them into `DECISIONS.md` § 7 and enforce a ~50-line cap plus a staleness check. An uncapped status file is how a resume surface becomes a changelog, and the changelog is the single most expensive thing in the evidence | **Medium-high** |
| D6 | **A status and review date on the 24 live suppressions** — now, or at the quarterly review | Now, as part of the already-approved `hard_after=` change: the same twenty lines, and 2,250 grandfathered suppressions is the earlier project's largest single enforcement failure | **High** |
| D7 | **The approach document: a file, or a section** — `docs/METHOD.md`, or a ~12-line `CLAUDE.md` section plus the existing learnings canon | The section. The earlier project's approach document had 0 reads and 0 writes across 1,127 transcripts while its content was among the most valuable in the corpus: the content transfers, the container does not | **Medium-high** (read counts are floors; shell reads are invisible) |
| D8 | **A sub-agent brief template** at `docs/reference/AGENT_BRIEF.md` reusing the `CLAUDE.md` routing rows, or continue writing briefs ad hoc | The template. The census shows the reference corpus was consumed mainly inside sub-agent transcripts, and 77 memories reached agents only by being pasted into briefs — the brief is the routing surface that actually fires | **Medium-high** |

---

*Prepared 2026-09-13 from a read-only pass over the earlier project's archive findings. Nothing in that
archive was modified; nothing was written under this repository outside the git-ignored build directory.
The transfer calls are judgements over the measurements, not measurements; where the evidence is a proxy
(read counts understate consultation because shell-based reads are invisible), the confidence says so.*

*last-verified: 2026-09-13 — first pass; every number above was read from the findings in this pass.*
