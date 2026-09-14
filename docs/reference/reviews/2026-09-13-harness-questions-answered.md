# The 26 harness questions, answered from the earlier project's archive

**Status:** draft for the planning session to review and move into `docs/reference/reviews/`.

**What this is.** § 9 of `docs/reference/reviews/2026-09-13-harness-assessment.md` lists 26 questions the eight
retrospective documents could not settle. Eight agents then went to the earlier project's archive — a
repository backup, its session transcripts, its predecessor repositories, folders that were never in git, and
a full-text index over the whole drive — and gathered evidence. This document answers each question, says what
the answer changes in the mechanism catalogue (§§ 3 and 6 of that assessment), and ends with recommendations
aimed at the **earlier repository itself**.

**Reading notes.** The earlier project's internal file names and codenames are abstracted here (its issue
register, its fix log, its decision record, its memory index, its architecture guide, and so on); the
unabstracted copy with full citations lives with the evidence, in the archive, as
`findings/H-26-questions-answered.md`. Citations below are to the findings files by agent letter and question
(for example `[A Q1]`, `[G §1.7]`). No people, emails, tokens, tickets, hosts or machine names appear; the
operator is "Wes", and the two machines are "the first machine" and "the second machine".

---

## 1. How the evidence was gathered, and its limits

### The sources

| Source | What it is | Size |
|---|---|---|
| The repository backup | the earlier project's monorepo, a git repo | 4,287 commits, final commit 2026-09-06 |
| The session transcripts | one JSONL file per session | **1,127 files** = 264 top-level sessions + 863 nested subagent transcripts, ~1 GB, 406,050 JSON lines |
| The two predecessor repositories | indexed 2026-04-01 → 2026-06-09 | the only surviving pre-merge history |
| Drive-only and "removed from repo" folders | including a snapshot of the operator's global harness directory | 3,378 indexed paths, never in git |
| A full-text index over the whole drive | queried read-only | nine source groups |

Eight agents: **A** guards, **B** registers and decision records, **C** memory and hooks, **D** documents,
commands, the fetch stop rule, stamps and the labelling loop, **E1** transcript counts, **E2** transcript time
and workflow, **E3** transcript behaviour, **G** the non-git sweep (which also corrects several earlier
numbers), **H1** a document-usage census. Everything read-only.

### Six limits every number inherits

1. **The git history was squashed** to a single root commit on 2026-06-09. No `git log -S` claim can see behind
   that date, so every repo-side "never happened" is bounded by it. The predecessor repositories partly repair
   this, which is why the non-git sweep could answer several "cannot be determined" items.
2. **Only 15 transcripts carry behavioural evidence.** 249 of the 264 top-level transcripts are under 100 lines
   (median 27) — automated scheduled runs that load the instruction file, drain a chat bridge, append a log
   line and exit. Substantive work lives in 15 sessions, five of which carry most of it `[E3 caveat]`. So
   "appears in 264 sessions" usually means "the string is in an always-loaded document".
3. **Absolute transcript counts are inflated roughly 3×.** The earlier project's own instrument documents the
   trap: the same tool call is written to the transcript many times — once per file that replays the turn, and
   repeatedly within one file ("one assistant event was observed written 16 times in a single transcript"). On
   this corpus a naive scan reported **532** memory reads against a true **179** distinct tool calls `[G §4.3]`.
   **What survives is set membership and ratios**, because duplicate counting cannot change which files were
   touched at all — and the project's instrument independently reproduced the never-read set.
4. **Bash is invisible.** Only the dedicated read/edit/write/search tool calls were counted, and the structured
   search tool was invoked **exactly once** in 1,127 transcripts, so essentially all searching went through
   shell commands this method cannot see. Every read count is a floor `[E1 limits]`, `[H1 method]`.
5. **"Active time" is harness-engagement time.** Hours come from gaps between timestamped messages capped at 10
   minutes, and nearly all measured time sits in two long-lived sessions kept alive by scheduled wake-ups every
   ~30 minutes `[E2 Q3]`.
6. **A repo-scoped absence claim about this project has already been wrong once**, caught by the operator: an
   earlier "it does not exist" was an unverified absence claim scoped only to the repository, and the artifact
   lived outside it `[G §13.2]`. Treat every "not found anywhere" below as "not found in these nine source
   groups".

---

## 2. Summary table

Confidence is in the evidence for the answer as given, not in the answer being the whole truth.

| # | Question (short) | One-line answer | Conf. | What only Wes can add |
|---|---|---|---|---|
| 1 | Which guards saved you, which were noise | Two pattern lints and one documentation lint have repeat post-birth catches out of 29 registered; 14 of 29 never fired; the noise had a measured root cause — 80% of daily-runner alert volume was one machine's environment | high (record) / medium (felt value) | Which he mentally skipped versus trusted |
| 2 | Was the ratchet runner ever in a pre-push hook | Yes — born 2026-07-13, first actually installed 2026-07-27, still installed at backup; the contradiction is commit-path versus push-path plus one document written two days before the hook existed | high | Whether he ever pushed with the bypass flag; whether the second machine's hook was ever installed |
| 3 | Hours/week on memory and docs, and the worst mechanism | ~33.6% of measured active time was harness maintenance; the session changelog plus pre-compaction handoffs cost ~49 h of 158 h; a second instrument names the memory routing-metadata layer (~41,600 tokens authored for a recall path that does not exist) | medium | Real hours; how long the metadata rewrite took |
| 4 | Which register re-read, which write-only | Read more than written: decision record, settled negatives, results ledger, breakage patterns. Written far more than read: session changelog, backlog, doc router, script manifest, compound insights. One named register was never touched at all | high (sets/ratios) / low (absolutes) | Nothing material |
| 5 | Was the two-register boundary ambiguous | No. One entry in 459 had to cite the taxonomy decision; zero deliberations in 264 transcripts. The boundaries that cost thought were register-versus-ledger, register-versus-changelog, report-versus-durable | high | Whether he debated it in chat that was never banked |
| 6 | Of ~74 merge-window decision records, how many load-bearing | 42 of 74 (57%) are cited by at least one Python file; none is cited nowhere; 8 of 74 (11%) were walked back or never spent. The project's own better instrument scores ~27% of governance mechanically enforced | medium-high (counts) / low (regret list) | The "wouldn't decide this again" list — nothing in nine source groups expresses one |
| 7 | Did a "body NOT re-attested" stamp change behaviour | It worked as a writer's discipline and failed as a reader's trigger: 426 real occurrences, all in what agents *wrote*, none in visible reasoning; the alert form was ignored (5 loud warnings, 1 remediation run in 264 transcripts) | high | Whether he ever de-trusted a doc on reading the clause |
| 8 | How often did the session-start carry-forward change the next session | Essentially never. 151 fires in 9 sessions; referenced in 1; zero follow-through in a mechanical audit; every named command remediation at 0 invocations | high | Nothing material |
| 9 | How long was the memory export silently deleting; were restores verified complete | Origin was the repository merge (~58 files stranded); the traceable loss is one day-old operator directive; restore verifies a copy count, never completeness — and a second silent-restore defect was found one day after the final commit and exists in no commit | high (the verification finding) / medium (the loss story) | When the mirror-delete was written; whether the eight dangling second-machine index links were repointed |
| 10 | Memory versus in-repo doc | Practised rule: memory holds the invariant and the behavioural trigger; the doc holds the number, mechanism and evidence — and agents argued the reverse direction explicitly too. But the recall mechanism the rule assumed does not exist | high | Per-file editorial calls |
| 11 | Which memories earned their keep | A small set of standing prohibitions and epistemic disciplines; one stopped a 49,343-file shared write. Three instruments disagree informatively: reads favour operational facts, citations favour principles, operator-voice handoffs give a third list | high (the list) / medium (the ranking) | Why the most-constraining one was later retired |
| 12 | Which ten commands per week, and what the dispatch command did | There is no top ten: 197 recorded invocations in five months, 17 distinct names ever, and the most-used was a built-in. The dispatch command was never invoked once — a written playbook followed by hand, whose hard rule #0 is "stage only, never commit" | high | Which playbooks he typed out of habit |
| 13 | Was the agent-report exhaust consulted again; was there a retirement pass | Yes to both: one measured retirement pass (713 cited / 2,487 orphan) plus five re-tracking corrections and a documented third consultation eleven weeks later. But more than half the on-disk corpus is one untracked exploratory batch | high | Whether he personally reopened reports outside the audited passes |
| 14 | At what doc count did the curated set stop fitting | Two answers: ~120 documents in one repository (2026-04-24, the first delegated census and a 26-item judgment queue) and ~4,286 documents / 78% orphaned (2026-07-11). The binding constraint was never the curated count but the always-loaded slice | high (events) / medium (which he felt) | Which of the two he experienced as the moment |
| 15 | Did any guard cause damage | Yes, in all three modes, ~30 recorded incidents — including six checks with a defect found in the check itself while its own record read clean, and a hard block that stranded a session against a written design decision made a month earlier | high | How much work was abandoned rather than fixed when a gate went red |
| 16 | Is Insight Miner's memory keyed to the Desktop working directory | Insight Miner question. Current state: memory is now keyed to the repository | n/a | Nothing |
| 17 | Is there a decision record for removing the fleet detector | Yes, a full explicit reversal three weeks after the detector was built, on notification noise rather than a technical failure — and the detector's own alert ledger recorded **zero genuine alerts** in its whole life | high | The triggering moment |
| 18 | What is Insight Miner's "irreversible few" | Insight Miner question. Current state: not yet written | n/a | The list itself |
| 19 | Parallel sessions or one at a time | In the earlier project, parallel was the default: 4+ concurrent top-level sessions on 57% of days, peak 8, under a written doctrine of "conflict-gated, not count-gated (~5 comfortable)" — but mandatory worktree self-isolation measured at 7 of 264 sessions | high (concurrency) / medium (worktrees) | Whether Insight Miner runs parallel at all |
| 20 | Which ONE mechanism to rebuild first, which never again | Judgment question. The evidence's default: rebuild the blocking gate at the push boundary first; never rebuild the authored routing-metadata layer, and never rebuild a warn-only nudge whose remedy is a command | low (as an answer) / high (the default) | His actual pick |
| 21 | Are Insight Miner's 24 suppressions accepted or open | Insight Miner question. Current state: still without status | n/a | One of two words per line |
| 22 | Is work left staged but uncommitted across sessions | Yes — routinely, and by design: every dispatched session was required to stage only. So max+1-from-the-file is disqualified as an id allocator, and the first duplicate register number predates the merge by three months | high | Nothing material |
| 23 | Did the pre-compaction critical subset ever surface anything | At every one of 151 compactions, and never once a clean tree — but 140 reports produced **0 FAILs**; the same worktree finding appeared 130 times. Its threshold sat below the normal working state | high | Nothing material |
| 24 | How did you stop a fetch | A novelty-run stop rule with a safety floor (100-item steps, ≥1 new shape, floor 500, three quiet steps, ceiling 7,000); the constants never moved, the scope changed six times. Two recorded defects, one under-fetching 31.7% of eligible buckets | high | The informal signal before it was mechanised |
| 25 | Did the labelling loop's pre-registered rule survive disputed labels | Only two runs ever, both accepted without recorded pushback. A sibling mechanism shows the dynamic: when Wes checked the arithmetic himself, the finding was retracted, not his scrutiny | medium-high | Whether he privately disagreed either time |
| 26 | Was `⛔ DO NOT REDISCOVER` obeyed | Yes, in every episode where an agent met it — and no, as a fence: a bare comment did not stop the question being re-derived until every path to it carried a pointer | high | How many distinct sessions re-raised it before the fix |

**Tally: 19 answered at high confidence** (Q1, 2, 4, 5, 7–15, 17, 19, 22–24, 26 — several with a named
lower-confidence sub-claim), **3 at medium or medium-high** (Q3, Q6, Q25), **1 at low** (Q20, which asks for a
judgment the archive cannot supply), and **3 are Insight Miner questions** the archive cannot answer (Q16,
Q18, Q21).

---

## 3. The 26 answers

### Q1 — "Which guards did you experience as having saved you, and which as noise you routed around?"

**Answer.** Of **29 guards registered in the blocking tuple** (27 blocking lints + 2 advisory by design, plus an
in-process contract check = 28 checks that actually block), only two lints have repeat attributed post-birth
catches — an unreachable-code lint (five, independently attributed) and a silent-exception lint (two).
**Fourteen of twenty-nine registered clean and never fired.** One is rated SELF-SERVING ("both reds resolved by
allowlisting rather than a fix, and the motivating defect still live and uncaught"); by inference it is the
knowledge-table lint, the only check whose entire post-birth record is two reds both closed by adding a registry
row. A second audit two days later counted twelve of 28 with an attributed catch, because it included the newest
cohort's same-week catches `[A Q1.0–Q1.1]`.

**What agents actually did when a guard fired is the strongest positive result in the corpus.** 236 distinct
red events across 6 sessions; 26 episodes read in full; **24 of 26 were fixed rather than bypassed; zero
episodes show a guard disabled, a baseline re-baked to swallow new debt, or a finding argued away.** The
baseline-rebake flag was never invoked once. The observable weakness is the sanctioned-marker path: a red was
sometimes closed by a justification comment rather than a structural change `[E3 Q1]`.

**Three findings change how to read the yield numbers** `[G §1]`:
- **A red is not a catch.** *"At least half of reconstructable red-to-green transitions were closed by editing
  the test, so a recorded red is not by itself evidence of a caught production defect."* Also 555 of 795 test
  files (69.8%) have neither gone red in 36 recorded runs nor been named in a register entry.
- **The noise had a measured cause.** On one day the daily runner reported 15,386 tests / 11 failures, 8 of them
  machine-local. The operator: *"80% of the alert volume is one machine's environment, and THAT is why nobody
  acts on the runner … the rational response is to stop reading. **Fix is the measurement design, not more
  diligence.**"* An inventory found **117 time-based threshold constants, ~12 genuine staleness gates set
  sub-weekly**, against a confirmed weekly operating cadence.
- **A whole second guard layer was never audited.** The operator's global harness directory holds five
  session-end hooks; **exactly two are registered.** The three unwired ones each implement a block path and each
  quotes a repeated operator complaint as its reason for existing. The one style guard that *was* wired was
  demoted to log-only by operator ruling, because *"a blocked draft is already rendered on the operator's
  screen, so ANY forced rewrite ships as a visible near-duplicate reply."* Its log then accumulated **1,187
  detection events / 2,219 violations over 18 days**, of which 46% were dash-style and **56% of events flagged
  nothing but ordinary capitalised English or universal acronyms** — its two most-flagged tokens being the
  harness's own status vocabulary.

**Catalogue effect.** § 3.3's design rule (structural-shape guards earn their keep; list-policing guards do not)
is confirmed, and its header gains a corollary: **a guard's own clean record is not evidence — six of 28 checks
had a defect found in the check itself while reading clean.** § 6b's "Which of the ~64 checks and the ~22
ratchets ever went RED" closes.

**Confidence: HIGH** for the record, the disposition pattern and every count from the style-hook log.
**MEDIUM** for the identity of the SELF-SERVING guard and the unnamed documentation lint, both inferred.
**Only Wes can add** which guards he *experienced* as saving him — and whether he ever read the style hook's
log, which was written "for periodic self-review" and which no document, report or commit cites.

---

### Q2 — "Was `run_ratchets` ever actually in a pre-push hook?"

**Answer.** Yes, and it still was at the moment of backup. The two contradicting documents are not in conflict:
one says *pre-push*, the other says *commit path*, and both are true — there is no pre-commit hook running
ratchets, so a plain commit runs none. The third cited line is simply stale: it was written **two days before
the hook existed** `[A Q2]`.

**Evidence.** The installed hook is byte-identical to its tracked source and runs three blocking gates: the
ratchet runner, a test-hygiene meta-lint suite, and a critical functional subset. Born 2026-07-13; **2026-07-27
the gap closes** — *"the pre-push ratchet gate existed, was tested, and had never run on this machine"*, and
the test that was green throughout *"passes against a hook whose entire body is `exit 0`, because the comment
text alone satisfies every assertion"*; functional gate added 2026-08-05; made fail-closed 2026-08-15 after it
exited 0 whenever the expected Python was not on PATH (*"7/7 green on one machine and 2 RED on the other at the
same commit, purely from PATH"*); the **installed** copy found stale and fail-open 2026-08-16 because the
installer copies rather than symlinks; gates 2 and 3 made fail-closed-if-absent 2026-08-17; a dry-run flag added
2026-08-17, until when there was no way to run the gates without attempting a push.

**Three things the non-git sweep closes** `[G §2]`:
- **For the whole pre-merge era there was no installed git hook of any kind** — zero hits for the ratchet runner
  or its installer in either predecessor repository. What existed was a pre-commit config *not installed*, a
  planned lint-staging ladder with status OWED, and a *proposed* pre-push guard. So 2026-07-13 is the true
  birth, and the prior state was "designed, written down in three places, never installed."
- **The second machine was suspected ungated as late as 2026-08-16**: *"the pre-push hook may not be installed
  on [the second machine] … If so, [its] pushes have been ungated."* And the test that would have detected the
  missing install was itself a candidate for suppression, because it builds a throwaway repo and attempts a
  push.
- **A third bypass mode nobody had counted: exit-code loss through a pipe.** *"Three commits sat UNPUSHED for
  hours while I reported them pushed"* — a push piped into another command returns the pipe's exit code, not the
  push's, and the gate had blocked them. A gate can be routed around with no bypass-flag trace.

**Catalogue effect.** The assessment's § 8 "internal inconsistency" #1 resolves: the pre-push hook existed, so
the governing weakness ("the only thing between a regression and the corpus was someone remembering") is
**stale**, and the enforcement story is stronger than the retrospectives suggest. This also establishes the
single most load-bearing fact for the whole catalogue: **the push gate is the only mechanism in the corpus that
reliably redirected work** (§ 5.1).

**Confidence: HIGH.** **Only Wes can add** whether he ever used the bypass flag, and whether the second
machine's hook was ever installed.

---

### Q3 — "How much of your own time went into maintaining the memory and doc layer per week, and which single mechanism consumed the most of it?"

**Answer.** About **a third of measured active time, steadily** — 158.4 of 604.9 hours over ten weeks (33.6% of
harness+product), split memory 22.7 h, documents 127.9 h, enforcement 7.7 h. Weekly harness share ran 25–42%,
with one low outlier (11%) and one week where it exceeded product work (56%, the final week). The biggest
mechanism by editing hours is **the session changelog plus pre-compaction handoffs, ~49.1 h** — 31% of all
harness time, 8% of all active time, and a top-three harness mechanism in 8 of 10 weeks `[E2 Q3]`.

**The limit that must travel with those numbers:** active minutes are message gaps capped at 10 minutes and
attributed proportionally; only 16 of 264 sessions have any classified file operation, and nearly all measured
time sits in two long-lived orchestrator sessions kept alive by scheduled wake-ups every ~30 minutes. Read it as
*harness engagement*, not hands-on-keyboard.

**A second instrument names a different winner in a different unit** `[G §3]`. An adversarial reviewer report
measured the always-loaded instruction layer at **111,972 bytes / 918 lines / ~27,992 tokens before any work**,
then:

> *"The 166 memory files carry `description:` fields totalling 166,371 bytes, about 41,592 tokens of authored
> routing metadata … Per the documentation, this metadata is never loaded on its own… **This is the largest
> single block of wasted authoring effort in the system.**"*

and on the pass that rewrote all 166: *"tuned a dial that is not connected to anything."* It also prices one
duplicated rule exactly — a style rule stated in all four instruction files, *"consuming 6,102 bytes, roughly
1,525 tokens, every session, in four places — and it is already mechanically enforced by hooks. This is the
clearest single case of paying twice"* — and notes the whole instruction load is multiplied by every non-fork
subagent, against 4+ concurrent sessions on 57% of days.

Corroboration for the changelog answer, in the operator's voice: an August handoff lists *"a self-churning
[session changelog]"* among the uncommitted working tree; by August its churn was a background constant.

**Catalogue effect.** § 6b's "What the harness cost in hours" closes with a measured range and its limit.
§ 3.2's changelog-and-backlog row keeps **adopt**, but its guardrail becomes mandatory rather than advisory:
*keep the entry short enough that writing it is not the work* now has ~49 hours behind it. And a warning belongs
beside § 3.1's auto-memory row: **authored routing metadata for a recall mechanism you have not verified exists
is a zero-return cost.**

**Confidence: MEDIUM** on the hours; **HIGH** on the byte and token measurements; **MEDIUM** on reconciling the
two answers — they use different units and neither is wrong, but only the second had a zero return *by
construction*. **Only Wes can add** real hours and how long the metadata rewrite took.

---

### Q4 — "Which register did you re-read, and which did you only ever write into?"

**Answer.** Three groups `[E1 Q4]`:

- **Read more than written — genuinely consulted:** the decision record (15 reads to 1 write, i.e. written once
  and read repeatedly), the settled-negatives register (4:1), the results ledger (2.6:1), the breakage-pattern
  catalogue (1.7:1), the guard-rationale document (1.5:1), the issue register (1.4:1), the key-learnings
  document (1.2:1). Almost every read is an *independent* later consultation, not an immediate double-check.
- **Written far more than read — fed, rarely opened:** the session changelog (0.44, and the heaviest-touched
  file in the set), the backlog (0.66), the doc router (0.33), the script manifest (0.35), the compound-insights
  file (0.25). These two also carry nearly all the self-reread activity, consistent with append-then-glance-back.
- **Never touched at all:** one named strategic-discoveries register — zero reads, zero searches, zero writes
  anywhere in 1,127 transcripts.

*Absolute counts are inflated ~3× (§ 1 limit 3); the ratios and the sets are the safe readings. Shell-based
reads are invisible.*

**For the memory register the answer is now direct.** A durable, deduped read log survived on the delivery
drive: **126 records, 14 sessions, June → September.** Of those reads, **64 (51%) are one cross-machine handoff
file** and 24 (19%) are the index; only **34 distinct topic files were ever read**; **140 of 174 live memory
files (80%) have zero logged reads** `[G §4.2]`. The architecture critique's headline is *"the memory system is
write-mostly"*, and its second-tier index — 19.6 KB routing 128 files — *"was read 6 times in 629 sessions. As a
routing surface it is effectively inert."*

**The document side matches** `[H1 §1]`. **572 of 783 curated documents (73%) were never opened** with the read
tool in any captured session; 536 show no activity at all. The never-read mass concentrates in a few whole
subtrees (an external citation library, per-module scaffolding, deep-research material, retired docs) rather
than spreading evenly — a more optimistic reading than "73% of authoring was wasted". **Four named
meta-documents about how to run the harness show zero reads and zero writes** in the whole window.

**Catalogue effect.** § 6b's "The register set: six homes or two" closes on the *read* axis: three or four
registers were consulted and four were essentially write-only — which argues for keeping the decision record,
the settled negatives, the results ledger and the issue register, and for treating the changelog and backlog as
working memory whose cost must be capped rather than as reference material. § 3.2's router row keeps **adopt**
but loses its strongest premise: the router itself was in the write-mostly group, and the second-tier memory
index was read six times in 629 sessions.

**Confidence: HIGH** for ratios and sets; **LOW** for absolute counts. **Only Wes can add** nothing material —
this is now measured on three independent instruments.

---

### Q5 — "Was the KI/SF boundary ever ambiguous in practice?"

**Answer.** No. The shape-based rule held, and the boundaries that actually cost thought were different ones.

**Evidence.** The taxonomy decision gives each register a sharp bar (a bug in the data pipeline versus a fix to
the system we use to do the work), and the fix log's own header carries a "when in doubt" clause — itself
evidence the designers anticipated ambiguity. Across **345 issue-register headings + 114 fix-log headings = 459
entries, exactly one** had to invoke the taxonomy decision by number to justify its classification, and no entry
made the reciprocal argument. No entry was ever deleted from one register and re-added to the other. A topic
that could plausibly have crossed (the fleet detector) stayed entirely on the harness side: 61 mentions in one
register, 0 in the other `[B Q5]`.

**The transcripts agree and sharpen it** `[E3 Q5]`. Every phrasing was searched; a broadened sweep produced 89
candidate lines in 8 sessions, all read. **Exactly one clean ruling exists**, applied in a single line with no
visible weighing. What was genuinely argued: issue-register versus results ledger; issue-register versus session
changelog; issue-register versus a module journey entry; agent report versus anything durable. One
agent-authored lint docstring reasons about the two registers as a *class* and treats them as equivalent, not as
a boundary.

**Two additions** `[G §5]`. Pre-merge, each predecessor repository kept its **own** issue register with
independent numbering, so the same numbers coexisted with different content — the recorded incidents there are
*numbering* collisions, not misfiling. And a decay dimension nobody measured: **13 test files cited by a register
entry no longer exist on disk**, each meaning either a guard was retired without updating the entry or a defect
lost its regression test silently.

**Catalogue effect.** § 6b's "six homes or two" closes on the *routing* axis too: "routes by shape, not
judgment" held. The transferable correction is that the sharp bar was drawn in the wrong place — the expensive
routing decisions were **durable register versus ledger versus changelog versus session artifact**, and none of
those had a written rule. A new obligation attaches to § 3.2's register rows: **a register entry that cites a
test must fail when the test disappears**, because 13 did not.

**Confidence: HIGH.** **Only Wes can add** whether he debated it live in chat that was never banked.

---

### Q6 — "Of the ~74 ADRs from the merge window, how many are still load-bearing, and how many would you not write again?"

**Answer.** The counts are exact; the second half is not answerable from any evidence in the archive.

**Evidence** `[B Q6]`. The decision record holds **91 headings**, numbered to 092, with one number reserved,
never written up, and yet cited by a live code comment as if it existed. Status: 3 reserved-empty, 23 proposed
and never promoted, 64 accepted at some point, 1 superseded-as-written before it ever fired. The merge-window
definition checks out exactly: 78 numbers minus the missing one minus the three reserved-empty = **74
substantive decisions**.

| Scope | Decisions | Cited by ≥1 Python file | Docs only | Nowhere |
|---|---:|---:|---:|---:|
| All 92 numbers | 92 | 56 (61%) | 36 (39%) | **0** |
| Merge window | 74 | **42 (57%)** | 32 (43%) | **0** |
| Post-merge | 14 | 11 (79%) | 3 (21%) | 0 |

**Nobody's citation count is zero** — even the never-written reserved number has a live code citation — because
the project's own convention leaves a decision-number breadcrumb at every relocation. So "cited nowhere" is not
a discriminator here; the 32 doc-only decisions are the better candidate pool for regret, and they are the
process ones whose enforcement is a norm rather than a mechanism. The evidence-based **floor** for regret is
**8 of 74 (11%)**: four decisions the project decided not to make, one superseded before shipping, three
accepted then overturned.

**Two corrections** `[G §6]`. **There is no "too many decisions" complaint anywhere** — four phrasings return
zero hits across all nine source groups, so the archive has nothing to mine for a regret list. And the project
had a **better instrument than citation counts**: a governance map tracing 19 rules to enforcing checks with
BUILT / OWED / PARTIAL / PROCESS status, scored by its companion as ***"~27% of governance is mechanically
enforced; ~73% is advisory or owed"***, with a strong data-correctness perimeter and a weak module-structure
one. That answers the question Q6 actually asks — *what would have caught a violation* — and agrees with the
citation proxy on shape.

**Catalogue effect.** § 6b's "The ADR bar" is reframed rather than answered: the transferable rule is not a
count but **"a decision record is load-bearing when something goes red if it is violated"** — and the project's
own honest score on that test was 27%. § 3.1's "irreversible four" row gains support: the decisions that
mattered were the ones with a rail.

**Confidence: MEDIUM-HIGH** on counts; **HIGH** on the governance score as a quotation; **LOW** on "wouldn't
write again". **Only Wes can add** that list.

---

### Q7 — "When an agent read a stamp saying 'body NOT re-attested,' did its behaviour change — or was the fresh date read as a green light?"

**Answer.** Both, in different roles. **The stamp worked as a writer's discipline and failed as a reader's
trigger.** And before the mechanism existed, a fresh date *was* being read as attestation — the fix entry says
so directly: *"the doc-cleanup pass found the corpus's worst-stale docs hiding under fresh backfilled stamps —
a date alone reads as attestation … an honest 'not actually verified' state must exist and be visible, **or the
absence of red reads as green**"* `[D Q7]`.

**Scale.** 167 files carry the qualifier at the final commit, three months after the fix; 1,391 carry a stamp of
some form. Sampling ten heavily-stamped documents, 6 of 60 stamp-touching commits were pure stamp bumps with
zero body change — and each self-declared the honesty qualifier rather than claiming freshness. The *convention*
held while the *behaviour* it was meant to end kept recurring.

**The transcript evidence is decisive** `[E3 Q7]`. 426 real occurrences in 8 sessions after stripping
always-loaded boilerplate. **Zero assistant text or thinking blocks in the four largest sessions contain the
word "re-attest"** — every agent-side occurrence is inside a tool input (99 edits, 13 shell commands, 9 subagent
briefs, 3 writes). When an agent was already editing a stamped document, the stamp made it scope precisely what
it had re-verified, what it had re-read and found unchanged, what was absent, and *why it could not verify
something* (one stamp names a machine-boundary epistemic limit rather than laziness); in two episodes it drove a
live re-measurement that found and fixed stale content; in one the agent declined to stamp 30 documents and
escalated the choice. But when the stamp arrived as an **alert**, it was read and walked past: a report of
*"24/640 doc(s) carry a mechanical 'body NOT re-attested' stamp — owed a real re-attestation"* is followed in
the very next turn by a readiness summary; the compaction-time stale-docs warning fired 5 times, and the
remediation command it names **ran exactly once in the entire 264-transcript corpus**.

**The pre-history is now measured.** Stamps were in heavy use before the merge — 295 documents in one
predecessor repository, 22 in the other — while the honesty qualifier has **zero occurrences in either**. So for
at least six weeks ~300 stamped documents carried a date with no way to disclaim attestation. Stamp *coverage*
had been enforced since May; stamp *truthfulness* had no mechanism until 2026-06-10 `[G §7]`.

One inverse failure worth carrying: the compaction hook once fired a false loud alarm treating 12
freshly-stamped-but-unattested documents as >30 days stale — *"0 docs were actually >30d; all 12 flagged were
stamped 1 DAY ago"* — so the honesty qualifier had to be split out of the age gate.

**Catalogue effect.** § 6b's "Whether `last-verified` stamps changed behaviour or were read as green lights"
closes, and splits § 3.2's stamp row in two. **Adopt** the writer's half at high confidence — one line naming
what was *not* checked, which is the half that carried the value. **Skip** any reader-side alert, debt report or
periodic re-attestation nudge: 5 loud warnings and 1 remediation run stand against it.

**Confidence: HIGH** for the writer-side behaviour and the ignored-alert result; **MEDIUM** for the negative
claim that a stamp never changed a *reading* decision — silent de-trusting leaves no trace. **Only Wes can add**
whether he ever caught an agent trusting a stale body under a fresh stamp in real time.

---

### Q8 — "How often did the SessionStart carry-forward actually change what the next session did?"

**Answer.** Essentially never — and the project had already measured the adjacent signals and cut them.

**Exact over the whole corpus** `[E3 Q8]`. The session-start hook fired 268 times on startup, 95 on resume and
**151 on compaction**. The carry-forward is gated to compaction, so it fired 151 times in 9 sessions with real
content every time. Reading the first turn after every one of those 9 first carry-forwards: **in 8 of 9 it is
never referenced**; the ninth mentions "a safe housekeeping item flagged by the hook". A mechanical audit of the
80 records after each first carry-forward found **zero sessions** did any of the three things its
recommendation block names.

| Nudge | Sessions nudged | Sessions that ran it |
|---|---:|---:|
| the post-compaction re-orient command | 9 (151 fires) | **0** |
| the memory-consolidation command | 144 | **0** |
| the instruction-file condense command | 0 fired | 0 |
| the worktree-integration command | 130 mentions | **0** |
| the memory export (a plain shell command) | 43 | **8** |
| the chat-bridge command | 143 | 7, plus 8 that ran the script directly |

The single exception is the one remediation that is a plain shell command rather than a slash command.

**The project had already measured this class and acted** `[C Q8]`. A 2026-07-27 commit, *"cut the four
session-end blocks that were 90% of all noise"*, measured across 629 transcripts: a skill-candidate list
**19,274 fires / 43 sessions**; a staleness signal **14,422 fires / 527 of 629 sessions** with *"0-of-10
genuinely stale today"*; an agent-report reminder **13,187 fires / 20 sessions** that *"could never clear"*
because it compared a lifetime count against one session's output. The signals kept, for cause, fired in **1, 3
and 5 sessions out of 629**.

**And the mechanism at the final commit is the end of a narrowing, not the design** `[G §8]`. In the pre-merge
hook there were *two* carry-forward channels and only one was gated: the session-end channel was surfaced
**unconditionally, on every session start**, and its designed content was precisely the two signals later cut as
90% of the noise. Also: one predecessor repository *"has no hooks directory at all"*, so for half the pre-merge
project there was no carry-forward; and a seventh hook was added after the final commit, existing in no commit.

**Catalogue effect.** The clearest move in the set. § 3.1's session-start row — currently **adapt** at medium,
with § 6b's "were the five hooks load-bearing" open — **moves from uncertain to skip for the prescriptive
half.** The diagnostic half (writing carry-forward state) costs nothing and can stay; what must not be rebuilt
is a nudge whose remedy is a command, because 0 of 151, 0 of 144 and 0 of 130 is not a sampling artefact.

**Confidence: HIGH.** Fire counts and zero-invocation results are exact; the follow-through audit is mechanical.
**MEDIUM** only on "no diffuse effect" — one session noted a branch full of memory consolidation *"consistent
with the memory-bloat nudge that keeps firing at session start"*, i.e. the nudge changed what accumulated
without ever being run as the command.

---

### Q9 — "How long was `snapshot_memory.py` silently deleting memories before the memory-deletion register entry was filed, and what was lost?" / "were the restored files ever verified as complete, or only as 'restored'?"

**Answer to the second half first, because it is the transferable one: only as "restored".** The restore path
copies any snapshot file missing from live, never clobbers an existing one, and prints a **count**. There is no
checksum, no manifest comparison, no "expected N, got N" assertion anywhere in it, and its only test asserts
that a missing file gets added and an existing one is not overwritten — not that the restored set is complete
`[C Q9]`. There is also **no dedicated positive control** for the add/update-only fix itself; the four
regression tests are documented as failing pre-fix, which is an assertion in the register rather than a verified
meta-test.

**And that gap produced a live failure, found one day after the final commit, existing in no commit** `[G §9.2]`.
The drive-only copy of the script is 583 lines against the committed 560, and the difference is a real fix to
the path-encoding function:

> *"An export path such as `/Volumes/<drive name>/[project]` is named `-Volumes-…`: the underscore and the
> space EACH become a dash too. Flattening only the separators yields [the wrong spelling], so **`--restore`
> writes into a folder that is never read and still exits 0** — the same silent-onboarding failure the
> separator fix above was written to end, reached through a path containing an underscore or a space rather
> than through Windows."*

This is the predicted consequence realised: a restore that copied nothing, into a directory nothing reads,
returning success.

**How long, and what was lost.** The repo-side answer is bounded by the squash: the fix landed 2026-06-14, five
days after the reset, so the visible window is five days and the true duration is invisible. The non-git
material dates the *origin*: the script exists because the auto-memory is per-user, per-machine, keyed to the
repository path and not in git — *"That is what stranded **~58** project memory files when [the two repos]
merged"* `[G §9.1]`. The traceable loss from the deletion bug is one file: a day-old operator directive whose
substance, per the register, *"survived nowhere"*, reappearing as a new file the same day as the fix.

**A whole class of memory damage the repo-side pass could not see** `[G §9.3]`: an integrity check ignored the
retirement ledger while its sibling honoured it, so **67 declared retirements were reported as orphans
forever**; reachability was seeded only from one machine's index, so *"in a shared pool with per-machine indexes
every peer's memories read as unreachable orphans"* — the correction being *"I reported the 13 as 'possibly
lost, several load-bearing' … **That was wrong. Nothing was lost.**"*; and the one real red left was **8
dangling links in the second machine's index**, because a consolidation on the first machine deleted shared
topic files the other machine still pointed at. Plus, in the operator's voice: *"I pruned 69 tombstoned
memory-snapshot files to make [a check] green and thereby created 69 dangling index entries + 13 dead
cross-references — REVERTED."*

**Catalogue effect.** § 3.1's memory-snapshot row keeps **adopt** and gains a specification it did not have: the
export fix is necessary but not sufficient — **the restore must assert completeness against the manifest, not
report a copy count, and must ship a positive control**; and any path-derived directory name needs a test with a
space and an underscore in it. A second rule belongs beside it: **a consolidation that deletes a shared file
must check every index that points at it.**

**Confidence: HIGH** on the "restored, never complete" finding and on the second defect (a direct diff);
**MEDIUM** on the loss story; **LOW** on duration before the squash. **Only Wes can add** when the mirror-delete
was written, and whether the eight dangling links were ever repointed — the handoff says *"DO NOT silence the
test"*, and no later record closes it.

---

### Q10 — "How did you decide whether a fact belonged in auto-memory versus an in-repo doc?"

**Answer.** The stated rule was *memory holds durable operator framings and working principles; never save what
the repo already records; point at a repo doc for any movable number* — stated in near-identical wording in
three independent places `[C Q10]`. The practised rule, recovered from 24 episodes read with their verbatim
rationale, is one refinement sharper: **memory got the invariant and the behavioural trigger; the in-repo
document got the number, the mechanism and the evidence** `[E3 Q10]`.

**The reasons agents actually gave**, in frequency order: *it generalises beyond this incident* (6 episodes);
*it auto-loads and will therefore bite the next session* (4); *a future session would otherwise re-derive it*
(2); *an operator directive turned standing rule* (2).

**The reverse direction was argued just as explicitly** (3 episodes): a memory was *refused* because the fact
already lived in a durable in-repo home and a second copy would be bloat; another because *"circular gold is
already thoroughly documented — two strong memories … the lever is **not** 'add another memory'"*. The most
disciplined pattern (3 episodes) is the split: author the canonical document, then add a one-line pointer to the
memory index — *"routing to the canonical homes rather than restating drift-prone numbers"*. Four more episodes
broaden or correct an existing memory rather than adding one. Roughly half of the 243 memory writes are hygiene
bookkeeping with no stated reason. **Two episodes show the cost of getting it wrong the other way**: a memory
that had gone stale actively misled the agent that trusted it.

**But the routing half of the rule was unachievable by construction** `[G §10]`. The architecture critique's
central finding: *"The recall mechanism does not exist."* The index claimed second-tier entries auto-recall via
their description field; topic files are not loaded at startup and there is *"no description-matching, no
embedding, no semantic surfacing."* Measured: 40 files linked from the index, **127 reachable only via a
second-tier index read 6 times in 629 sessions**, 110 of 168 never read — and independently, *"I took a
distinctive body sentence from each of 154 topic files and searched all 629 transcripts. **71 of 154 files have
body text that appears nowhere in any transcript.**"* Worse, the two-tier split optimised against a budget that
was never binding: the always-loaded index used **42 lines and 6.8 KB of a 200-line / 25 KB limit**, *"so 127
files were demoted into effective invisibility to reclaim context that was never scarce."* The index also became
the summary it forbids — its own rule caps a routing line at ~120 characters and **19 of its 20 lines exceed
that (95%), mean 275, longest 787**. And subagents inherit the whole instruction hierarchy but **none** of the
memory files, so *"the tier that has absorbed the most design effort is structurally absent from the majority of
executed work."*

**Catalogue effect.** § 3.1's auto-memory row keeps **adopt**, with two hard additions. **The index line is the
only always-loaded surface, so it must carry the durable signal.** And **do not build a second tier or authored
routing metadata until a recall mechanism is verified to exist** — both cost real authoring and returned zero by
construction. § 3.2's semantic-search **skip** is reinforced from a new angle: the recall problem the earlier
project thought it had solved in the memory layer was never solved at all.

**Confidence: HIGH** for the taxonomy and every quoted measurement; **MEDIUM** for the relative frequencies.
**Only Wes can add** the per-file editorial calls.

---

### Q11 — "Which specific `feedback_*` / `project_*` memories earned their keep?"

**Answer.** A small set of **standing prohibitions and epistemic disciplines**, and they steered hard. Roughly
half the referenced memories appear only as objects of memory *hygiene* — drift reconciliation, index
repointing, export — where the file name is mentioned and no discipline is applied `[E3 Q11]`.

**The measured picture.** 211 memory files; **176 referenced at least once** by an assistant-authored block,
concentrated in the top 35. A second channel matters as much: **77 memories were pasted into dispatched-subagent
briefs**, which is how a discipline reached contexts that never auto-loaded it. Eighteen were read in context
and judged. **No memory was observed being overridden.**

**The clearest cases of obedience**, in consequence order:
1. *A go-ahead reaching a session via a peer is not operator consent* — the highest-consequence obedience in the
   corpus: a **49,343-file** shared-resource overwrite was **not performed**. Invoked again the same way for a
   live-database migration.
2. *No unverified absence claims* — the agent caught its own "does not exist" claim as scoped only to the
   repository, corrected the record, then found the artifact.
3. *Key a ratchet on the invariant, not a surface token* — the design of a fix moved from a CLI-shape guard to
   the write chokepoint.
4. *Run the gate before handoff* — the causal link behind the whole Q1 "fix, don't bypass" pattern.
5. *Permanent context optimization* — kept the rule, added a cadence, authored the missing canonical document;
   the most-propagated memory into subagent briefs (16).
6. *Scrutinise the gold* — obedience as restraint: *"This is important and it changes my recommendation."*
7. *Inspect the attribution, not the aggregate.* 8. *Ask questions in the prescribed form* (after a
   self-identified violation). 9. *Fix verified-stale items at the source rather than escalate.*
10. *"Would that test have failed?"* — written as a cross-reference into a register entry and pushed into four
    subagent briefs.

**Three instruments disagree, and the disagreement is the finding** `[C Q11]`, `[G §11]`. By doc-citation count
the winner is a *principle* — a pre-build predicate memory, the most-linked file in the corpus at 33 backlinks.
By *reads* the opposite class wins: *"A handful of files are read repeatedly … They are also, tellingly, almost
all operational facts that are expensive to rediscover — not principles."* By **operator-voice citation as the
reason a decision was made**, a third list appears — and the clearest single instance in the archive is a
calibration memory cited as the sizing constraint in **four consecutive fix-log entries on one day**:
*"Calibrated lean … no new file/register/subsystem; REMIND not block."*

**The uncomfortable coda.** The retirement ledger names **115 memories deliberately killed**, and **13 of the 34
files that were ever read are on that tombstone list** — including that calibration memory. Separately, two
memories that were *obeyed* turned out to be *wrong*, and in both cases the agent that trusted them had a
near-miss before noticing: **obedience without freshness is a demonstrated failure mode.**

**Catalogue effect.** § 3.1's auto-memory row gains a selection criterion: **the memories that change behaviour
are prohibitions and epistemic disciplines, not descriptions** — while the ones that get *opened* are
expensive-to-rediscover operational facts. Both belong; they are different jobs and should be labelled as such.
Second: **propagation into a dispatched agent's brief is a first-class delivery channel.** Third: **a stale
memory is obeyed exactly as hard as a fresh one.**

**Confidence: HIGH** on reference counts and the operator-voice citations; **MEDIUM-HIGH** on the
obeyed/restated judgements (a sample of 18); **MEDIUM** on the read ranking, which is pre-dedup. **Only Wes can
add** whether the most-constraining memory was retired because it had been internalised or judged wrong.

---

### Q12 — "Of the 48 commands, which ten did you use in a typical week?" / "what did `/dispatch` actually do?"

**Answer to the first half: there is no top ten.** The premise does not survive measurement, on three
independent instruments.

(a) Scanning all 1,127 transcripts for the client's command wrapper turns up **four distinct command names,
ever**: the built-in compaction command (112), the chat command (46), the channel-cleanup command (27) and the
built-in model command (26). **50 of the 52 defined commands were never invoked as a slash command anywhere.**
(b) Counting direct file-reads of the command definitions adds eight more with 1–10 reads; combining both,
**only 10 of 52 show any evidence of use at all, and 42 show zero** `[E1 Q12]`. (c) Decisively, the client's own
usage counter survived on the drive — per-command invocation counts with last-used timestamps spanning five
months: **197 recorded invocations, 17 distinct entries, ever.** The single most-used command in the whole
project is a **built-in loop command at 67**, ahead of every project command `[G §12]`.

Meanwhile the command surface grew from 10 to 52 in three months, the architecture document's count of 48 was a
stale derive-live figure, and **8 of the 52 are explicit "superseded by" pointer files**, so the genuinely
distinct workflow count is closer to 44 `[D Q12]`. What ran instead were scheduled tasks executing playbook
steps directly, with no operator and no command involved.

**Answer to the second half.** The dispatch command is a meta/orchestration command with three modes: bare (kick
off a wave — a standing 7-step loop: anchor to the real plan, size the front at 3–5 sessions as a "wide-front
default, not a law", choose topics, keep the main thread productive, fire subagents, track the wave, hand back);
with a task (classify it session-shape versus subagent-shape, then fire a background subagent or scaffold a
paste-ready 7-section brief); and a status mode. Every brief it emits carries **hard rule #0, "STAGE ONLY, never
commit"** — a dispatched agent never commits or pushes; the main thread commits everything in batch. It writes a
**numbered ID range** per brief to prevent parallel-wave collisions, and forbids editing shared hot registers
directly. Against the question's four options: it does not set read-only mode and does not by itself require a
report file; it does mandate a written context, an allocated numbering range where the work allocates decision
numbers, and a learning write-up if a ledger row or substantive finding resulted `[D Q12]`.

**And it was never invoked once** — not in 1,127 transcripts, not in the client's counter — while dispatch waves
demonstrably happened (up to 8 concurrent top-level sessions, 863 subagent transcripts). **It functioned as a
written playbook that sessions followed by hand.**

**Catalogue effect.** § 6b's "The 48-command slash surface" closes. § 3.4's command row keeps **adapt — single
digits** and gains its evidence. Two corrections attach: **a command nobody types is a document** — which is
fine, but it should then be maintained as one; and the assessment's "a door listed but not built is worse than
no door" needs its inverse: **a door built but never opened is a maintenance surface pretending to be an
interface.**

**Confidence: HIGH** on all three instruments. **MEDIUM** on "never invoked anywhere" for the dispatch command,
since the counter is per-machine — though the transcript scan independently found zero.

---

### Q13 — "Did the ~3,500 agent-report exhaust files ever get consulted again?" / "Was there ever a retirement pass?"

**Answer.** Both: the tree grew hugely, **and** it was audited, retired, re-audited and re-consulted — this is
one of the better-managed parts of the estate.

**The retirement pass happened once, deliberately, backed by measurement** `[B Q13]`. A 2026-07-12 commit
untracked the ~3,288-file corpus after *"a 5-agent per-theme harvest (durable knowledge ~95% already promoted to
canonical homes) and a citation-graph pass (**713 cited / 2,487 orphan = 22%/78%**)"*, keeping every file on
disk, preserving them at an annotated tag, and recording a per-theme map of where each theme's findings landed.

**The policy was then corrected five times, each by a measured problem**: the blanket ignore rule was silently
swallowing *new* reports (18 had accumulated untracked); the date-negation globs were prefix-anchored and missed
trailing-date names; 23 reports existed only on branches about to be deleted and 13 of them were cited by live
documents; 18 more were cited by 28 links in live documents including an auto-loading instruction file, so the
link checker was green only because it checks local disk while the shipped export would ship dead links; and the
shipped index named 584 files of which only 36 were tracked, so **93% of the index's own entries were unopenable
by a recipient** — 485 were re-tracked.

**Consultation, measured three ways.** 446 curated documents cite into the tree, naming **960 distinct
reports**. Of the 122 reports whose creation a transcript can prove, **50% were re-read by a different later
session and 50% never were** — against 69% for the reference-document comparison set. But this method sees only
~3–4% of the files on disk `[E1 Q13]`. And a **third consultation pass is documented** eleven weeks later: a
2026-09-04 inventory reopened named June reports as the "before" side of an A/B, *"every asset opened + git-log
+ verdict-tooling verified, not from memory"* `[G §13.1]`.

**One correction to the denominator:** more than half the on-disk corpus is a single **~1,847-file exploratory,
untracked, non-operator-graded batch**, which materially changes how to read the 22/78 split `[G §13.3]`.

A retrospective judgment on the method that produced the exhaust, injected at every session start: *"Review
finished artifacts adversarially; don't run correlated build-panels … **N same-model build-agents are
correlated — their agreement is not corroboration.**"*

**Catalogue effect.** § 3.2's agent-reports row keeps **adopt the separation** and gains three requirements:
count exhaust separately from documentation; **every entry in a shipped index must be openable by the
recipient**, because 93% once were not; and **a report is a session artifact unless promoted** — the promotion
event, not the file, is the durable thing.

**Confidence: HIGH** on the retirement pass, the citation rate, the five corrections and the third
consultation; **MEDIUM** on whether the median report was ever opened twice.

---

### Q14 — "At what doc count did you stop being able to hold the curated set in your head?"

**Answer.** Two answers, four months and ~4,000 documents apart, and the earlier one is the sharper.

**The event the retrospectives describe** `[D Q14]`: between 2026-07-10 and 2026-07-15 the tracked report count
crashes from 3,135 to 12 — not deletion but the mass untrack. At the peak the tree held **~4,286 documents,
~3,135 of them agent reports**, and the citation-graph audit found **78% orphaned**. The architecture document
states the census: *"roughly 4,330 markdown files … but roughly 81% of that is machine-generated agent-report
exhaust … The curated, human-facing documentation set is only about 700 to 820 docs."* The machinery arrived
just before: the doc-intent router 2026-06-14 (itself a response to the instruction file becoming too big), the
semantic-search recall arm and the orphan lint together 2026-07-05, five days before the audit.

**The earlier event** `[G §14.1]`: the first documentation-overwhelm response is dated **2026-04-24, at ~120
files in one repository** — *"Total files inventoried: 120 … Stale/archived: 23 files"* — and the response was
already the mature pattern: a 5-phase plan, per-repository inventories, an inbound-reference tiering map, a move
log and path-migration map, **seven agent proposals**, and a **26-item judgment queue surfaced to the
operator**, under an explicit protocol of "no live-file edits; mechanical fixes apply directly; judgment calls
surface for sign-off."

**And the binding constraint was never the curated count.** It was the always-loaded slice: ~28,000 tokens
across four instruction files, the largest at 2.4× the vendor's stated adherence target. The document census
agrees from the other side: 73% of curated documents never opened, and four named meta-documents about the
harness itself showing zero reads and zero writes in the whole window `[H1 §1–2]`.

**Catalogue effect.** The honest answer is **~120 documents in one repository** — the point at which the
operator stopped reading and started delegating a census and answering a judgment queue. This reframes every
scale-dependent row in § 3.2 (semantic search **skip**, hub-and-companion **skip**, router **adopt**): the
trigger to revisit is not a document count, it is **the first time a census has to be delegated rather than
read**. It also promotes a rule the assessment states only in passing: **the number that binds is the
always-loaded slice, not the corpus.**

**Confidence: HIGH** on both events and their sizes; **MEDIUM** on the causal framing — the April cleanup's
stated trigger is redundancy and staleness, not an explicit "I can't hold this". **Only Wes can add** which of
the two he experienced as the moment.

---

### Q15 — "Did any guard ever cause damage — block a legitimate change, mask a real problem behind a green, or get silenced and then miss something?"

**Answer.** Yes, in all three modes, roughly thirty recorded incidents. The registers are unusually candid,
which makes this the best-evidenced of the three guard questions `[A Q15]`.

**A. Blocked legitimate work.** The recorded stranding: a pre-compaction hook made ≥3 stale documents a hard
block, which *"left a GUI session unable to compact with no command-line to run [the fix], i.e. stranded"*; the
block was removed and the banner reworded from "BLOCKING" to "LOUD WARNING (compaction WILL proceed)". Others: a
path-prefix asymmetry meaning a flag *could never be cleared* even after a correct edit — *"a permanent
false-positive on any touched module (**alarm fatigue**)"*; a collision gate tripping on a legitimate
re-titling; a currency check failing on modification time alone; a cross-platform false negative that **blocked
every backup push** from one machine; a guard that blocked a relay message for merely *quoting* the pattern it
matches; a binding test that *"punished the remediation it exists to encourage"*; and four long-running corpus
checks where *"a check that existed to protect the corpus was itself the thing that stopped the corpus being
updated — not by failing, but by being unfinishable and unwatchable"* (one step took 258 minutes = 96% of
runtime; another produced 37 minutes of zero output before being killed).

**B. Masked a real problem behind a green — the largest category.** The project's own summary: ***"Six of the 28
checks have had a defect found IN THE CHECK ITSELF, and in every case the check's own record read clean while it
was broken."*** Concretely: a lint whose scope tuple named a path that had not existed since the merge
*"reported a clean 138-site baseline while never opening 138 files: 33 real sites in 20 files"* — roughly ten
weeks of meaningless green, found by the daily runner rather than the lint; its twin *"had never scanned [the
second deployment] AT ALL"*; **six code scanners at once** resolved a read-only archive clone instead of the live
tree *whenever run from a worktree — which is where every dispatched agent runs*; the pre-push hook three
separate times (never installed for 14 days behind a source-grep test; exiting 0 whenever the expected Python
was missing, so *"the ONLY blocking gate in the system reported SUCCESS whenever it could not run"*; then the
installed copy silently reverting to the fail-open version); two gates skipping silently and printing OK; the
wire-or-retire lint gated behind a flag the runner never passes, so *"registering it made it RUN and never
BLOCK"*; a six-guard blindness audit in which a database discriminator test *"passes with the constant set to
`/dev/null` or `README.md`"*, three rows compute a floor of exactly 0.0 so a 3,000-row corpus at 0.0% reported
PASS, and 18 of 39 contract features carry a zero floor so a simulated total producer wipeout **passed 18
silently**; a retired guard whose retirement note was wrong, leaving two files encoding **opposite policies for
the same 29 extensions** with *"Nothing has watched this since May"*; and 14 test modules running **zero** tests
and printing OK.

**C. Silenced, then missed something.** Five guards live and green while the routing gold was **99.96% identical
to the router's own output (33,981/33,994) for two months and doubled in size while staying 100% circular** —
one invariant-keyed measurement then found a 42-point gap. Nine of twelve canary suppressions resting on a false
or unproven cause, two silencing columns with live consumers and no fallback. A memory bookkeeping check *"made
green by deleting files that were still REFERENCED"*. Two guards on one field mandating **opposite nouns**, both
passing for the whole period the delivered card printed the wrong quantity. A marker window that stopped
counting when a justification reflowed onto a second line — found **six times in one day across two machines
working independently**. And the sharpest line: a proximity check failed and the commit it blamed had only
reworded a message — *"the check did not fail because code changed, it failed because **A COMMENT GOT
LONGER**."*

**Four additions from the non-git material** `[G §15]`:
- **The stranding was a regression against a written decision.** The pre-merge hook says, a month earlier:
  *"This hook intentionally does NOT block — we want REMIND, not gate, per … the operator's 'REMIND not BLOCK'
  preference … If a future use case wants blocking … the machinery is here."* It was made blocking anyway,
  stranded a session, and was reverted. **The machinery was left in place with a note saying how to turn it on,
  and someone did.**
- **A guard whose remedy itself did damage.** The style guard's fix was to force a rewrite — but a blocked draft
  is already on screen, so *"ANY forced rewrite ships as a visible near-duplicate reply."* The guard was correct
  about the writing and wrong about the remedy. Its earlier denylist design *"reported green while the operator
  was reading an unreadable message — the exact false-green class this session spent the night eliminating
  elsewhere."*
- **The scope-fence defect was known and deferred, not undetected.** The identical fence bug was fixed in one
  lint on 2026-05-31, and the same entry records *"the sibling … STILL excludes [the main tree] … left as a
  follow-up … lower-danger."* One un-propagated fix left at least three lints scanning the wrong tree for up to
  eleven weeks.
- **"A GUARD THAT PINS A SPELLING ARGUES AGAINST ITS OWN FIX — FOUR instances today"**, with numbers: a binding
  test that pinned a live defect and went red when the defect was fixed; an assertion that accepted a retired
  path; a test pinning a deliberately-broadened literal; and a test requiring one call within **2,000
  characters** of another, measured gap **2,392** after someone added a comment. Rule adopted: *"Assert what the
  code must DO, never how it is written."* And generally: *"A binding test pinned to a live defect argues against
  its own remediation — and the cheapest way back to green is to WEAKEN THE LINT. Pin to a FROZEN copy of the
  lived shape instead."*

**One undamaged thing, recorded for balance:** *"The irreversible-path guards and the calibration discipline
stay. They are why a wrong reach number never reached the operator."*

**Catalogue effect.** § 3.3's five design rules all gain harder evidence, and two need extending. **THE SECOND
RULE** (every gate ships a constructed-bad-state positive control) must extend to **the gate's own scope**: the
commonest self-defect was a dead scope fence, which a positive control planted *inside* the fence would catch
and one planted outside would not. **THE THIRD RULE** gains two corollaries: *assert what the code must do,
never how it is written*, and *never pin a binding test to a live defect*. And a new high-confidence row is owed
on **guard remedy design**: the remedy a guard imposes can cost more than the defect, and the operator pays it.

**Confidence: HIGH** throughout. **Only Wes can add** how much work was abandoned rather than fixed when a gate
went red — a bypassed push leaves no trace.

---

### Q16 — "Is Insight Miner's auto-memory deliberately keyed to the Desktop working directory rather than the repo path?"

**This is an Insight Miner question, not one the archive can answer.** Current state: **the memory is now keyed
to the repository**, not a Desktop working directory. The archive's only contribution is the failure class: the
earlier project's memory was path-keyed and off-git, and the merge of two repositories *"stranded ~58 project
memory files"* `[G §9.1]` — which is why its snapshot script exists at all.

---

### Q17 — "Is there a decision record for why the fleet-monitor detector and heartbeat were REMOVED entirely rather than fixed?"

**Answer.** Yes — a full, explicit decision record, and it is unambiguously "delete rather than fix". The stated
reason is a signal-to-noise judgment by the operator, **not** a technical failure of the detector, made about
three weeks after the same detector was carefully built and hardened `[B Q17]`.

**The record.** The decision (accepted 2026-07-14, operator-directed) explicitly reverses its predecessor:
*"In practice the 5-min × N-machine beat cadence was a constant, burdensome [chat] notification stream — the
operator judged the noise not worth the marginal fleet-liveness signal."* It deletes the detector scripts and
their three tests, strips two steps from the maintenance loop, deregisters the scheduled task, retires two
design documents, and marks the fix-log entry that built it REVERSED. Liveness then rests on four
already-existing mechanisms. The predecessor it reverses was the careful construction of exactly what was torn
out: *"red-teamed by 3 reviewer agents + full-context re-evaluated + QE-reviewed"*, built to eighteen hardening
gates, with 54 passing tests. **No attempt to fix the noise is described** — no raising the interval, routing to
a quieter channel, or making it opt-in.

**The number behind the judgment survived.** The detector's own alert ledger was recovered from the global
snapshot, in full: **two routine alerts ever, and the genuine-alert log empty.** Over its whole life it recorded
**zero genuine alerts** `[G §17.1]`. That converts the removal from a judgment call into a measured one. Two
codas: a month after removal a detector-shaped notification prompted a deliberate check for surviving dead code,
under the rule *"if post-removal → something runs dead code and THAT is the finding"*; and the removal left
register debt — three deleted test files are still named by register entries a month later.

**Catalogue effect.** § 3.3's use-triggered-maintenance row keeps **adopt the doctrine** and gains the strongest
supporting number in the corpus. The transferable rule is sharper than "prefer detect-and-warn": **give every
alerting path a ledger of genuine versus routine alerts from day one, and let the ledger decide whether it
survives.** That single artefact is what made this removal defensible rather than arbitrary — and it is directly
relevant to the planned failure-notification ping.

**Confidence: HIGH** on the record; **MEDIUM** on reading the empty log as lifetime-empty. **Only Wes can add**
whether a specific incident tipped the judgment.

---

### Q18 — "What is Insight Miner's 'irreversible few'?"

**This is an Insight Miner question.** Current state: **not yet written.** The archive's contribution is the
selection criterion: the earlier project's four were placed in the always-loaded file precisely because they are
*"the rules where 'the rule arrived late' means the damage is already done"* — and the strongest candidate from
this evidence is the one its own irreversible set already contained: never arm a session-bound watcher for a
long detached operation.

---

### Q19 — "Do you run parallel agent sessions, or one at a time?"

**The Insight Miner half is Wes's to state.** What the archive settles is the earlier project's answer, which is
what the four coupled mechanisms (worktrees, dispatch waves, the id broker, the one-committer invariant) were
built for.

**Parallel was the default, decisively** `[E2 Q19]`. Over 264 top-level sessions and 69 days: every session
overlapped at least one other (partly mechanical, since a few ran 3–26 days); **maximum simultaneous top-level
sessions at one instant: 8**; only **9 days** had a single session all day; **4 or more on 39 days (57%)**; 5 was
the most common non-trivial value. And this **excludes** subagents — up to 256 under one parent — so real
concurrency was higher.

**There was a written doctrine, injected at every session start, and measured behaviour matches it almost
exactly** `[G §19.1]`: *"**Parallelize by surface-disjointness, not by count** — fan out only when work
decomposes into disjoint, low-conflict fronts … parallel threads on a shared write surface is the invented-work
anti-pattern … **Conflict-gated, not count-gated (~5 sessions comfortable).**"* Plus a mandatory workspace rule:
*"a dispatched/parallel session self-isolates FIRST … add a worktree **BEFORE editing**, then **STAGE-only** …
the shared main checkout belongs to the integration thread ALONE."* And on compaction resume: *"re-establishing
a planning posture is the win, not manufacturing a parallel wave."* The harness also enumerated live sibling
sessions at every start, specifically to prevent a double-dispatch class.

**Three costs are recorded.** A purpose-built audit log records **nine "live-steal" events** across five weeks,
each one session taking a singleton chat listener from another. The one-committer model came under strain in the
operator's own voice: *"I AM FROZEN ON MAIN. DO NOT LAND ANYTHING UNTIL [the other machine]'S MERGE IS IN
FLIGHT … I put 12 commits on main today while it worked — **my velocity was the problem, so I stopped.**"* And a
"failed" push turned out to be a concurrent-push ref collision from two processes racing, concluding *"Serialize
pushes."*

**One unresolved tension.** Worktree self-isolation was **mandatory doctrine with a one-step launcher**, yet
measured usage was **7 of 264 sessions (2.7%)**. Either the rule was widely not followed, or the instrument
cannot see it (the launcher's name contains no worktree path, and 863 subagent transcripts were out of that
scan's scope) `[G §19.5]`.

**Catalogue effect.** § 3.4's one-committer row moves from **adapt / medium** toward **adopt**: the invariant is
stated to hold within a machine as well as across machines, and the recorded strain is about *velocity*, not the
invariant. The dispatch-machinery row keeps **skip the machinery**, with one exception forced by Q22: if
stage-only is ever adopted, the id allocator cannot be max+1-from-the-file. And one doctrine line is worth
lifting verbatim into any parallelism guidance: **conflict-gated, not count-gated** — measured behaviour matched
the stated target of ~5 three months after it was written.

**Confidence: HIGH** for concurrency mechanics and the doctrine; **MEDIUM** for what "8 concurrent" means
qualitatively, and for the worktree tension, which the archive can establish but not resolve.

---

### Q20 — "With hindsight, which ONE mechanism would you rebuild first on day one, and which would you never build again?"

**This is a judgment question and the archive cannot answer it.** It can supply the default the evidence points
at, which Wes can accept or overturn.

**Rebuild first: the blocking gate at the push boundary.** It is the only mechanism in the corpus that reliably
redirected work. 236 recorded gate reds; in 24 of 26 episodes read, the agent named the finding as its own and
fixed it; zero disables, zero baseline re-bakes, zero arguments. Every warn-only channel was read and walked
past `[E3 cross-cutting]`.

**Runner-up, and arguably the real answer: a small set of standing prohibitions in the always-loaded surface.**
The single largest behavioural intervention in the corpus is a memory, not a hook — a 49,343-file shared write
refused because the go-ahead came from a peer session rather than the operator.

**Never build again**, on this evidence: (1) **authored routing metadata for a recall mechanism you have not
verified exists** — ~41,600 tokens, rewritten once, connected to nothing; (2) **a warn-only nudge whose remedy
is a command** — 0 of 151, 0 of 144, 0 of 130; (3) **a second-tier index** — read 6 times in 629 sessions while
demoting 127 files into invisibility to reclaim a budget that was never binding; (4) **a style guard that judges
prose** — 56% of its events flagged nothing but ordinary English, and its own remedy shipped duplicate replies
to the operator.

**Confidence: LOW** as an answer to the question as asked; **HIGH** in each supporting measurement.

---

### Q21 — "Are Insight Miner's 24 live suppressions `accepted` or `open`?"

**This is an Insight Miner question.** Current state: **the 24 are still without status.** The archive's
contribution is the cost of not doing it: the earlier project reached **2,250 grandfathered entries across 13
baseline and allowlist files**, one holding **1,319** against two documented real defects, and of 18 such files
only **four ever shrank — and only two because debt was paid** `[A Q1.3]`. Its own registry states the
principle: *"918 grandfathered suppressions, 866 of them in THREE lints … Those three have therefore **never
forced a fix to existing code; they only tax new code. A baseline that only grows is a guard being SATISFIED,
not obeyed.**"*

---

### Q22 — "Do you ever leave work staged but uncommitted across sessions?"

**Answer. Yes — routinely, and by design.** This settles the id-allocator question, and it settles it against
the assessment's proposed replacement.

**The doctrine.** Every dispatched or parallel session was *required* to **stage only**, with the integration
thread on shared main doing all committing — stated in the session-start posture block and again as hard rule #0
in the dispatch playbook `[G §22.4]`, `[D Q12]`. Staged-but-uncommitted was the intended end state for the
fleet.

**The measurement, read against that doctrine** `[E2 Q22]`. 12 of 264 sessions ran at least one `git add`; 9 ran
at least one `git commit`; **6 sessions (2.3%) ended with the last `git add` never followed by a commit**, all
six clustering in July. One of them ran 28 adds and 22 commits over a 22-day span and *still* ended on an
uncommitted add. The "began with staged changes" half is under-powered (n=4, of which 1 showed staged changes).
Given the doctrine, **2.3% measures the integration thread's discipline, not the fleet's.**

**Why this matters: it disqualifies max+1-from-the-file as an allocator.** The recorded failure is exactly this
shape — duplicate register numbers *"from grep-the-highest-and-add-one"*. It does not require two concurrent
agents; it requires two reads of the file separated by an unwritten allocation, which is the normal state of a
stage-only workflow. And it is not a monorepo artefact: **the earliest recorded duplicate predates the merge by
three months**, in a predecessor repository, fixed by renumbering to "current max + 1" — the same mechanism that
later produced seven collisions in one August cleanup `[G §22.1]`, `[B Q5]`.

Two further findings on the same class `[G §22.2–22.3]`:
- **A collision in a shared counter, not a register**: *"The ratchet count pin is a TRAP. [One machine] moved it
  to 20 by adding two lints; I ALSO moved it to 20 by promoting a third. **Same number, different arithmetic** …
  the pin exists so a DROPPED ratchet goes red, so resolving it wrong fails exactly the way it is meant to
  prevent."* Resolved by recomputing from the union of both lists rather than either literal — *"the coincidence
  WAS the trap."*
- **The fix was designed in June and never approved.** A 2026-06-16 fix-log entry lists *"proposed companion
  hardenings awaiting operator nod: **per-machine reserved ranges**"*. The seven-collision renumbering is
  2026-08-16, and an August handoff still lists the renumbering among parked operator decisions. **The fix
  existed on paper for the whole period the collisions kept happening.**

**Catalogue effect.** § 6a row 4 (§ 5 #8, "replace the ID broker with a ten-line allocator that computes max+1
from the file") is **settled against the first pass**: the proposed replacement is the mechanism that produced
the recorded failure. The call moves to **the date-stamped id as the DEFAULT, because it cannot collide by
construction**; a max+1 allocator is acceptable only if the read and the write are one operation *and* it sees
staged-but-uncommitted entries. Dropping the reserved-range *ledger* stands either way. A generalisable second
rule: **never resolve a numeric conflict by agreement between two sides; recompute from the union.**

**Confidence: HIGH** for the ends-staged count and the doctrine; **LOW** for the begins-staged rate (n=4).
**Only Wes can add** why the reserved-range proposal was never approved.

---

### Q23 — "Did the PreCompact rf-check subset ever surface anything at a compaction?"

**Answer.** It surfaced something at **every one of 151 compactions and never once reported a clean tree** — and
that is the problem, not the vindication. Its threshold sat below the project's normal working state, so nothing
distinguished an ordinary night from a bad one.

**The exact profile** `[E3 Q23]`. The hook suppresses its carry-forward block when clean, so **"nothing to
report" occurred 0 times out of 151.**

| Reported condition | Occurrences (of 151) |
|---|---:|
| unintegrated worktrees (dirty / ahead / uncommitted reports) | **130** |
| a critical-check line present | **140** |
| — 0 FAIL · 1 WARN | 99 |
| — 0 FAIL · 2 WARN | 22 |
| — 0 FAIL · 3 WARN | 15 |
| — 0 FAIL · 4 WARN | 4 |
| — **any FAIL** | **0** |
| uncommitted decision-capture files | 22 |
| modules touched without a journey update | 9 |

One check accounts for 96 of the 140 first-named warnings. **The critical subset never produced a single FAIL in
the whole corpus.**

**A visibility finding that reframes the mechanism.** The hook's rich banner — the punch-list an operator sees
in a terminal — **never reaches a transcript at all**: zero occurrences of its signature strings in all 264
files. Everything the agent saw came through a small system message and the next session's replay. The detailed
half was addressed to Wes; the thin half to the agent.

**Two additions.** The one instance the repo-side pass found — a surviving on-disk state snapshot showing one
warning on a capture-frontier check `[C Q23]` — is the *same* check that fired on its **first live run** three
months earlier with the same class of condition; it fired at both ends of its life and the condition was never
cleared. And for a period the critical subset was **wired into the wrong copy of the hook**: the edits went into
a second, hand-maintained copy that does not run from the launch directory, so *"the learnings-lag check never
actually fired."* The guard against recurrence was left OWED, with an open question attached — *"whether [the
second hooks directory] should exist at all"* `[G §23.1–23.2]`. Finally: **41 of 46 pre-compaction handoffs
mention the hook, and not one cites a surfaced warning as the reason for anything.**

**The one genuine design success** is that it never blocked. After the hard block stranded a session, the hook
was changed to warn-and-proceed, and nothing in 264 transcripts shows a compaction being obstructed.

**Catalogue effect.** § 6a row 6 (the pre-compaction hook: "drop the critical subset") is **settled — the subset
is a skip.** The steelman's argument was sound (a compaction is an operation boundary in exactly the sense the
guard-design rule defines) and the implementation still failed, for a reason worth carrying: **a check whose
threshold sits below the normal working state stops carrying information.** 140 reports and 0 FAILs, with the
same finding 130 times, is a steady-state readout, not a detector. The other two halves are confirmed at high
confidence: **adopt the carry-forward write, and adopt the never-hard-block rule** — the latter now doubly
evidenced, since the stranding was a regression against a written decision (Q15).

**Confidence: HIGH.** All counts are exact and the 0-FAIL result is a full-corpus count. **MEDIUM** only on the
handoff absence.

---

### Q24 — "How did you actually stop a fetch — what told you a source was exhausted?"

**Answer.** A novelty-run stop rule with a safety floor, mechanised 2026-06-28. For each large, stable bucket the
fetcher feeds every fetched item's **near-duplicate signature key** into a tracker. Every **100** items it asks
whether that window added at least **1** genuinely new key. If it added none, and at least **500** items have
already been seen, that is a "quiet" step. **Three consecutive quiet steps → saturated, stop** — i.e. 300
straight items introducing zero new shapes. A hard ceiling of **7,000** stops a bucket that never goes quiet,
and a much higher ceiling exists for a manually-run deep-fetch tool that deliberately never saturates `[D Q24]`.

**The five constants landed together and never moved.** What changed six times was *who the rule applied to* and
*the formula around it*: banked as an opt-in tool (2026-06-28); folded into the recurring fetcher behind a
default-off flag (2026-06-30); activated on operator go-ahead (2026-07-11) on a written claim that it was
"additive-only"; a scoping bug found **the same day**, because the predicate caught both the primary pass and a
deliberately shallow legacy pass, deep-fetching ~1,740 legacy buckets against an intended cap; single-sourced
and **every bypass deleted** (2026-07-19) — the environment kill-switch and the CLI flag both removed, with an
unregistered attempt now raising rather than silently defaulting off, on the reasoning *"a boolean bypass that
exists will eventually be set, by some machine or some agent, and the corpus degrades SILENTLY"*; a
log-attribution contract added (2026-07-28); and the important correction (2026-08-13).

**The correction is the part worth carrying.** The "additive-only" safety claim was **false**: it reasoned about
the fetch *target*, not about where the stop rule actually fires. With the locked parameters the earliest
possible stop was 700 items, so **any bucket whose non-stopping target exceeded 700 was at risk of being
under-fetched — measured as 51 of 161 eligible buckets (31.7%)**, with live shortfalls up to 1,922 items on a
single bucket. The fix makes the tracker take a **required** target argument and sets
`safety_floor = max(safety_floor, flat_target)`, so the rule structurally cannot fire before the bucket has
captured at least what the old path would have.

**A sibling stop rule fired catastrophically early.** A low-yield "plateau" early-stop abandoned a plan of
10,338 items after only **25 items (0.24% of the plan)**, because its checkpoint was absolute rather than
relative to plan size and the 25-item sample was biased toward dormant buckets by construction. The honest limit
is recorded too: replaying the real numbers, even the new 5% floor **would still have fired**; the exemption,
not the floor, is what saves that source. A prior instance three weeks earlier had been downgraded from FAIL to
WARN on the reasoning that it was *"a saturation signature, not breakage"* — conflating two mechanisms under one
alarm, while the gate's exit code was being discarded downstream anyway.

**What the operator actually experienced** `[G §24]`, written with a saturating fetch live: *"**DO NOT trust any
per-pass attribution from that log.** All three passes write to ONE unlabelled log … **I twice reached a wrong
conclusion from it** … Get the authoritative per-source result from [the top-level command]'s final output when
it exits — not from the log and not from the process table."* The acceptance test set for the fix is the
cleanest statement of the requirement: ***"the log alone can answer *did legacy saturate*."*** Also: *"The
remaining pass's ETA has been reading in the thousands of minutes. Treat that number with suspicion — the same
ETA lied by two orders of magnitude on the beta pass earlier today."* And the conflation correction was carried
forward as a standing instruction so a future session would not make the test green the easy way: *"must be
REWRITTEN not satisfied."*

**Catalogue effect.** § 3.3's saturation row keeps **adopt the shape** and gains two design points the
assessment does not have: **(5) the run's own log must answer "did this source stop, and why" without recourse
to any other instrument** — nine days of ambiguity produced two wrong operator conclusions; and **(6) a stop
rule must never be able to fire below what the non-stopping path would have collected.** Plus one general rule:
**never downgrade an alarm to WARN to resolve a conflation — split the mechanisms.**

**Confidence: HIGH** on the mechanism, constants, dates, both defects, and the operating experience.
**Only Wes can add** the informal signal, before 2026-06-28, that told him a source was tapped out.

---

### Q25 — "Did the 'packet' loop's pre-registered decision rule ever survive contact with labels you disagreed with?"

**Answer.** There is no recorded instance of the rule meeting a label Wes disagreed with — because there are
only **two runs, ever**, and he accepted both. A sibling mechanism shows the dynamic, and it went the other way.

**The protocol** `[D Q25]`. Stood up 2026-07-06: a *packet* is a self-contained stratified sample of real rows,
each carrying everything needed to judge without digging, handed to Wes or a QE for a **blind** labelling pass.
The labels are then ingested through a **pre-registered, count-aware, plausibility-not-causality** rule: verdicts
split, "unsure" kept in the denominator, results reported stratified and never collapsed to one accuracy figure,
and the pass/fail bars fixed and operator-blessed **before the labels are seen**.

**Both runs.** Run A (2026-07-06): N=50 stratified rows; pre-registered bars *"proceed if credible <70% OR
incorrect+unlabeled >40% on EITHER slice"*; result 14.3% credible on one slice, 27.3% on another, unsure
66.7%/72.7% — **both slices tripped PROCEED**, and the journey document states plainly *"The operator greenlit
the response."* Run B (2026-07-13, independently re-derived 2026-07-14): 30 queries / 316 labelled rows; lexical
search binds, dense semantic does not; the next day an independent re-derivation reproduced the number exactly.
**No recorded disagreement in either.** No third run exists anywhere.

**The closest thing to the question's scenario is a sibling mechanism, and there the verdict lost.** A finding
that a printed reliability figure predicted correctness was **VOID — RETRACTED on operator challenge**:
***"THE OPERATOR CAUGHT IT FROM THE ARITHMETIC ALONE"*** — Wes noticed the correlation's mean and median flipped
sign depending on how it was cut, exposing that the two sides being correlated had been graded on different card
versions, making the join invalid. So when a data-driven verdict *about Wes's own labels* met his scrutiny,
**the verdict lost, not the scrutiny.** A prior finding cuts the other way: a deeper re-grounding of banked
labels flipped **~34.8% (16 of 46)**, and the flips cut across even operator-adjudicated labels.

**One terminology correction** `[G §25]`. "Packet" names two different mechanisms and the older one is much
larger: 96 pre-merge hits are all **operator-review packets** — per-module dossiers handed over for sign-off,
with their own currency guard. The blind-labelling sense is entirely post-merge. Any count of "packet" over this
corpus is dominated by the older sense, so the careful scoping to ledger rows was right and the "only two runs"
finding is safe. The later mechanism is best read as the **third generation** of a
hand-the-operator-a-self-contained-artifact pattern.

**Catalogue effect.** § 3.4's packet row keeps **defer-with-trigger** at medium and gains a caution: **the
mechanism was run twice in three months.** For a single-operator project that is the realistic cadence, which
argues for writing the rule down cheaply and not building machinery around it. It also gains the clause that
most needs preserving on transfer — *the bars are fixed before the labels are seen* — because the sibling case
shows what happens when a decision rule is applied to data whose join was never checked.

**Confidence: HIGH** that only two runs are recorded and both were accepted; **MEDIUM** on the overall answer.
**Only Wes can add** whether he privately disagreed with either verdict.

---

### Q26 — "Was `⛔ DO NOT REDISCOVER` ever obeyed?"

**Answer.** Yes as a code guard — and no as a fence, until it stopped being alone.

**Obeyed at the code level, verifiably** `[C Q26]`. The marker guards a deliberately counter-intuitive ordering.
Tracing every commit touching those exact lines: five commits, one of which introduces the ordering and the
marker together, and **none of the later ones reverts the precedence.** In the transcripts the marker appears 16
times across 2 sessions, collapsing to **3 distinct episodes, all read, all obeyed; zero episodes show an agent
editing anyway** `[E3 Q26]`:
- **The ideal outcome.** A census subagent met the marker, did *not* re-open the settled question, said so
  explicitly — and still reported a genuinely distinct downstream defect it measured itself: *"The defect here
  is not undisclosed — it is disclosed, quantified, and then re-introduced by the reanchor step."* It modified
  nothing.
- **Propagated.** An agent authoring a new precedence table carried the marker forward into it rather than
  re-deriving the ordering — *"This is the settled answer, not a tunable"* — and assembled the full enforcement
  map under the heading *"why you can't accidentally re-open this"*.
- **Cited as evidence the marker was insufficient.** A diagnosis agent filed it under *"CONFUSING
  (correct-but-uninterpretable; the friction source)"*, noting that the existence of the cure *"is itself
  evidence of how much confusion this one design point generated."*

**Not obeyed at the level it was written to serve.** The project's own record: *"This question has recurred many
times (most recently … when a morning leg-diff 're-discovered' it with a worse method and nearly flipped a
correct answer)"*, with the cause named: ***"ROOT CAUSE of the recurrence = no single home.*** The answer was
real but scattered across 5 places … so every fresh session (incl. me this AM with a leg-diff) re-derived it from
partial context."* The fix was not "trust the marker harder" but a four-part escalation: a canonical landing
page, one-hop pointers at every entry point, a tool-use tripwire on the relevant searches and diffs, and an
always-loaded memory. Four independent subagent contexts encountered the marker in situ, none edited the guarded
ordering, and by August it had been promoted to a **named category** in the project's vocabulary for in-code
markers `[G §26]`.

**Catalogue effect.** § 6a row 7 (docstring markers, "cap at three") is confirmed in the direction the steelman
argued: **`⛔ DO NOT REDISCOVER` deserves naming on day one**, and the count is not the criterion. But the
adoption must carry the lesson the marker's own history teaches, which the assessment does not yet state:
**a "do not rediscover" marker is a pointer, not a fence — it holds only if every path to the question passes a
pointer to it.** A bare in-code comment is reachable only by whoever already opened that file, which is why the
question kept being re-derived by sessions that never did. The transferable unit is *marker + canonical home +
one-hop pointers from every entry point*, ideally with a tripwire on the tools that lead there.

**Confidence: HIGH** for the obeyed/never-defied result and both halves of the split; **MEDIUM-HIGH** for "the
marker alone was insufficient", since the pre-fix rediscovery sessions are not in the transcript archive.
**Only Wes can add** how many distinct sessions re-raised the question before the canonical document.

---

## 4. What the evidence changes in the catalogue

Rows from §§ 3 and 6 of the harness assessment whose transfer call should move, with the evidence line that
moves it. Rows not listed are unaffected or merely strengthened.

| Catalogue row | Was | Moves to | The evidence line |
|---|---|---|---|
| § 3.1 SessionStart carry-forward (with § 6b "were the five hooks load-bearing") | adapt (thin version), medium / uncertain | **skip the prescriptive half; keep only the state write** | 151 fires, referenced in 1 of 9 sessions, zero follow-through in a mechanical audit, every named command remediation at 0 invocations (0/151, 0/144, 0/130) |
| § 3.1 PreCompact critical subset (§ 6a row 6) | uncertain — "a small subset at a boundary is not a clock" | **skip the subset; adopt the carry-forward write and the never-hard-block rule at high confidence** | 140 reports, **0 FAILs ever**; the same worktree finding 130 of 151 times; the threshold sat below the normal working state |
| § 5 #8 / § 6a row 4 — the ID allocator | uncertain — "a ten-line allocator that computes max+1 from the file" | **adopt the date-stamped id as the DEFAULT; rule out max+1-from-the-file** | Stage-without-commit was the *designed* end state, and the earliest recorded duplicate predates the merge by three months and was created by exactly that allocator |
| § 3.2 `last-verified` stamps (§ 6b row) | adapt (honesty half), medium | **adopt the writer's half at high confidence; skip every reader-side alert** | The stamp appears only in what agents *wrote* (0 occurrences in visible reasoning in the four largest sessions); as an alert it produced 5 loud warnings and 1 remediation run in 264 transcripts |
| § 6b "The register set: six homes or two" | open | **close: two registers is right, but write the routing rule for the layer above them** | 1 of 459 entries needed the taxonomy decision; 0 deliberations in 264 transcripts — while register-vs-ledger, register-vs-changelog and report-vs-durable were argued repeatedly and had no written rule |
| § 6b "The 48-command slash surface" (and § 3.4's command row) | open / adapt to single digits | **close: adopt single digits, and treat an uninvoked command as a document** | 197 recorded invocations in five months, 17 distinct names ever; the most-used primitive was a built-in; the dispatch command was never invoked once while its waves demonstrably ran |
| § 3.1 path-keyed harness (§ 6a row 5) | uncertain — invariant or rail | **adopt the rail** | The restore path silently no-opped on any path containing a space or an underscore and still exited 0 — found one day after the final commit, and the fix exists in no commit |
| § 3.1 memory-snapshot script | adopt (export fix as spec) | **adopt with two additions: assert completeness against the manifest, and ship a positive control** | Restore reports a copy count and nothing else; its only test does not check completeness; no positive control exists for the deletion guard |
| § 6b "Which checks ever went RED" | open | **close, with a correction to § 3.3's header** | 12 guards observed red; two lints with repeat catches; **6 of 28 checks had a defect found in the check itself while their own record read clean**; at least half of red→green transitions were closed by editing the test |
| § 3.3 THE SECOND RULE (positive controls) | adopt | **adopt, extended to the guard's own scope fence** | The commonest self-defect was a dead scope path — a clean 138-site baseline reported *while never opening 138 files* |
| § 3.3 THE THIRD RULE (marker windows) | adopt | **adopt, plus "assert what the code must DO, never how it is written" and "never pin a binding test to a live defect"** | Four dated instances in one day, including a check requiring one call within 2,000 characters of another and measuring 2,392 after a comment grew |
| § 3.3 use-triggered maintenance | adopt the doctrine | **adopt, plus: give every alerting path a genuine-vs-routine ledger from day one** | The removed detector's own ledger recorded two routine alerts and **zero genuine alerts** across its whole life — which is what made deleting it defensible |
| § 3.3 saturation / fetch stop rule | adopt the shape (four design points) | **adopt with two more: the run's own log must answer "did this source stop, and why"; the stop rule must not fire below the non-stopping path's yield** | Nine days in which per-pass attribution was unrecoverable and the operator drew two wrong conclusions; 51 of 161 eligible buckets (31.7%) exposed to under-fetching |
| § 3.4 one-committer invariant | adapt, medium | **adopt** | Stated to hold within a machine as well as across machines; the only recorded strain is velocity ("I put 12 commits on main today while it worked — my velocity was the problem, so I stopped") |
| § 6a row 7 — docstring markers | uncertain (the count) | **adopt `⛔ DO NOT REDISCOVER` explicitly, as marker + canonical home + one-hop pointers** | Obeyed in every episode where an agent met it; but a bare comment did not stop the question being re-derived by sessions that never opened that file |
| § 3.2 agent-report exhaust split | adopt the separation | **adopt, plus: every entry in a shipped index must be openable, and a report is a session artifact until promoted** | 93% of the shipped index's own entries were untracked and unopenable by a recipient until a rescue pass |
| § 3.1 transcript archive | adapt (schedule the sweep) | **adopt, plus: dedup on tool-call id, and write findings to a durable log** | A naive per-line scan over-counts ~3×; the earlier project built a durable read log precisely because the transcript window decays |
| § 3.1 auto-memory | adopt | **adopt, plus: the index line is the only always-loaded surface, and no second tier or authored routing metadata without a verified recall mechanism** | ~41,600 tokens of routing metadata for a feature that does not exist; a second-tier index read 6 times in 629 sessions; 80% of topic files never opened |

---

## 5. Cross-cutting findings

In order of how much they should change what gets built next.

### 5.1 What fired versus what redirected work

Every *detection* half worked. Every *prescription* half was inert.

- 151 of 151 compaction sweeps fired with real content. 268 session-start banners fired. 236 gate reds fired.
- The named remediations: the post-compaction re-orient command **0 of 151**; the memory-consolidation command
  **0 of 144**; the worktree-integration command **0 of 130**; the refactor-refresh command **1 invocation in
  264 transcripts** against 5 loud warnings. The only remediation ever executed — 8 of 43 — is the one that is a
  plain shell command rather than a slash command.
- The one mechanism that reliably redirected work is the one that **blocked a push**: in 24 of 26 episodes read
  in full the agent named the finding as its own and fixed it, with zero disables, zero baseline re-bakes and
  zero arguments.

**The rule this supports:** an advisory channel will be read and walked past, regardless of how good its content
is. If something must happen, it belongs at a boundary that stops.

### 5.2 Measured versus mandated

- 52 commands defined; **197 recorded invocations across five months; 17 distinct names ever**; the most-used
  primitive in the whole project was a built-in, ahead of every project command.
- The dispatch command — the central artifact of the agent-discipline layer — was **never invoked once**, while
  dispatch waves demonstrably happened (up to 8 concurrent sessions, 863 subagent transcripts).
- Worktree self-isolation before editing was **mandatory doctrine with a one-step launcher**; measured usage was
  **7 of 264 sessions (2.7%)**. The doctrine's *other* half — "conflict-gated, not count-gated, ~5 sessions
  comfortable" — matched measured behaviour almost exactly (4+ on 57% of days, mode 5).
- Alerting was calibrated for a daily cadence the operator confirmed he did not operate: **117 time-based
  threshold constants, ~12 genuine staleness gates set sub-weekly**, against weekly significant operations.

### 5.3 Installed versus written

- The push gate was **version-controlled, documented and tested for 14 days before it was ever installed**, and
  its test *"passes against a hook whose entire body is `exit 0`, because the comment text alone satisfies every
  assertion."*
- Three lints sat unwired for **7 weeks / 29 days / 21 days**; one *"existed … with its own passing test suite
  and was run by NOTHING."* And **the wire-or-retire lint was itself the most unwired guard in the tree.**
- **Three of five global session-end hooks were never registered** — and they are the ones written for the
  operator's loudest, most-repeated complaints.
- A registered compaction check was edited into the **non-live** of two hand-maintained hook copies, so it
  *"never actually fired."*
- Five lints exist on disk and are in no gate at all, two of them separately proven blind by an audit.
- The self-descriptions drifted too: the ratchet runner's docstring describes wiring into two commands that
  contain zero references to it and never have; the style hook's docstring still documented blocking behaviour
  after the block was removed; an architecture document asserted a wiring state two days before the mechanism
  existed.

### 5.4 Read versus written

- Registers split cleanly: the decision record (15:1), settled negatives (4:1), results ledger (2.6:1) and
  breakage patterns (1.7:1) were consulted; the session changelog (0.44), backlog (0.66), doc router (0.33),
  script manifest (0.35) and compound insights (0.25) were fed and rarely opened; one named register was never
  touched at all. *(Ratios and sets are sound; absolute counts are inflated ~3×.)*
- **140 of 174 live memory files (80%) have zero logged reads**; 51% of all logged memory reads are one
  cross-machine handoff file and 19% the index. Independently, 71 of 154 topic files have body text appearing in
  no transcript at all.
- **572 of 783 curated documents (73%) were never opened** with the read tool; four named meta-documents about
  the harness show zero reads and zero writes in the whole window.
- **78% of agent reports were orphaned** at the July citation audit; of the reports whose creation is traceable,
  half were never re-read by another session.
- The registers narrate failures, not saves: of 43 sentences naming a document with a judgment word, **40 blame
  and 3 credit** — a document essentially never gets an entry for "this prevented an incident".

### 5.5 Used versus defined

| Layer | Defined | With any evidence of use | With evidence of value |
|---|---:|---:|---:|
| Commands | 52 | 10 | 3 above single-digit invocations |
| Guards in the blocking tuple | 29 | 12 observed red | 2 lints + 1 documentation lint with repeat post-birth catches |
| Memory files | 211 | 176 referenced, 34 ever logged as read | ~20 observed steering a decision; 77 propagated into subagent briefs |
| Merge-window decision records | 74 | 74 (all cited somewhere) | 42 cited in code; the project's own governance score is 27% mechanically enforced |
| Agent reports | 3,562 on disk | 960 cited by curated docs | 713 cited at the July audit; more than half the corpus is one untracked exploratory batch |
| Global session-end hooks | 5 | 2 registered | 1, demoted to log-only |

### 5.6 Three findings that do not fit the pattern but change the reading

1. **A guard's clean record is not evidence.** Six of 28 checks had a defect found in the check itself, and in
   every case the check's own record read clean while it was broken. The commonest defect was a dead scope path.
2. **A red is not a catch.** At least half of reconstructable red-to-green transitions were closed by editing
   the test; 70% of test files have no recorded evidence on either axis.
3. **Obedience without freshness is a failure mode.** No memory was ever observed being overridden — and two
   that were obeyed were stale, and both produced near-misses.

---

## 6. Recommendations for the earlier repository

Grounded only in the earlier project's own evidence — its registers, transcripts, hooks, baselines, logs and
handoffs. Nothing here is imported from this repository's assessment. Effort: **XS** under an hour, **S** a few
hours, **M** a day, **L** more than a day.

### 6a. Cheap and clear

| # | Finding that motivates it | The change | Effort | Conf. |
|---|---|---|---|---|
| 1 | **Three of five global session-end hooks are written, tested and unregistered** — and they encode the operator's most-repeated complaints. The same defect hit the repo layer: three lints unwired for up to 7 weeks, and the wire-or-retire lint was itself unwired | For each of the three: wire it or delete it. Then add one check that every hook file present in the global hooks directory is either registered in settings or explicitly listed as retired — the wire-or-retire check applied to the layer it never covered | S | high |
| 2 | **The style hook logs 1,187 detections / 2,219 violations over 18 days that nothing consumes**, 46% dash-style and 56% of events flagging only ordinary capitalised English or universal acronyms — its two most-flagged tokens being the harness's own status vocabulary. The log was written "for periodic self-review" and nothing cites it | Decide it: retire the hook (the evidence supports this), or replace the all-caps shape rule with a project-jargon list that excludes the harness's own vocabulary and common acronyms. Either way, stop writing a log nobody reads | XS / S | high |
| 3 | **Its docstring still documents the removed blocking behaviour** — the same stale-self-description class as the ratchet runner's docstring, which claims wiring into two commands that contain zero references to it and never have | Correct both docstrings, then add the cheapest guard for the class: assert that every command or file a module's docstring claims invokes it actually contains its name | XS + S | high |
| 4 | **42 of 52 commands show zero evidence of ever running**, by either instrument; 8 are explicit "superseded by" pointers; the architecture document's command count is a stale derive-live figure | Delete the 8 pointer files. For the rest, stop calling them an interface: move the never-invoked playbooks under a documented "playbooks, not commands" heading, and regenerate the count | S | high |
| 5 | **13 register entries cite test files that no longer exist on disk** — each meaning either a guard was retired without updating the entry or a defect lost its regression test silently | Resolve the 13, then add a lint: any register entry naming a test path must resolve or the entry goes red. This is a structural-shape check, the class the project's own audit says earns its keep | S | high |
| 6 | **The restore path verifies a copy count, never completeness**, and a real consequence was found one day after the final commit: a path containing a space or an underscore made restore write into a directory nothing reads **and exit 0**. The fix exists in no commit | Land the drive-only fix into git. Make restore assert the restored set against the snapshot manifest and exit non-zero on any shortfall. Add a test whose path contains both a space and an underscore | S | high |
| 7 | **No positive control exists for the memory export's add/update-only guard** — the four regression tests are documented as failing pre-fix, which is an assertion in the register, not a verified meta-test | Add the positive control: construct the pre-fix condition and assert the test fails | XS | high |
| 8 | **Eight dangling links sit in the second machine's memory index**, created when a consolidation on the first machine deleted shared topic files the other machine still pointed at. The handoff says "DO NOT silence the test", and no later record closes it | Repoint or remove the eight. Then make any memory consolidation check every index in the pool, not only the local one — the same root as the reachability defect that once made every peer's memories read as orphans | S | high |
| 9 | **A pipe swallowed the gate's exit code**: three commits sat unpushed for hours while the session reported them pushed, because a push piped into another command returns the pipe's status | Set `pipefail` in the wrapper scripts and add a parse-the-wrapper test asserting no phase pipes a gated command into anything. The project reached exactly this conclusion for a different wrapper: five bugs in two days, all of which *"would have been caught by a parse-the-wrapper test that asserts each phase's command satisfies a declared postcondition"* | S | high |
| 10 | **The hook installer copies rather than symlinks**, which is why the installed gate silently reverted to a fail-open version that nobody re-ran the installer to fix | Make the installed hook's freshness a checked condition that fails loudly on drift, rather than something a health command reports. The detector exists; it just is not at a boundary that stops | S | high |
| 11 | **A falsifiable prediction was set and never checked.** The August assessment wrote that with registration frozen the new-lint cohort's 4.1× catch-rate advantage should collapse, and *"Do not quote the 4.1x as settled before [2026-09-01]."* Nothing after 2026-08-18 checks it | Run the check, or mark the 4.1× figure UNMEASURED in the do-not-quote list. The project's honesty taxonomy already has the vocabulary | XS | high |
| 12 | **One guard is formally HELD pending an operator call**, and **six checks were rated DEMOTE-ADVISORY and are still blocking** — deliberately not acted on, because a separate panel showed the saving is only 6.7% | Record the decision either way, with a date. An undecided hold is indistinguishable from an oversight six months later | XS | high |
| 13 | **Four named meta-documents about how to run the harness show zero reads and zero writes** in the whole four-month transcript window, while three are named as the subject of a staleness fix | Retire them into the archive tree or fold their live content into a document that is actually opened. A meta-document nobody opens is the purest form of the maintenance surface the project was trying to shrink | S | med-high |
| 14 | **The un-attested-stamp debt was reported and ignored** — "24/640 doc(s) … owed a real re-attestation", and the next turn moved on. The remediation ran once in 264 transcripts | Stop reporting it: either pay the 24 down in one pass, or make the honesty clause a permanent non-nagging property of the stamp. The reporting has a measured compliance rate of roughly zero | XS + M | high |

### 6b. Worth investigating

| # | Finding that motivates it | What to investigate | Effort | Conf. |
|---|---|---|---|---|
| 15 | **Baselines only grew.** 2,250 grandfathered entries across 13 files at the August stamp (~2,612 across 18 at the final commit); the largest holds 1,319 against two documented real defects; of 18 files only four ever shrank and only two because debt was paid; three lints grandfathered the whole existing tree and *"therefore never forced a fix to existing code; they only tax new code"* | Decide, per baseline, whether it is a **declared permanent exemption** (rename it, stop calling it a ratchet) or a **debt with an owner and a burn-down**. The project already has the vocabulary from its own suppression work: `accepted` versus `open`, each with a reason and a review date | M | high |
| 16 | **Six checks had a defect found in the check itself while reading clean**, and the commonest was a dead scope fence. One fence bug was fixed in one lint on 2026-05-31 with a note that the sibling *"STILL excludes [the main tree] … left as a follow-up … lower-danger"* — leaving at least three lints scanning the wrong tree for up to eleven weeks | Audit every lint's scope fence by planting a known-bad file **inside** it and confirming the lint goes red. This is the project's own second design rule applied one level inward. Two lints are already documented as fenced to the wrong directories | M | high |
| 17 | **The daily runner is not read**, for a measured reason: *"80% of the alert volume is one machine's environment … everything arrives with identical urgency and the rational response is to stop reading. **Fix is the measurement design, not more diligence.**"* | Split fleet-wide from machine-local before anything else. The operator's own two-category rule applies: retired entities still being graded are safe to prune (*"the tell: a finding nobody could act on even in principle"*), and threshold retuning must **not** be done blind off the wrong machine, because *"retuning off [the wrong machine] converts a noise problem into a BLINDNESS problem"* | M | high |
| 18 | **117 time-based threshold constants, ~12 sub-weekly staleness gates, against confirmed weekly operation.** A worked example: a dead-man switch shipped at 36h fires about every 10 days, and 5 of its 7 long gaps were simply nobody using the system — gating on commits does not fix it (tested; all 7 gaps had commits). The retune was already deferred once, from 2026-06-04, at LOW priority | Retune the ~12, on fleet-wide data only, and record the operating cadence they assume. The inventory already exists | M | high |
| 19 | **A guard whose remedy did damage.** The style guard's fix forced a rewrite, but a blocked draft is already on screen, so *"ANY forced rewrite ships as a visible near-duplicate reply."* The compaction hard block stranded a session — against a written decision a month earlier saying *"we want REMIND, not gate"*, with the blocking machinery left in place and a note explaining how to enable it | Institute a remedy review for every blocking guard: what does the operator see when this fires, and is that cheaper than the defect? And treat "the machinery is here if a future use case wants it" as a hazard — reversing a recorded operator preference should require re-opening the decision, not flipping a flag | S | high |
| 20 | **The id allocator still computes max+1 from the file**, in a workflow where staging without committing is the designed end state. The earliest duplicate predates the merge by three months; seven collisions were renumbered in one August pass; and **the designed fix — per-machine reserved ranges — was proposed 2026-06-16 "awaiting operator nod" and still sat parked in mid-August** | Either approve the reserved ranges or switch to a date-stamped id, which cannot collide by construction. Also adopt the counter lesson: *"the coincidence WAS the trap"* — never resolve a numeric conflict by agreement between two sides; recompute from the union | S | high |
| 21 | **The second machine may never have had the push gate installed** — *"If so, [its] pushes have been ungated"* — and the test that would have detected it was itself a candidate for suppression because it builds a throwaway repo and attempts a push | Settle it. Then make hook-installation state a **blocking** precondition on that machine rather than a health report, and keep the throwaway-repo test un-suppressed by giving it a local remote rather than removing it | S | high |
| 22 | **Two hand-maintained hook directories drift**, and a registered check once lived only in the non-live copy so it *"never actually fired."* The project left the guard OWED with its own open question attached: *"whether [the second hooks directory] should exist at all"* | Answer that question first; if the second copy must exist, add the superset assertion the fix entry specifies (the live hook's registered checks must be a superset of the other copy's) | S | high |
| 23 | **The memory routing-metadata layer is ~41,592 tokens authored for a recall mechanism that does not exist**, rewritten once in a pass that *"tuned a dial that is not connected to anything"*; the second-tier index was read 6 times in 629 sessions; 127 files were demoted to reclaim a budget that was never binding (42 of 200 lines used) | Collapse the two tiers back into one index while there is headroom, and either delete the description fields or repurpose them as the index line — the only always-loaded surface. Also fix the index's own violation of its ≤120-character routing rule (19 of 20 lines exceed it, mean 275) | M | high |
| 24 | **Subagents inherit the whole instruction hierarchy and none of the memory**, while parallel fan-out is the standing default — *"the cost and the value are attached to exactly the wrong layers"* — and 77 memories were in practice pasted into briefs by hand to compensate | Make the brief template carry the standing-directive memories automatically, and trim the instruction hierarchy every subagent pays for. One duplicated rule alone costs ~1,525 tokens per session in four places while already being mechanically enforced | M | high |
| 25 | **A stop rule under-fetched 31.7% of eligible buckets** and its sibling abandoned a 10,338-item plan after 25 items; for nine days the log could not answer *"did this pass saturate"* and the operator drew two wrong conclusions from it; an ETA *"lied by two orders of magnitude"* | Make the acceptance test the project itself wrote a standing property: **the log alone must answer "did this source stop, and why"**. Add a regression check that no stop rule can fire below the non-stopping path's yield. And honour the standing instruction that the downgraded conflation test *"must be REWRITTEN not satisfied"* | M | high |
| 26 | **Half of reconstructable red-to-green transitions were closed by editing the test**; 19 of 21 standing reds are unexplained; 555 of 795 test files have neither gone red nor been named in a register entry | Sample the red-to-green transitions and classify them. The project's own conclusion — *"a recorded red is not by itself evidence of a caught production defect"* — undercuts the yield table it uses to justify keeping guards, and nothing has re-derived the yield numbers under that correction | M | med-high |
| 27 | **The registers narrate failures, not saves**: 40 blame sentences to 3 credit across both registers | Add a one-line "what this caught" field to guard-related entries. Without it there is no way to distinguish a guard that earned its keep from one that merely never broke — which is the question the whole August audit was trying to answer | S | medium |

### Where the project's own documents already planned the change

Six of these are not new ideas — they are the project's own, unactioned:

- **#18** the threshold retune was scheduled for reassessment on 2026-06-04 at LOW priority; the 117-constant
  inventory that proves it is needed is dated 2026-08-15.
- **#20** per-machine reserved id ranges were proposed 2026-06-16 *"awaiting operator nod"* and still parked in
  mid-August, while collisions recurred.
- **#22** the superset guard for the two hook copies was left OWED with its prerequisite question written down.
- **#16** the sibling lint's scope-fence gap was recorded as a follow-up on the day the first was fixed, and
  priced as *"lower-danger"*.
- **#12** six DEMOTE-ADVISORY verdicts were deliberately not acted on, with the reason recorded; one guard is
  formally HELD pending an operator call.
- **#11** the 4.1× prediction was written as falsifiable with a due date and never checked.

---

## 7. Decisions for Wes

Only genuine choices — each with a real fork, a recommendation, and a confidence in that recommendation.

| # | The decision | Recommendation | Conf. |
|---|---|---|---|
| 1 | **The three unwired global session-end hooks: wire or delete?** They encode the complaints you repeated most | **Delete two, wire one.** Warn-only channels are walked past and blocking remedies can cost more than the defect; wire whichever has the cheapest remedy when it fires | medium |
| 2 | **The style guard: retire, or re-scope its token rule?** 56% of its events flag ordinary English, and its remedy ships duplicate replies | **Retire it.** Its own history contains the argument: the denylist could not work, the shape rule over-corrected, and the remedy was ruled not tenable. What remains is a preference, not a defect class | medium-high |
| 3 | **Should the second hooks directory exist at all?** The project asked this itself and never answered | **No — one hooks directory.** Two hand-maintained copies drifted and made a registered check dead; the superset guard is a workaround for a structure with no stated reason to exist | medium-high |
| 4 | **Reserved id ranges, or date-stamped ids?** The reserved-range fix has been designed and unapproved since June | **Date-stamped ids.** They cannot collide by construction, need no approval, and survive a workflow in which staging without committing is normal | high |
| 5 | **The three grandfathering baselines (1,319 / 235 / 109): drain, or declare?** | **Declare them as permanent exemptions and rename them.** Nothing in four months suggests they will drain, and calling a permanent exemption a ratchet is precisely what the project's own audit identified as the failure | medium-high |
| 6 | **The six DEMOTE-ADVISORY guards: demote now, or keep blocking?** A panel measured the saving at 6.7% and the risk as real | **Keep them blocking and record the decision with a date.** The evidence for demotion is a runtime saving; against it is that six checks had defects in themselves while reading clean. The undecided state is the worst option | medium |
| 7 | **The daily runner: fix the measurement design, or stop running it?** 80% of its volume is one machine's environment and nobody reads it | **Fix it once — split fleet-wide from machine-local — and if it is still unread a month later, stop.** The removed fleet detector is the precedent: an alerting path with an empty genuine-alert ledger was deleted and nothing broke | medium-high |
| 8 | **Was the most-constraining memory retired because it had been internalised, or because it was judged wrong?** It is cited as the sizing rule in four consecutive fix-log entries on one day, and it is on the tombstone list | Only you know. If internalised, it belongs in the always-loaded surface as one line, not in a retired file — it is the closest thing in the archive to a memory that visibly constrained design decisions | n/a |
| 9 | **Was the second machine's push gate ever installed?** | If not, the archive's push history from that machine is ungated, and any "the gate held" claim about it should be marked UNMEASURED | n/a |
| 10 | **Do the 24 remaining un-attested stamps get paid down, or does the clause become permanent?** | **Make it permanent and stop reporting it.** A debt report with a measured compliance rate of roughly zero is a cost with no return; the honesty clause itself is the part that carried value | medium |

---

## Related

- `docs/reference/reviews/2026-09-13-harness-assessment.md` — the assessment whose § 9 poses these questions,
  and whose §§ 3 and 6 rows § 4 above moves.
- The ten findings files behind every number here live with the evidence, in the archive, alongside the
  unabstracted copy of this document.

*Prepared 2026-09-13 from the earlier project's 2026-09-06/07 archive. No people, hosts, tokens, tickets or
machine names appear.*
