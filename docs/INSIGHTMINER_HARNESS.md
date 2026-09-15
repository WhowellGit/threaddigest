# The harness: how this project keeps an agent-built codebase honest

> **What this is.** The one page on the *working method*: the mechanisms that sit in the path of every
> change, why each exists, and how they fit together. The inventory at the bottom is generated from
> the tree by `tools/harness_page.py` and gated (G54), so this page cannot describe a mechanism that
> no longer exists. **Update policy:** prune-stale; the prose is corrected in place, the block is
> regenerated. Where the method came from, and what it cost the project it came from, is in
> `docs/reference/earlier-project/EARLIER_PROJECT_REFERENCE.md`; how it has evolved here is in the
> dated notes of `docs/learnings/LEARNINGS_TRANSFER.md` § 7. This page states the current shape only.

## 1. The idea in one paragraph

A written rule is read and walked past. What changes an agent's behaviour is a mechanism in the path
of the action, before it executes, that refuses with a printed reason. So every rule in this project
names the thing that enforces it, or is labelled review-only, and the number of review-only rules is a
ceiling that only goes down. The mechanisms are cheap, deterministic, and self-protecting; the human
reads output that tools derived, never claims that an agent typed. The recurring failure the method
guards against is drift after the first build: a test quietly weakened, a count narrated instead of
measured, a document describing a target state as if it were built, a hook present but never
installed. Each of those has a mechanism below, and each mechanism has a recorded birth incident and a
positive control that proves it can go red.

## 2. The four parts

**Memory and context.** The working agreement (`CLAUDE.md`) is short and always loaded: the four
irreversible rules at the top, the rules table with an enforcer per row, and a routing table that says
which document to read before touching which surface. Path-scoped rule files under `.claude/rules/`
load only when a matching file is edited. The document router (`docs/INDEX.md`) lists every document
once, with when to read it, and a gate checks the router against the tree in both directions. The
auto-memory outside the repo is snapshotted into `memory-snapshot/` add-or-update only, and `make
check` fails when the snapshot is behind live memory. Sessions start in the repository root, because
project hooks load only from the starting directory; that fact is written where a resuming session
reads first.

**The documentation system.** One plan, canonical for design (`docs/PLAN.md`), rewritten as a version
when it has accreted rather than annotated forever. One status page, the only rewritten resume
surface, capped and stamped and forbidden to restate counts (G45). Three registers with a sharp bar:
decisions (append-only, each with a revisit trigger and a machine-read retired-claims table, G34),
known issues (every fixed bug cites the regression test that proves it, G40), and the guards ledger
(every gate's birth incident, mechanism, positive control, and verdict). Learnings are append-only
and dated; status is rewritten. A number has one home, where a tool prints it, and prose points at
it. Reference material from the earlier project is abstracted before it enters the tree and a gate
scans tracked text for imported identifiers (G35).

**Enforcement.** Three PreToolUse hooks in the project settings, in the path of every tool call: no
bypass of the commit gate, no push to `main`, and no merge into `main` of a tree the check has not
stamped green; no hand edit of the enforcement surfaces (the ratchet files, the hook scripts, the hook
settings); and a read-before-touch check that logs first and blocks only once its ledger shows it is
right. Pre-commit on every commit (format, lint, types on the whole tree, secret scan, size, no
commits on `main`) and a pre-push stage that runs the full check. `make check` is one command: lint,
types, import-linter layering, the test suite with the network blocked and warnings as errors,
coverage, code health, the ratchet compare three ways, the hooks line, the memory audit, and finally
the green stamp that names the tree it passed. Ratchets are one-way floors and ceilings written only
by `tools/ratchet.py`; a loosening pauses for approval and lands a ledger row; a birth relaxation
carries an expiry. Gates in `tests/gates/` each ship a positive control that constructs the bad state
and asserts red. Post-run invariants at runtime flip a run to `failed` rather than warn. **The honest
limit:** the hooks parse command text and are mistake prevention for the agent, not a security
boundary; the boundary against a deliberate bypass is pre-commit, CI once a remote exists, review, and
branch protection (G23).

**Agent discipline.** The main session plans, synthesizes, and decides; sub-agents do bounded work
and return evidence, not conclusions, each on a named model tier (Opus for judgement, Sonnet for
mechanical work; nothing inherits). Every brief follows `docs/reference/AGENT_BRIEF.md`. Reviews are
refute-framed, weighed by evidence rather than tallied, and aimed at the previous round's
conclusion; an external round receives a packet built from the committed tree by a script, hashed,
with a claims list to falsify (G52); every review on a review-required surface has a register row
(G50). A fix is hardened through the `harden` skill: failing test, register row, the strongest
enforcer that fits, positive control, mirrors swept, proof pasted. Work lands as small green commits
on a branch, fast-forwarded into `main` after the check stamps the tree.

## 3. How the parts hold each other

The router names documents; a gate checks the router. The rules table names enforcers; a gate resolves
every enforcer named. The registers cite tests; a gate collects every cited test. The status page
carries no counts; a gate refuses one. The ratchet files are written by one tool; a hook refuses a
hand edit and the compare goes red on a stale floor. The hook scripts must all be registered; a test
fails when one is not. The memory snapshot must not fall behind; the check runs in `make check`. And
this page's inventory is generated; G54 refuses a stale block. A mechanism that only *looked* like
enforcement is the failure the earlier project measured most often, so each of these is arranged so
that its own absence or drift is visible to another one.

## 4. What is deliberately not here

No standalone approach narrative, session changelogs, or handoff documents: measured in the earlier
project as the largest cost for the fewest readers; the status page and the automatic compaction
summary carry state. No test-count gate (N-09), no mutation-score ratchet (N-10), no stress corpus (N-11),
no runtime fingerprint that refuses to run (N-13): cut by the adversarial review on 2026-09-13 with
reasons in `docs/decisions/DECISIONS.md` § 3. No slash-command surface beyond one skill. No semantic search over
a few dozen documents. Each has a trigger in the earlier-project reference that would adopt it in one
step; none has fired.

## 5. Inventory (generated)

<!-- harness-inventory:begin -->

_Generated by `tools/harness_page.py` from the tree; gate G54 fails when this block and the tree disagree. Regenerate with `uv run python tools/harness_page.py --write`. Installed-ness of the git hooks is machine-local and is printed by `make check` and `doctor`, never here._

**Hook scripts and their registration** (`.claude/settings.json`):
- `tools/hooks/enforcement_files_script_only.sh`: PreToolUse `Bash|Edit|Write|MultiEdit`
- `tools/hooks/no_bypass_git.sh`: PreToolUse `Bash`
- `tools/hooks/read_before_touch.sh`: PreToolUse `Edit|Write|MultiEdit`; mode `log`

**Pre-commit stages** (`.pre-commit-config.yaml`): `check-added-large-files`, `end-of-file-fixer`, `trailing-whitespace`, `no-commit-to-branch`, `ruff-check`, `ruff-format`, `gitleaks`, `dmypy`, `make-check` (stage pre-push)

**Gate files** (`tests/gates/`, 26): `test_code_health`, `test_counters_deltas`, `test_data_dir_isolation`, `test_dependency_pins`, `test_doc_currency`, `test_harness_page`, `test_hooks`, `test_invariants_planted`, `test_known_issues_cite_collected_tests`, `test_layering`, `test_memory_snapshot`, `test_mutating_commands`, `test_no_bypass`, `test_no_imported_identifiers`, `test_no_sleep_under_pytest`, `test_no_tracked_daemon_state`, `test_pk_stability`, `test_pytest_config`, `test_ratchet`, `test_review_packet`, `test_review_register`, `test_routing_rows_resolve`, `test_rules_name_their_enforcer`, `test_sqlite3_confined`, `test_status_page`, `test_superseded_claims`

**Guards ledger rows** (`docs/runbook/GUARDS.md`): Active 36, External controls 5, Retired 0, Loosenings 3

**Ratchet files and keys** (`.ratchets/`; values live in the files):
- `.ratchets/code_health.txt`: `cognitive_over_15`, `cyclomatic_over_15`, `dead_code`, `dead_code_whitelisted`, `duplicate_blocks`, `mi_below_a`, `size_rule_violations`
- `.ratchets/coverage.txt`: `line_percent`
- `.ratchets/review_only_rules.txt`: `count`, `guards_without_control`
- `.ratchets/skips.txt`: `count`
- `.ratchets/suppressions.txt`: `filterwarnings_ignore`, `mypy_overrides`, `noqa`, `pragma_no_cover`, `type_ignore`
- `.ratchets/tests.txt`: `asserts`, `collected`

**Import-linter contracts** (`.importlinter`): `Layers: web | cli > services > db | adapters > ports > core`, `praw and prawcore are imported only by insightminer.adapters.reddit_praw`, `web must not import cli (the CLI mirrors the UI, never the reverse)`

**Path-scoped rule files** (`.claude/rules/`):
- `.claude/rules/db.md`: `src/insightminer/db/**`, `tests/db/**`
- `.claude/rules/services.md`: `src/insightminer/services/**`, `tests/services/**`, `tests/e2e/**`
- `.claude/rules/web.md`: `src/insightminer/web/**`, `tests/web/**`

**Skills** (`.claude/skills/`): `harden`

**Tools** (`tools/*.py`): `check_stamp.py`, `code_health.py`, `harness_page.py`, `hooks_status.py`, `make_demo_fixture.py`, `memory_snapshot.py`, `ratchet.py`, `render_plan.py`, `review_packet.py`, `vulture_whitelist.py`

**`make` targets**: `help`, `setup`, `hooks`, `check`, `memory-check`, `memory-export`, `code-health`, `ratchet-bump`, `ratchet-loosen`, `schema`, `test`, `fixture`, `run`, `plan-html`

**Machine-read registers and their readers**:
- `docs/runbook/KNOWN_ISSUES.md`: read by `test_known_issues_cite_collected_tests.py`
- `docs/runbook/GUARDS.md`: read by `test_harness_page.py`, `test_hooks.py`, `test_known_issues_cite_collected_tests.py`, `test_no_imported_identifiers.py`, `test_ratchet.py`, `test_rules_name_their_enforcer.py`
- `docs/reference/reviews/REGISTER.md`: read by `test_review_register.py`
- `docs/reference/reviews/templates/claims.md`: read by `test_known_issues_cite_collected_tests.py`, `test_review_packet.py`
- `docs/TEST_STRATEGY.md`: read by `test_known_issues_cite_collected_tests.py`
- `docs/decisions/DECISIONS.md`: read by `test_known_issues_cite_collected_tests.py`, `test_no_imported_identifiers.py`, `test_review_packet.py`, `test_superseded_claims.py`
- `docs/recent/STATUS.md`: read by `test_status_page.py`
- `docs/INDEX.md`: read by `test_doc_currency.py`, `test_routing_rows_resolve.py`

<!-- harness-inventory:end -->
