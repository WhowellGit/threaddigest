---
purpose: How to set up, operate, deploy, migrate, restore, review, and keep the documents and memory of Insight Miner.
update-policy: prune-stale
mirrors: [docs/PLAN.md, docs/INSIGHTMINER_HARNESS.md, deploy/launchd/README.md]
verified-at: M1a-A
---
# Runbook — operating Insight Miner

> Skeleton seeded 2026-09-13 from `docs/PLAN.md` (Deployment path, Release/upgrade/migration practices, Portability targets, Workflows table) and the enforcement and database panel reports. Prune-stale: replace a step when the code changes it; never keep two versions of a procedure. Steps marked **(M1+)**, **(M2+)**, **(M4)** do not exist yet. The UI is the operator surface; every CLI line below has, or will have, a UI control, and the CLI is for schedulers, containers, tests, and break-glass.

## 1. Setup (fresh machine)

Target: under 10 minutes from clone to first run; the weekly portability CI job proves it on a clean Ubuntu container.

1. Prerequisites on a Mac: Homebrew; `brew install uv gh`; git identity `Wes Howell <wes@weshowell.com>`; `uv python install 3.13`.
2. Reddit side (Wes only): dedicated account with verified email; script app at reddit.com/prefs/apps (type **script**, redirect `http://localhost:8765`); accept the Data API terms; request API access through the form linked from the Data API wiki and keep the approval (the Responsible Builder Policy requires explicit approval before any data is accessed; `docs/reference/reddit-policy-facts-2026-09-14.md`); keep `client_id`, `client_secret`, username.
3. `git clone <repo> ~/repos/insightminer` — the path must be outside `~/Desktop`, `~/Documents`, `~/Downloads`, `/Volumes/*` (launchd/TCC) and contain no spaces. `doctor` checks this.
4. `make setup` — installs `uv` if missing (Homebrew, else the official installer), `uv python install 3.13`, `uv sync --all-groups`, copies `.env.example` to `.env` if absent, `uv run pre-commit install`. `db init` arrives with the CLI in M1a.
5. Put credentials in `.env` (owner-only permissions; never committed) or, from M2, use the browser `/setup` wizard (paste credentials, **Test connection**, choose subreddits, first sweep).
6. `uv run insightminer doctor` — expects auth OK with rate-limit headers and exactly two HTTP calls (token + about), DB at head, data dir writable and outside TCC folders.
7. **(M1a+)** `make run` for the first sweep (today it only prints that the command is not built yet), or `insightminer run --budget 5000` under `caffeinate -i` for the one-shot backfill (~1 hour). **(M1a+)**
8. Scheduler **(M1d+)**: `deploy/launchd/*.plist` with `ProgramArguments[0]` the absolute `.venv` interpreter (never `python3`, which is 3.9 on stock macOS), `StartCalendarInterval` Monday and Thursday at 06:30 for the run and hourly at :15 for `doctor --alert-if-stale 5d` (D-30), wrapped in `caffeinate -i`; `plutil -lint` the plist; load with `launchctl` through `deploy/launchd/install.sh` (steps in `deploy/launchd/README.md`). A two-minute test job verifies TCC behavior on this Mac before relying on it.
9. Non-developer hand-over **(M4)**: `docker compose up` then the `/setup` wizard; no terminal after that. The coworker registers their own Reddit app; secrets are never shared or exported.

Start every agent session in `~/repos/insightminer` (the repo root): the project's hard-block hooks are in `.claude/settings.json`, and project settings load only from the session's starting directory, never from a parent directory or a worktree (2026-09-13).

**Human-only edits arrive as generated scripts (Wes, 2026-09-14).** The enforcement hook refuses any agent write to `.claude/settings.json`, and that stays. When a hook entry must be added or changed, the agent generates a complete Terminal script by default and the human runs it, rather than hand-editing JSON: a subshell with `set -e` that makes a branch, applies the edit idempotently through a JSON round trip (refusing to apply twice), prints the diff, runs `make check`, commits, fast-forwards `main`, deletes the branch, and prints `tools/hooks_status.py`. The agent then verifies from its side with two positive controls: a write to the protected file (expected `BLOCKED`) and an edit the new hook governs (expected to fire). Why: the process stays deliberate, a human still runs the change, and the human is spared the syntax.

## 2. Daily operation from the UI

Recurring human duties are held to three: read the digest, acknowledge alerts in the UI, label theme tags while browsing.

1. Open `http://127.0.0.1:8765`. The header status pill (computed from `runs`, polled every 60 s) is the canonical alert: green ok, amber partial (warnings recorded), red failed or stale.
2. Read the digest at `/reports/{date}` **(M1d+)**: per theme, posts ranked by distinct authors; top untagged posts of the last 7 days with ≥3 distinct authors; rising title phrases; per-subreddit counts and statuses; backlog, gaps, errors, unknown enum values, reconcile tier in force. Weekly, read one digest against Reddit itself and file mismatches as issues.
3. `/runs`: history with per-sub outcomes. **Run now** offers full run, fetch only, reconcile only, re-tag only, saved searches only (M3); 409 while a run is active; Cancel ends the run at the next batch boundary. Errors are mapped to plain text (401 credentials, 403 UA/blocked, 429 backed off, network, DB locked) with the log and traceback below.
4. `/settings/subreddits`: add with live validation and preview; pause/resume; comment mode; **Stop, keep data** vs **Stop and delete captured data** (typed word + verified backup gate).
5. `/settings/themes`: edit rules with the live preview (denominators shown; a rule tagging most of everything is visibly non-diagnostic); Save re-tags through the CLI subprocess with a run row; stale badge until re-tagged. Thumbs up/down on tags while browsing **(M2+)**.
6. `/system`: every `doctor` check as a row; **Run checks** (no-network by default, checkbox for the auth ping); migration state; last backup; **Send test notification**. `/system/backups`: create, verify, restore (gated). `/system/maintenance`: reconcile now, re-tag all, reprocess from raw, import config YAML or an export archive from a server-side path, recent logs.
7. `/export`: builds `data/exports/insightminer-<ts>.zip` (DB snapshot via the backup API + integrity check, live-content JSONL, config YAML without secrets, redacted settings, `MANIFEST.json`, `README.txt`); keeps the last 3; refuses when free disk < 2× data size.
8. If the pill is red: open `/runs/{id}` for the mapped error; if credentials, `/setup`; if migrations pending, `/system` → **Apply pending migration** (backs up first); if the run never happened, check Healthchecks.io **(M1d+)** and `launchctl list`.

## 3. Deploy (code change)

1. Failing test first → implement → `make check` green locally (ruff, mypy strict, import-linter, pytest with `--block-network` and `-W error`, schema snapshot, pytest-alembic, ratchet compare).
2. Commit on a branch (pre-commit: ruff format+lint, `dmypy` whole tree, gitleaks, large-file check, `no-commit-to-branch main`). Never `--no-verify`.
3. Open the PR with the template: `## Tests changed` (file, reason per changed `tests/**` file), the pasted `make check` block, ratchet table, `## Independent review` for deletion/scrub/migration/`repo.py` changes.
4. CI required check today: `check` (the workflow also has `py314`, `portability`, `actionlint`). Planned for M1: `ratchets`, `ratchet-loosen-approval` (runs only on a loosening; Wes clicks approve after reading the `GUARDS.md` ledger row), `pr-body`. CI has not executed yet: the repo has no remote. Merge when green.
5. **(M1d+)** `make deploy` on the Mac: `git pull`, `uv sync --frozen`, `insightminer db upgrade` (backs up first, § 4), restart `serve`; then `insightminer doctor`.
6. Post-deploy: the next scheduled run's status on `/runs`; the weekly `audit` issue lists every enforcement-surface change for Wes to read.
7. Roll back: previous git tag + `db restore` of the pre-migration backup (§ 5). Never auto-downgrade.

## 4. Migrate (schema change)

Every schema change is an Alembic migration (`render_as_batch=True`, naming convention, reversible, never edited after it is applied). Full PR checklist: database panel report § C (`docs/reference/reviews/2026-09-13-panel-db-integrity.md`).

1. **(M1a+)** Before writing the migration, generate the fixture DB for the *current* head from pre-change code: `make fixture` → `tests/fixtures/db/<rev>.sqlite` + manifest (the set must equal `alembic history` minus head). Until the generator exists, the fixture for the current head is the previous fixture upgraded by the migrations as they stand before the new one, checkpointed so no sidecar is left, with its row counts copied into the manifest; revision 0002's was made that way on 2026-09-14, and revision 0003's on 2026-09-15 (upgrading the 0002 fixture before writing revision 0004).
2. Write the migration; batch operations on `posts`/`comments` must `DROP VIEW posts_live` first, recreate the view and the three FTS triggers after, then run the FTS `'rebuild'`; `PRAGMA foreign_keys=OFF` is issued in `env.py` outside the transaction (a no-op inside one); `transaction_per_migration=True`.
3. New NOT NULL columns are expand/contract: add nullable → backfill from `raw_json` → switch reads → drop later. Never rename in place. A new invariant is scoped by `normalizer_version` or a backfill flag so it cannot turn day one red.
4. `make schema` regenerates `src/insightminer/db/schema.sql` (DDL plus the generated column-comment section); review its diff in the PR. Models must match DDL (`include_object` excludes `%_fts`, `%_fts_%`, `%_live`).
5. Apply on a machine: `insightminer db upgrade` (or `/system` → **Apply pending migration**): online `Connection.backup()` to `data/backups/pre-migrate-<from>-<to>-<utc>.db` + `quick_check` **before** Alembic runs; after: `integrity_check`, `foreign_key_check`, `alembic_version == head`, `backups` row `kind='pre-migrate'`. On failure the copy is restored byte-identical and the command exits non-zero. Keep the last few pre-migration copies (D-31; and, until the retention pruning lands at M1d, no backup older than `retention.backups_days`, `DECISIONS.md` § 2).
6. `serve` runs in **maintenance-only mode** (system, backups, health, setup pages) while migrations are pending; `run` refuses (exit 78).
7. Semantic change to an existing column = separate PR with a `normalizer_version` bump, updated reprocess golden rows; a refactor keeps the reprocess golden byte-identical.

## 5. Restore drill

Backups: one `VACUUM INTO data/backups/<date>.db` at the end of each scheduled run, taken after reconcile so it is already scrubbed, each recorded in the `backups` table with path, sha256, size, integrity result, kind. The database is the long-term archive and backups are disaster-recovery copies: the two most recent post-reconcile copies are kept plus the off-machine copy once the NAS remote exists, and the last few pre-migration copies (decided 2026-09-15; `docs/PLAN.md` § Release). Retention pruning is an M1d blocker; until it is built, `retention.backups_days` in `config/settings.yaml` bounds the age of every copy. Destructive operations (`db restore/downgrade/reprocess`, `subs remove --delete-data`, container `INIT`, retention sweep) require a verified backup within N hours plus the `Confirmation` (typed word in the UI, `--yes` on the CLI), checked inside the service.

Drill (plan: quarterly, manual, logged here; panels propose weekly automation — `db restore --to-temp --verify` writing a `drills`/`backups` row and `doctor` red when the last drill is older than 100 days — **pending Wes**):

1. Pick the latest verified backup on `/system/backups` (stored integrity result; **Verify now** re-checks the file).
2. `insightminer db restore <file> --to-temp <dir>` **(M1c+)**: restores into a temporary data dir, runs `doctor --no-network`, compares per-table counts with the `backups` row.
3. Record date, backup file, counts compared, and outcome below. A failed drill is a `KNOWN_ISSUES.md` row.
4. Real restore (`/system/backups` → **Restore**, typed `restore`): pre-restore backup first, atomic swap under the lock, engine reopened; 409 while a run is active; 75 if the lock is held.

| Date | Backup | Method | Counts match | `doctor` | Outcome / notes |
|---|---|---|---|---|---|
| | | | | | |

## 6. Quarterly guard review

Source: enforcement panel report § F and the plan's guard design rules. Ledger: `docs/runbook/GUARDS.md`.

1. `make guard-review` **(M3+)** prints one row per gate id: date its positive control last ran (junit), firings this quarter (pinned "Guard firings" issue, never typed), runtime cost.
2. Wes assigns a verdict per guard: **EARNED** (fired in anger and was right), **EARNED AT BIRTH ONLY**, **UNPROVEN**, **SELF-SERVING** (fires only on its own test or on formatting).
3. Rules: SELF-SERVING → drop or redesign this quarter. UNPROVEN for four consecutive quarters and > 5 s per run → drop candidate unless the class is data loss or compliance (thresholds pending Wes). Every loosening approved this quarter is re-read for a pattern. Adding a guard goes through the guard-count approval path and needs a birth incident, a positive control, and a `GUARDS.md` row; widening an existing guard is preferred and needs no approval.
4. Record the count in the review note **with its source line** from the tool output; move dropped guards to `GUARDS.md` § Retired with the reason and what replaced them.
5. Same session: restore drill (§ 5) if not automated; prune `docs/` for exhaust; re-read `DECISIONS.md` triggers.
6. Routing drill (review-only, added 2026-09-14): give one fresh-context agent a brief for one routed area (`docs/reference/AGENT_BRIEF.md`) and check from its transcript that it read the routed documents before editing; record hit or miss in the table below. The structural half (every pointer resolves) is mechanical: `tests/gates/test_routing_rows_resolve.py`.

| Quarter | Date | Active count (source line) | Verdicts changed | Dropped / widened | Notes |
|---|---|---|---|---|---|
| | | | | | |

## 7. External review packet

When a review trigger fires (a complex problem solved, a significant design plan finalised, a risky fix confirmed, a module started or finished, any change to an enforcement surface; `docs/reference/reviews/REGISTER.md`), an outside reviewer gets the committed tree and nothing else.

1. Commit everything; the builder refuses a dirty tree. Run `uv run python tools/review_packet.py --desktop`. It writes the packet under `.build/review-packets/<date>-<commit>/` (originals under `tree/`, four bundles, the README with the reading order, the brief rendered from `docs/reference/reviews/templates/external-deep-research.md`, the claims list from `templates/claims.md`, and `MANIFEST.json` with a sha256 per file and one packet hash) and copies the upload set to the Desktop.
2. Before the first upload to a consumer plan, confirm that plan's data controls exclude the conversation from training (`docs/decisions/DECISIONS.md` § 2026-09-14 (later)). Upload the eight files of the upload set and paste `01-QUERY.md` as the prompt, once per provider, the same packet to each, so the findings are comparable.
3. Triage every finding by re-running the specific check it names, never by reading it twice: confirmed, refuted with the evidence, or cannot tell. Findings are weighed by independence and evidence, never tallied; one evidenced dissent outranks three agreements. A finding that rests on a live page is checked against the page by the session itself: the browser pane first, a plain HTTPS fetch as the fallback (Reddit's hosts refuse the fetch tool), the facts recorded in a dated file under `docs/reference/` that the next packet carries; never delegated to a human. A reviewer whose citations name files the packet does not contain is judged on substance alone and weighed as low independence.
4. Write one record per packet round, `docs/reference/reviews/<date>-external-round-<n>.md`, with a section per reviewer labelled A, B, C (never a product or model name: the register's tier convention): what the reviewers were given (the commit and packet hash), each finding with its triage verdict and evidence, how the reviewers were weighed, and what changed as a result; add one register row with the packet's commit as scope. Delete the Desktop copy once the uploads are done; the packet's home is `.build/`, untracked, and it can be rebuilt from the commit at any time.

## 8. Documents and memory: the update process

**In one paragraph.** Every living document under `docs/` declares what it is for, how it may change, which documents mirror it, and the milestone it was last verified at, in front matter that a tool checks (`tools/doc_policy.py`, G55). Logs are appended; everything else is rewritten in place, section by section, when a fact changes. A dated annotation in the prose of a rewritten document is a debt the ratchet counts; the count is a pressure the milestone pass reads, and once it accretes the answer is a targeted rewrite or a new version, never another annotation. A fact listed in the live-facts table has one home and one literal, and every listed mirror must state it; that is the mechanical part of the sweep, and whether a mirror's prose still agrees with its source is the review part. Memory routes to documents and never restates state that has a document home.

**The policies.** `append-only` (the decisions log, the insights, the learnings, the drift findings): add entries anywhere, insert a dated parenthetical into a line or extend its end, never delete, move, or otherwise change a line that existed at the merge base with `main`; a named table column may be filled in (`exempt-sections`); the policy declared at the base governs, so a document cannot exempt itself. `prune-stale` (the runbook, the guards ledger, the known-issues register, the test strategy, the overview, the harness page, the router): when a fact changes, rewrite the section that states it, delete what is wrong, and do not leave a trail; the section's history is in git; a ledger's own rule that a row is never deleted is review. `versioned` (the plan): corrected in place between versions and rewritten as a new version once annotations accrete, with every retired section given a home in the decisions log in the same change. `rewritten` (the status page): replaced whole, stamped, capped; its `milestone` is the clock the lag check reads. A generated block, such as the harness inventory, is a region inside a prune-stale page, produced by a tool and gated. `docs/reference/` holds dated records of what a reviewer, a report, or an earlier project said: a record is added, never edited, because editing it rewrites history, and the check compares every record with the base; the review register is append-only and the templates are reviewed like code.

**Choosing the move.** Ask what kind of document holds the fact. In a log, append a dated entry and, if an earlier entry is now wrong, insert a dated parenthetical into that entry's line pointing at the new one. In a rewritten document, find every section that states the fact and rewrite it; a targeted rewrite of one section is the normal move, a whole-document rewrite is the move when the accretion ceiling is reached or a milestone changes the shape of the document. Never add a paragraph that begins "update:" or "note:"; never leave the old sentence beside the new one.

**The sweep, after any change that settles or changes a fact** (the `docs-sweep` skill is the checklist): (1) name the fact and its canonical home; (2) list the mirrors: the `mirrors` of the document you changed, every document whose `mirrors` names it, the live-facts row if one exists, and the code defaults behind any configured value; (3) for each, choose the move above and make it, reading the mirror's prose yourself, because only the facts table is checked mechanically; (4) if the fact retires a phrase, add a retired-claims row; if it is a fact that will repeat, add or update a live-facts row; (5) run `uv run python tools/doc_policy.py --check` and `make check`; (6) record a decision entry if a choice was made.

**Retiring a document.** Move a record to `docs/reference/` or delete the file; remove its router line (the currency gate requires it) and add a tombstone line under the router's retired list naming the successor; run the check, which reports every rewritten document that still points at it.

**The milestone pass.** When the status page's milestone advances, every rewritten document must be re-read within one milestone: confirm or rewrite it and set its `verified-at`. The lag gate makes the pass mandatory rather than remembered. The pass also reviews memory (below) and the accretion count.

**Memory: what to keep, how to prune.** Memory is the router that survives compaction and session boundaries: a memory says where to look and what to do differently, in a few lines, and points at the document that holds the state. Keep: how Wes works and what he has corrected (feedback); who he is and what the project is for (user); the routing hooks into the corpus and the facts no document holds, such as where the archive lives and how a change lands (project); pointers to external resources (reference). Do not keep: state the status page or the decisions log holds, counts, chronologies, or anything a gate derives. Etiquette for a new memory: one fact per file, a name that is a slug, a description that is the recall hook, a short body, links to related memories, and a document path when the fact has a home; write it when a correction or a durable fact appears, not for every fix. Pruning: at every milestone pass and whenever a memory is superseded, delete the superseded memory rather than annotate it, shorten any file near the cap, and re-read the index as a stranger would. The checks (`tools/memory_snapshot.py check` in `make check`): the index budget, reachability, the frontmatter contract, one memory home, a byte cap per topic file, and a project memory that names an existing repository path; the snapshot in `memory-snapshot/` is add-or-update only and must never lag live memory.
