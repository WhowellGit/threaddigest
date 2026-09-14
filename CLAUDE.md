# Insight Miner: working agreement

Personal, rules-compliant Reddit harvester. Plan: `docs/PLAN.md`. Doc router: `docs/INDEX.md`.
Everything runs through `uv`: `make setup` once, then `make check` before every PR.
This file applies to every agent and human working in the repo.

## The irreversible few

Rules whose late arrival is unrecoverable, so they sit here at the top and in every agent's path:

1. Never write outside the resolved data directory; tests and the fake gateway never touch the default one (`tests/gates/test_data_dir_isolation.py`, `tests/gates/test_no_bypass.py`).
2. Never commit a secret, another system's identifier, or an attribution trailer: history keeps them (gitleaks in pre-commit; `tests/gates/test_no_imported_identifiers.py`; `tools/hooks/no_bypass_git.sh`).
3. Never run an unbounded fetch: every run has a budget and the hard cap holds (`tests/gates/test_no_bypass.py`).
4. Never hand-edit the enforcement surfaces (`.ratchets/`, the hooks, the hook settings) or bypass a gate (`tools/hooks/enforcement_files_script_only.sh`, `tools/hooks/no_bypass_git.sh`).

## How this project uses its agents

The main session plans, synthesizes, and decides; sub-agents do bounded work under the model tiers
below and return evidence, not conclusions. Work lands as small green commits on a branch that is
fast-forwarded into `main` (one commit per module, tests and implementation together, about 800
hand-written lines before a commit needs a stated reason; generated data comes from a script and
is never committed). Every rule names what enforces it or is labelled review-only, and the number
of review-only rules can only go down. Documents derive their state from tools and tests, never
from a claim in a message. Reviews are refute-framed, weighed by evidence rather than tallied, and
aimed at the previous round's conclusion. Lessons from other systems arrive abstracted; their
identifiers and mechanisms do not. A fix is hardened through the `harden` skill
(`.claude/skills/harden/SKILL.md`): failing test, register row, the strongest enforcer that
fits, positive control, mirrors swept, proof pasted. The reasoning behind these choices is in
`docs/learnings/LEARNINGS_TRANSFER.md` and
`docs/reference/reviews/2026-09-13-documentation-practices-assessment.md`.

## Rules and what enforces them

Enforcement is mechanical wherever possible. "Review" is the PR body plus a human or an
independent agent; it is the weakest column and appears only where no tool can check the rule.
The table is itself enforced: `tests/gates/test_rules_name_their_enforcer.py` resolves every
backticked path, pytest marker, ruff code and `make` target in the right-hand column against the
tree, so a row may not name an enforcer that does not exist; a row with no resolving enforcer must
say "review", and the number of review-only rows is a ceiling in `.ratchets/review_only_rules.txt`
that only goes down.

| Rule | Enforced by |
|---|---|
| Never weaken, skip, or delete a test to make a change pass | PR body "Tests changed" table (one reason per file); skip/xfail ratchet, each needing `reason="#issue …"`; assert-count, collected-test, and coverage floors in `.ratchets/`; `xfail_strict` |
| Never `git commit --no-verify`; never push to `main` | hard-block PreToolUse hook `tools/hooks/no_bypass_git.sh` (fails closed), proven by `tests/gates/test_hooks.py`; pre-commit `no-commit-to-branch` in `.pre-commit-config.yaml`; required CI in `.github/workflows/ci.yml` |
| Never catch a broad exception without recording it on the run row | ruff `E722`, `BLE001`, `S110`, `S112`, `B904`, `TRY*`; a run with any warning is `partial`, never `ok` |
| Every bug fix starts with a failing test and a `docs/runbook/KNOWN_ISSUES.md` row pointing at it | `tests/gates/test_known_issues_cite_collected_tests.py` (a row's node id must name a test that exists); that a fix has a row at all is review of the PR body; the `harden` skill is the checklist |
| Every schema change ships a migration, a prior-revision fixture DB in `tests/fixtures/db/`, and an updated `src/insightminer/db/schema.sql` | schema snapshot test; pytest-alembic models == DDL; `make schema`; the committed fixtures are upgraded by `tests/db/test_alembic.py`; that a new revision adds its own fixture is review |
| Never hand-edit `.ratchets/` or the hook settings | hard-block hook; `tools/ratchet.py` is the only writer; floors are compared three ways on every `make check`, so a stale or hand-edited floor is red |
| Never touch the production DB by hand | `tests/gates/test_data_dir_isolation.py`: tests run in a temp `DATA_DIR` and settings refuse the default dir under pytest; a destructive operation takes a recorded fresh backup first (`tests/services/test_migrate_service.py`); the typed confirmation is review until the mutating commands land |
| Never store or log credentials | gitleaks in `.pre-commit-config.yaml` (allowlist in `.gitleaks.toml`: the ratchet address only); `.env` is gitignored (`.gitignore`); validation errors hide their input (KI-003's regression test); the M2 config export must exclude secrets (review until built) |
| Report results by pasting the `make check` block, never by describing it | review of the PR body against the pasted-block section of the PR template; CI is the authority, not the message |
| A new guard needs a birth incident, a positive control in `tests/gates/`, a `docs/runbook/GUARDS.md` row, and a check whether an existing guard can be widened | `gate` marker; `tests/gates/` review; GUARDS.md quarterly review |
| No new abstraction without two concrete uses | review |
| Four layers only: `web \| cli` > `services` > `db \| adapters` > `ports` > `core`; `praw` only in `adapters/reddit_praw.py` | import-linter contracts in `.importlinter`; `tests/gates/test_layering.py` |
| `create_engine`, `text()`, `sqlite3.connect` only inside `db/`; `mock.patch` only in `tests/adapters/`; `encoding=` on every text open | ruff `TID251`, `PLW1514` |
| Never import another system's identifiers, attribution trailers, or model names into tracked text | `tests/gates/test_no_imported_identifiers.py`; `tools/hooks/no_bypass_git.sh` refuses a commit whose message carries a trailer |
| Every rule in this table names an enforcer that exists, or says review; review-only rules are a ceiling that only goes down | `tests/gates/test_rules_name_their_enforcer.py`; `.ratchets/review_only_rules.txt` |
| Generated data is produced by a script and never committed; one green commit per module | `tools/make_demo_fixture.py`; `.pre-commit-config.yaml` (large-file check); review for commit size |
| Tests never touch the network; warnings are errors | pytest `--block-network -W error` in `pyproject.toml`; `tests/gates/test_pytest_config.py` |
| Routing pointers (the routing tables, the rule files, the memory snapshot) name documents, sections, and paths that exist | `tests/gates/test_routing_rows_resolve.py` |
| `docs/recent/STATUS.md` is stamped within two days of HEAD, capped, carries the four resume headings, and restates no counts | `tests/gates/test_status_page.py` |
| Every gate file and every `gate` marker id has a `docs/runbook/GUARDS.md` row; every commit hash cited in a document resolves; Active rows without a positive control are a ceiling | `tests/gates/test_known_issues_cite_collected_tests.py`; `.ratchets/review_only_rules.txt` |
| One memory home; the committed snapshot is never behind live memory | `tools/memory_snapshot.py` `check` and `diff` in `make check`; `tests/gates/test_memory_snapshot.py` |
| Numbers have one home: a count or percentage lives where a tool prints it (`make check`, `.ratchets/`, the guards ledger) and prose points at it | `tests/gates/test_status_page.py` for the status page; elsewhere review |

## Routing: read before you touch

| If you are about to… | Read first |
|---|---|
| Start a session | `docs/recent/STATUS.md` |
| Touch the schema, migrations, upserts, FTS, backups | `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §1–§2, then `docs/runbook/RUNBOOK.md` § Migrate |
| Touch deletion, scrubbing, reconcile, or anything compliance-related | `docs/PLAN.md` § Data model (content-state machine), `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §2, `docs/runbook/KNOWN_ISSUES.md` |
| Add or change a gate, ratchet, invariant, or test policy | `docs/PLAN.md` § Robustness → "Guard design rules", `docs/reference/reviews/2026-09-12-db-learnings-review-A.md` §B, `docs/runbook/GUARDS.md` |
| Change the collector's fetch, budget, revisit, or search behavior | `docs/PLAN.md` § Collector algorithm, `docs/reference/reviews/2026-09-12-collector-design-review.md` §1 |
| Change the web UI | `docs/PLAN.md` § Web UI, `docs/reference/reviews/2026-09-12-ui-design-review.md` |
| Wonder why something was decided the way it was | `docs/insights/INSIGHTS_2026-09-12.md`, then `docs/decisions/DECISIONS.md` |
| Evaluate a new approach or library | `docs/decisions/DECISIONS.md` § settled negatives first (do not rebuild a killed lever) |
| Write a brief for a sub-agent | `docs/reference/AGENT_BRIEF.md` (the template), then the routing rows the task touches |
| Decide whether to adopt a practice from the earlier project | `docs/reference/reviews/2026-09-13-documentation-practices-assessment.md`, `docs/reference/reviews/2026-09-13-harness-assessment.md` § 7 |
| Run a retrospective, or judge whether a lesson from the earlier project held | `docs/learnings/LEARNINGS_TRANSFER.md` (§5 predictions; §6 how to evolve it) |
| Fix a bug, or harden a resolution so it cannot regress | `.claude/skills/harden/SKILL.md` (the checklist), then `docs/runbook/KNOWN_ISSUES.md` and `docs/runbook/GUARDS.md` |

## PR protocol

1. Branch from `main` (the pre-commit hook refuses commits on `main`). Write the failing test
   first (`core/` is strict TDD; `services/` test against the fake gateway and a temp DB created by
   `alembic upgrade head`). One green commit per module, tests and implementation together.
2. `make check` is green locally. Pre-commit runs on every commit: ruff, dmypy on the whole
   `src` tree, gitleaks, no files over 1 MB, no commits on `main`.
3. Open the PR with `.github/pull_request_template.md`: **What**; **Tests changed** (every file
   under `tests/`, with a reason); the pasted **make check** block; **Ratchets** moved;
   **Independent review** for anything under `db/migrations`, `services/scrub`, `core/deletion`,
   or `db/repo`.
4. Ratchets move only through `make ratchet-bump` (tighter) or
   `make ratchet-loosen KEY=… REASON="…"` (a loosening pauses for approval and lands a
   `GUARDS.md` row).
5. Land with `git merge --ff-only` into `main` once the gate is green (a merge commit on `main`
   is refused); never push to `main` directly once a remote exists; a push runs `make check` through the
   pre-push hook, because a remote is a backup and never the gate. Every fixed bug lands a
   `KNOWN_ISSUES.md` row and every settled choice a `DECISIONS.md` entry.

## Operator surface

The web UI is the operator surface for every routine action: runs, harvesting a post,
reconcile, re-tag, backups and restore, health checks, config and archive import/export,
first-run setup. The CLI exists for schedulers, containers, tests, and break-glass recovery.
The CLI mirrors the UI, never the reverse: both call the same `services/` functions, and
`web` never imports `cli` (import-linter enforces it).

## Reporting to Wes

Clarity, not brevity. Write for a typical engineer who does not carry the project's whole history in
their head: plain English, jargon reduced and explained on first use, more context where the logic is
complicated, never dumbed down. An update opens with a short summary of what happened and offers
detail rather than dumping it. Never bring a half-formed question: assess thoroughly first, then
present a plain-English summary with context, a recommendation, a confidence level, and the pros,
cons, and risks; ask only if a genuine choice remains. Every set of findings or options carries a
recommendation and a confidence level. Applies to chat, PR bodies, and document summaries.

## Practices carried from the earlier project (2026-09-13)

- **Claim provenance.** Any claim of the form "X works / is fixed / improved" in a PR body, commit
  message, or `DECISIONS.md` entry names the exact test, command, or query that verifies it; the
  review pass checks that the cited test asserts the claim, not that a similarly named test exists.
  A count, percentage, or date range an agent reports gets one spot-check against the data before it
  is written into a document. The operator is never the first to question a load-bearing claim.
- **Every mirror in the same change.** A decision that changes a settled fact is not complete until
  every document stating the old fact is annotated in the same PR, and the PR body names the
  documents swept.
- **Swept and clean.** A suspicion investigated and found not to be a bug is recorded in
  `docs/runbook/KNOWN_ISSUES.md` § Swept with how it was checked, so no later session re-investigates it.
- **Partial findings early.** On work spanning more than one stage or touching a core surface
  (deletion, scrub, migrations, `db/repo`, the ranking, the digest), the first partial finding or
  open question goes to Wes as a three-line note when it exists, not at the end.
- **Sessions start in the repo root.** Project hook settings load only from the session's starting
  directory, so a session that starts elsewhere runs without the hard-block hooks.
- **Number homes.** A count, percentage, or date range lives in one place, where a tool prints it
  (the `make check` output, `.ratchets/`, the guards ledger, a generated block), and prose points
  at it instead of restating it; the status page is gated on this and the rest is review.

## Agent model tiers

Every sub-agent call (the `Agent` tool or a workflow `agent()`) names its model; nothing inherits.
The main session carries planning, synthesis, decisions, and edits to the plan or enforcement
surfaces. **Opus** for judgement-bearing work: reviewers, judges and critics, migrations,
`core/deletion`, `services/scrub`, `db/repo`, under-specified services, red-gate debugging.
**Sonnet** for well-specified mechanical work: inventories, scans, codemods, tests written from a
spec row, fixture scrubbing, residue sweeps. Unsure → the higher tier, with the reason in the
workflow's `meta.description`. Full table: `docs/PLAN.md` § Review harness → "Agent model tiers". Every brief follows `docs/reference/AGENT_BRIEF.md`: purpose, the routing rows to read, the rules that bite, the files in scope, the output contract, and the model tier.

## Commands

`make setup` · `make check` · `make test` · `make run` · `make schema` · `make ratchet-bump` ·
`make ratchet-loosen KEY=… REASON="…"`
