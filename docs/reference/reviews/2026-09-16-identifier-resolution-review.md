# Identifier resolution: refute pass (2026-09-16)

## Claim under test

"The change closes the identifier-shaped part of the drift recorded as findings 23 and 24 in
`docs/learnings/DOC_DRIFT_FINDINGS_2026-09-13.md`. Its exemptions (a line naming a milestone later
than the status page's, the word planned, a tranche, a retirement word or a decision id; a table row
dated in its first cell; fenced code; HTML comments) cannot be used to hide a real drift cheaply.
Its positive controls exercise the gate as `make check` runs it. The class-name ceiling counts a
class-like name only when no code file uses it as an identifier. Every touched document says exactly
what is mechanical and what remains review. The append-only decisions log and the reference records
are intact. The retired-claims scan now reads through backticks."

Branch `identifier-resolution`, one commit `7e8412c` on top of `main` (`4238992`).

## Method

Read: `docs/reference/AGENT_BRIEF.md`; `CLAUDE.md` § "Rules and what enforces them" and §
"Practices carried from the earlier project"; `docs/reference/reviews/2026-09-15-doc-policy-review.md`
(the standard this pass is held to); the whole diff (`git diff main`, 20 files, +529/-52); the new
code in `tools/doc_policy.py` lines 396–676; `tools/ratchet.py` `SPECS`; the new tests in
`tests/gates/test_doc_policy.py`, `test_ratchet.py`, `test_superseded_claims.py`; every touched
document.

Ran, in `/Users/wesmax/repos/insightminer`:

```
$ uv run python tools/doc_policy.py --check
doc policy: contracts, records, and facts hold

$ uv run pytest tests/gates/test_doc_policy.py tests/gates/test_superseded_claims.py \
    tests/gates/test_ratchet.py -p no:cacheprovider
.........................................................                [100%]
57 passed in 7.80s

$ uv run ruff check     -> All checks passed!
$ uv run ruff format --check -> 165 files already formatted
```

Experiments ran in two throwaway worktrees under the scratchpad (`wt-R` at `HEAD`, `wt-main` at
`main`), both removed at the end; the repository itself was never edited (`git status` clean,
`git worktree list` back to one entry).

End-to-end gate run, planting `` `ZorbleWidget` `` into `wt-R/docs/PLAN.md` and running the two
commands `make check` runs, in order:

```
$ uv run python .../wt-R/tools/doc_policy.py --root .../wt-R --write .../wt-R/.build/doc_policy.json --check
doc policy: contracts, records, and facts hold
doc_policy exit=0                      # correct: a class name is a ceiling, not a problem

$ uv run python .../wt-R/tools/ratchet.py --root .../wt-R compare --main-ref none
OK        docs.dated_annotations             ceiling=31 measured=31
RED       docs.unresolved_class_names        measured 1 is above the ceiling 0 (slack 0)
HIT       unresolved_class_name docs/PLAN.md:552 `ZorbleWidget` [doc-policy]
ratchet: 19 ok, 1 red, 0 stale, 0 loosening, 2 relaxed, 0 expired -> exit 1
```

Reproduction of "the first run" against `main`'s documents with `HEAD`'s tool:

```
AGAINST main (8 problems, 2 class hits):
  P docs/PLAN.md:124: `adapters/reddit_praw.py` does not exist
  P docs/PLAN.md:536: `services/scrub` does not exist
  P docs/runbook/GUARDS.md:18: `adapters.reddit_praw` names a module or attribute that does not exist
  P docs/runbook/GUARDS.md:50: `tests/live` does not exist
  P docs/runbook/RUNBOOK.md:39: `README.txt` does not exist
  P CLAUDE.md:55: `adapters/reddit_praw.py` does not exist
  P CLAUDE.md:104: `services/scrub` does not exist
  P CLAUDE.md:168: `services/scrub` does not exist
  C unresolved_class_name docs/PLAN.md:92 `SearchIndex`
  C unresolved_class_name docs/PLAN.md:273 `PrawGateway`
```

## Findings

### 1. CRITICAL — the `table.column` check never fires in this repository

`_table_block` (`tools/doc_policy.py:551`) matches
`CREATE TABLE "?<table>"?\s*\((.*?)\n\)` — it requires a newline before the closing paren. Every
`CREATE TABLE` in `src/insightminer/db/schema.sql` is written on **one line**
(`CREATE TABLE posts ( pk INTEGER … );`). So the regex never matches, `_table_block` returns `None`
for every table, and `_judge_reference` falls through to `return OK`:

```
schema.sql chars: 26954
_table_block('posts')      -> None (CHECK IS DEAD)
_table_block('comments')   -> None (CHECK IS DEAD)
_table_block('runs')       -> None (CHECK IS DEAD)
_table_block('subreddits') -> None (CHECK IS DEAD)
judge posts.no_such_column -> ('ok', '')
judge runs.zzz             -> ('ok', '')
```

Planting `` `posts.no_such_column` `` into the real `docs/PLAN.md` in `wt-R` was green, while the
same plant in the unit test's fixture tree is red. The positive control
`tests/gates/test_doc_policy.py::test_positive_control_a_dead_module_attribute_or_column_is_red`
passes only because `_code_tree` (line 340) writes its own multi-line schema:
`'CREATE TABLE "posts" (\n\tpk INTEGER NOT NULL,\n\ttitle TEXT\n);\n'`. This is precisely the class
the 2026-09-15 pass named — a control that exercises a fixture rather than the artifact the gate
reads. The column half of the rule is advertised as mechanical in `CLAUDE.md`, `docs/runbook/GUARDS.md`
(G55), `docs/runbook/RUNBOOK.md` § 8 and `docs/INSIGHTMINER_HARNESS.md`.

*Falsified by:* a run showing `_table_block` returning a block for a real table, or a control that
resolves a column against `src/insightminer/db/schema.sql` itself and goes red.

*Fix:* parse the real DDL (match to the closing `)` on the same line, not `\n)`), and add a control
that reads the committed `schema.sql` rather than a hand-written one.

### 2. HIGH — the exemptions are line-granular and cover 37% of the plan's backticked lines; a real drift hides on them

`_judged_lines` drops the **whole line** when any of `future_marker` or `RETIRED` matches anywhere on
it. `RETIRED` is `\b[DN]-\d{2}\b` plus
`cut|retired|superseded|downgraded|dropped|deferred|declined|replaced|removed|renamed`, case
insensitive — ordinary vocabulary in a collector that deletes and scrubs, and a decision id sits on
most rows of a design table. Measured against `HEAD`:

| Document | lines | with backticks | exempt lines carrying backticks |
|---|---|---|---|
| `docs/PLAN.md` | 547 | 248 | **93** (64 future, 28 retirement, 1 fence) |
| `CLAUDE.md` | 180 | 88 | 6 (all future) |

Appending ``Implemented in `db/ghost_module.py` and proven by `tests/gates/test_ghost.py::test_ghost`;
run `make ghost`.`` — three dead identifiers of three different kinds — to six real lines:

| Line | why exempt | result |
|---|---|---|
| `docs/PLAN.md:92` (the Postgres-exit sentence **this commit repaired**) | the new rationale says "N-20" | HIDDEN |
| `docs/PLAN.md:33` (the Storage row, the other home of the same drift) | "D-25" | HIDDEN |
| `CLAUDE.md:45` (the no-bypass hook / stamp / CI rule) | "(none yet, MB)" — `MB` is a milestone | HIDDEN |
| `CLAUDE.md:55` (the layering rule) | "(tranche B)", added by this commit | HIDDEN |
| `docs/PLAN.md:174` (the Scrub definition) | the word "removed" | HIDDEN |
| `docs/PLAN.md:390` (the documentation-gates row) | the words "retired claims" | HIDDEN |

The two lines that carried findings 23 and 24 are now permanently outside the check that was built
to catch them. `docs/PLAN.md:236`, `:306` (tombstones, deleted-or-removed content) and `:377`, `:383`
are exempt for the same vocabulary reason; `CLAUDE.md:51` (the credentials rule) is exempt for "M2".

Partly mitigated: `CLAUDE.md`'s "Enforced by" cells are separately resolved by G39
(`tests/gates/test_rules_name_their_enforcer.py`), so the rule table is not wholly unguarded.

*Falsified by:* a run where one of those six plants is reported.

*Fix:* narrow the exemption from the line to the token — judge a backticked token unless the
milestone/tranche/retirement marker is adjacent to *that* token (e.g. inside the same parenthetical),
and drop the bare retirement vocabulary in favour of an explicit marker.

### 3. HIGH — the repair this commit applied is the exemption, so the gate's pressure is to annotate

Seven of the eight first-run problems were closed by appending a milestone or tranche token to the
line rather than by correcting or removing an identifier: `(tranche B)` on `CLAUDE.md:55`,
`docs/PLAN.md:124` and `:273`; `(M1c)` on `CLAUDE.md:104`, `:168`, `docs/PLAN.md:536` and
`docs/TEST_STRATEGY.md:309`; `(M2)` on `docs/runbook/RUNBOOK.md:39`; `(M1b, opt-in)` on
`docs/runbook/GUARDS.md:50`. Each annotation switches off identifier resolution for every other token
on its line — `.importlinter`, `tests/gates/test_layering.py`, `db/migrations`, `core/deletion`,
`db/repo`, `ports.py`, `FakeRedditGateway`, `docs/TEST_STRATEGY.md` among them. This is the shape the
dated-annotation ceiling exists to resist (annotate rather than rewrite), reappearing in a rule that
has no ceiling of its own: the number of exempt lines is not measured and cannot only go down.

*Falsified by:* a measurement showing exempt-line count is bounded or ratcheted.

*Fix:* count exempted-because-of-a-marker lines into `.ratchets/docs.txt` as a third key, so the
annotation route is itself a ceiling.

### 4. MEDIUM — bare file names are unjudged or judged arbitrarily, and that drove a document edit in this commit

`TABLE_COLUMN` (`^[a-z_]+\.[a-z_]+$`) is tried before the path check, so any lowercase/underscore
bare filename is swallowed and (given finding 1, and even without it) returns OK:

```
judge never_ever_existed.py -> ('ok', '')       # TABLE_COLUMN swallow
judge an.py                 -> ('ok', '')
judge NeverEverExisted.py   -> ('problem', 'does not exist')
judge never-ever-existed.py -> ('problem', 'does not exist')
```

For names that do reach `_path_resolves`, the fallback is a raw substring search of the entire
non-document corpus (`token in tree.corpus`, line 496) — not a word match, not a path. The
consequence is visible in this diff: `docs/runbook/RUNBOOK.md:39` lost `README.txt` from the export
archive's stated contents, while `MANIFEST.json` on the same line survived — and it survives only
because `tools/review_packet.py`, an unrelated feature, writes a file of that name:

```
MANIFEST.json          -> ('ok', '')        # resolved against tools/review_packet.py
README.txt             -> ('problem', ...)
posts.jsonl            -> ('ok', '')
settings.redacted.yaml -> ('problem', ...)
```

`posts.jsonl` and `settings.redacted.yaml` are members of the same unbuilt M2 export; the gate calls
one live and the other dead. No decision entry records that the export's README was cut; the only
other document naming it is a historical review record.

*Falsified by:* showing `README.txt` was cut by a recorded decision, or that bare-name resolution
uses something better than a substring.

*Fix:* try the path judgement before `TABLE_COLUMN`; resolve a bare name only against the file list
(`f.rsplit('/',1)[-1] == token`), never against the corpus text.

### 5. MEDIUM — the "nine" written into the decisions log and the guards ledger is not reproducible

`docs/decisions/DECISIONS.md` § 2026-09-16 and `docs/runbook/GUARDS.md` G55 both say the first run
found "nine" unresolved identifiers, "all planned modules stated without their milestone and one
packet file the builder does not write". `HEAD`'s `identifier_problems` against a `main` worktree
reports **8 problems and 2 class hits** (output pasted above) — seven planned-module references plus
`README.txt`. No reading of that output gives nine. The project's own rule is that a count an agent
reports gets one spot-check before it is written into a document, and both homes are documents a
later session will trust.

*Falsified by:* a recorded run of an intermediate build producing nine, cited in the entry.

*Fix:* correct the number, or replace it with a pointer ("the first run's hits are the identifier
rows of that commit's check output") since counts are supposed to live where a tool prints them.

### 6. MEDIUM — three documents overstate what is mechanical

- `CLAUDE.md:66` states the exemption as "unless its line names a later milestone, a tranche, or a
  retirement", omitting `planned`, a decision id, and a dated first cell — three of the six real
  exits. The full list is only in `docs/runbook/GUARDS.md` G55 and the tool's docstring.
- `CLAUDE.md:66`, `docs/runbook/RUNBOOK.md:105` and `docs/INSIGHTMINER_HARNESS.md:122` all assert
  that a `table.column` named in a rewritten document resolves against the tree. Finding 1 shows it
  never does.
- `docs/runbook/GUARDS.md` G55's cell now carries two separate "What stays review:" clauses, and its
  Verdict is still "EARNED AT BIRTH ONLY (2026-09-15)" though the widened rule found eight real hits
  on 2026-09-16 (a SEEN RED event for the new half).

*Fix:* state the six exits in the working agreement; drop the column claim until finding 1 is fixed;
merge the two review clauses and add the 2026-09-16 firing to the verdict.

### 7. MEDIUM — "no code file uses it as an identifier" is inaccurate for non-Python files

`_code_only` strips docstrings, strings and comments only for `.py` (`load_tree`, line 465); every
other tracked non-`.md`, non-`memory-snapshot` file goes into `code_corpus` verbatim, and `_word_in`
is a plain word match. Writing `ZorbleWidget is mentioned here only in a data file.` into
`config/zorble_note.txt` made the planted class hit disappear. So a class name in a YAML value, a
`.txt` note, a shell comment, a `.sql` comment or a JSON string counts as "the code defines it". The
`.py` half works as the unit test asserts.

*Fix:* resolve a class name against an actual `class <Name>` definition (or at least strip comments
from the non-Python corpus).

### 8. MEDIUM — G34's widened matching still misses the natural recurrences of this very drift

Backtick stripping is a real improvement, but matching is exact substring, so only one phrasing of
each claim is caught:

| line | verdict |
|---|---|
| ``Backups are a `VACUUM INTO` copy taken after reconcile.`` | CAUGHT |
| ``Backups are `VACUUM INTO` copies taken after reconcile.`` (plural) | green |
| ``Backups are a `VACUUM INTO` disaster-recovery copy …`` (one word between) | green |
| ``Every backup is taken with `VACUUM INTO`.`` | green |
| ``The search index sits behind a `SearchIndex` port.`` | CAUGHT |
| ``The search index sits behind a `SearchIndex`.`` | green |
| ``The search index sits behind the `SearchIndex` protocol.`` | green |

A recurrence in a code comment is caught, but only under `src/**/*.py` and `deploy/**`
(`SOURCE_GLOBS`); `tools/`, `tests/`, `alembic/`, `config/`, the `Makefile` and `.github/` are not
scanned. (`tests/db/test_fts.py` legitimately executes `VACUUM INTO`, so widening to tests would need
a carve-out.)

*Fix:* add the bare-mechanism phrases (`SearchIndex`, `VACUUM INTO` alone) with the retirement
marker as the escape, or match phrase words with a small word gap.

### 9. LOW — the append-only log is mechanically intact but the new rows break its own ordering rule

`append_only_problems(root, baseline_ref(root))` returns `[]` against the merge base
`4238992f9f316cb3804f4569238e73aaa9e4e2bc`; every edit to `docs/decisions/DECISIONS.md` (D-25, the § 2
Backups row, § 4, D-31) is an inserted dated parenthetical, and nothing else changed. Reference
records are untouched. But `docs/learnings/DOC_DRIFT_FINDINGS_2026-09-13.md` says in its own preamble
"add dated findings at the end", and rows 23 and 24 were inserted **before** row 22, so the table now
reads 21, 23, 24, 22. Mechanically green, review-red.

*Fix:* move rows 23 and 24 after row 22 — which the append-only gate permits, since the rows are new.

### 10. LOW — a count in memory went stale in the same commit

`memory-snapshot/feedback-tooling-habits.md` gained a seventh habit; its closing line still reads
"follow the six habits above".

### 11. LOW — the new retired-claims rows are dated `2026-09-13` in the Since column

Every other row carries the date the retirement was recorded; these carry the build date. Defensible
if Since means "retired since", but the table's other rows do not read that way. One sentence in the
table's preamble would settle it.

## Bypasses tried

Each planted into `docs/PLAN.md` in a worktree at `HEAD` and judged with the real
`identifier_problems`. "Cheap?" means a single word or token a writer would plausibly add anyway.

| Bypass | Result | Cheap? |
|---|---|---|
| dead path `tools/gone_forever.py` (control) | RED | — |
| dead make target `make nope-target` (control) | RED | — |
| dead test id `…::test_never_written` (control) | RED | — |
| dead command `insightminer nuke --everything` (control) | RED | — |
| dead attribute `db.fts.optimise_all()` (control) | RED | — |
| dead column `posts.no_such_column` (control) | **green — check is dead (finding 1)** | n/a |
| class-like `ZorbleWidget` (control) | counted into the ratchet, compare RED | — |
| a later milestone anywhere on the line ("… lands at M2") | green | yes |
| the bare token `MB` (e.g. "(none yet, MB)") | green | yes |
| the word "planned" | green | yes |
| a decision id (`D-25`, `N-20`) | green | yes |
| the word "removed" / "cut" / "replaced" / "dropped" / "deferred" | green | yes — ordinary domain vocabulary |
| a table row whose first cell is a date | green | yes |
| a fenced code block | green | yes (intended) |
| an HTML comment | green | yes (intended) |
| bare lowercase `never_ever_existed.py` | green (TABLE_COLUMN swallow) | yes |
| bare lowercase `never_ever_existed.sql` | green | yes |
| bare name the code writes as a string anywhere | green | yes (intended, but substring-loose: `an.py` passes) |
| leading-slash path `/tools/gone_forever.py` | green (`NOT_A_PATH`) | yes |
| `~/repos/…/gone_forever.py` | green (`NOT_A_PATH`) | yes |
| `data/…`, `.build/…` prefixes | green (`NOT_A_PATH`) | yes (intended) |
| a template char (`tools/gone_forever*.py`) | green (`TEMPLATE_CHARS`) | yes |
| unknown top directory (`zzz/gone_forever`) | green (`_looks_like_path` false) | yes |
| uppercase directory (`Tools/gone_forever.py`) | RED | no |
| class name in a `.py` docstring / string / comment only | still counted (works) | no |
| class name in a tracked `.txt` / data file | green — hit disappears (finding 7) | yes |
| dead identifiers appended to six real exempt lines of `PLAN.md` / `CLAUDE.md` | HIDDEN, all six | yes |

## What I could not check

- The full `make check`. I ran `doc_policy.py --check`, the three gate files, `ruff check`,
  `ruff format --check`, and an end-to-end `ratchet measure` + `compare` in a worktree; I did not run
  mypy, import-linter, the full suite, or the stamp.
- Whether the "nine" in finding 5 refers to an intermediate working tree that no longer exists; I
  could only reproduce the run against `main`'s documents with `HEAD`'s tool.
- The behavioural (non-identifier) claims in the plan — explicitly out of scope of this gate and
  handed to the wider plan review.
- Whether `docs/reference/` records are byte-identical beyond what `doc_policy --check` asserts; I
  relied on the gate for that.

## Verdict

**The claim holds in part and fails in three of its six clauses.**

Holds: the append-only log and the reference records are intact (`append_only_problems` empty against
the merge base; every decisions edit is an inserted dated parenthetical). The ratchet is genuinely
wired — a planted class name goes `RED docs.unresolved_class_names`, exit 1, through the same two
commands `make check` runs. G34 does now read through backticks. Paths, make targets, test ids,
command lines and package attributes are genuinely red when dead.

Fails: (a) *"positive controls exercise the gate as make check runs it"* — the column control passes
only against a hand-written fixture schema; against the committed `schema.sql` the check cannot fire
at all. (b) *"the exemptions cannot be used to hide a real drift cheaply"* — a single ordinary word
exempts a whole line, 93 of 248 backticked lines in the plan are exempt today, and drift planted on
the two lines that carried findings 23 and 24 is invisible. (c) *"every touched document says exactly
what is mechanical"* — three documents claim the column check, the working agreement states half the
exemption list, and a count in two documents is not reproducible. The class-name clause is
approximately true but not as stated (non-Python files resolve a name).

**Confidence: high** for findings 1, 2, 3, 4, 6, 7, 8 (each reproduced by a pasted command);
**medium** for 5 (depends on what "first run" denoted).

Recommendation: do not land as-is. Fix 1 (the dead column check) and 6 (the three documents that
claim it) before the merge — they are small and they are the difference between a gate and a claim.
Fix 2/3 (token-granular exemptions, or a ceiling on exempted lines) in the same change if the
milestone pass is near, otherwise as an immediate follow-up with a `KNOWN_ISSUES.md` row, because the
current shape trains writers to annotate. 4, 5, 7–11 are follow-ups.

## Outcome (main session, 2026-09-16)

Closed before landing, on the same branch: (1) the column check parses the one-line committed schema by matching parentheses, and a control reads `src/insightminer/db/schema.sql` itself; (2) a marker exempts only the token whose own neighbourhood holds it (the text to the next backticked token either side, within the sentence and the cell; a parenthetical that opens the span belongs to the previous token), a decision id is no longer a marker, and a table row exempts itself only through a cell of its own that is a milestone or the word planned; (3) an identifier that a marker in prose excuses is counted into the docs ratchet file as `exempted_in_prose`, a ceiling; (4) a bare name resolves against the file list, the string literals of Python code, or a gitignore rule, never a substring of the corpus, and a token with a code suffix is a path before it is a column, with a package reference that resolves taking precedence; the runbook's export line names its files in words; (5) the count in the decisions entry and the ledger became a pointer to the check's output; (6) the working agreement names every exit, the ledger cell carries one review clause, and the verdict records the firing; (7) a class-like name resolves against Python identifiers and structured configuration (JSON, plist, YAML, TOML), never a note or a script comment; (8) the bare phrases `SearchIndex` and `VACUUM INTO` joined the retired-claims table, with a retirement marker as the escape for a test's own control; (9) rows 23 and 24 follow row 22; (10) the memory habit count; (11) the Since column carries the date the retirement was recorded. Not changed: the source globs of the retired-claims scan (tools and tests would need a carve-out for a test that runs the statement as its control); that stays review and is noted in the ledger.
