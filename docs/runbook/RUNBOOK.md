# Runbook — operating Insight Miner

> Skeleton seeded 2026-09-13 from `docs/PLAN.md` (Deployment path, Release/upgrade/migration practices, Portability targets, Workflows table) and the enforcement and database panel reports. Prune-stale: replace a step when the code changes it; never keep two versions of a procedure. Steps marked **(M1+)**, **(M2+)**, **(M4)** do not exist yet. The UI is the operator surface; every CLI line below has, or will have, a UI control, and the CLI is for schedulers, containers, tests, and break-glass.

## 1. Setup (fresh machine)

Target: under 10 minutes from clone to first run; the weekly portability CI job proves it on a clean Ubuntu container.

1. Prerequisites on a Mac: Homebrew; `brew install uv gh`; git identity `Wes Howell <wes@weshowell.com>`; `uv python install 3.13`.
2. Reddit side (Wes only): dedicated account with verified email; script app at reddit.com/prefs/apps (type **script**, redirect `http://localhost:8765`); accept the Data API terms; keep `client_id`, `client_secret`, username.
3. `git clone <repo> ~/repos/insightminer` — the path must be outside `~/Desktop`, `~/Documents`, `~/Downloads`, `/Volumes/*` (launchd/TCC) and contain no spaces. `doctor` checks this.
4. `make setup` — installs `uv` if missing (Homebrew, else the official installer), `uv python install 3.13`, `uv sync --all-groups`, copies `.env.example` to `.env` if absent, `uv run pre-commit install`. `db init` arrives with the CLI in M1a.
5. Put credentials in `.env` (owner-only permissions; never committed) or, from M2, use the browser `/setup` wizard (paste credentials, **Test connection**, choose subreddits, first sweep).
6. `uv run insightminer doctor` — expects auth OK with rate-limit headers and exactly two HTTP calls (token + about), DB at head, data dir writable and outside TCC folders.
7. **(M1a+)** `make run` for the first sweep (today it only prints that the command is not built yet), or `insightminer run --budget 5000` under `caffeinate -i` for the one-shot backfill (~1 hour). **(M1a+)**
8. Scheduler **(M1d+)**: `deploy/launchd/*.plist` with `ProgramArguments[0]` the absolute `.venv` interpreter (never `python3`, which is 3.9 on stock macOS), `StartCalendarInterval` 06:30, wrapped in `caffeinate -i`; `plutil -lint` the plist; load with `launchctl`. A two-minute test job verifies TCC behavior on this Mac before relying on it.
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

1. **(M1a+)** Before writing the migration, generate the fixture DB for the *current* head from pre-change code: `make fixture` → `tests/fixtures/db/<rev>.sqlite` + manifest (the set must equal `alembic history` minus head).
2. Write the migration; batch operations on `posts`/`comments` must `DROP VIEW posts_live` first, recreate the view and the three FTS triggers after, then run the FTS `'rebuild'`; `PRAGMA foreign_keys=OFF` is issued in `env.py` outside the transaction (a no-op inside one); `transaction_per_migration=True`.
3. New NOT NULL columns are expand/contract: add nullable → backfill from `raw_json` → switch reads → drop later. Never rename in place. A new invariant is scoped by `normalizer_version` or a backfill flag so it cannot turn day one red.
4. `make schema` regenerates `src/insightminer/db/schema.sql` (DDL plus the generated column-comment section); review its diff in the PR. Models must match DDL (`include_object` excludes `%_fts`, `%_fts_%`, `%_live`).
5. Apply on a machine: `insightminer db upgrade` (or `/system` → **Apply pending migration**): online `Connection.backup()` to `data/backups/pre-migrate-<from>-<to>-<utc>.db` + `quick_check` **before** Alembic runs; after: `integrity_check`, `foreign_key_check`, `alembic_version == head`, `backups` row `kind='pre-migrate'`. On failure the copy is restored byte-identical and the command exits non-zero. Keep the last 3 pre-migration backups (and no backup older than 14 days, `DECISIONS.md` § 2).
6. `serve` runs in **maintenance-only mode** (system, backups, health, setup pages) while migrations are pending; `run` refuses (exit 78).
7. Semantic change to an existing column = separate PR with a `normalizer_version` bump, updated reprocess golden rows; a refactor keeps the reprocess golden byte-identical.

## 5. Restore drill

Backups: daily `VACUUM INTO data/backups/daily-<date>.db` at the end of each run (7 daily + 4 weekly kept, none older than 14 days), each recorded in the `backups` table with path, sha256, size, integrity result, kind. Destructive operations (`db restore/downgrade/reprocess`, `subs remove --delete-data`, container `INIT`, retention sweep) require a verified backup within N hours plus the `Confirmation` (typed word in the UI, `--yes` on the CLI), checked inside the service.

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
3. Triage every finding by re-running the specific check it names, never by reading it twice: confirmed, refuted with the evidence, or cannot tell. Findings are weighed by independence and evidence, never tallied; one evidenced dissent outranks three agreements.
4. Write the record as `docs/reference/reviews/<date>-external-<provider>.md` (what the reviewer was given: the commit and packet hash; each finding with its triage verdict; what changed as a result) and add the register row with the packet's commit as scope. Delete the Desktop copy once the uploads are done; the packet's home is `.build/`, untracked, and it can be rebuilt from the commit at any time.
