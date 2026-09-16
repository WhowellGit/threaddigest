# Plan version two: collector claims against the code (2026-09-16)

## Claim under test

"Every sentence in `docs/PLAN.md` that describes what a built collector component does (the run
loop's steps, the budget and its hard cap, the retry classes and what each does, paging and
exhaustion, normalization and rejects, the deletion predicates, revisit scheduling with
`next_check_at`, the run row's status vocabulary and when each status is set, counters and
invariants at the end of a run, the lock, the fake gateway's scenario builder and what it records,
the failure matrix rows marked as covered) is true of the code, and a test asserts it."

Refute-framed: the job was to find the sentences that are not true. Identifier-shaped drift (paths,
names, settings keys) is checked mechanically by G55 and was not re-checked here.

## Method

1. Read `docs/PLAN.md` whole, then extracted every behavioural statement (order, threshold,
   default, guarantee) from the module map (L128–142), the data model (L146–176), the collector
   algorithm (L178–194), the CLI table (L214–217), the testing-strategy principle (L273), the
   failure-mode matrix (L288–331), the gates table's collector rows (L384) and the silent-failure
   controls (L396–402).
2. For each claim, located the implementing code and the asserting test, recorded both as
   `file:line` / node id, and classified: `holds`, `holds, untested`, `differs`, `not built`,
   `not found`.
3. Judged severity for a reader who will build tranche B and M1b on top of the plan.
4. Read `docs/runbook/KNOWN_ISSUES.md` (open and fixed rows touching the collector) against the
   plan's wording.

Read-only throughout; no tests were run (every classification is from code and test source, which
is what "a test asserts it" can be checked against without executing the suite).

Repository at `7e8412c`, branch `identifier-resolution`, clean tree.

## Claims

Code paths are relative to `src/insightminer/`; test node ids are relative to the repository root.

| n | Plan line | Claim (short) | Code | Test | Status |
|---|---|---|---|---|---|
| 1 | 128 | normalize: raw dict → rows, rejects, crosspost parent reduced | `core/normalize.py:1` | `tests/unit/test_normalize.py::test_canonical_raw_keeps_only_the_parent_pointer_of_a_crosspost` | holds |
| 2 | 129 | deletion: state machine with an exhaustive table test | `core/deletion.py:112` | `tests/unit/test_deletion.py::test_table` | holds |
| 3 | 130 | paging: stop, cap, gap and removal-candidate detection built | `core/paging.py:99,127,143` | `tests/unit/test_paging.py::test_cap_reached_on_tenth_full_page` | holds |
| 4 | 131 | milestones: ladder tested "unit, time-machine" | `core/milestones.py:21` | `tests/unit/test_milestones.py::test_ladder_stages` | differs (F14) |
| 5 | 133 | budget: per-run request accounting with a reserve | `core/budget.py:57` | `tests/unit/test_budget.py::test_can_afford_respects_reserve` | holds |
| 6 | 134 | retry: ladder, classification, statuses, exit codes, wait planning | `core/retry.py:49,296,329,372` | `tests/unit/test_retry.py::test_classify_table` | holds |
| 7 | 136 | fake gateway tested by a contract suite matching the real adapter | `adapters/reddit_fake/` | `tests/adapters/test_fake_gateway.py` | differs (F16) |
| 8 | 140 | services built: lock, runs, collect, sweep, seed, invariants, doctor, migrate | `services/` | `tests/services/` | holds |
| 9 | 141 | cli built: run, doctor, db init/upgrade/current, config validate | `cli.py:75-79` | `tests/gates/test_mutating_commands.py` (`EXPECTED_COMMAND_TREE`) | holds |
| 10 | 146 | a PK-stability invariant checks pk, first_seen_at, max(pk)==count(*) | no run invariant | `tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at`; `tests/db/test_alembic.py:86` | differs (F13) |
| 11 | 146 | upserts are ON CONFLICT DO UPDATE, never INSERT OR REPLACE | `db/repo.py` (`on_conflict`) | `tests/db/test_repo_upsert.py`; KNOWN_ISSUES § Swept 2026-09-14 | holds |
| 12 | 148 | the sweep never updates first_seen_at, check_stage, next_check_at | `services/sweep.py:507-533`; `db/ownership.py` | `tests/services/test_sweep_writes.py::test_sweep_never_touches_first_seen_at_check_stage_next_check_at_or_scrubbed_at` | holds |
| 13 | 162 | runs.status vocabulary: the ten listed values | `db/schema.sql:16`; `core/retry.py:296` | `tests/unit/test_retry.py::test_run_status_values_match_the_runs_table_enum` | holds |
| 14 | 162 | run_subreddits.stop_reason: exhausted / cap / error | `core/paging.py:30` | `tests/services/test_sweep_status.py::test_stop_reason_values_match_the_stored_check_constraint` | holds |
| 15 | 172 | deleted category or `[deleted]` marker → deleted_by_author, terminal | `core/deletion.py:162-167` | `tests/unit/test_deletion.py::test_deleted_markers_are_terminal_from_any_prior` | holds |
| 16 | 172 | `[removed]` → removed_by_moderator unless the category names Reddit | `core/deletion.py:168-183` | `tests/unit/test_deletion.py::test_table` | differs (F9b) |
| 17 | 172 | moderator removals may return to live if re-approved | `core/deletion.py:176` | `tests/unit/test_deletion.py::test_table` | holds |
| 18 | 172 | `author is None` with intact body → account_deleted | `core/deletion.py:174,212-218` | `tests/unit/test_deletion.py::test_table` | differs (F9a) |
| 19 | 172 | absent from info() → gone_unconfirmed, gone at the second, non-consecutive omission | `core/deletion.py:164,194-209` | `tests/unit/test_deletion.py::test_two_omissions_around_a_bodyless_return_still_reach_gone` | holds |
| 20 | 172 | a returned item with no body holds without counting a miss | `core/deletion.py:170-175,205` | `tests/unit/test_deletion.py::test_a_bodyless_return_then_one_omission_is_still_an_unconfirmed_hold` | holds |
| 21 | 180 | settings validated first; exit 78 with no run row | `cli.py:288` | `tests/e2e/test_run_lock_and_preconditions.py::test_invalid_settings_exit_78_with_no_run_row` | holds |
| 22 | 180 | pending migrations refuse the run, no run row | `cli.py:461-466` | `tests/e2e/test_run_lock_and_preconditions.py::test_pending_migrations_exit_78_with_no_run_row` | holds |
| 23 | 180 | the migration check happens **before** the flock | `cli.py:305` (lock) precedes `cli.py:435` (`_require_head`) | — | differs (F10) |
| 24 | 180 | flock on data/locks/collector.lock, exit 75 if held | `cli.py:82,305`; `services/lock.py:135` | `tests/e2e/test_run_lock_and_preconditions.py::test_held_lock_exits_75_with_zero_gateway_calls` | holds |
| 25 | 180 | stale running rows stamped crashed before the run row | `services/collect.py:137`; `services/runs.py:288` | `tests/services/test_runs_lifecycle.py::test_stale_running_row_is_marked_crashed` | holds |
| 26 | 180 | the run row is inserted before any fetch | `services/runs.py:327-362` | `tests/services/test_runs_lifecycle.py::test_start_run_commits_a_running_row_with_versions_fingerprint_and_baselines` | holds |
| 27 | 180 | one cheap auth ping before any paging | `services/sweep.py:941,1017` | `tests/services/test_sweep_errors.py::test_a_run_with_no_enabled_sources_skips_the_preflight_entirely` | holds |
| 28 | 180 | config and auth failures never leave a running row | `services/collect.py:159-167` | `tests/e2e/test_run_lock_and_preconditions.py::test_exit_code_table_is_total_over_run_status` | holds |
| 29 | 180 | every mutating command takes the flock and writes a run row | `cli.py:305`; `services/migrate.py:249` | `tests/gates/test_mutating_commands.py`; `tests/e2e/test_db_commands.py::test_db_init_takes_the_lock_and_writes_a_run_row` | holds (of the three built) |
| 30 | 180 | stage-bearing heartbeat; `rate_wait:37s` counts as alive | `services/runs.py:410`; `services/sweep.py:916` | `tests/services/test_runs_lifecycle.py::test_rate_wait_stage_is_written_before_the_sleep`; `tests/services/test_doctor.py::test_lock_not_stale_is_ok_during_a_declared_rate_wait` | holds |
| 31 | 180 | the wall-clock ceiling ends the run partial after the current batch | `services/sweep.py:378,1019`; `services/runs.py:462` | `tests/services/test_sweep_paging.py::test_the_wall_clock_ceiling_stops_the_subreddit_without_a_stop_reason` | holds |
| 32 | 180 | a run with no collectable source is "refused loudly" | `services/sweep.py:1010-1015` | `tests/services/test_collect_sources.py::test_a_run_with_no_enabled_source_is_partial_not_ok` | differs (F11) |
| 33 | 181 | up to ten pages of a hundred (the listing cap) | `core/paging.py:21,117`; `services/sweep.py:115` | `tests/unit/test_paging.py::test_cap_reached_on_tenth_full_page`; `tests/services/test_sweep_paging.py::test_a_page_ceiling_stops_the_subreddit_without_claiming_exhausted` | differs (F12) |
| 34 | 181 | forward `after` paging only | `services/sweep.py:481` | `tests/services/test_sweep_paging.py::test_sweep_pages_forward_only_and_never_uses_before` | holds |
| 35 | 181 | one transaction per page | `services/sweep.py:625` | `tests/services/test_sweep_errors.py::test_db_locked_write_fails_the_page_with_nothing_committed` | holds |
| 36 | 181 | score and comment counts refreshed for free | `services/sweep.py:643`; `db/ownership.py` | `tests/db/test_repo_ownership.py` | holds |
| 37 | 181 | the sweep yields a removal signal, confirmed via info() | `core/paging.py:143` (no caller) | `tests/unit/test_paging.py::test_candidates_are_unseen_known_posts_inside_the_window` | not built (F5) |
| 38 | 181 | cap before known territory → gap_suspected_at and stop_reason cap | `services/sweep.py:775-790` | `tests/services/test_sweep_paging.py::test_cap_stop_sets_gap_suspected` | holds |
| 39 | 181 | KI-018: an end of listing on the tenth page is a cap stop | `services/sweep.py:468-472` | `tests/services/test_sweep_paging.py::test_a_listing_ending_at_the_cap_with_filtered_slots_is_a_cap_stop_not_exhausted` | holds |
| 40 | 181 | stickies are excluded from stop logic | `core/paging.py:77-86,117` | `tests/unit/test_paging.py::test_stickies_excluded_from_window_but_recorded` | differs (F8) |
| 41 | 186 | counters and api_requests on the run row | `services/collect.py:155`; `services/runs.py:488` | `tests/e2e/test_run_happy_path.py::test_first_run_writes_the_definition_of_done` | holds |
| 42 | 186 | the post-run invariants run at the end of the run | `services/collect.py:157` | `tests/gates/test_invariants_planted.py::test_planted_violation_flips_the_run` | holds |
| 43 | 186 | `wal_checkpoint(TRUNCATE)` at the end, outside any transaction | `services/collect.py:163,275` | `tests/e2e/test_run_happy_path.py::test_wal_is_truncated_at_end_of_run`; `tests/services/test_collect_checkpoint.py::test_a_reader_during_the_final_checkpoint_leaves_a_warning_and_a_partial_run` | holds |
| 44 | 186 | a per-run online backup to `data/backups/<date>.db` | absent from `services/collect.py` | — | not built (F6) |
| 45 | 186 | a notification on failure | `services/collect.py:318-337` | — | holds, untested (F15) |
| 46 | 186 | settings_fingerprint stamped on the run row | `services/runs.py:358` | `tests/services/test_runs_lifecycle.py::test_start_run_commits_a_running_row_with_versions_fingerprint_and_baselines` | holds |
| 47 | 186 | unknown enum values stored raw and counted, never coerced | `services/sweep.py:318`; `services/invariants.py:253` | `tests/services/test_sweep_writes.py::test_unknown_enum_is_stored_raw_and_counted` | holds |
| 48 | 186 | a recovered subreddit has status, counters and gap flag cleared in the same run | `services/sweep.py:786-790` | `tests/services/test_sweep_status.py::test_complete_sweep_clears_status_failures_last_error_and_gap` | holds |
| 49 | 182/188 | the hard cap is never exceeded by any flag | `cli.py:469-480`; `core/budget.py:45,53` | `tests/gates/test_no_bypass.py::test_budget_is_clamped_to_the_hard_cap` | holds |
| 50 | 188 | exit codes 0/1/3/4/5/75/78/130 | `core/retry.py:309-340` | `tests/unit/test_retry.py::test_exit_codes_match_the_plan` | holds |
| 51 | 194 | connectivity and auth preflight before any paging | `services/sweep.py:941-977` | `tests/services/test_sweep_errors.py::test_preflight_network_outage_ends_the_run` | holds |
| 52 | 194 | the outer 30/120/300 ladder around every page (trees, info at M1b) | `core/retry.py:49`; `services/sweep.py:929` | `tests/services/test_sweep_errors.py::test_transient_page_error_walks_the_30_120_300_ladder` | holds |
| 53 | 194 | an unreachable Reddit exits network, writes nothing but its run row | `services/sweep.py:931` | `tests/services/test_sweep_errors.py::test_a_network_outage_walks_the_ladder_then_ends_the_run_network` | holds |
| 54 | 194 | a rate-limited run pauses in-process; over the ceiling it exits rate_limited | `core/retry.py:372-396`; `services/sweep.py:907-918` | `tests/services/test_sweep_errors.py::test_rate_limited_waits_then_retries_once`; `::test_wait_beyond_the_ceiling_ends_the_run` | holds |
| 55 | 194 | freshness is reported in the digest when a source misses two runs | `services/invariants.py:312`; `core/digest.py:266-327` | `tests/services/test_invariants.py::test_freshness_skips_runs_that_swept_nothing` | holds (digest assembly M1d) |
| 56 | 194 | doctor's staleness default outlasts the longest scheduled gap | `services/doctor.py` (`DEFAULT_ALERT_IF_STALE`) | `tests/deploy/test_schedule_contract.py::test_doctor_default_threshold_outlasts_the_longest_gap_and_matches_the_wrapper` | holds |
| 57 | 214 | `--dry-run` fetches and writes nothing, not even a run row | `cli.py:297-303,433`; `services/runs.py:382` | `tests/gates/test_no_bypass.py::test_dry_run_writes_nothing_anywhere` | differs (F17) |
| 58 | 214 | `--no-comments` records a written reason on the run row | `cli.py:261-263,483-502` | `tests/gates/test_no_bypass.py::test_no_comments_requires_a_reason_and_records_it` | holds |
| 59 | 215 | doctor runs every listed check by name | `services/doctor.py` | `tests/services/test_doctor.py::test_run_checks_covers_every_documented_check_name` | holds |
| 60 | 216 | `db upgrade` always backs up first | `services/migrate.py` | `tests/services/test_migrate_service.py::test_backup_precedes_migration_and_records_a_row` | holds |
| 61 | 273 | the fake's ten builder methods exist | `adapters/reddit_fake/builders.py:31,133,209`, `content_state.py:18,39,74,82`, `injection.py:30,62,68` | `tests/adapters/test_fake_gateway.py` | holds |
| 62 | 273 | the fake records every call | `adapters/reddit_fake/recording.py:22-50` | `tests/adapters/test_fake_gateway.py` | holds |
| 63 | 273 | it ships in src so `run --gateway fake` works for demos | `cli.py:111-118` | `tests/e2e/test_seam_is_honest.py::test_default_gateway_factory_is_installed_by_default` | holds |
| 64 | 273 | it drives the whole failure matrix | — | — | differs (F7) |
| 65 | 273 | KI-023's fidelity limit (a large `more` subtree in one request) | `adapters/reddit_fake/trees.py:56` | `tests/adapters/test_fake_gateway.py::TestTree::test_a_large_more_node_reveals_at_most_a_hundred_per_request` | holds |
| 66 | 273 | tests control time through the injected Clock and never sleep | `cli.py:130-147` | `tests/gates/test_no_sleep_under_pytest.py` | holds |
| 67 | 288 | "each row is a test" | — | — | differs (F7) |
| 68 | 292 | 429: bounded wait, retry once; a second 429 ends the run rate_limited | `services/sweep.py:904-918` | `tests/services/test_sweep_errors.py::test_second_rate_limit_ends_the_run_rate_limited` | holds |
| 69 | 293 | 401 at the token endpoint: before any listing request, exit 78, no running row | `services/sweep.py:956-959` | `tests/e2e/test_run_lock_and_preconditions.py::test_exit_code_table_is_total_over_run_status` | holds |
| 70 | 293 | ...and a notification | `services/collect.py:329-337` | — | holds, untested (F15) |
| 71 | 294 | 401 invalid_token mid-run: prawcore refreshes transparently | tranche B | — | not built (marked tranche B by the Simulation column only) |
| 72 | 295 | 403 private: forbidden, +1 failure, others continue, run partial | `services/sweep.py:278`; `services/runs.py:462` | `tests/services/test_sweep_status.py::test_forbidden_marks_the_source_and_others_continue` | holds |
| 73 | 295 | doctor counts the source as uncollectable (KI-017) | `services/doctor.py` | `tests/services/test_doctor.py::test_check_enabled_sources_is_an_error_when_every_enabled_source_is_forbidden` | holds |
| 74 | 296 | 404 banned: not_found, alert | `services/sweep.py:279` | `tests/services/test_sweep_status.py:264` (error-level notify asserted) | holds |
| 75 | 297 | redirect: auto-disabled after three runs, loudly | `services/sweep.py:102,280` | `tests/services/test_sweep_status.py::test_redirect_auto_disables_after_three_runs_with_an_alert` | holds |
| 76 | 298 | casing merges to one row; a differing t5 aborts that sub loudly | `services/sweep.py:331-340` | `tests/services/test_sweep_status.py::test_casing_merges_to_one_row`; `::test_t5_mismatch_aborts_the_subreddit_before_any_row_is_written` | holds |
| 77 | 299 | persistent 5xx: that sub fails, committed pages stay, watermark untouched | `services/sweep.py:427,734-768` | `tests/services/test_sweep_errors.py::test_ladder_exhaustion_fails_only_that_subreddit` | holds |
| 78 | 300 | crash between pages: rerun, no duplicates, no gaps, first_seen_at unchanged | `services/sweep.py:597-672` | `tests/e2e/test_run_happy_path.py::test_crash_between_pages_commits_earlier_pages_and_rerun_completes` | holds |
| 79 | 301 | crash mid comment-tree: nothing committed, still due | M1b | — | not built (unmarked in the matrix) |
| 80 | 302 | overlapping run: exit 75 with zero API calls | `cli.py:304-310` | `tests/e2e/test_run_lock_and_preconditions.py::test_held_lock_exits_75_with_zero_gateway_calls` | holds |
| 81 | 302 | ...and a `skipped_locked` row | `cli.py:380-424` | — | holds, untested (F15) |
| 82 | 303 | DB locked: retries within busy_timeout, then fails cleanly | `db/engine.py` (busy_timeout) | `tests/db/test_repo_busy_timeout.py`; `tests/services/test_sweep_errors.py::test_db_locked_write_fails_the_page_with_nothing_committed` | holds |
| 83 | 304 | stale running row marked crashed; the new run proceeds | `services/runs.py:271-324` | `tests/services/test_runs_lifecycle.py::test_hard_crash_then_immediate_rerun_marks_the_row_crashed` | holds |
| 84 | 305 | malformed items → raw_rejects, the run continues | `services/sweep.py:628` | `tests/services/test_sweep_writes.py::test_a_malformed_item_is_rejected_and_the_page_still_commits` | holds |
| 85 | 306 | deleted/removed content: transitions, scrub, index bytes, canary | M1c | — | not built (unmarked in the matrix) |
| 86 | 307 | account deletion applied everywhere, authors row deleted | M1c | — | not built (unmarked) |
| 87 | 308 | missing from info(): gone_unconfirmed, misses=1, second omission scrubs | `core/deletion.py:164` | `tests/unit/test_deletion.py::test_info_absence_counts_a_miss` | holds at the pure layer; no service applies it yet |
| 88 | 309 | config validation errors: exit 78 before any API call | `cli.py:288` | `tests/e2e/test_run_lock_and_preconditions.py::test_invalid_settings_exit_78_with_no_run_row` | holds |
| 89 | 310 | DB missing or behind head: refuse with instructions | `cli.py:291-294` | `tests/e2e/test_run_lock_and_preconditions.py::test_missing_database_exits_78_and_names_db_init` | holds |
| 90 | 311 | disk write failure: aborted, no partial file, run failed | M1c/M2 (backup/export unbuilt in the run) | — | not built (unmarked) |
| 91 | 312 | clock skew: identical rows and decisions | `core/paging.py`, `core/milestones.py` are `created_utc`-only | `tests/unit/test_milestones.py::test_shift_invariant_in_created_utc` (module level only) | holds, untested at run level (F14) |
| 92 | 313 | empty subreddit or zero new: ok, exhausted, watermark unchanged | `services/sweep.py:778-788` | `tests/services/test_sweep_paging.py::test_empty_subreddit_is_ok_and_exhausted`; `::test_empty_sweep_leaves_a_prior_watermark_intact` | holds |
| 93 | 314 | Cloudflare HTML 403: abort the run, not the sub, no tight retry | `services/sweep.py:919-920` | `tests/services/test_sweep_errors.py::test_html_403_aborts_the_run_not_the_subreddit` | holds |
| 94 | 315 | overlapping pages: the upsert dedupes, counts correct | `db/repo.py` upsert | `tests/services/test_sweep_paging.py::test_overlapping_pages_produce_one_row_each` | holds |
| 95 | 316 | quarantined: disabled with an alert | `services/sweep.py:104,281` | `tests/services/test_sweep_status.py::test_quarantined_is_disabled_with_an_alert` | holds |
| 96 | 317 | budget exhausted: tree harvesting stops at the reserve | M1b (source-level stop only) | `tests/services/test_sweep_errors.py::test_a_spent_budget_stops_the_run_before_the_next_source` | not built (tree half, unmarked) |
| 97 | 318 | listing cap before known territory: never `exhausted` | `services/sweep.py:465-472` | `tests/services/test_sweep_paging.py::test_a_listing_ending_before_its_tenth_page_is_still_exhausted` | holds |
| 98 | 319 | column all NULL: the population floor **fails the run** | `services/invariants.py:279-309` (WARNING) | `tests/gates/test_invariants_planted.py::test_planted_violation_flips_the_run` | differs (F1) |
| 99 | 320 | a gate gone inert: its positive control fails | `tests/gates/` | `tests/gates/test_invariants_planted.py::test_every_invariant_has_a_planter` | holds |
| 100 | 321 | per-source freshness flags `degraded`; the digest names the source | `services/invariants.py:312` | `tests/gates/test_invariants_planted.py` (`_plant_per_source_freshness`) | differs (F2) |
| 101 | 322 | tests pointed at the real data dir: settings refuse to start | `settings.py` | `tests/gates/test_data_dir_isolation.py` | holds |
| 102 | 323 | repeated reruns churn PKs: the PK-stability invariant fails | gate test only | `tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at` | differs (F13) |
| 103 | 324 | shape parity: the same post via two paths | `core/normalize.py` | `tests/unit/test_normalize.py::test_praw_shaped_post_normalizes_identically` | holds |
| 104 | 325 | a recovered subreddit: status, counters, last_error, gap cleared | `services/sweep.py:786` | `tests/services/test_sweep_status.py::test_complete_sweep_clears_status_failures_last_error_and_gap` | holds |
| 105 | 326 | a dry run makes zero DB writes | `cli.py:433`; `services/runs.py:382` | `tests/gates/test_no_bypass.py::test_dry_run_writes_nothing_anywhere` | holds |
| 106 | 327 | a failed restore leaves the live database untouched (KI-015) | `db/backup.py` | `tests/db/test_backup.py::test_a_restore_whose_copy_fails_leaves_the_live_database_and_its_log_untouched` | holds |
| 107 | 328 | a crosspost parent is reduced whatever shape it arrives in | `core/normalize.py` | `tests/unit/test_normalize.py::test_a_non_mapping_crosspost_parent_entry_keeps_no_parent_text` | holds |
| 108 | 329–331 | workspace delete, manual tag origins, `watch_until` | M2 | — | not built (unmarked) |
| 109 | 384 | post-run invariants: violation ⇒ run `failed`, notification | `services/invariants.py:93-101`; `services/collect.py:62` | `tests/gates/test_invariants_planted.py:252` (accepts exit 1 **or** 3) | differs (F1) |
| 110 | 398 | every handler re-raises or records a warning; `ok` = zero warnings | `services/runs.py:238,443-464` | `tests/services/test_runs_lifecycle.py::test_warn_records_the_warning_and_bumps_the_counter` | holds |
| 111 | 398 | exception text never reaches an error column with content (KI-010) | `db/engine.py` (`hide_parameters`); `services/sweep.py:691` | `tests/services/test_sweep_errors.py::test_a_failed_page_write_keeps_post_text_out_of_the_error_message` | holds |
| 112 | 400 | the seven built invariants are exactly those listed | `services/invariants.py:348` | `tests/services/test_invariants.py::test_invariants_tuple_matches_the_spec_order` | holds |
| 113 | 400 | each is planted through `run --gateway fake` by a positive control | `tests/gates/test_invariants_planted.py` | `::test_every_invariant_has_a_planter` | holds |
| 114 | 400 | index membership by content, not count alone (KI-022) | `services/invariants.py:200-229` | `tests/services/test_invariants.py::test_fts_membership_equals_live_flags_an_equal_count_substitution` | holds |
| 115 | 400 | a new invariant is scoped by normalizer_version | `services/invariants.py:240,288` | `tests/services/test_invariants.py::test_floor_is_scoped_by_normalizer_version` | holds |
| 116 | 400 | a zero-yield run across all sources flags `degraded` | — | — | not built (F2) |
| 117 | 401 | coverage counters on the run row and in the digest, with denominators | `services/runs.py:92-102`; `core/digest.py:330` | — | not built (F3) |
| 118 | 402 | structured JSON-lines logs per run; error counts mirrored on the row | — (`log_path` written NULL at `services/runs.py:359`, `cli.py:406`, `services/migrate.py:249`) | — | not built (F4) |
| 119 | 402 | the launchd wrapper maps the exit code and notifies on failure | `deploy/launchd/run.sh:139-152` | `tests/deploy/test_schedule_contract.py` | holds |

## Findings

### F1. "Violations flip the run to `failed`" is false for four of the seven shipped invariants — CRITICAL

**Plan:** L400 "**Post-run invariants** (violations flip the run to `failed`…)"; L384's gates row
"Post-run invariants | end of every run | … | run `failed`, notification"; L319's matrix row
"Population-floor invariant **fails the run** and names the column".

**Code:** `services/invariants.py:93-101` defines two severities. Only
`counters_equal_table_deltas` and `no_other_running_rows` are `Severity.FAILURE`. The other four —
`fts_membership_equals_live` (:218), `rows_carry_current_normalizer_version` (:244),
`unknown_enum_values_are_counted` (:271), `population_floors_hold` (:295) — and
`per_source_freshness` (:342) are `Severity.WARNING`. `services/runs.py:462` maps a WARNING
violation to `RunStatus.PARTIAL`, and `services/collect.py:62` deliberately excludes `PARTIAL` from
`NOTIFYING_STATUSES` ("an amber run is seen through the digest line, and alerting on it would train
the operator to ignore the alert"). The gate agrees with the code, not the plan:
`tests/gates/test_invariants_planted.py:252` asserts `result.exit_code in {1, 3}` and
`row["status"] != "ok"`.

So an index that has drifted from the live rows, a column that is silently all NULL, a row written
by a stale normalizer, and an uncounted unknown enum value each produce an **amber run with no
notification**, not a red one. The plan says the opposite in three places and never mentions that a
severity exists at all.

**Why it matters for M1b/M1c:** every invariant planned for those stages (`comments_captured`
equals the actual count; scrubbed rows carry no content columns; the reconcile bound) will be
written by someone reading L400. Choosing FAILURE where the code's convention is WARNING turns
every run red on a benign day; choosing WARNING for the compliance bound makes "compliance cannot
lapse quietly" lapse quietly. The plan gives them no basis for the choice.

**Fix:** rewrite L400's opening and L384's "Fails how" cell to state the two severities, which
consequence each carries (`failed` + notification vs `partial` + digest line), and which of the
seven is which; `services/invariants.py:93-101` is the source.

### F2. `degraded` is a status that exists nowhere in the code — HIGH

**Plan:** L400 "…and a zero-yield run across all sources flags `degraded`"; L321's matrix row
"Per-source freshness flags `degraded`; the digest names the source".

**Code:** the string `degraded` appears in no file under `src/` or `tests/` (grep over the tree;
only `docs/PLAN.md` uses it). `per_source_freshness` (`services/invariants.py:312-342`) returns a
WARNING `Violation` when a source was not fetched successfully within the last two *sweeping* runs;
the digest's `SubredditLine` (`core/digest.py:266-327`) has `SubredditStatus` and a `stale` flag,
whose vocabulary is not `degraded` either. And a run in which every source is fetched successfully
but yields nothing new is plain `ok` — `tests/services/test_sweep_paging.py::test_zero_new_run_records_zero_new_items`
and `tests/e2e/test_run_happy_path.py::test_rerun_after_a_clean_run_reports_zero_new_items` both
assert exit 0 — so the "zero-yield run" clause describes a mechanism that was never built.

**Fix:** in § Silent-failure controls and the matrix row, name the real mechanism (a WARNING
freshness violation and the digest's stale/gap lines) and drop the `degraded` vocabulary, or build
it and give it a ledger row.

### F3. Coverage counters are not on the run row — MEDIUM

**Plan:** L401 "**Coverage counters** on the run row and in the digest, each with its denominator:
the share of self posts with `selftext_html`, of comments with `author_fullname`, of due posts
harvested, of posts tagged, plus `raw_rejects` and `unknown_enum_values`".

**Code:** `services/runs.py:92-102` is the closed counter set written to `runs.counters_json`:
`posts_new, posts_updated, comments_new, rejects, unknown_enum_values, scrubs_pending, pages,
api_requests, warnings` — and `tests/services/test_runs_lifecycle.py::test_counters_keys_are_the_closed_set_and_round_trip_through_the_row`
pins it closed. Of the four shares named, only `due_posts_harvested` exists anywhere
(`core/digest.py:331`, in the digest model that is not yet assembled from the DB); there is no
`selftext_html` share, no `author_fullname` share and no tagged share in either place. The last two
items (`raw_rejects`, `unknown_enum_values`) do hold.

**Fix:** mark the bullet with the milestone that builds it (the shares are M1b–M1d work), or reduce
it to the two counters that exist today.

### F4. There are no structured per-run logs — MEDIUM

**Plan:** L402 "**Structured logs** per run (JSON lines) with error and warning counts mirrored on
the run row and in the digest".

**Code:** no JSON-lines logging exists anywhere in `src/` (no formatter, no logging configuration
beyond `logging.getLogger` in `services/invariants.py:70`). The `runs.log_path` column exists
(`db/schema.py:838`) and every insert site writes NULL into it: `services/runs.py:359`,
`cli.py:406`, `services/migrate.py:249`. Of the mirroring claim, `counters.warnings` holds
(`services/runs.py:89,241`); there is no error counter at all. The wrapper half of the bullet holds
(`deploy/launchd/run.sh:139-152`).

**Fix:** split the bullet: the wrapper's exit-code mapping is built; the per-run log file and its
error counter are not, and should carry their milestone.

### F5. Step 1's removal signal is computed by nothing — MEDIUM

**Plan:** L181 "…and yields a removal signal (a known post inside the window that no longer appears
→ confirm via `info()`)". Step 1 carries no milestone marker, so it reads as built.

**Code:** `core.paging.removal_candidates` (`core/paging.py:143`) exists and is unit-tested, but no
module under `services/` imports or calls it (grep over `src/`: the only references are in
`tests/unit/test_paging.py`). The sweep neither computes candidates nor records them; the `info()`
confirmation is reconcile, which is M1c.

**Why it matters:** a reader building M1c will assume the sweep already hands them a candidate list
on the run and will look for where it is persisted. It is not: `SweepState.seen_ids` is discarded
when the sweep returns.

**Fix:** mark the clause "(M1c)" in step 1, or say the detection function is built and unwired.

### F6. Step 6's per-run backup does not happen — MEDIUM

**Plan:** L186 "a per-run online backup to `data/backups/<date>.db` (`db/backup.py::online_backup`,
SQLite's backup API) taken *after* reconcile so it is already scrubbed". The only milestone marker
in the sentence is "(M1d)", attached to the dead-man ping at its end.

**Code:** `services/collect.py` neither imports nor calls `db.backup`; the run's finish is
counters → invariants → `finish_run_from` → checkpoint → notify (`collect.py:155-174`).
`online_backup` is called only by the migrate service's pre-migration backup
(`tests/services/test_migrate_service.py::test_backup_precedes_migration_and_records_a_row`). No
collection run has ever produced a backup file.

**Fix:** state which milestone lands the per-run backup (it is bound to reconcile, i.e. M1c), so
step 6 does not read as a list of things that happen today.

### F7. "Each row is a test" is not true of the failure matrix — MEDIUM

**Plan:** L288 "**Failure-mode matrix (each row is a test):**"; L273 says the fake "drives the
whole failure matrix".

**Evidence:** at least ten of the forty rows have no test today, and unlike the module and CLI
tables, the matrix has no state column to say so: L294 (401 mid-run, tranche B), L301 (crash mid
comment-tree, M1b), L306 (deleted/removed content through reconcile, M1c), L307 (account deletion,
M1c), L311 (disk write failure on backup or export, M1c/M2), L312 (clock skew — no test uses
`time_machine` at all, see F14), L317 (budget exhausted mid-tree, M1b), L329–331 (workspace delete,
manual tag origins, `watch_until`, all M2). Rows L306–308 have unit tests for the *decision*
(`core/deletion.py`) but nothing that exercises the stated end state (content columns null, index
bytes gone, `post_themes` gone, canary absent).

**Fix:** give the matrix the same state column the module and CLI tables have, or change the header
to "each row is a test or the test a stage owes", which is what it actually is.

### F8. Stickies are not excluded from stop logic — MEDIUM

**Plan:** L181 "…stickies are excluded from stop logic".

**Code:** `SweepState.absorb` (`core/paging.py:75-87`) adds **every** page item to `items_seen`,
stickies included; only the `created_utc` window (`seen_min/seen_max`) filters them out. The cap
stop is `new_state.items_seen >= cap` (`core/paging.py:117`), so a sticky consumes a listing slot
and moves the sweep toward a `cap` stop exactly like any other item — which is right, because
Reddit's cap counts positions.
`tests/unit/test_paging.py::test_stickies_excluded_from_window_but_recorded` asserts precisely
this: recorded in `items_seen`, absent from the window.

**Fix:** say "stickies are excluded from the window the gap detector uses, not from the cap count"
in step 1.

### F9. Two deletion predicates are stated more loosely than the code applies them — MEDIUM

**Plan:** L172.

(a) "`author is None` with intact body → `author_state = account_deleted`". The code needs a second
condition and excludes a case: `_author_state` (`core/deletion.py:212-218`) returns
`ACCOUNT_DELETED` only when `author is None` **and** `author_fullname_present` is False — with the
fullname present it keeps the prior state — and rule 7 (`core/deletion.py:174`) diverts a *link*
post with no author and no category to a hold (`gone_unconfirmed`) instead, pending an `info()`
check. KNOWN_ISSUES § Swept (2026-09-14) states both conditions correctly; the plan does not.

(b) "`== "[removed]"` → `removed_by_moderator` unless `removed_by_category` names Reddit →
`removed_by_reddit`". `_classify_removal` (`core/deletion.py:179-183`) fails closed on *anything*
that is neither `deleted` nor `moderator`: an unknown or unseen category — the module's docstring
names the observed-but-unexplained value `"author"` — becomes `removed_by_reddit`, not
`removed_by_moderator`. The plan's "unless it names Reddit" reads as an allow-list.

**Why it matters:** these are the predicates M1c's reconcile and scrub act on, and the plan is the
canonical design document for them.

**Fix:** restate the content-state sentence from `core/deletion.py:118-157`, which is already
written as an ordered rule list.

### F10. The flock is taken before the pending-migration check, not after — LOW

**Plan:** L180 "validate settings → open the DB, refuse if migrations are pending → `fcntl.flock` …
→ mark stale `running` rows as `crashed` → insert the `runs` row", introduced by "**Order
matters:**".

**Code:** `cli._run_ordered` (`cli.py:285-311`) checks that the database *file* exists (`:291`),
creates the data tree, then acquires the lock (`:305`); `require_head` runs inside
`_collect_through` (`cli.py:435`), i.e. after the lock. The code's order is defensible — the lock
holder may be a `db upgrade` mid-migration, which is why
`tests/e2e/test_run_lock_and_preconditions.py::test_held_lock_during_a_migration_still_exits_75`
exists — but it is not the order the plan prints under a heading that says the order matters.

**Fix:** correct step 0's arrow list to: settings → database present → data tree → flock →
migrations at head → stale sweep → run row → auth ping.

### F11. A run with no collectable source is not "refused" — LOW

**Plan:** L180 "A run with no collectable source is refused loudly (KI-017)."

**Code:** `sweep_all` (`services/sweep.py:1010-1015`) records a `no_enabled_sources` warning and
continues; the run completes, closes `partial` and exits 3
(`tests/services/test_collect_sources.py::test_a_run_with_no_enabled_source_is_partial_not_ok`).
Nothing is refused; `doctor`'s `enabled_sources` check is the error-severity half
(`tests/services/test_doctor.py::test_check_enabled_sources_is_an_error_when_every_source_is_disabled`).
KI-017's own row says "partial not ok", so the plan is looser than the issue it cites.

**Fix:** "a run with no collectable source is never `ok`: it warns, ends `partial`, and `doctor`
reports an error".

### F12. "Up to ten pages of a hundred" is the slot cap, not a page limit — LOW

**Plan:** L181.

**Code:** the cap is on listing slots — `DEFAULT_CAP = 1000` with the stop at `items_seen >= cap`
(`core/paging.py:21,117`) — and Reddit serves short pages routinely (the fake models this, and
KI-018 is about exactly that). The fail-closed page ceiling is `MAX_PAGES_PER_SUBREDDIT = 120`
(`services/sweep.py:111-115`), so a listing served in fifty-item pages is fetched over twenty pages,
not ten, before the cap fires. `CAP_PAGES = 10` (`core/paging.py:27`) is used only for KI-018's
"tenth full page" rule.

**Fix:** "up to a thousand listing slots (Reddit's cap), normally ten pages of a hundred, with a
fail-closed ceiling of 120 pages per source per run".

### F13. The "PK-stability invariant" is a gate test, not a post-run invariant — LOW

**Plan:** L146 "a PK-stability invariant checks that repeated reruns leave `pk`, `first_seen_at`,
and `max(pk) == count(*)` unchanged"; L323's matrix row "PK-stability invariant fails".

**Code:** `INVARIANTS` (`services/invariants.py:348`) has no such member, so no production run ever
checks it. The claim is carried by two tests instead:
`tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at` (three CLI reruns;
pk and first_seen_at only) and `tests/db/test_alembic.py:85-86` (`max(pk) == count(*)`, after a
migration). The word "invariant" in the plan elsewhere means a post-run check that can turn a run
amber or red; here it means a test.

**Fix:** call it "a PK-stability gate" at L146 and in the matrix row, and name the two tests that
split the claim.

### F14. No test uses `time-machine` — LOW

**Plan:** L277 and L278 name `time-machine` as a tool of the unit and collector-e2e layers; L312's
matrix row simulates clock skew with it; L420 lists it as the control for time-dependent flaky
tests.

**Evidence:** `time-machine>=2.16` is a declared dependency (`pyproject.toml:39`) and is in
`uv.lock`, but no file under `tests/` or `src/` imports `time_machine` (grep over the tree; the only
other mention is a 2026-09-12 review document). Time is controlled by the injected `FakeClock`
(`adapters/clock.py`) and by `GuardClock`, which refuses to sleep under pytest (`cli.py:130-147`) —
a stronger control than the plan claims, in fact. There is also no clock-skew test of any kind:
`tests/unit/test_milestones.py::test_shift_invariant_in_created_utc` is the closest thing, and it
tests the ladder function, not a run's rows.

**Fix:** replace `time-machine` with the injected clock in the three places, or write the skew test
the matrix row promises. A dependency no test uses is also a candidate for removal.

### F15. Three claimed behaviours hold in code but nothing asserts them — LOW

- **The run-level notification.** `collect._notify_outcome` (`services/collect.py:318-337`) and the
  crashed-run notification in `_sweep_stale` (`:236`) have no test: no test file references
  `NOTIFYING_STATUSES` or asserts a notifier message on a `failed` / `rate_limited` / `network` run.
  Per-source notifications *are* asserted (`tests/services/test_sweep_status.py:182,200,220,264`),
  and `tests/services/test_sweep_status.py:445` asserts a dry run never notifies. The plan rests on
  the run-level half at L186 ("a notification on failure"), L293 (401 row, "notification") and L384.
- **The `skipped_locked` row** (L302's matrix row). `tests/e2e/test_run_lock_and_preconditions.py::test_held_lock_exits_75_with_zero_gateway_calls`
  asserts exit 75 and zero gateway construction, never that the row was written; the only test that
  touches `_record_skipped_locked` is the one that drops `runs` to prove the failure path still
  exits 75 (`:138`).
- **Clock skew** (F14).

**Fix:** these are cheap tests to add; the notification one also closes the gates-table row at L384.

### F16. The fake's "contract suite (same cases as the real adapter)" does not exist yet — LOW

**Plan:** L136's module row gives `adapters.reddit_fake` the "Tested by" value "contract suite (same
cases as the real adapter)" with state "built".

**Code:** the only suite is `tests/adapters/test_fake_gateway.py`, the fake's own. The contract
suite is a tranche-B artefact by definition (L137 says so for `adapters.reddit_praw`), so the built
row's Tested-by cell describes a future test. Minor, but the module table is the one place a reader
checks "is this tested".

### F17. The dry run's guarantee is stated more absolutely than the code claims — LOW

**Plan:** L214 "`--dry-run` fetches and writes nothing, not even a run row".

**Code:** `tests/gates/test_no_bypass.py::test_dry_run_writes_nothing_anywhere` proves no table
changes, and `cli.py:519-525` deliberately prints "dry run: no database rows written" rather than
"nothing was written", with the comment naming the external round-one finding behind the precision:
a dry run does create the data directories and the read-only engine's `-wal`/`-shm` sidecars. The
plan reverted to the wording the code was corrected away from.

Also minor, in the same row: the CLI table omits `--fixture`, `--reason`, `--trigger` and
`--allow-fake-against-real-data`. The last is a bypass flag under N-06 and is guarded by two
gate tests (`tests/gates/test_no_bypass.py::test_fake_gateway_refused_against_the_default_data_dir`,
`::test_fake_gateway_refused_against_a_database_holding_real_runs`); the plan does not mention the
D-10 guard at all.

### Where the claims held

The core of the collector is described accurately, and the descriptions are tested, often by a
test written for that exact sentence:

- **The retry classes.** The 30/120/300 ladder, the classification table (rate-limited, auth,
  network-down, transient, fatal), the `min(retry_after, 300)` bound, the ceiling rule, the second
  429 ending the run at once (KI-007), the HTML-403 run-level abort and the 78 override for auth —
  every one holds with a named test.
- **Paging.** Forward-only cursors, one transaction per page, the slot cap, the gap rule, KI-018's
  tenth-page rule and its control, empty and sticky-only listings, overlapping pages, the stalled
  cursor and page-ceiling guards (which the plan does not mention but which only fail closed).
- **The per-source status machine.** forbidden / not_found / redirect (three runs) / quarantined
  (one run) / identity mismatch, the single terminal transaction, the announcements-after-commit
  rule, and the recovery clear.
- **The lock and the run lifecycle.** flock semantics, exit 75, the stale sweep's four clauses,
  the heartbeat throttle and its stage, `cancelled` on Ctrl-C with exit 130, `crashed` stamped by
  the next run, the status vocabulary and the total exit-code table.
- **The deletion state machine**, including the KI-021 correction the plan states correctly.
- **The finish order**: counters final before the invariant pass, invariants on a read-only
  connection, the row closed, then `wal_checkpoint(TRUNCATE)` outside every transaction with
  KI-013's retry-and-warn.
- **The fake gateway's builder API**: all ten named methods exist, calls and request costs are
  recorded, the fixture path works, and KI-023's fidelity limit is pinned by its own test.

**KI cross-check.** No plan sentence describes a fixed bug's old behaviour: KI-007 (second 429),
KI-013 (checkpoint), KI-017 (no enabled source, modulo F11's wording), KI-018 (cap on the tenth
page), KI-021 (non-consecutive omissions), KI-022 (membership by content), KI-024 and KI-026
(schedule-bound thresholds), KI-025 (no same-day deferral: `core/retry.py:10-16` now cites D-30) are
all reflected in the current text. The one open row, KI-014 (AUTOINCREMENT after a batch migration),
is named in the plan's migrations testing row (L280) as a checklist owed before the next migration
on `posts` or `comments` — the plan does not claim the absence of that bug.

## What I could not check

- **Test outcomes.** I read test source and did not run the suite, so "a test asserts it" means the
  assertion is in the file, not that it passes today. `make check` is the authority.
- **Unbuilt stages.** Steps 2–5 (M1b–M1d), the web UI, workspaces, search, export and the migration
  rows are design statements about code that does not exist; I checked only that the plan marks them
  as such, not whether the design is right.
- **Identifier resolution** (paths, settings keys, test node ids cited in documents) — G55 and G40
  own that and I did not duplicate it.
- **Numeric estimates** in step 4 (request counts at four months and a year) and step 2's PRAW
  request arithmetic: unverifiable without the real adapter and the probe day.
- **The `tests/deploy` and `tests/web` layers** beyond the two schedule-contract tests the claims
  above lean on.
- **Whether the WARNING/FAILURE split is the right design** — F1 reports that the plan and the code
  disagree, not which of them should move. That is the main session's call.

## Verdict

Of 119 claims: **87 hold**, **4 hold but nothing asserts them**, **16 differ from the code**,
**12 are not built**, **0 not found**.

Of the twelve not built, five sit in prose that gives no milestone marker (step 1's removal signal,
step 6's per-run backup, the `degraded` flag, the coverage counters, the structured logs), six are
failure-matrix rows the matrix does not mark at all (F7), and one (401 `invalid_token` mid-run) is
marked tranche B only by its Simulation column.

**The claim under test does not hold.** The plan is accurate about the collector's mechanism — the
run loop, the retry classes, paging, the status machine, the lock, the deletion predicates and the
finish order are all described correctly and tested — but it is wrong in three ways that matter: it
states a consequence for invariant violations (`failed` + notification) that four of the seven
shipped invariants do not have; it names a `degraded` state that exists nowhere; and in eleven
places it describes behaviour as present that no code implements, without the milestone marker it
uses elsewhere for exactly that purpose. Severity: one CRITICAL, one HIGH, seven MEDIUM, eight LOW.

**Recommendation:** correct F1 and F2 before the plan is used as the source for M1b's invariants —
they are wrong rather than merely incomplete, and F1 will propagate into new code. Fold F3–F7 into
the same pass as milestone markers (the plan already has the convention; these seven sentences just
do not use it). F8–F17 are wording repairs for the next milestone rewrite. None of them requires a
code change: in every case the code is the more careful of the two.

**Confidence: high** for F1, F2, F3, F4, F5, F6, F8, F13, F14 (each rests on a grep over the whole
tree plus the code that contradicts the sentence); **medium** for F7 (the count of untested matrix
rows depends on how generously a row's "expected behaviour" is read) and F9 (the code is right and
the plan's looseness may be deliberate compression); **high** for the "where the claims held"
section.
