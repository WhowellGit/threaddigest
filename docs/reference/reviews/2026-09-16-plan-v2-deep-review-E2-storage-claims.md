# Plan version two: storage and operations claims against the code (2026-09-16)

## Claim under test

"Every sentence in `docs/PLAN.md` that describes what a built storage, migration, backup,
health, or deployment component does (the pragmas on every connection and their values, the
checkpoint at the end of a run and its retry, the upsert form and the PK-stability invariant,
the FTS design (external content over live views, the change-gated triggers, secure-delete,
optimize), the backup mechanism and what is recorded on the backups table, what `db upgrade`
does before and after migrating and what `restore` does on failure, the fingerprint warning,
every doctor check named in the CLI row, the post-run invariants named in Silent-failure
controls, the launchd schedule and its wrapper's behaviour, the reconcile tiers and their
bounds, the retention bound) is true of the code, and a test asserts it."

Refute-framed: the pass looked for sentences the code contradicts, sentences describing
components that do not exist, and sentences asserting that a test exists when it does not.

## Method

1. Read `docs/PLAN.md` whole, then extracted every behavioural sentence from the sections the
   brief named: § Data model (conventions, table-to-writer map, the `backups` and FTS rows,
   schema revisions, the content-state machine, scrub, SQLite facts), § Collector algorithm
   steps 0, 4 and 6, § Resilience, the `doctor` and `db` CLI rows, § Silent-failure controls,
   § Release (Schema, Safety, Backups and retention, Connections, Reprocessing, Startup
   checks), § Deployment path, and the storage-rationale paragraph (line 92).
2. For each, read the implementing module and located the asserting test by node id. Nothing
   in the repository was written to; no test run was needed to settle any row, because every
   claim resolved by reading the shipped code and the shipped test bodies (the two places a
   run would have added information — the launchd wrapper's exit-code map and the checkpoint
   retry — both carry explicit assertions that were read directly).
3. Judged severity for two readers: someone building tranche B, M1b or M1c from this plan, and
   the compliance invariant of `DECISIONS.md` § 2 (a deletion learned on Reddit must leave the
   store and the backups within the stated bounds).
4. Cross-read `docs/runbook/KNOWN_ISSUES.md` (KI-009, KI-010, KI-012 to KI-016, KI-024 to
   KI-026) for fixed-bug old behaviour restated and open-bug consequence omitted.
5. Read `docs/runbook/RUNBOOK.md` § 4 (Migrate) and § 5 (Restore drill / Backups) against the
   same code.

Status vocabulary: `holds` (code does it, a test asserts it), `holds, untested` (code does it,
no test), `differs` (code does something else), `not built` (stated as present-tense fact but
absent), `not found`.

## Claims

| n | Plan line | Claim (ten words) | Code file:line | Test node id | Status |
|---|---|---|---|---|---|
| 1 | 463 | every connection sets `journal_mode=WAL` | src/insightminer/db/engine.py:47 | tests/db/test_engine_pragmas.py::test_two_pool_checkouts_both_carry_the_pragmas | holds |
| 2 | 463 | every connection sets `synchronous=NORMAL` | src/insightminer/db/engine.py:48 | same as 1 | holds |
| 3 | 463 | every connection sets `foreign_keys=ON` | src/insightminer/db/engine.py:49 | tests/db/test_engine_pragmas.py::test_foreign_keys_are_enforced | holds |
| 4 | 463 | every connection sets a `busy_timeout` (30 s) | src/insightminer/db/engine.py:42,50 | tests/db/test_engine_pragmas.py::test_busy_timeout_is_overridable_and_defaults_to_30s | holds |
| 5 | 463 | every connection sets `temp_store=MEMORY` | src/insightminer/db/engine.py:51 | same as 1 | holds |
| 6 | 463 | every connection sets `secure_delete=ON` | src/insightminer/db/engine.py:52 | same as 1 | holds |
| 7 | 387 | only `db.engine` creates engines (chokepoint) | src/insightminer/db/engine.py:102 | tests/gates/test_sqlite3_confined.py, tests/gates/test_layering.py | holds |
| 8 | 463 | database on a local filesystem, never a share | — | — | holds, untested (review-only) |
| 9 | 186,463 | `wal_checkpoint(TRUNCATE)` at the end of a run | src/insightminer/services/collect.py:163; db/engine.py:143 | tests/e2e/test_run_happy_path.py::test_wal_is_truncated_at_end_of_run | holds |
| 10 | — | the checkpoint's retry, warning and `partial` (KI-013) | src/insightminer/services/collect.py:271-291 | tests/services/test_collect_checkpoint.py::test_a_reader_during_the_final_checkpoint_leaves_a_warning_and_a_partial_run | code holds; **plan silent** (finding 7) |
| 11 | 463 | a minimum SQLite version, checked by `doctor` | db/backup.py:43; services/doctor.py:317 | tests/services/test_doctor.py::test_check_sqlite_version_is_an_error_below_the_secure_delete_floor | holds |
| 12 | 146 | `pk INTEGER PRIMARY KEY AUTOINCREMENT` on posts/comments | db/migrations/versions/0001_initial.py:730,905 | tests/db/test_schema_shape.py::test_every_pk_column_is_a_rowid_alias | holds |
| 13 | 146 | upserts `ON CONFLICT(reddit_id) DO UPDATE`, never REPLACE | db/repo.py:248-270 | tests/db/test_alembic.py::test_on_conflict_upsert_preserves_pk_and_first_seen_at (control ::test_insert_or_replace_burns_the_pk_and_detaches_fts) | holds |
| 14 | 146 | reruns leave `pk` and `first_seen_at` unchanged | db/ownership.py:110-116 | tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at | holds |
| 15 | 146 | ...and `max(pk) == count(*)` unchanged | only tests/db/test_alembic.py:85 (no-purge fixture) | — | **differs** (finding 4) |
| 16 | 146 | `next_check_at` is NOT NULL | db/schema.sql | tests/db/test_schema_shape.py::test_next_check_at_is_not_null | holds |
| 17 | 146 | every column carries a SQLAlchemy `comment=` | db/schema.py | tests/db/test_schema_shape.py::test_every_column_has_a_single_line_comment | holds |
| 18 | 146 | all timestamps are INTEGER epoch seconds | db/schema.py | tests/db/test_schema_shape.py::test_every_timestamp_is_integer_epoch_and_no_datetime_anywhere | holds |
| 19 | 146 | subreddit identity unique within a workspace | db/schema.sql (uq_subreddits_workspace_*) | tests/db/test_schema_shape.py::test_subreddit_identity_is_per_workspace | holds |
| 20 | 146 | the eight declared indexes exist | db/schema.sql:25-32 | tests/db/test_schema_shape.py::test_declared_indexes_exist | holds |
| 21 | 146 | `EXPLAIN QUERY PLAN` assertions prove hot queries use them | — | tests/db/test_query_plans.py (4 tests) | holds |
| 22 | 148 | the sweep never moves `first_seen_at`/`check_stage`/`next_check_at` | db/ownership.py:88-117 | tests/db/test_repo_ownership.py | holds |
| 23 | 148 | the web layer writes seven tables through a repository | — | — | not built (M2, marked in the module map) |
| 24 | 56,166 | FTS5 external content over `posts_live`/`comments_live` | db/schema.sql:8,13,23,24 | tests/db/test_fts.py::test_fts_definition_shape | holds |
| 25 | 166 | tokenizer `porter unicode61` | db/schema.sql:8,13 | same as 24 | holds |
| 26 | 166,168 | update triggers gated on an actual change (0003) | db/schema.sql:38,41 | tests/db/test_fts.py::test_a_routine_upsert_with_identical_text_leaves_the_index_untouched (control ::test_positive_control_the_unconditional_trigger_rewrote_the_index) | holds |
| 27 | 166,168 | persistent `secure-delete` on both indexes (0004) | db/migrations/versions/0004_fts_secure_delete.py:44 | tests/db/test_fts.py::test_scrub_with_secure_delete_leaves_no_term_bytes_without_an_optimize (control ::test_positive_control_without_secure_delete_the_term_survives_a_scrub_until_optimize) | holds |
| 28 | 166 | membership counted from `posts_fts_docsize` | db/fts.py:32-39 | tests/db/test_fts.py::test_naive_count_is_the_content_count_not_membership | holds |
| 29 | 176 | `count(*)` on external content returns the content count | db/fts.py:8-10 | same as 28 | holds |
| 30 | 176 | rebuild / live-only views ("re-indexes tombstones") | db/fts.py:42-45 | tests/db/test_fts.py::test_rebuild_indexes_live_rows_only_and_passes_integrity_check | holds; **sentence garbled** (finding 13) |
| 31 | 168,174 | the `optimize` after each scrub is `db.fts.optimize` | db/fts.py:48 exists, no caller | — | not built (M1c, marked) |
| 32 | 174 | scrub nulls content, tombstones raw_json, drops post_themes | — | — | not built (M1c, marked at line 387) |
| 33 | 176 | `secure_delete` does not reach FTS5 shadow segments | — | tests/db/test_fts.py::test_positive_control_without_secure_delete_the_term_survives_a_scrub_until_optimize | holds |
| 34 | 460 | `render_as_batch`, one transaction per migration | db/migrations/env.py:99-100 | tests/db/test_alembic.py::test_foreign_keys_off_inside_migration_and_clean_after | holds |
| 35 | 460 | `include_object` excludes shadow tables and live views | db/migrations/env.py:41-80 | tests/db/test_schema_golden.py (models == DDL) | holds |
| 36 | 460 | foreign keys off during batch migrations | db/migrations/env.py:82-93 | tests/db/test_migrate_revisions.py::test_a_batch_recreate_with_foreign_keys_on_would_cascade | holds |
| 37 | 460 | a naming convention so batch ops drop constraints by name | db/schema.py:129 | tests/db/test_schema_shape.py::test_constraint_names_follow_the_naming_convention | holds |
| 38 | 460 | FTS tables and triggers created with `IF NOT EXISTS` | 0001_initial.py:33-90; 0003:32-77 | tests/db/test_schema_golden.py | holds |
| 39 | 460 | the fixture test asserts index membership equals live rows | — | tests/db/test_alembic.py::test_revision_fixture_upgrades_clean | holds |
| 40 | 176,460 | batch recreates fail while a view references the table | — | — | holds, untested (finding 15) |
| 41 | 168 | revisions 0001-0004 as described, each with a fixture | db/migrations/versions/ | tests/db/test_alembic.py::test_fixture_set_equals_non_head_revisions | holds |
| 42 | 146,460 | AUTOINCREMENT means a purge cannot recycle a rowid | 0001_initial.py:730,905 | tests/db/test_schema_shape.py::test_every_pk_column_is_a_rowid_alias | holds today; **KI-014 consequence omitted** (finding 8) |
| 43 | 461 | `db upgrade` takes an online backup first | services/migrate.py:377-378 | tests/services/test_migrate_service.py::test_backup_precedes_migration_and_records_a_row | holds, except "always" (finding 10) |
| 44 | 461 | `quick_check` on the copy, abort before migrating | services/migrate.py:379-409 | tests/services/test_migrate_service.py::test_quick_check_failure_aborts_before_migrating | holds |
| 45 | 461 | then `integrity_check` and `foreign_key_check` | services/migrate.py:467-496 | tests/services/test_migrate_service.py::test_post_checks_run_after_upgrade, ::test_a_failed_integrity_check_also_restores | holds |
| 46 | 461 | on failure it restores the copy and exits non-zero | services/migrate.py:499-564 | tests/e2e/test_db_commands.py::test_failed_upgrade_restores_and_finishes_the_run_row_failed | holds |
| 47 | 461 | `restore` copies the live file aside first (KI-015) | db/backup.py:242-279 | tests/db/test_backup.py::test_a_restore_whose_copy_fails_leaves_the_live_database_and_its_log_untouched | holds |
| 48 | 461 | `restore` swaps atomically, under the lock | db/backup.py:275 (atomic); no `db restore` command | tests/db/test_backup.py::test_restore_swaps_the_file_and_removes_wal_sidecars | partly not built (the lock half: M1c) |
| 49 | 92,186 | the copy is SQLite's online backup API, not a file copy | db/backup.py:159-196 | tests/db/test_backup.py::test_online_backup_succeeds_while_the_source_has_an_uncommitted_writer | holds |
| 50 | 163 | the `backups` row's eight columns | db/schema.sql:5; db/repo.py BackupInsert | tests/db/test_repo_upsert.py::test_backup_rows_round_trip_newest_first_and_delete_by_pk | holds |
| 51 | 163 | the destructive gate keys on a `backups` record | — | — | not built (M1c-M2, marked at line 388) |
| 52 | 462 | the last few pre-migration copies are kept | services/migrate.py:80,262-293 | tests/services/test_migrate_service.py::test_prune_pre_migrate_backups_deletes_the_rows_and_returns_the_files | holds |
| 53 | 186,462 | one online-backup copy per scheduled run, after reconcile | no caller of `online_backup` outside `db upgrade` | — | **not built** (finding 1) |
| 54 | 462 | `retention.backups_days` is the configured bound | settings.py:161 declares it; no reader in `src/` | — | **not built** (finding 1) |
| 55 | 462 | the compliance canary asserts backup file ages | — | — | **not built** (finding 1) |
| 56 | 215 | the fourteen `doctor` checks, in that order, plus hooks | services/doctor.py:708-772 | tests/services/test_doctor.py::test_run_checks_covers_every_documented_check_name (+ an ok and a not-ok test per check) | holds |
| 57 | 194,215 | `--alert-if-stale` default outlasts the longest gap, shared with the wrapper | services/doctor.py:150 | tests/deploy/test_schedule_contract.py::test_doctor_default_threshold_outlasts_the_longest_gap_and_matches_the_wrapper | holds |
| 58 | 176,383 | the fingerprint is derived, not stored, and warns | db/schema_dump.py:124,163; services/doctor.py:336 | tests/services/test_doctor.py::test_schema_fingerprint_mismatch_is_a_warning_not_an_error | holds |
| 59 | 215 | `doctor` writes nothing (not even the data tree) | services/doctor.py:203-231 | tests/services/test_doctor.py (tree snapshot), tests/gates/test_mutating_commands.py | holds |
| 60 | 466 | `run` refuses if migrations are pending | cli.py:435,461-465 | tests/e2e/test_run_lock_and_preconditions.py | holds (`serve`: M2) |
| 61 | 400 | invariant: counters equal table deltas | services/invariants.py:151 | tests/gates/test_invariants_planted.py; tests/services/test_invariants.py | holds |
| 62 | 400 | invariant: no other `running` rows | services/invariants.py:184 | same as 61 | holds |
| 63 | 400 | invariant: index membership equals live rows by content | services/invariants.py:200-229 | tests/services/test_invariants.py::test_fts_membership_equals_live_flags_an_equal_count_substitution | holds |
| 64 | 400 | invariant: rows carry the current `normalizer_version` | services/invariants.py:232 | same as 61 | holds |
| 65 | 400 | invariant: unknown enum values are counted | services/invariants.py:253 | tests/services/test_invariants.py::test_unknown_enum_counter_is_final_before_the_invariants_run | holds |
| 66 | 400 | invariant: population floors on three posts columns | services/invariants.py:86,279 | same as 61 | holds |
| 67 | 400 | freshness covers "each **enabled** subreddit" | db/repo.py:928-943 (enabled **plus** error-disabled) | tests/services/test_invariants.py | **differs**, in the safe direction (finding 3) |
| 68 | 400 | "a zero-yield run across all sources flags `degraded`" | no `degraded` anywhere in `src/` | — | **not found** (finding 3) |
| 69 | 400 | each invariant has a positive control through `run --gateway fake` | — | tests/gates/test_invariants_planted.py (parametrized over `INVARIANTS`) | holds |
| 70 | 398 | any warning makes the run `partial`; `ok` means zero | services/runs.py::resolve_status | tests/services/test_runs_lifecycle.py | holds |
| 71 | 398 | exception text never reaches an error column (KI-010) | db/engine.py:99-102 | tests/db/test_engine_pragmas.py::test_error_text_hides_bound_parameters; tests/services/test_sweep_errors.py::test_a_failed_page_write_keeps_post_text_out_of_the_error_message | holds |
| 72 | 402 | structured per-run JSON-line logs, counts mirrored on the run row | `runs.log_path` written NULL at runs.py:359, cli.py:406, migrate.py:249; no formatter | — | **not built** (finding 5) |
| 73 | 402 | the launchd wrapper maps the exit code and notifies on failure | deploy/launchd/run.sh:141-151 | tests/deploy/test_launchd.py::test_run_maps_each_exit_code_to_its_action | holds; **also notifies on `partial`** (finding 9) |
| 74 | 180 | order: settings → pending check → flock (75) → stale sweep → run row | cli.py:428-465; services/collect.py:137-145 | tests/e2e/test_run_lock_and_preconditions.py | holds |
| 75 | 180 | one cheap auth ping before paging | — | — | not built (tranche B, marked) |
| 76 | 180 | the wall-clock ceiling ends the run `partial` after the batch | services/sweep.py:366-380 | tests/services/test_sweep_paging.py::test_the_wall_clock_ceiling_stops_the_subreddit_without_a_stop_reason | holds |
| 77 | 180 | "a run with no collectable source is refused loudly" | services/collect.py (no refusal); sweep warns | tests/services/test_collect_sources.py::test_a_run_with_no_enabled_source_is_partial_not_ok | **differs** (finding 2) |
| 78 | 186 | the run stamps `settings_fingerprint` | services/runs.py:357 | tests/services/test_runs_lifecycle.py | holds |
| 79 | 186 | a recovered subreddit has status, counters, gap flag cleared | db/repo.py::clear_subreddit_error | tests/db/test_repo_upsert.py::test_clear_subreddit_error_resets_the_trio_and_leaves_the_coverage_columns_alone | holds |
| 80 | 186 | a per-run backup to `data/backups/<date>.db` | — | — | **not built** (finding 1) |
| 81 | 184 | `reconcile.full_sweep_every_hours` shorter than the gap; tier bounds fit | config/settings.yaml:14-17 | tests/deploy/test_schedule_contract.py::test_reconcile_bounds_fit_the_schedule | holds (config); reconcile itself is M1c |
| 82 | 464 | "a test asserts a full reprocess reproduces identical rows" | no `reprocess` command | DB-47 / PA-02 are `planned` in docs/TEST_STRATEGY.md:81,139 | **not built** (finding 6) |
| 83 | 473 | launchd: `run` Mon+Thu 06:30, `doctor --alert-if-stale 5d` hourly at :15 | deploy/launchd/*.plist; run.sh:125 | tests/deploy/test_schedule_contract.py::test_run_job_is_scheduled_monday_and_thursday_at_0630, ::test_doctor_job_is_hourly_off_the_run_minute | holds |
| 84 | 473 | wrapper: absolute venv interpreter, never `python3` | deploy/launchd/run.sh:44 | tests/deploy/test_launchd.py::test_program_arguments_run_the_wrapper_with_bash_never_python3, ::test_run_refuses_without_the_venv_interpreter | holds |
| 85 | 473 | wrapper refuses a TCC-protected folder | deploy/launchd/run.sh:40 | tests/deploy/test_launchd.py::test_run_refuses_a_repo_inside_a_tcc_protected_folder | holds |
| 86 | 473 | wrapper loads `.env` without printing values | deploy/launchd/run.sh:63-93 | tests/deploy/test_launchd.py::test_env_file_is_loaded_without_echoing_values | holds |
| 87 | 473 | wrapper wraps the job in `caffeinate -i` | deploy/launchd/run.sh:131-133 | tests/deploy/test_launchd.py (script parse + arg map) | holds |
| 88 | 473 | `doctor` checks the data directory is outside TCC paths | services/doctor.py:234-258 | tests/services/test_doctor.py::test_check_data_dir_outside_tcc_is_not_ok_under_a_protected_path | holds |
| 89 | RUNBOOK 60 | `db upgrade` post-check includes `alembic_version == head` | not in `_migrate_and_verify` | asserted only in tests/services/test_migrate_service.py:150 | **differs**, minor (finding 11) |
| 90 | RUNBOOK 66 | one online backup at the end of each scheduled run | — | — | **not built, unmarked** (finding 12) |

## Findings

### 1. The whole backup-retention compliance story is stated as fact and none of it exists — CRITICAL (for the compliance invariant)

**Evidence.** Plan line 462 (§ Release → Backups and retention), line 186 (§ Collector step 6),
`DECISIONS.md` § 2 backups row, D-31, and `RUNBOOK.md` § 5 all state, in the present tense:
one online-backup copy per scheduled run taken after reconcile; the two most recent
post-reconcile copies kept; `retention.backups_days` bounding the age of every copy until the
pruning lands; the compliance canary asserting file ages.

In the tree: `db/backup.py::online_backup` has exactly one caller,
`services/migrate.py:378` (`db upgrade`). No run path writes a backup —
`services/collect.py` neither imports nor calls it. `retention.backups_days` is parsed by
`settings.py:161` and read by nothing in `src/`. The word "canary" appears in `tests/` only as
a unique phrase inside four unrelated tests (`tests/db/test_fts.py:22`,
`tests/db/test_engine_pragmas.py:144`, `tests/services/test_sweep_errors.py:594`,
`tests/services/test_invariants.py:347`); there is no compliance canary test.

**What the compliance invariant actually gets today.** The only backups ever written are
`pre-migrate-*.db`, pruned by `prune_pre_migrate_backups` **by count** (`KEEP_PRE_MIGRATE_BACKUPS = 3`,
`services/migrate.py:80`), never by age. A pre-migration copy taken before a scrub therefore
holds the deleted text indefinitely — until three later migrations happen — which is precisely
what § 2's "no backup older than 14 days is retained (… and pre-migration copies alike)"
forbids. The exposure is small today because migrations are rare and no content has been
harvested, but the bound as written is unenforced by anything, and both the plan and the
decisions log say it is bounded.

**Why it matters more than an unbuilt feature.** Three documents state a bound and name an
enforcer (the canary) that does not exist. Under the project's own claim-provenance rule the
sentence "the compliance canary asserts file ages" is the failure mode that rule exists to
catch: a named verifier that was never built.

**Fix.** In plan § Release → Backups and retention, split the decided policy from the built
state: mark the per-run copy, the two-copy keep rule, the age bound and the canary as M1d, and
say plainly that today the only copies are pre-migration ones pruned by count. Mirror into
`RUNBOOK.md` § 5 and the `DECISIONS.md` § 2 backups row (as a dated parenthetical, that log
being append-only). If a bound is wanted before M1d, the cheapest real enforcement is to add an
age clause to `prune_pre_migrate_backups` reading `retention.backups_days`.

### 2. "A run with no collectable source is refused loudly" — the code does not refuse — HIGH

**Evidence.** Plan line 180, last sentence, cites KI-017. The KI-017 fix does the opposite of
refusing: `sweep_all` runs over an empty source list, the run closes `partial` with one
`no_enabled_sources` warning (exit 3), and the alert is carried by the hourly `doctor`'s
`check_enabled_sources` (`services/doctor.py:401-428`), which is ERROR severity.
`tests/services/test_collect_sources.py::test_a_run_with_no_enabled_source_is_partial_not_ok`
asserts `second.status is RunStatus.PARTIAL` and one warning; nothing anywhere refuses the run
or exits 78. KI-017's own row says the same.

**Why it matters.** Step 0 is the ordered precondition list an M1b/M1c author implements
against. "Refused loudly" reads as a precondition abort before the run row, which is a
different design (and would break KI-017's intended chain: the run row is what the freshness
window and the Runs page read). A builder following the plan would remove the very mechanism
the fix installed.

**Fix.** Replace the sentence in § Collector step 0 with the built behaviour: a run whose
sources are all disabled or permanently failing collects nothing, closes `partial` with a
recorded warning, and the hourly `doctor` goes red on `enabled_sources`.

### 3. The freshness invariant's description names a status that does not exist — HIGH

**Evidence.** Plan line 400: "**per-source freshness**: each enabled subreddit fetched
successfully within the last two runs, checked separately from run status, and a zero-yield run
across all sources flags `degraded`."

- `degraded` appears nowhere in `src/` or `deploy/`. `runs.status`'s CHECK constraint
  (`db/schema.sql`, the `ck_runs_status` clause) allows ten values and `degraded` is not one.
  `services/invariants.py:312-342` returns a `Severity.WARNING` violation, which
  `runs.resolve_status` turns into `partial`. `docs/TEST_STRATEGY.md:136` (FR-01) records the
  same: "`partial`/amber, not `failed`".
- There is no zero-yield-across-all-sources clause in `per_source_freshness` at all. The nearest
  built thing is a different mechanism — KI-017's `no_enabled_sources` warning in the sweep.
- "each **enabled** subreddit" is narrower than the code: `repo.all_sources_for_freshness`
  (`db/repo.py:928-943`) deliberately covers enabled sources **plus** sources disabled by an
  error status, so a subreddit auto-disabled by a failure cannot leave the population (ingest
  B8). The plan's word is wrong in the safe direction, but it is wrong.

**Why it matters.** This is the sentence an M1c author reads when adding the remaining
invariants. Building a `degraded` status would need a migration to widen the status CHECK, for a
state the design does not actually have.

**Fix.** Rewrite the freshness clause in § Silent-failure controls: every enabled source, plus
every source disabled by an error status, must have been fetched successfully in the last two
sweeping runs; a violation is a WARNING, so the run is `partial`/amber and the digest names the
source. Sweep the same wording into the § Testing failure-matrix row at line 321.

### 4. The PK-stability sentence restates a claim an adversarial review retired — MEDIUM

**Evidence.** Plan line 146: "a PK-stability invariant checks that repeated reruns leave `pk`,
`first_seen_at`, and `max(pk) == count(*)` unchanged." Two things are off.

- The shipped gate, `tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at`
  (the whole file is 34 lines), asserts `pk` and `first_seen_at` only.
  `docs/TEST_STRATEGY.md:165` records the reason: "drop `max(pk)==count(*)` (A10)"; line 54
  adds "only in this no-purge scenario, never at runtime". The surviving assertion lives in
  `tests/db/test_alembic.py:85-86` against a fixture that never purges.
- It is not a post-run invariant. `services/invariants.py:348` lists seven invariants and no PK
  check; the enforcement is a gate test. The § Testing failure-matrix row at line 323
  ("PK-stability invariant fails") repeats the same misnomer.

**Why it matters.** M1c introduces recorded purges (`runs.purge_counts_json` already exists in
the schema and `counters_equal_table_deltas` reserves the exemption). An author who reads line
146 as a runtime invariant and builds it will ship a check that goes red on the first purge —
exactly what A10 predicted.

**Fix.** In § Data model conventions, say the PK-stability *gate* re-runs the collector three
times and asserts `pk` and `first_seen_at` are unchanged, and note that `max(pk) == count(*)`
holds only in a no-purge fixture and is deliberately not a runtime check (A10). Mirror the
failure-matrix row.

### 5. Structured per-run JSON-line logs do not exist — MEDIUM

**Evidence.** Plan line 402 states them as built, with no milestone marker, among neighbours
that do carry one. `runs.log_path` is passed `None` on every writing path
(`services/runs.py:359`, `cli.py:406`, `services/migrate.py:249`); there is no logging
configuration, no JSON formatter, and the only `getLogger` in the tranche is
`services/invariants.py:70`, used for one `logger.exception`. The only per-run log on disk is
the launchd wrapper's plain text at `data/logs/launchd-<job>.log` (`deploy/launchd/run.sh:52`).

**Why it matters.** The § Silent-failure controls list is where an operator (and an M1b
debugger) goes to learn what evidence a failed run leaves. Today it leaves a `runs` row and the
wrapper's text log, nothing structured, and "error and warning counts mirrored on the run row"
is true only in the sense that `counters_json` holds a warning count.

**Fix.** Mark the structured-log bullet with its milestone in § Silent-failure controls, or
replace it with what exists: counters and violations on the run row plus the wrapper's job log.

### 6. "A test asserts a full reprocess reproduces identical rows" — that test is `planned` — MEDIUM

**Evidence.** Plan line 464 (§ Release → Reprocessing) and line 406 ("a refactor keeps the
reprocess golden byte-identical"). `docs/TEST_STRATEGY.md:81` (DB-47) and :139 (PA-02) both read
`planned`, with the note "no `reprocess` command exists yet; not built in tranche A". A grep for
`reprocess` across `tests/` returns one unrelated comment
(`tests/services/test_sweep_writes.py:305`).

**Why it matters.** This is the plan asserting the existence of an enforcer, which is the exact
shape CLAUDE.md's claim-provenance practice forbids ("names the exact test … the review pass
checks that the cited test asserts the claim"). It is also the guarantee on which the
"two-gate discipline for semantics" rests.

**Fix.** In § Release → Reprocessing and in the two-gate bullet, name the test ids and mark them
M1c/M2 (they are already spec'd as DB-47 and PA-02), rather than asserting the test runs today.

### 7. The plan never states KI-013's residual consequence: scrubbed page images can survive in the WAL — MEDIUM

**Evidence.** Plan line 463 lists `wal_checkpoint(TRUNCATE)` at the end of a run without
qualification, and line 174 says the scrub's `secure_delete=ON` means "freed pages are
overwritten". The code is more honest: `services/collect.py:275-291` retries the checkpoint
three times, and when a reader still holds the write-ahead log it records a
`wal_checkpoint_busy` warning whose text is "the pages written this run stay in it until a later
checkpoint"; KI-013's row adds "which `secure_delete` does not cover; the web UI is a reader by
design". The run then closes `partial`, which the in-process notifier never announces
(`services/collect.py:62`).

**Why it matters.** This is the one shipped path by which scrubbed bytes remain inside the data
directory after a run, and it becomes the normal case once M2's web UI is running while the
collector runs. The compliance sections (§ Data model → Scrub, § Release → Connections,
`DECISIONS.md` § 2) describe an unconditional overwrite, and the M1c canary specification at
line 278 scans "the DB, the index bytes, and a fresh export" — not `insightminer.db-wal`.

**Fix.** Add the qualification to § Release → Connections and to § Data model → Scrub (the
checkpoint is retried and, if a reader holds the log, the run is `partial` and the pages persist
until a later checkpoint), and add `-wal` to the canary's scan list in the § Testing collector
e2e row.

### 8. KI-014 is open, and the section a migration author reads does not carry its consequence — MEDIUM

**Evidence.** KI-014 (status `open`, no regression test) says that after the first Alembic
batch-mode migration on `posts` or `comments`, a purged top primary key can be reused, breaking
the AUTOINCREMENT guarantee, unless the migration passes
`table_kwargs={"sqlite_autoincrement": True}` and re-stamps `sqlite_sequence`. Plan line 460
gives the batch checklist — drop and recreate the views and triggers, rebuild the index, one
transaction per migration — and says nothing about the sequence. Plan line 146 states the
guarantee flatly ("so a purge cannot recycle a rowid into a stale FTS entry"). KI-014 is named
only in the § Testing migrations row (line 280) and in the M1c definition of done (line 488).

**Why it matters.** § Release is the checklist a migration author follows, and the first batch
migration on `posts`/`comments` is an M1b/M1c event. The stale-FTS-entry failure line 146
invokes is the one KI-014 reopens.

**Fix.** Add the sequence re-stamp and `sqlite_autoincrement` to § Release's batch sentence, and
qualify line 146's guarantee with a pointer to KI-014 until the checklist tests land.

### 9. The launchd wrapper notifies on every `partial` run, contradicting the code's own rationale — MEDIUM

**Evidence.** `deploy/launchd/run.sh:148` maps exit 3 to `notify "partial" …`, asserted by
`tests/deploy/test_launchd.py:39,341`. `services/collect.py:58-64` deliberately excludes
`partial` from `NOTIFYING_STATUSES` because "an amber run is seen through the digest line, and
alerting on it would train the operator to ignore the alert", and
`services/doctor.py:401-411`'s rationale for `check_enabled_sources` rests on the premise that
"`partial` never notifies". For a scheduled run that premise is false. The plan describes
neither behaviour precisely: line 473 says "On failure the wrapper posts a macOS notification",
line 186 says "a notification on failure".

**Why it matters.** Every run with any warning is `partial` — a source that 403s, a budget
exhaustion, a busy checkpoint, a freshness miss — so on the built design a scheduled run
produces a macOS notification on ordinary amber days. That is the alert-fatigue failure the code
comment names, and it undercuts the KI-017 reasoning that made `doctor` the alert channel.

**Fix.** Decide which is right and state it in § Deployment path (and align the other side):
either the wrapper logs exit 3 without notifying, matching the in-process rule, or the plan says
plainly that a scheduled `partial` notifies while an interactive one does not.

### 10. "`upgrade` always backs up first" — not when nothing is pending — LOW

`services/migrate.py:339-351`: when the current revision equals head, the command records a run
row and returns with `backup_path=None`; no copy is taken. Asserted by
`tests/services/test_migrate_service.py::test_db_upgrade_with_nothing_pending_is_a_no_op_but_still_records_a_run`.
Harmless behaviour, but the word "always" at plan lines 216 and 461 is false. Fix: "takes an
online backup before any migration it actually runs".

### 11. The runbook lists a post-migration check the command does not run — LOW

`RUNBOOK.md` § 4 step 5: "after: `integrity_check`, `foreign_key_check`, `alembic_version ==
head`, `backups` row `kind='pre-migrate'`". `_migrate_and_verify` (`services/migrate.py:467-496`)
runs the first two only; `is_at_head` is asserted by the test
(`tests/services/test_migrate_service.py:150`), not by the command, and the `backups` row is
inserted **before** the migration, not verified after. Fix: reword step 5 to the command's real
sequence, or add the head assertion to `_migrate_and_verify`.

### 12. The runbook's Backups paragraph is unmarked and untrue — MEDIUM

`RUNBOOK.md` § 5, first paragraph, states the per-run backup and the destructive-operation gate
("require a verified backup within N hours plus the `Confirmation` … checked inside the
service") in the present tense with no milestone marker, while every other unbuilt step in the
same runbook carries one — `(M1c+)`, `(M2+)`, `(M4)`, including step 2 of the drill three lines
below. An operator reading § 5 concludes that a verified copy exists for every scheduled run.
It does not: see finding 1. Fix: mark both sentences `(M1d+)` and `(M1c+)` respectively, and
resolve the unspecified "N hours".

### 13. "A `rebuild` … re-indexes tombstones" reads as the opposite of the behaviour — LOW

Plan line 176's compressed clause — "a `rebuild` with live-gated triggers re-indexes tombstones,
so the index points at live-only views" — states, on a plain reading, that a rebuild indexes
tombstones. `db/fts.py:42-45` and
`tests/db/test_fts.py::test_rebuild_indexes_live_rows_only_and_passes_integrity_check` show a
rebuild re-reading the live-only content view and indexing live rows only. The intended meaning
is the counterfactual (a rebuild *would* re-index tombstones if the content source were the base
table, which is why it is the view). Fix: restore the counterfactual in § Data model → SQLite
facts.

### 14. Two column names in the data-model table do not match the schema — LOW

Line 162 gives `run_subreddits` as "pages, items_seen, new, updated, stop_reason, error"; the
columns are `new_items` and `updated_items` (`db/schema.sql`). Line 165 gives `ui_state` as
"key, value"; the table also has `updated_at`. Neither is backticked, so the identifier gate
(G55) cannot see them. Fix in § Data model's table.

### 15. Untested claims that carry weight

- **"Alembic batch recreates fail while a view references the table"** (line 176, repeated as
  the premise of § Release's batch rule and `RUNBOOK.md` § 4 step 2). No test constructs the
  failure, and no shipped migration touches a table a view references — 0002 recreates `runs`,
  which no view names. The neighbouring foreign-key hazard *does* have a positive control
  (`tests/db/test_migrate_revisions.py::test_a_batch_recreate_with_foreign_keys_on_would_cascade`).
  This is the rule M1b/M1c's first `posts` migration depends on, so it deserves the same. MEDIUM.
- **"The DB lives on a local filesystem, never a network share"** (line 463). Nothing checks it;
  `doctor` checks TCC paths, not filesystem type. Review-only, and the rules table does not list
  it. LOW.
- **"the restore drill compares counts against `table_counts_json`"** (line 163).
  `table_counts_json` is written only by `db upgrade` (`services/migrate.py:188-193,421`); the
  `db restore --to-temp --verify` command that would read it is M1c. LOW (marked elsewhere).

### Where the claims held, plainly

The great majority of the plan's storage and operations prose is exact. All six connection
pragmas hold by value on every pool checkout, with a test asserting each. The end-of-run
checkpoint, the upsert form and its `INSERT OR REPLACE` positive control, the field-ownership
table and the emitted-SQL test behind it, the whole FTS design (external content over the
live-only views, `porter unicode61`, change-gated update triggers from 0003, persistent
secure-delete from 0004, membership from `_docsize`, the `rank = 1` integrity check), the
online-backup mechanism and every column of the `backups` row, `db upgrade`'s full order
(backup → `quick_check` → migrate → `integrity_check` + `foreign_key_check` → restore on
failure → prune), KI-015's restore ordering, the derived-and-warning-only schema fingerprint,
all fourteen `doctor` checks in the documented order with an ok and a not-ok test each, six of
the seven built post-run invariants, the launchd schedule and every wrapper behaviour the plan
lists, and the reconcile bounds tied to the schedule — each was found in the code and each has a
test asserting it. The two identifier-level drifts that started this review (the `SearchIndex`
port, `VACUUM INTO`) have no siblings among the mechanisms: where the plan named a module or a
statement, it named the right one.

## What I could not check

- **Runtime behaviour.** No tests were run; every row was settled by reading shipped code and
  shipped test bodies. Where a test's name alone would have been weak evidence I read its body
  (the pragma values, the PK-stability gate, the fixture upgrade, the wrapper's exit map, the
  doctor name list).
- **macOS-only paths.** `tests/deploy/test_launchd.py` is deselected off macOS, so the wrapper's
  exit-code map and the `plutil` lint are asserted only when `make check` runs on this Mac; the
  cross-platform half is `tests/deploy/test_schedule_contract.py`, which does not cover the
  notification map. The "`partial` notifies" behaviour in finding 9 therefore rests on reading
  `run.sh:148` plus the macOS-only assertion.
- **Anything the plan marks tranche B, M1b–M1d, M2+ was checked only for "absent, and marked".**
  I did not judge whether the unbuilt designs are good, only whether the plan claims they exist.
- **The deletion state machine and the collector's sweep/paging semantics** were out of this
  brief's scope except where they touch storage; KI-021's follow-up and KI-018 were read but not
  re-verified line by line.
- **`DECISIONS.md` § 2's bounds are marked "pending Wes confirmation"**, so finding 1 judges them
  as stated bounds, not as ratified ones.

## Verdict

**Counts (90 claims extracted).** holds 62; holds, untested 4 (rows 8, 40, and the two in
finding 15); not built but marked with a milestone 9 (rows 23, 31, 32, 48-partial, 51, 75, plus
the M1c/M2 halves); **not built and stated as fact 6** (rows 53, 54, 55, 72, 80, 82 — plus
runbook row 90); **differs 5** (rows 15, 67, 77, 89, and the wrapper/`partial` contradiction);
**not found 1** (row 68).

**Does the claim hold?** **No — but narrowly, and by a small number of sentences.** The claim
under test asserts that *every* such sentence is true of the code and has a test. Sixty-two of
ninety are exactly right and well tested, and the mechanism-level naming that produced today's
two drift findings has no further siblings. But five sentences describe behaviour the code does
not have (`refused loudly`; `degraded`; `max(pk) == count(*)`; the runbook's head check; the
wrapper's failure-only notification), one names a status the schema forbids, and six state
components or tests as built when they are not — and those six cluster on the compliance
surface: the per-run backup, the retention bound, and the canary that is supposed to assert it.

**Confidence: high** on the `differs` and `not found` rows (each is a direct read of the
implementing function and its test), **high** on the six `not built` rows (each confirmed by an
exhaustive grep for the only possible caller or reader), **medium** on the severity ranking of
findings 7 and 8, which depend on how soon M1b/M1c migrations and a concurrent web reader
arrive.
