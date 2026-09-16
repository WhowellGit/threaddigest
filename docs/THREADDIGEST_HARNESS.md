---
purpose: The working method, plain English first, then the detail, with a generated inventory of every mechanism in the tree.
update-policy: prune-stale
mirrors: [docs/PLAN.md, docs/runbook/GUARDS.md, docs/runbook/RUNBOOK.md, CLAUDE.md]
verified-at: M1a-A
---
# The harness: how this project keeps an agent-built codebase honest

> **What this is.** The one page on the *working method*: what the harness is for, what it is good
> at, how it came to be, its four parts, and how they hold each other, each section in plain
> English first and the detail after. The inventory at the bottom is generated from the tree by
> `tools/harness_page.py` and gated (G54), so this page cannot describe a mechanism that no longer
> exists; the page's own policy is in its front matter. Where the method came from, and what it cost the project it came from, is in
> `docs/reference/earlier-project/EARLIER_PROJECT_REFERENCE.md`; how it has evolved here is in the
> dated notes of `docs/learnings/LEARNINGS_TRANSFER.md` § 7. This page states the current shape only.

## 1. If you read one paragraph

This project is built mostly by an AI agent, and the danger with that is not the first build but
the drift afterwards: a test quietly weakened, a count typed instead of measured, a document that
describes what was meant rather than what exists, a rule that everyone has read and nobody obeys.
The harness is the set of mechanisms that make each of those impossible to do quietly. A hook
refuses the forbidden command before it runs. The main branch accepts only a tree the full check
has just passed. Every rule names the thing that enforces it, or is labelled as review-only, and
the number of review-only rules can only go down. Every gate has a test that plants the bad state
and proves the gate goes red. Every document declares what it is for and how it may change, and a
tool checks that it did. Reviews are asked to break the work, not to bless it, and an outside
reviewer who ran the code found real defects that two internal panels had not. The result is a
small project whose claims can be believed because a mechanism, not a person, is what makes them
true.

## 2. What it is for

The intent is that Wes can trust the codebase for years and hand it to someone else, while an
agent does most of the typing. Three things follow. The human reads output that tools derived,
never claims that an agent wrote. The agent is held to the same rules as a person, by mechanisms
that sit in the path of every action rather than by instructions it may or may not follow. And the
project's own documents are part of the system under test: the plan, the ledgers, the status page,
and the memory that carries context between sessions are checked the way code is, so a reader
starting cold can believe what they read.

## 3. Its strengths, in plain English

- **Nothing is advisory.** Every check either fails the build or lands in a ledger that needs an
  approval; an agent cannot dismiss a warning. When a floor must be loosened, the loosening pauses
  for approval and is recorded with its reason.
- **The forbidden is refused, not discouraged.** Hooks in the path of every tool call refuse a
  bypass of the commit gate, a push to the main branch, a merge of an unchecked tree, and any hand
  edit of the enforcement files. They fail closed on their own errors and protect their own
  registration. Their honest limit is stated in the ledger: they stop mistakes, not a determined
  bypass, and the boundary against that is pre-commit, review, and, once a remote exists, CI.
- **Every guard has been seen to go red.** A gate ships with a positive control that constructs the
  bad state and asserts the gate catches it. A guard that has never failed is treated as a
  hypothesis and says so in its ledger row.
- **Numbers have one home.** A count lives where a tool prints it; the status page is forbidden to
  restate one; the harness inventory on this page is generated. A number in prose is a future lie
  and the gates treat it as one.
- **Documents are held to a contract.** Each living document declares its purpose, how it may
  change, which documents mirror it, and the milestone it was last verified at. Logs may only grow,
  measured against the branch base, and records are never edited. Dated annotations in the prose
  of rewritten documents are counted into a ceiling that only goes down, a pressure toward a
  rewrite. A fact listed in the live-facts table has one home and one literal, and every listed
  mirror must state it; a retired phrase cannot be stated as live. The rest of a sweep, whether a
  mirror's prose still agrees, is review with a checklist.
- **Reviews are built to disagree.** Every review prompt is refute-framed. Findings are weighed by
  evidence, never tallied. An external round receives a packet built from the committed tree with a
  list of claims to falsify, and every finding is re-run against the tree before it is believed.
  The rounds so far found their real defects only through seats that ran the code, so a
  code-executing seat is now standing.
- **Memory routes; it does not restate.** The agent's memory across sessions is an index of where
  to look and how to work, capped, snapshotted into the repository, and audited on every check.

## 4. How it came to be

The method was not invented here. Wes's earlier project built a large harness over months and
then measured it: which guards had fired, which documents were read, what the process cost. This
project began by studying that record, adopting the mechanisms with evidence behind them, and
declining the rest with the measured reason written down. An adversarial review then cut about a
third of the gates the transfer had produced, before any were built. The enforcement went in at
M0, before the collector, because the failures it guards against are the irreversible ones. Two
panels and an external review round then hardened it: the external round proved a line
continuation could walk past the git hook, and the fix and the honest limit both landed in the
ledger. The plan's rewrite as version two exposed the last gap, the writing side of the documents,
and the document contract closed it. Each step is recorded in the decisions log with its date and
its reason, and the earlier-project reference keeps the trigger that would adopt each mechanism
that was declined.

## 5. The four parts

### Memory and context

*In plain English: an agent starting a session knows where to look, and the routing is checked.*

The working agreement (`CLAUDE.md`) is short and always loaded: the four irreversible rules at the
top, the rules table with an enforcer per row, and a routing table that says which document to
read before touching which surface. Path-scoped rule files under `.claude/rules/` load only when a
matching file is edited. The document router (`docs/INDEX.md`) lists every document once, with
when to read it, and a gate checks the router against the tree in both directions; another checks
that every routing pointer names a document and a section that exist. The auto-memory outside the
repository is an index of routing hooks and working habits, capped per file, snapshotted
add-or-update only into a private folder outside the repository (D-35: the notes are Wes's and
the repository is public), and `make check` fails when the snapshot is behind live memory, when
that folder is missing, or when a project memory points at nothing. Sessions start in the repository root, because
project hooks load only from the starting directory; that fact is written where a resuming
session reads first.

### The documentation system

*In plain English: each document knows what kind of document it is, and a tool holds it to that.*

One plan, canonical for design (`docs/PLAN.md`), corrected in place between versions and rewritten
as a version once annotations accrete, with every retired section given a home. One status page,
the only surface replaced whole, capped, stamped, naming the current milestone, and forbidden to
restate counts. Three registers with a sharp bar: decisions (append-only, each with a revisit
trigger, plus two machine-read tables, the retired claims that may not be stated as live and the
live facts every mirror must state), known issues (every fixed bug cites the regression test that
proves it), and the guards ledger (every gate's birth incident, mechanism, positive control, and
verdict). Every living document under `docs/` opens with a contract in its front matter: purpose,
update policy from a fixed vocabulary, mirrors declared from both sides, and the milestone it was
verified at; `tools/doc_policy.py` checks the contract, holds append-only documents and reference
records to their diff against the merge base with `main`, counts dated annotations in the prose of
rewritten documents into a ratchet ceiling, fails a document that lags the status page's milestone
by more than one or is stamped ahead of it, resolves every document path with a directory and every code identifier (a path, a
make target, a test id, a command line, a package reference, a table column) that a
rewritten document names unless its own annotation says which milestone it waits on,
counts class-like names no code uses and identifiers exempted in prose into the same
ceiling file, and checks the live-facts table against every listed mirror. Reference material
from the earlier project is abstracted before it enters the tree, and a gate scans tracked text
for imported identifiers. The procedure for landing a changed fact everywhere it repeats is
`docs/runbook/RUNBOOK.md` § 8 and the `docs-sweep` skill.

### Enforcement

*In plain English: the forbidden is refused before it happens, and the main branch only ever
receives a tree the full check just passed.*

Three PreToolUse hooks in the project settings, in the path of every tool call: no bypass of the
commit gate, no push to `main`, and no merge into `main` of a tree the check has not stamped green;
no hand edit of the enforcement surfaces (the ratchet files, the hook scripts, the hook settings);
and a read-before-touch check that logs first and blocks only once its ledger shows it is right.
Pre-commit on every commit (format, lint, types on the whole tree, secret scan, size, no commits on
`main`) and a pre-push stage that runs the full check. `make check` is one command: lint, types,
import-linter layering, the test suite with the network blocked and warnings as errors, coverage,
code health, the document contract, the ratchet compare three ways, the hooks line, the memory
audit, and finally the green stamp that names the tree it passed. Ratchets are one-way floors and
ceilings written only by `tools/ratchet.py`; a loosening pauses for approval and lands a ledger
row; a birth relaxation carries an expiry. Gates in `tests/gates/` each ship a positive control.
Post-run invariants at runtime close a run `failed` (a failure) or `partial` (a warning) rather than pass silently; the plan names the severity of each. **The honest limit:** the
hooks parse command text and are mistake prevention for the agent, not a security boundary; the
boundary against a deliberate bypass is pre-commit, CI once a remote exists, review, and branch
protection (G23).

### Agent discipline

*In plain English: the main session decides, helpers do bounded work and bring evidence, and
reviews try to break the work.*

The main session plans, synthesizes, and decides; sub-agents do bounded work and return evidence,
not conclusions, each on a named model tier (a stronger tier for judgement, a lighter one for
mechanical work; nothing inherits). Every brief follows `docs/reference/AGENT_BRIEF.md`. Reviews
are refute-framed, weighed by evidence rather than tallied, and aimed at the previous round's
conclusion; an external round receives a packet built from the committed tree by a script, hashed,
with a claims list to falsify (G52); every review on a review-required surface has a register row
(G50). A fix is hardened through the `harden` skill: failing test, register row, the strongest
enforcer that fits, positive control, mirrors swept, proof pasted. A settled fact is landed
everywhere it repeats through the `docs-sweep` skill. Work lands as small green commits on a
branch, fast-forwarded into `main` after the check stamps the tree.

## 6. How the parts hold each other

The router names documents; a gate checks the router. The rules table names enforcers; a gate
resolves every enforcer named. The registers cite tests; a gate collects every cited test. The
status page carries no counts; a gate refuses one. Each document declares its policy and mirrors;
a tool checks the declaration and the diff. The ratchet files are written by one tool; a hook
refuses a hand edit and the compare goes red on a stale floor. The hook scripts must all be
registered; a test fails when one is not. The memory snapshot must not fall behind; the check runs
in `make check`. And this page's inventory is generated; G54 refuses a stale block. A mechanism
that only *looked* like enforcement is the failure the earlier project measured most often, so
each of these is arranged so that its own absence or drift is visible to another one.

## 7. What is deliberately not here

No standalone approach narrative, session changelogs, or handoff documents: measured in the earlier
project as the largest cost for the fewest readers; the status page and the automatic compaction
summary carry state. No test-count gate (N-09), no mutation-score ratchet (N-10), no stress corpus
(N-11), no runtime fingerprint that refuses to run (N-13): cut by the adversarial review on
2026-09-13 with reasons in `docs/decisions/DECISIONS.md` § 3. No slash-command surface beyond two
skills. No semantic search over a few dozen documents. No prose scanner for words like "now" or
"currently": the accretion ceiling and the live-facts table catch the damage those words hide.
Each declined mechanism has a trigger in the earlier-project reference that would adopt it in one
step; none has fired.

## 8. Inventory (generated)

<!-- harness-inventory:begin -->

_Generated by `tools/harness_page.py` from the tree; gate G54 fails when this block and the tree disagree. Regenerate with `uv run python tools/harness_page.py --write`. Installed-ness of the git hooks is machine-local and is printed by `make check` and `doctor`, never here._

**Hook scripts and their registration** (`.claude/settings.json`):
- `tools/hooks/enforcement_files_script_only.sh`: PreToolUse `Bash|Edit|Write|MultiEdit`
- `tools/hooks/no_bypass_git.sh`: PreToolUse `Bash`
- `tools/hooks/questions_in_session.sh`: Stop `*`; mode `log`
- `tools/hooks/read_before_touch.sh`: PreToolUse `Edit|Write|MultiEdit`; mode `log`

**Pre-commit stages** (`.pre-commit-config.yaml`): `check-added-large-files`, `end-of-file-fixer`, `trailing-whitespace`, `no-commit-to-branch`, `ruff-check`, `ruff-format`, `gitleaks`, `dmypy`, `make-check` (stage pre-push)

**Gate files** (`tests/gates/`, 27): `test_code_health`, `test_counters_deltas`, `test_data_dir_isolation`, `test_dependency_pins`, `test_doc_currency`, `test_doc_policy`, `test_harness_page`, `test_hooks`, `test_invariants_planted`, `test_known_issues_cite_collected_tests`, `test_layering`, `test_memory_snapshot`, `test_mutating_commands`, `test_no_bypass`, `test_no_imported_identifiers`, `test_no_sleep_under_pytest`, `test_no_tracked_daemon_state`, `test_pk_stability`, `test_pytest_config`, `test_ratchet`, `test_review_packet`, `test_review_register`, `test_routing_rows_resolve`, `test_rules_name_their_enforcer`, `test_sqlite3_confined`, `test_status_page`, `test_superseded_claims`

**Guards ledger rows** (`docs/runbook/GUARDS.md`): Active 38, External controls 5, Retired 0, Loosenings 3

**Ratchet files and keys** (`.ratchets/`; values live in the files):
- `.ratchets/code_health.txt`: `cognitive_over_15`, `cyclomatic_over_15`, `dead_code`, `dead_code_whitelisted`, `duplicate_blocks`, `mi_below_a`, `size_rule_violations`
- `.ratchets/coverage.txt`: `line_percent`
- `.ratchets/docs.txt`: `dated_annotations`, `exempted_in_prose`, `unresolved_class_names`
- `.ratchets/review_only_rules.txt`: `count`, `guards_without_control`
- `.ratchets/skips.txt`: `count`
- `.ratchets/suppressions.txt`: `filterwarnings_ignore`, `mypy_overrides`, `noqa`, `pragma_no_cover`, `type_ignore`
- `.ratchets/tests.txt`: `asserts`, `collected`

**Import-linter contracts** (`.importlinter`): `Layers: web | cli > services > db | adapters > ports > core`, `praw and prawcore are imported only by threaddigest.adapters.reddit_praw`, `web must not import cli (the CLI mirrors the UI, never the reverse)`

**Path-scoped rule files** (`.claude/rules/`):
- `.claude/rules/db.md`: `src/threaddigest/db/**`, `tests/db/**`
- `.claude/rules/services.md`: `src/threaddigest/services/**`, `tests/services/**`, `tests/e2e/**`
- `.claude/rules/web.md`: `src/threaddigest/web/**`, `tests/web/**`

**Skills** (`.claude/skills/`): `docs-sweep`, `harden`

**Tools** (`tools/*.py`): `check_stamp.py`, `code_health.py`, `doc_policy.py`, `harness_page.py`, `hash_remap.py`, `hooks_status.py`, `make_demo_fixture.py`, `memory_snapshot.py`, `ratchet.py`, `render_plan.py`, `review_packet.py`, `vulture_whitelist.py`

**`make` targets**: `help`, `setup`, `hooks`, `check`, `memory-check`, `memory-export`, `code-health`, `doc-policy`, `lint-fix`, `ratchet-bump`, `ratchet-loosen`, `schema`, `test`, `test-live`, `fixture`, `run`, `plan-html`

**Machine-read registers and their readers**:
- `docs/runbook/KNOWN_ISSUES.md`: read by `test_known_issues_cite_collected_tests.py`
- `docs/runbook/GUARDS.md`: read by `test_harness_page.py`, `test_hooks.py`, `test_known_issues_cite_collected_tests.py`, `test_no_imported_identifiers.py`, `test_ratchet.py`, `test_rules_name_their_enforcer.py`
- `docs/reference/reviews/REGISTER.md`: read by `test_doc_policy.py`, `test_review_register.py`
- `docs/reference/reviews/templates/claims.md`: read by `test_known_issues_cite_collected_tests.py`, `test_review_packet.py`
- `docs/TEST_STRATEGY.md`: read by `test_known_issues_cite_collected_tests.py`
- `docs/decisions/DECISIONS.md`: read by `test_doc_policy.py`, `test_known_issues_cite_collected_tests.py`, `test_no_imported_identifiers.py`, `test_review_packet.py`, `test_superseded_claims.py`
- `docs/recent/STATUS.md`: read by `test_doc_policy.py`, `test_status_page.py`
- `docs/INDEX.md`: read by `test_doc_currency.py`, `test_doc_policy.py`, `test_routing_rows_resolve.py`

<!-- harness-inventory:end -->
