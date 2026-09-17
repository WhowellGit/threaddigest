---
purpose: The router from every spec item to the test that proves it, with layer, phase, priority, and status.
update-policy: prune-stale
mirrors: [docs/PLAN.md, docs/runbook/GUARDS.md, docs/runbook/KNOWN_ISSUES.md]
verified-at: M1a-A
---
# Test strategy — v1 (2026-09-13)

> A router, not a copy. Every spec below is specified in full (given/when/then, fixture, positive control) in one of the five raw panel reports under `docs/reference/reviews/2026-09-13-*.md`; the plan's `Testing strategy` and `Robustness` sections are canonical for policy. This file lists what exists, where it lives, its layer, phase, priority, and whether the adversarial review (`docs/reference/reviews/2026-09-13-adversarial-review.md`; its adoptions are in `docs/decisions/DECISIONS.md` § 3 and the 2026-09-13 entries) cut or altered it. Status vocabulary: `planned` (as specified by the panel), `changed` (kept with the alteration in the last column), `cut` (not built; reason given). Flip `planned` to `shipped` with the node id as tests land. Priority vocabularies are the panels' own: DB and ingest H/M/L; enforcement P1 (M0) / P2 (M1) / P3 (optional); UI P0 (blocks M2 operator-complete) / P1 / P2.

## 1. Policy

Testing is layered, and the layer decides the approach: `core/` is strict TDD (every failure-matrix row is a failing test before the service exists); `services/` is TDD against `FakeRedditGateway` plus a temp DB created by `alembic upgrade head`; the PRAW adapter is probe-first (Reddit's behavior is captured with `probe --save-fixture`, never assumed, and the fixture drives both the cassette and the fake through one schema); migrations are test-first with a per-revision fixture DB and the `schema.sql` golden; web routes are test-with, the DOM assertion written alongside the template. Nothing in the suite touches the network (`--block-network`, extended across the subprocess seam), sleeps (injected `Clock`), or mocks internals (`mock.patch` banned outside `tests/adapters/`); tests run only against a temp data dir. Guards obey the design rules in § 5: shape over list, invariant over proxy, a constructed bad state for every post-run invariant, fail never skip, zero-suppression baseline, hold the count. The shipped gate set starts small (§ 4) and grows only on recurrence; the panels' full tables are the menu.

## 2. Kinds of tests and sweeps

| Kind | What it proves | Tools / where | Source |
|---|---|---|---|
| Unit (`core/`) | normalize, deletion state table, paging/stop/gap, ladder, budget, theme rules incl. regex timeout, digest golden, UA | pytest, hypothesis with stated properties (NM-01) | ingest §B.9, B.12; DB §A1 |
| Service / e2e against the fake | whole `run` and each stage through `CliRunner` with the scenario-builder fake (`add_post`, `delete`, `remove`, `vanish`, `fail_page`, `rate_limit_next`, …; unconsumed injections fail the test) and a temp DB | `FakeRedditGateway`, `FakeClock`, `FakeNotifier`, `tmp_path` | ingest §A, §B |
| Adapter: cassette + `responses` + contract | happy paths from recorded cassettes (test subreddit only; pytest-recording's default record mode is `none`, so replay never records); failure paths with exact request counts; the same cases against fake and PRAW so the fake stays honest | pytest-recording, `responses`, one fixture schema | ingest §B.14, §C probes P-01…17 |
| Migration with per-revision fixtures | `schema.sql` golden, models == DDL, single head, up/down; every prior revision's fixture DB upgrades clean with FTS (`_docsize`) == live, canaries checked | pytest-alembic, `tests/fixtures/db/<rev>.sqlite` + manifest, generated from pre-change code | DB §A1, §A8, §B, §C |
| Gate positive controls | each CI gate/ratchet made red from a constructed bad state in `tmp_path`, asserting the tool's own message; config-borne gates proven by running pytest as CI runs it | `tests/gates/`, `@pytest.mark.gate("<ID>")` | enforcement §B; adversarial A3 split |
| Workflow tests spanning stages and operator flows | one fake corpus through sweep → trees → revisit → reconcile → tag → digest → backup; setup → first sweep; theme edit → retag; backup → restore drill; pending migration → apply; export → import on a fresh data dir; end state, counters, delivered artifacts | pytest, fake, temp data dir | plan § Testing "Workflow"; UI §B checklist |
| Web route / DOM / middleware | every route on seeded and empty DB, fragment vs page, tombstones, deep links, sanitizer, CSRF and Host, Run now, gates, export, setup wizard, operator-complete gate | FastAPI TestClient + selectolax, hypothesis for query params | UI §A |
| Scheduled production sweeps | post-run invariants after every run (§ 4); per-source freshness; on each scheduled run (twice a week, D-30) the compliance reconcile; weekly: `EXPLAIN QUERY PLAN` assertions (the stress corpus is cut), portability job, restore drill into a temp dir (automation pending Wes); quarterly guard review. Dead-man = Healthchecks.io ping from M1d; notifications best-effort, the UI pill is canonical | launchd + CI schedules; `RUNBOOK.md` § 5–6 | plan § Sweeps; adversarial A4/A5 |
| Live smoke | `pytest -m live`: auth ping, 5 posts from r/premiere, rate-limit headers; deselected by `addopts`, run locally before a PRAW bump, **never in CI** | real PRAW, credentials on the Mac only | enforcement E8 |

## 3. Spec index

### 3.1 Database integrity and migrations — `2026-09-13-panel-db-integrity.md` §A (55)

| ID | Name | Layer | Phase | Pri | Status | Reason if cut/changed |
|---|---|---|---|---|---|---|
| DB-01 | schema_sql_golden_matches_head | migration | M0 | H | planned | |
| DB-02 | models_match_ddl_with_fts_filter | migration | M0 | H | planned | |
| DB-03 | single_head_and_up_down_consistency | migration | M0 | H | planned | |
| DB-04 | every_reddit_keyed_table_has_rowid_alias_pk | db | M0 | H | planned | |
| DB-05 | timestamp_columns_are_integer_epoch | db+unit | M0 | H | planned | |
| DB-06 | next_check_at_not_null_enforced | db | M1a | H | shipped | tests/db/test_schema_shape.py::test_next_check_at_is_not_null |
| DB-07 | derived_enums_closed_upstream_enums_open | db | M1a | H | shipped | tests/db/test_schema_shape.py::test_check_rejects_unknown_derived_state, ::test_check_rejects_unknown_run_status, ::test_check_accepts_unknown_upstream_enum_values |
| DB-08 | hot_queries_use_declared_indexes | db | M1a | M | shipped | the four `EXPLAIN QUERY PLAN` assertions the plan keeps in place of the stress corpus (stress corpus cut 2026-09-13, N-11); tests/db/test_query_plans.py::test_due_posts_uses_next_check_at_index, ::test_window_query_uses_subreddit_created_index, ::test_author_query_uses_author_index, ::test_live_feed_uses_content_state_index |
| DB-09 | every_column_has_a_comment | unit | M0 | M | planned | |
| DB-10 | fts_definition_shape (live views, `_docsize`) | db | M1a | H | shipped | tests/db/test_fts.py::test_fts_definition_shape |
| DB-11 | create_engine_only_in_db_engine | gate | M0 | H | changed | symbol ban is ruff `TID251` (`create_engine`, `text(`, `sqlite3.connect`); import-linter confines modules only |
| DB-12 | pragmas_effective_on_public_write_connection | db | M0 | H | planned | |
| DB-13 | foreign_keys_enforced_behaviorally | db | M1a | H | shipped | tests/db/test_engine_pragmas.py::test_foreign_keys_are_enforced |
| DB-14 | busy_timeout_waits_then_fails_cleanly | db | M1a | M | shipped | tests/db/test_repo_busy_timeout.py::test_second_writer_waits_then_page_fails_with_nothing_committed |
| DB-15 | secure_delete_leaves_no_canary_bytes | db | M1a | H | shipped | pulled forward 2026-09-14 (KI-009), strengthened by revision 0004 (2026-09-15): `tests/db/test_fts.py::test_scrub_with_secure_delete_leaves_no_term_bytes_without_an_optimize` asserts the term absent from the index's data blocks, the database file, and a fresh copy the test takes with `VACUUM INTO` immediately after the scrub (the test's own control; the backup mechanism is the online backup API, which replaced the statement); the first byte-level assertion, the class the methodology seat asked for |
| DB-16 | read_only_paths_cannot_write | db/web | M2 | H | changed | web `mode=ro` read session cut (one rw engine behind the writer-map repository, DB-52); Datasette `mode=ro` launcher assertion kept |
| DB-17 | wal_truncated_at_end_of_run | e2e | M1a | L | shipped | tests/e2e/test_run_happy_path.py::test_wal_is_truncated_at_end_of_run |
| DB-18 | settings_refuse_default_data_dir_under_pytest | unit/gate | M0 | H | planned | |
| DB-19 | only_data_dir_is_writable_during_tests | gate/e2e | M0/M1a | H | planned | |
| DB-20 | pk_stability_across_reruns | e2e | M1a | H | shipped | `AUTOINCREMENT` on posts/comments; `max(pk)==count(*)` only in this no-purge scenario, never at runtime (adversarial A10); tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at; positive control tests/db/test_alembic.py::test_insert_or_replace_burns_the_pk_and_detaches_fts |
| DB-21 | field_ownership_per_ingest_path | db | M1a | H | shipped | may be deleted with the second wire shape if trees are fetched via `reddit.request()` (decide M1b); tests/db/test_repo_ownership.py::test_ownership_covers_every_column, ::test_emitted_statement_matches_ownership, ::test_value_builder_emits_exactly_the_declared_insert_columns |
| DB-22 | upsert_never_resurrects_terminal_content | db+e2e | M1c | H | planned | |
| DB-23 | moderator_removed_returns_to_live_reindexes | db | M1c | M | planned | |
| DB-24 | orphan_parent_comment_without_fk | db | M1b | M | planned | |
| DB-25 | unknown_enum_values_stored_raw_and_counted | e2e | M1a | H | shipped | tests/services/test_sweep_writes.py::test_unknown_enum_is_stored_raw_and_counted, ::test_overlapping_pages_count_one_unknown_occurrence |
| DB-26 | fts_membership_equals_live_via_run (`_docsize`) | gate/e2e | M1a | H | shipped | a failure since 2026-09-16 (the index is a compliance surface); tests/services/test_invariants.py::test_fts_membership_equals_live_passes_when_the_index_matches_live_rows, ::test_fts_membership_equals_live_flags_a_membership_mismatch; planted control tests/gates/test_invariants_planted.py::test_planted_violation_flips_the_run |
| DB-27 | fts_insert_gated_on_live | db | M1a | H | shipped | tests/db/test_fts.py::test_live_post_is_indexed, ::test_tombstone_insert_is_not_indexed |
| DB-28 | fts_scrub_removes_entry_and_snippets | db | M1c | H | planned | |
| DB-29 | fts_author_scrub_reindexes_without_author | db | M1c | H | planned | |
| DB-30 | fts_rebuild_indexes_live_only_and_integrity_check_passes | migration/db | M1a | H | shipped | tests/db/test_fts.py::test_rebuild_indexes_live_rows_only_and_passes_integrity_check |
| DB-31 | scrub_touches_four_surfaces_in_one_call | e2e | M1c | H | changed | the JSONL surface is gone (sidecar cut 2026-09-13); canary also in a title |
| DB-32 | compliance_canary_absent_everywhere_incl_backup | e2e/gate | M1c | H | changed | also asserts no backup older than 14 d and no export older than 7 d (adversarial B1); title canary (B3) |
| DB-33 | scrubbed_rows_have_no_content_columns | gate | M1c | H | planned | |
| DB-34 | compressed_jsonl_verified_before_plain_deleted | unit/e2e | M1c | M | cut | per-run JSONL sidecar cut 2026-09-13 |
| DB-35 | partial_trailing_jsonl_line_tolerated_db_authoritative | unit | M1c | M | cut | per-run JSONL sidecar cut 2026-09-13 |
| DB-36 | per_run_vacuum_into_backup_recorded_and_verified | e2e | M1c | H | planned | one copy per scheduled run, after reconcile (D-30, D-31); renamed from the daily-era name 2026-09-15 |
| DB-37 | pre_migrate_backup_order_and_post_checks | migration/e2e | M1a | H | shipped | tests/services/test_migrate_service.py::test_backup_precedes_migration_and_records_a_row, ::test_quick_check_failure_aborts_before_migrating, ::test_post_checks_run_after_upgrade |
| DB-38 | transaction_per_migration_no_half_state | migration | M1a | H | shipped | tests/e2e/test_db_commands.py::test_failed_upgrade_restores_and_finishes_the_run_row_failed; tests/services/test_migrate_service.py::test_a_failed_integrity_check_also_restores |
| DB-39 | destructive_ops_require_recent_verified_backup | gate/e2e | M1c/M2 | H | changed | gate takes a `Confirmation` value object (UI phrase or CLI flag) checked inside the service; `backups` table ships in rev 1 so the UI gate is live at M2 |
| DB-40 | restore_is_atomic_under_lock | e2e | M2 | H | planned | |
| DB-41 | online_backup_consistent_under_concurrent_writes | db | M1c | M | planned | |
| DB-42 | import_export_roundtrip_preserves_and_refuses | e2e | M2 | M | planned | |
| DB-43 | runtime_fingerprint_agreement | e2e/gate | M0 | H | changed | mismatch is a warning on `doctor` and `/system`, ordinary tables only, never exit 78 (adversarial A9); stamping assertions kept |
| DB-44 | fixture_db_per_revision_upgrades_clean | migration | M1a→ | H | shipped | tests/db/test_alembic.py::test_revision_fixture_upgrades_clean |
| DB-45 | fixture_set_equals_revision_set_and_every_table_seeded | gate | M1a | H | shipped | tests/db/test_alembic.py::test_fixture_set_equals_non_head_revisions, ::test_every_table_seeded_in_each_fixture |
| DB-46 | downgrade_one_and_back_preserves_data | migration | M1a | M | shipped | tests/db/test_migrate_revisions.py::test_downgrade_one_steps_back_exactly_one_revision, ::test_downgrade_rewrites_network_rows_to_failed |
| DB-47 | reprocess_from_raw_json_byte_identical | e2e | M1a | H | planned | no `reprocess` command exists yet; not built in tranche A |
| DB-48 | rows_written_this_run_carry_current_normalizer_version | gate | M1a | H | shipped | adversarial A15 would fold it into DB-47; the plan did not adopt that; tests/services/test_invariants.py::test_rows_carry_current_normalizer_version_passes_when_all_rows_are_current, ::test_rows_carry_current_normalizer_version_flags_a_stale_row_written_this_run |
| DB-49 | settings_fingerprint_changes_only_on_non_secret_change | e2e | M1d | M | planned | |
| DB-50 | population_floors_fail_the_run_and_name_the_column | gate/e2e | M1a | H | shipped | structural floors only: 100% on live rows with `author_state=known` (A11, ingest D-13), not 95% over all rows; amber, not `failed`, by severity (the code carries no clock); tests/services/test_invariants.py::test_empty_population_with_writes_is_a_violation |
| DB-51 | floors_scoped_by_normalizer_version_and_empty_population_fails | gate | M1a/M1c | H | shipped | tests/services/test_invariants.py::test_floor_is_scoped_by_normalizer_version, ::test_empty_population_with_writes_is_a_violation |
| DB-52 | web_writer_map_enforced | gate/web | M2 | H | planned | |
| DB-53 | authors_counters_match_count | gate | M1c | M | planned | |
| DB-54 | counters_equal_table_deltas | gate | M1a | H | shipped | the `raw_files.item_count` clause is dropped (sidecar cut 2026-09-13); tests/gates/test_counters_deltas.py::test_counters_equal_table_deltas_on_a_clean_run, ::test_planted_extra_row_fails_the_run |
| DB-55 | row_counts_never_decrease_without_recorded_purge | gate | M1c/M2 | M | planned | |
| DB-56 | fts_update_trigger_fires_only_on_a_change | db | M1a | H | shipped | KI-012, 2026-09-14 (revision 0003): `tests/db/test_fts.py::test_a_routine_upsert_with_identical_text_leaves_the_index_untouched`; control `::test_positive_control_the_unconditional_trigger_rewrote_the_index` downgrades to 0002 and shows the growth |
| DB-57 | wal_checkpoint_busy_is_a_run_warning | service | M1a | H | shipped | KI-013, 2026-09-14: `tests/services/test_collect_checkpoint.py::test_a_reader_during_the_final_checkpoint_leaves_a_warning_and_a_partial_run` |
| DB-58 | error_text_hides_bound_parameters | db | M1a | H | shipped | KI-010, 2026-09-14: `tests/db/test_engine_pragmas.py::test_error_text_hides_bound_parameters` (control: a bare engine renders the value); `tests/services/test_sweep_errors.py::test_a_failed_page_write_keeps_post_text_out_of_the_error_message` |
| DL-01 | a_hold_on_a_returned_item_does_not_count_toward_gone | unit | M1a | H | shipped | KI-021, 2026-09-14: `tests/unit/test_deletion.py::test_a_bodyless_return_then_one_omission_is_still_an_unconfirmed_hold`; the parametrized hold rows carry the corrected miss counts |
| NM-12 | crosspost_parent_text_never_stored_on_any_surface | unit+service | M1a | H | shipped | KI-016, 2026-09-14: `tests/unit/test_normalize.py::test_canonical_raw_keeps_only_the_parent_pointer_of_a_crosspost`, `::test_a_rejected_crosspost_keeps_no_parent_text_either`, `tests/services/test_sweep_writes.py::test_a_crosspost_row_keeps_no_copy_of_the_parent_text_or_author` |
| DB-59 | restore_copies_before_it_deletes | db | M1a | H | shipped | KI-015, 2026-09-14: `tests/db/test_backup.py::test_a_restore_whose_copy_fails_leaves_the_live_database_and_its_log_untouched` (a crash-left log survives a restore whose copy fails) |
| DB-61 | secure_delete_clears_the_term_without_an_optimize | db | M1a | H | shipped | KI-009 / revision 0004, 2026-09-15: `tests/db/test_fts.py::test_scrub_with_secure_delete_leaves_no_term_bytes_without_an_optimize`; control `::test_positive_control_without_secure_delete_the_term_survives_a_scrub_until_optimize` |
| DB-62 | sqlite_version_meets_the_secure_delete_floor | service | M1a | M | shipped | KI-009 / revision 0004, 2026-09-15: `tests/services/test_doctor.py::test_check_sqlite_version_is_ok_on_the_runtime_library`; control `::test_check_sqlite_version_is_an_error_below_the_secure_delete_floor` |
| DB-63 | run_display_reads_for_the_runs_page | db | M1a | H | shipped | the first web slice, 2026-09-16: the display columns `RunRow` does not carry, the run behind one local day, the ranked window and the denominator counted over the same population. `tests/db/test_repo_reads.py::test_run_display_carries_every_column_a_page_shows`, `::test_run_for_window_returns_the_newest_finished_run_anchored_on_its_start`, `::test_ranked_posts_orders_by_rank_posts_and_not_by_the_database`, `::test_ranked_posts_limits_after_ranking_and_counts_its_own_window`, `::test_recent_sweeping_runs_never_looks_past_the_run_it_anchors_on` |
| CF-11 | shipped_display_timezone_is_resolvable_and_validated_at_load | unit | M1a | H | shipped | KI-011, 2026-09-15: `tests/unit/test_settings.py::test_shipped_display_timezone_is_a_zone_the_digest_can_resolve`; control `::test_settings_reject_an_unresolvable_display_timezone` |

### 3.2 Ingest and collector — `2026-09-13-panel-ingest.md` §B (60); probes §C P-01…17

| ID | Name | Layer | Phase | Pri | Status | Reason if cut/changed |
|---|---|---|---|---|---|---|
| SW-01 | sweep_full_window_forward_after_only | unit+service | M1a | H | shipped | tests/services/test_sweep_paging.py::test_sweep_pages_forward_only_and_never_uses_before |
| SW-02 | sweep_cap_sets_gap_stickies_excluded | unit+service | M1a | H | shipped | tests/services/test_sweep_paging.py::test_cap_stop_sets_gap_suspected, ::test_stickies_are_seen_but_excluded_from_the_window |
| SW-03 | sweep_overlapping_pages_dedupe | service | M1a | H | shipped | tests/services/test_sweep_paging.py::test_overlapping_pages_produce_one_row_each |
| SW-04 | sweep_crash_between_pages_one_txn_per_page | e2e | M1a | H | shipped | tests/e2e/test_run_happy_path.py::test_crash_between_pages_commits_earlier_pages_and_rerun_completes |
| SW-05 | field_ownership_per_ingest_path | unit+service | M1a | H | shipped | see DB-21 (M1b decision on the second wire shape); tests/db/test_repo_ownership.py::test_emitted_statement_matches_ownership; tests/services/test_sweep_writes.py::test_sweep_never_touches_first_seen_at_check_stage_next_check_at_or_scrubbed_at |
| SW-06 | sweep_removal_signal_confirmed_via_info | service | M1a/M1c | H | planned | needs the reconcile step's `info()` confirmation (M1c); not built in tranche A |
| SW-07 | sweep_empty_or_zero_new_ok | service | M1a | M | shipped | its zero-yield counter is the per-source zero-new detection kept in place of the anchor; tests/services/test_sweep_paging.py::test_empty_subreddit_is_ok_and_exhausted, ::test_zero_new_run_records_zero_new_items |
| SW-08 | end_of_listing_on_the_tenth_page_is_the_cap | service | M1a | H | shipped | KI-018, 2026-09-14: `tests/services/test_sweep_paging.py::test_a_listing_ending_at_the_cap_with_filtered_slots_is_a_cap_stop_not_exhausted`; control `::test_a_listing_ending_before_its_tenth_page_is_still_exhausted` |
| FK-01 | more_expansion_reveals_at_most_a_hundred_per_request | adapter | M1a | H | shipped | KI-023, 2026-09-14: `tests/adapters/test_fake_gateway.py::TestTree::test_a_large_more_node_reveals_at_most_a_hundred_per_request`; the probe day confirms the real shape |
| SS-01 | sub_forbidden_others_continue | service | M1a | H | shipped | tests/services/test_sweep_status.py::test_forbidden_marks_the_source_and_others_continue |
| SS-02 | sub_not_found_banned_policy | service | M1c | M | planned | P-16 fixture may be unresolvable |
| SS-03 | sub_redirect_auto_disabled_after_n | service | M1a | M | shipped | tests/services/test_sweep_status.py::test_redirect_auto_disables_after_three_runs_with_an_alert |
| SS-04 | sub_quarantined_disabled_with_alert | service+adapter | M1a | M | shipped | tests/services/test_sweep_status.py::test_quarantined_is_disabled_with_an_alert |
| SS-05 | sub_identity_casing_merges_t5_change_aborts | service+CLI | M1a | H | shipped | tests/services/test_sweep_status.py::test_casing_merges_to_one_row, ::test_t5_mismatch_aborts_the_subreddit_before_any_row_is_written |
| SS-06 | sub_recovery_clears_error_state_after_complete_sweep | service | M1a | M | shipped | tests/services/test_sweep_status.py::test_complete_sweep_clears_status_failures_last_error_and_gap |
| TE-01 | transient_page_error_outer_retry_backoff | service | M1a | H | shipped | tests/services/test_sweep_errors.py::test_transient_page_error_walks_the_30_120_300_ladder |
| TE-02 | rate_limited_and_fatal_gateway_errors | service | M1a | H | shipped | tests/services/test_sweep_errors.py::test_rate_limited_waits_then_retries_once, ::test_auth_failed_aborts_the_run_with_78, ::test_html_403_aborts_the_run_not_the_subreddit |
| TR-01 | tree_skip_when_num_comments_zero | service | M1b | H | planned | |
| TR-02 | tree_more_accounting_and_per_post_cap | service | M1b | H | planned | cap is per fetch (ingest D-3), pending Wes |
| TR-03 | tree_crash_mid_tree_nothing_committed | e2e | M1b | H | planned | |
| TR-04 | tree_budget_reserve_newest_first | service | M1b | H | planned | |
| TR-05 | tree_missing_known_comments_checked_via_info | service | M1c | H | planned | |
| RV-01 | ladder_pure_never_null | unit+hypothesis | M1a | H | shipped | ladder gains a 365-day stage; `next_check_at` is never a far-future sentinel; tests/unit/test_milestones.py::test_never_none_and_always_after_creation, ::test_default_ladder_matches_plan |
| RV-02 | ladder_advances_on_complete_refetch_skew_safe | service | M1c | H | planned | clock-skew claim scoped per ingest D-2 |
| RC-01 | deletion_state_table_fail_closed | unit | M1a | H | shipped | predicate keys on `removed_by_category='deleted'` first; `author is None` on a link post = deletion pending `info()`; predicates unlocked until probes land (incl. a deleted link post); tests/unit/test_deletion.py::test_never_raises_and_invariants_hold, ::test_never_live_without_intact_content, ::test_info_absence_counts_a_miss, ::test_deleted_markers_are_terminal_from_any_prior |
| RC-02 | reconcile_batches_100_match_by_fullname | service | M1c | H | planned | reconcile upserts the full normalized row (edits are an event) |
| RC-03 | reconcile_misses_scrub_second_transient_resets | service | M1c | H | planned | same-run re-check of first misses (D-9) pending Wes |
| RC-04 | author_deletion_terminal_mod_removal_returns | service | M1c | H | planned | |
| RC-05 | account_deletion_scrubs_author_only | service | M1c | H | planned | |
| RC-06 | reconcile_cadence_invariant_and_tier_fallback | service+digest | M1c/M3 | M | changed | invariant is per tier: 60 h ≤ 30 d, 8 d to 1 y, 35 d beyond (replaces 48 h + 12 h grace) |
| SC-01 | scrub_is_one_function_all_surfaces | service | M1c | H | changed | JSONL surface gone (sidecar cut 2026-09-13); canary in a title too; FTS5 persistent secure-delete (revision 0004) removes the term bytes as the scrub trigger runs, so `db.fts.optimize` is periodic maintenance, not the compliance step (KI-009, revised 2026-09-15) |
| SC-02 | compliance_canary_end_to_end | e2e | M1c | H | changed | scans `data/**`; digest is a route (no file); asserts backup/export file ages (B1) |
| FR-01 | per_source_freshness_degraded | e2e | M1a | H | shipped | `partial`/amber, not `failed`, by severity (no clock); also iterates disabled-by-error sources (B8); tests/services/test_invariants.py::test_freshness_skips_runs_that_swept_nothing, ::test_freshness_stands_down_on_a_terminal_run |
| FR-02 | freshness_anchor_uniform_staleness | e2e | M1a | H | cut | anchor cut (adversarial A8: sweep and anchor are the same call); `new_head()` port and `set_live_anchor` go with it; SW-07 zero-yield detection kept |
| PA-01 | shape_parity_listing_tree_info_search | unit+contract | M1a | H | planned | needs one real post captured four ways (probe P-10); may be deleted with the second shape (M1b decision) |
| PA-02 | reprocess_golden_byte_identical | db/unit | M1a | H | planned | no `reprocess` command exists yet; not built in tranche A |
| NM-01 | normalize_missing_fields_and_rejects | unit+hypothesis | M1a | H | shipped | tests/unit/test_normalize.py::test_missing_required_post_key_rejects_and_preserves_raw, ::test_missing_required_comment_key_rejects |
| NM-02 | unknown_enum_stored_raw_and_counted | service | M1a | H | shipped | tests/services/test_sweep_writes.py::test_unknown_enum_is_stored_raw_and_counted |
| NM-03 | population_floor_and_coverage_median_via_run | gate | M1a | H | shipped | (a) floors shipped, scoped to live `author_state=known` rows: tests/services/test_invariants.py::test_empty_population_with_writes_is_a_violation, ::test_floor_is_scoped_by_normalizer_version; (b) trailing-median alarm deferred to M3 after 60 days of baseline |
| RL-01 | preconditions_exit_78_no_running_row | e2e | M0/M1a | H | shipped | full exit-code table (0/1/3/4/75/78/130) proposed, pending Wes; tests/e2e/test_run_lock_and_preconditions.py::test_invalid_settings_exit_78_with_no_run_row, ::test_pending_migrations_exit_78_with_no_run_row, ::test_exit_code_table_is_total_over_run_status |
| RL-02 | flock_held_exit_75_zero_calls | e2e | M1a | H | shipped | tests/e2e/test_run_lock_and_preconditions.py::test_held_lock_exits_75_with_zero_gateway_calls |
| RL-03 | stale_running_row_marked_crashed_at_45m | e2e | M1a | H | shipped | threshold is 3 min (shared settings key with the UI); a held flock means alive regardless of heartbeat age; `queued` > 2 min without pid → `failed`; tests/services/test_runs_lifecycle.py::test_stale_running_row_is_marked_crashed, ::test_orphan_queued_row_older_than_two_minutes_fails |
| RL-04 | every_mutating_command_takes_lock_writes_run_row | gate | M1a | H | shipped | tests/gates/test_mutating_commands.py::test_every_mutating_command_takes_the_lock_and_writes_a_run_row |
| RL-05 | wall_clock_ceiling_partial_after_batch | service | M1d | M | planned | |
| RL-06 | sigterm_finishes_batch_cancelled | e2e | M1d | M | planned | cancel at the request boundary (D-16), pending Wes |
| RL-07 | write_side_failures_abort_page_cleanly | e2e | M1a | H | shipped | (b)/(c) sink cases dropped (sidecar cut 2026-09-13); (a) DB-locked case stays: tests/services/test_sweep_errors.py::test_db_locked_write_fails_the_page_with_nothing_committed |
| JS-01 | jsonl_per_run_file_compress_verify_before_delete | unit+service | M1c | H | cut | per-run JSONL sidecar cut 2026-09-13 |
| JS-02 | jsonl_retention_gate_and_partial_trailing_line | service | M1c | M | cut | per-run JSONL sidecar cut 2026-09-13 |
| TH-01 | theme_regex_timeout_and_caps | unit | M1d | H | planned | |
| TH-02 | theme_inputs_bot_exclusion_retag | service | M1d | H | changed | crosspost parent text stripped to `{id, subreddit}` at ingest (no `matched_field=crosspost_parent`); bot flag is a heuristic per author, never inherited |
| DG-01 | digest_golden_denominators_from_state | unit+service | M1d | H | changed | golden gains the M1d sections pulled forward: distinct-author ranking, top untagged (7 d, ≥3 authors), rising title phrases. The unit half's golden moved once, on 2026-09-16, when the top-post heading gained the window the list covers (`WorkspaceSection.window_days`), because a heading that named no window invited a reader to take a seven-day list for an all-time one; the service half landed early with the first web slice, 2026-09-16, because a page on an unfinished assembler could not be reviewed on its own: `tests/services/test_report_service.py::test_assemble_digest_takes_its_numbers_from_the_run_row`, `::test_an_unstaged_section_shows_a_zero_against_a_real_denominator`, `::test_the_assembled_model_renders_through_both_templates` |
| DG-02 | notifier_proof_recorded | service | M1d | M | cut | notifications are best-effort; the UI pill computed from `runs` is the canonical alert (adversarial A4) |
| CF-01 | dry_run_no_network_zero_http_zero_db_writes | gate | M1a | H | shipped | `--dry-run` fetches (HTTP counted, zero DB writes); zero-HTTP applies to `doctor --no-network` and `config validate` (ingest D-1); tests/gates/test_no_bypass.py::test_dry_run_writes_nothing_anywhere |
| CF-02 | no_bypass_flags_budget_hard_cap | gate | M1a | H | shipped | option-name grep dropped (list-policing, A7); budget cap and "reconcile and scrub still run" kept; bypass flags record a reason on the run row; `--gateway fake` refused against the default data dir (D-10); tests/gates/test_no_bypass.py::test_budget_is_clamped_to_the_hard_cap, ::test_no_comments_requires_a_reason_and_records_it, ::test_fake_gateway_refused_against_the_default_data_dir, ::test_fake_gateway_refused_against_a_database_holding_real_runs |
| CF-03 | settings_extra_forbid_and_fingerprint | unit | M0 | M | planned | |
| CF-04 | data_dir_isolation_refusal | gate | M0 | H | changed | extended across the subprocess seam: env-var data dir, injectable `ProcessRunner`, CLI refuses under `PYTEST_CURRENT_TEST` without `--gateway fake` (B4) |
| CF-12 | serve_refuses_a_missing_or_behind_head_database | e2e | M1a | H | shipped | the first web slice, 2026-09-16: `serve` refuses a missing database, one behind head and one from an older revision, each at 78 with no run row and with `run`'s own wording; it then refuses to open a socket under pytest, which is why no test in the suite starts a server. `tests/e2e/test_serve_command.py::test_serve_refuses_a_missing_database`, `::test_serve_refuses_a_database_behind_head`, `::test_serve_refuses_a_database_from_an_older_revision`, `::test_serve_refuses_unresolvable_settings`, `::test_serve_refuses_to_start_a_server_under_pytest` |
| AD-01 | cassette_auth_ping_two_requests_ua_limits | adapter-cassette | M0 | H | planned | needs a recorded auth exchange (probe P-15); the `vcr_config` filters it will be recorded under ship with AD-02. Its offline twin exists and holds the two-call cost today: `tests/adapters/test_praw_gateway.py::test_the_auth_ping_costs_exactly_two_http_calls` drives `services.doctor.check_auth_ping` through a real `PrawGateway` with `responses`. What the cassette still owes is the wire shapes and the user-agent, which hand-built payloads cannot prove |
| AD-02 | responses_failure_paths_exact_counts | adapter-responses | M1a | H | shipped | tests/adapters/test_praw_gateway.py::test_a_401_at_the_token_endpoint_costs_one_request, ::test_an_invalid_token_midrun_buys_a_fresh_token_for_every_retry, ::test_a_private_subreddit_is_forbidden, ::test_an_html_403_is_an_edge_block_and_not_a_private_subreddit, ::test_a_quarantine_body_is_named_as_such, ::test_a_404_is_a_missing_subreddit, ::test_a_302_carries_the_path_it_redirected_to, ::test_a_429_carries_its_retry_after_as_a_number, ::test_a_429_without_the_header_has_no_retry_after, ::test_a_503_is_transient_only_after_prawcores_two_retries, ::test_a_dropped_connection_is_transient_and_still_counted |
| AD-03 | cassette_tree_serialization_no_lazy_fetch | adapter-cassette | M1b | H | planned | needs a recorded tree (probes P-08, P-11, P-20); the offline suite drives trees from hand-built payloads, which cannot prove a lazy fetch never fires |
| AD-04 | contract_suite_fake_vs_praw | contract | M1a–M1c | H | planned | needs cassettes to run the same cases against PRAW; parametrizing the suite before they exist would add a case that proves nothing |
| GT-01 | guard_reachability_meta_and_planted_invariants | gate | M0→ | H | shipped | sidecar-dependent plantings dropped (sidecar cut 2026-09-13); scope is post-run invariants only (A3 split); tests/gates/test_invariants_planted.py::test_planted_violation_flips_the_run, ::test_a_crashing_invariant_fails_the_run_rather_than_leaving_it_running |
| GT-02 | pk_stability_three_reruns | gate | M1a | H | shipped | drop `max(pk)==count(*)` (A10); `pk`/`first_seen_at` stability kept; tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at |
| GT-03 | behavioural_dependency_pins_keep_their_bound | gate | M1a | H | shipped | G53, external round one panel 2026-09-15: `tests/gates/test_dependency_pins.py::test_praw_is_pinned_to_the_tested_major`, `::test_installed_praw_satisfies_the_pin` (the `praw>=8,<9` pin had no control; a loosening to 7.x is now red) |
| GT-04 | schedule_contract_checked_without_macos_tooling | deploy | M1a | H | shipped | external round one panel 2026-09-15: `tests/deploy/test_schedule_contract.py` parses the plist with stdlib plistlib and reads run.sh, so the Monday/Thursday 06:30 schedule and `--alert-if-stale 5d` (D-30) are enforced on Linux CI too, not only the macOS-gated `test_launchd.py` |

### 3.3 Enforcement, gates, ratchets, CI — `2026-09-13-panel-enforcement.md` §B (38), hooks §D

| ID | Name | Layer | Phase | Pri | Status | Reason if cut/changed |
|---|---|---|---|---|---|---|
| G01 | Exception-policy lint | gate | M0 | P1 | planned | |
| G02 | Banned APIs (`TID251`) | gate | M0 | P1 | planned | |
| G03 | mypy strict, `dmypy` whole tree in pre-commit | gate | M0 | P1 | planned | |
| G04 | Layering (import-linter) | gate | M0 | P1 | planned | |
| G05 | External-package chokepoints | gate | M0 | P1 | planned | |
| G06 | Network block | gate | M0 | P1 | changed | extended across the subprocess seam (B4); a `Popen` child is not blocked by the plugin |
| G07 | Warnings are errors | gate | M0 | P1 | planned | |
| G08 | Static skip/xfail ratchet | gate | M0 | P1 | planned | |
| G09 | Runtime skipped == 0 | gate | M0 | P1 | planned | `-m "not live"` in `addopts` |
| G10 | Suppression ratchet | gate | M0 | P1 | changed | also counts mypy `[[tool.mypy.overrides]]` (declared with a reason) |
| G11 | Coverage ratchet (hard floor, 0.5 slack) | gate | M0 | P1 | planned | |
| G12 | Test-count and assertion floors | gate | M0 | P1 | changed | collected-test floor cut by the adversarial review and the plan; the assert-count floor under the loosening protocol was adopted from this panel; the plan carries both statements — Wes to confirm |
| G13 | One-way protocol vs `main` (three comparisons) | gate | M0 | P1 | shipped | the three-way compare lives in `tools/ratchet.py compare` and is covered by the ratchet ledger rows (G10, G11, G51) rather than a row of its own; the approval fallback (required label + auto-opened issue) waits for a GitHub remote |
| G14 | Guard-count ceiling | gate | M0 | P2 | planned | |
| G15 | Schema snapshot | gate | M0 | P1 | planned | |
| G16 | Models == DDL | gate | M0 | P1 | planned | |
| G17 | Per-revision fixture DBs | gate | M1a | P2 | shipped | "FTS count == live count" is measured via `posts_fts_docsize`, never `count(*) FROM posts_fts` (DB panel verification); tests/db/test_alembic.py::test_revision_fixture_upgrades_clean, ::test_fixture_set_equals_non_head_revisions, ::test_every_table_seeded_in_each_fixture |
| G18 | Runtime schema fingerprint | runtime | M1a | P1 | shipped | warning on `doctor` and `/system`, ordinary tables only; never refuses (A9); tests/services/test_doctor.py::test_check_schema_fingerprint_is_ok_at_head, ::test_schema_fingerprint_mismatch_is_a_warning_not_an_error |
| G19 | DATA_DIR isolation | gate | M0 | P1 | changed | across the subprocess seam (B4) |
| G20 | TCC path and interpreter | gate/runtime | M0, M1d | P1 | planned | |
| G21 | Size caps | gate | M0 | P1 | changed | `C901` and `PLR0915` only (plan); the file-length test and `PLR0913` not adopted |
| G22 | Cross-platform | gate | M0, M1 | P1 | planned | |
| G23 | Hard-block hooks | hook | M0 | P1 | shipped | three hooks since 2026-09-14, a fourth (the log-first Stop hook G56) and a fifth (the log-first one-session-per-checkout hook G57, on PreToolUse and SessionEnd) since 2026-09-16: H1 `no_bypass_git`, H3 `enforcement_files_script_only`, and `read_before_touch` (log-first; N-16 amended); H2 `no_prod_db_writes` cut (command-text list-policing, A6); the two hard blocks fail closed on internal error |
| G24 | Hook wiring currency | gate | M0 | P1 | shipped | every registered command names an executable script (`tests/gates/test_hooks.py`); `tools/hooks_status.py` prints which scripts are not registered, because registration is a human edit; folded into the ledger's G23 row rather than a row of its own |
| G25 | `make check` summary | gate | M0 | P1 | planned | the pasted summary block is printed by the ratchet tool today; a structured summary artifact gets its own ledger row when built |
| G26 | PR-body gate | CI | M0 | P2 | planned | needs a GitHub remote (milestone MB defers GitHub); a ledger row when built |
| G27 | Changed-tests sticky comment | CI | M0 | P2 | planned | |
| G28 | Portability | CI | M0 | P1 | planned | external control: "last seen red" line in `GUARDS.md` |
| G29 | pre-commit hooks | commit | M0 | P1 | shipped | installed 2026-09-14 (`make hooks`); a pre-push stage runs `make check` |
| G30 | Guard reachability | gate | M1a | P1 | shipped | the required half of the positive-control split; tests/gates/test_invariants_planted.py::test_every_invariant_has_a_planter |
| G31 | Connection chokepoint (behavioral) | gate | M0 | P1 | planned | |
| G32 | No-bypass proof | gate | M1 | P2 | changed | dry-run fetches; zero-HTTP is for `doctor --no-network` and `config validate` (see CF-01) |
| G33 | Doc currency | gate | M0 | P1 | shipped | only the INDEX ↔ `docs/**` bidirectional check remains (plan); `KNOWN_ISSUES` node ids, `GUARDS` ↔ markers, data dictionary, count regex not gates |
| G41 | Guard firings ledger | CI | M0 | P2 | planned | |
| G42 | Weekly enforcement audit | CI | M0–M1 | P2 | planned | deferrable to M1 |
| G43 | Settings-drift check | CI | M0 | P2 | planned | deferrable to M1; agent token drops `administration`/`workflows` after M0 |
| G44 | Routing pointers resolve | gate | M1a | P1 | shipped | `tests/gates/test_routing_rows_resolve.py`; found two dangling pointers on its first run |
| G45 | Status-page contract | gate | M1a | P1 | shipped | `tests/gates/test_status_page.py`; stamp, cap, headings, no restated counts |
| G46 | No sleeping under pytest | gate | M1a | P2 | shipped | `tests/gates/test_no_sleep_under_pytest.py` (id assigned 2026-09-14) |
| G47 | Memory snapshot and one memory home | gate | M1a | P1 | shipped | `tools/memory_snapshot.py` check + diff in `make check`; `tests/gates/test_memory_snapshot.py` |
| G48 | No tracked daemon state | gate | M1a | P2 | shipped | `tests/gates/test_no_tracked_daemon_state.py` (KI-001; id assigned 2026-09-14) |
| G49 | Read before touch (third hook) | hook | M1a | P1 | shipped (registration pending Wes) | `tools/hooks/read_before_touch.sh`, log-first with a ledger; controls in `tests/gates/test_hooks.py` |
| G50 | Review register | gate | M1a | P1 | shipped | `tests/gates/test_review_register.py`; `docs/reference/reviews/REGISTER.md`; baseline 2026-09-15 |
| G57 | One live session per checkout (fifth hook) | hook | M1a | P1 | shipped (registration pending Wes) | `tools/hooks/one_session_per_checkout.sh`, log-first with a ledger and a lock in the checkout; controls in `tests/gates/test_hooks.py` |
| G37 | Weekly stress | CI | M1d | P3 | changed | 50k/500k corpus cut; the `EXPLAIN QUERY PLAN` assertions live in DB-08 |
| G38 | Mutation (informational) | CI | M3 | P3 | cut | optional tool, never a ratchet; no `.ratchets/mutation.txt` (plan) |
| G34 | Retired claims not stated as live | gate | M1a | P1 | shipped | the panel proposal formerly numbered G34 is now G41 |
| G35 | No imported identifiers in tracked text | gate | M1a | P1 | shipped | the panel proposal formerly numbered G35 is now G42 |
| G36 | Attribution trailers refused at commit time | hook | M1a | P1 | shipped | the panel proposal formerly numbered G36 is now G43 |
| G39 | Rules name an enforcer that exists | gate | M1a | P1 | shipped | resolves every backticked path, pytest marker, ruff code and `make` target in CLAUDE.md's rule table; a row with no resolving enforcer must say "review", capped by `.ratchets/review_only_rules.txt`; tests/gates/test_rules_name_their_enforcer.py::test_positive_control_an_enforcer_that_does_not_exist_is_red, ::test_positive_control_a_review_row_is_counted_not_failed |
| G40 | Register node ids resolve | gate | M1a | P1 | shipped | every node id in `KNOWN_ISSUES.md`'s regression-test column and `GUARDS.md`'s positive-control column must name a test that exists, resolved structurally with `ast`; tests/gates/test_known_issues_cite_collected_tests.py::test_positive_control_a_dangling_node_id_is_red, ::test_positive_control_a_second_control_from_the_same_file_resolves; since 2026-09-16 every row-shaped line of `KNOWN_ISSUES.md` must be one the parser returned, the format example inside its comment excepted (KI-034), ::test_positive_control_a_row_the_parser_cannot_see_is_red, ::test_positive_control_a_parsed_row_the_shape_misses_is_red, ::test_positive_control_a_second_row_on_one_line_is_red |

> **Id note (2026-09-14):** guard ids are assigned in `docs/runbook/GUARDS.md`, the register that owns them. Three enforcement-panel proposals in this table originally carried G34–G36 before the ledger gave those ids to gates that were built (retired claims, imported identifiers, trailer refusal); the proposals are now G41–G43 and keep their `planned` status.


Note (2026-09-13): the five rows above (G34, G35, G36, G39, G40) are the guard-ledger ids `GUARDS.md` assigned to gates discovered and built during the M1a tranche A build (retired claims, imported identifiers, attribution trailers, rule-enforcer names, register node ids). G34, G35 and G36 collide with this table's own three-panel-numbered rows above (`Guard firings ledger`, `Weekly enforcement audit`, `Settings-drift check`), which the build never touched and which remain `planned` under the enforcement panel's original G-nn sequence; this is a pre-existing numbering clash between the panel's spec and the guards ledger, not a claim that either of the colliding rows is the same gate. G39 and G40 do not collide (the panel's own sequence stopped at G38).

### 3.4 Web UI and delivery surface — `2026-09-13-panel-ui.md` §A (55); operator checklist §B; setup threat model §C

| ID | Name | Layer | Phase | Pri | Status | Reason if cut/changed |
|---|---|---|---|---|---|---|
| UI-01 | Every page route renders on seeded and empty DB | route | M2 | P0 | shipped | the first web slice, 2026-09-16: the routes are discovered by walking `app.routes` (a structural scan, never a typed list), each rendered against a seeded and an empty database, with one `h1` and no undefined value on the page; a route with a path parameter the scan cannot fill fails rather than being skipped. `tests/web/test_app.py::test_every_page_route_renders_on_a_seeded_database`, `::test_every_page_route_renders_on_an_empty_database` |
| UI-02 | Same URL: fragment vs page, with `Vary` | route | M2 | P0 | planned | no route serves a fragment yet: the first web slice has no `HX-Request` branch and htmx is not vendored, so there is nothing for `Vary: HX-Request` to vary on. Lands with the first list route that has a rows fragment (M2) |
| UI-03 | Query parameters never 500 | route | M2 | P1 | shipped | the first web slice, 2026-09-16: hypothesis over the paging cursor plus a table of unusable run ids (negative, textual, unicode digits, forty digits); an unusable value is a 422 and never a traceback, and a pk wider than a 64-bit column is refused before it reaches the query. `tests/web/test_app.py::test_query_parameters_never_500`, `::test_an_unusable_run_id_is_refused_rather_than_raised`, `::test_an_unknown_query_parameter_is_ignored` |
| UI-04 | 422 forms swap and flash OOB wired | template | M2 | P1 | planned | |
| UI-05 | Content safety headers and template scan (CSP) | template | M2 | P1 | changed | the headers half shipped with the first web slice, 2026-09-16: `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options` and `Referrer-Policy` on every response, the stylesheet, a 404 and a refused request included, with no script element and no off-origin asset on either page. `tests/web/test_app.py::test_every_response_carries_the_content_safety_headers`, `::test_the_pages_load_no_external_asset_and_run_no_inline_script` -- the template scan for `|safe` operands waits for the first template that renders stored content (M2); nothing in this slice renders any |
| UI-06 | Nested comments are DOM descendants at seeded depth | template | M2 | P0 | planned | |
| UI-07 | Depth cap 10, continue-thread swap and permalink | template | M2 | P0 | planned | |
| UI-08 | Load-more pages by top-level with whole subtrees | template | M2 | P1 | planned | |
| UI-09 | Comment sort top / new / old | route | M2 | P2 | planned | |
| UI-10 | Tombstones render honestly by `content_state` | template | M2 | P0 | planned | |
| UI-11 | Tombstones never listed on author pages, search, author filter | route | M2 | P0 | planned | |
| UI-12 | Bot items flagged and excluded from theme counts | template | M2 | P1 | changed | `author_is_bot` is a heuristic surfaced as "suspected bots" with one-click confirm; per author, never inherited by a megathread's comments |
| UI-13 | Coverage line, stubs, "as of", collect button | template | M2 | P0 | planned | |
| UI-14 | `[NEW]` badge derived from latest completed run | template | M2 | P1 | planned | |
| UI-15 | Deep-link href exactness per item kind | template | M2 | P0 | planned | |
| UI-16 | Markdown safety asserted on the rendered page | behavior | M1a/M2 | P0 | planned | |
| UI-17 | FTS snippet escaping incl. marker chars | behavior | M2 | P0 | planned | |
| UI-18 | Reflected params and cookie escaped | route | M2 | P1 | planned | |
| UI-19 | FTS mini-grammar sanitizer never raises | behavior | M1a/M2 | P0 | planned | |
| UI-20 | Search tabs, counts, grammar semantics | route | M2 | P1 | planned | |
| UI-21 | Cross-site POST rejected | middleware | M2 | P0 | changed | missing `Sec-Fetch-Site` (plain-HTTP LAN) falls back to `Origin`/`Referer` host vs allowed `Host`, instead of rejecting (adversarial D1) |
| UI-22 | Host check on every request | middleware | M2 | P0 | shipped | the first web slice, 2026-09-16: loopback names pass on any port (the attack is on the name, not the port), anything else is refused on a GET and the refusal never echoes the host it was given; the control serves the same request through the same inner application with the middleware taken away. `tests/web/test_app.py::test_a_foreign_host_header_is_refused_on_a_read`, `::test_a_loopback_host_is_served_on_any_port`, `::test_a_request_without_a_host_header_is_refused`, `::test_the_default_test_client_host_is_refused`, `::test_positive_control_without_the_host_check_a_foreign_host_is_served` |
| UI-23 | No GET route writes | behavior | M2 | P1 | planned | |
| UI-24 | Basic auth via env var | middleware | M2 | P1 | planned | |
| UI-25 | Web reads `mode=ro`; writes only via the repository | behavior | M2 | P0 | changed | `mode=ro` engine cut; the table-delta assertion against the writer map stays (= DB-52) |
| UI-26 | Run now: queued row before spawn, argv parity with launchd | behavior | M2 | P0 | planned | through the injectable `ProcessRunner`; the first web slice is read-only, so no route spawns anything (M2) |
| UI-27 | 409 while a run is active | behavior | M2 | P0 | planned | nothing can be started from a page yet, so there is no second start to refuse (M2) |
| UI-28 | Polling stops when idle | template | M2 | P0 | planned | no panel polls: the first web slice has no fragment route and no htmx (M2) |
| UI-29 | Stale-run detection | behavior | M2 | P0 | changed | one shared 3-minute key; flock held ⇒ alive; orphan `queued` rows > 2 min without pid → `failed` (B9); the Runs pages show the row a sweep leaves behind but do not sweep (M2) |
| UI-30 | Cancel | behavior | M2 | P1 | planned | `cancel_requested_at` polled at batch boundaries (UI D5); the column arrives with the curation migration and there is nothing to cancel from a read-only page (M2) |
| UI-31 | Error mapping and status banner derived from run row | template | M2 | P1 | changed | shipped for the Runs pages with the first web slice, 2026-09-16: the verdict is read off `runs.status` through one map, an unmapped status reads as a problem and never as green, a `partial` run names the warning that made it amber -- the invariant's, and since revision 0005 its own, from `runs.warnings_json` -- and counts the warnings a row written before that revision could not name, and a failed run shows its recorded error beside the invariant that failed. `tests/web/test_runs_page.py::test_a_partial_run_names_the_warning_that_made_it_amber`, `::test_a_run_names_the_warnings_it_recorded_itself`, `::test_a_run_from_before_0005_reports_the_warnings_it_cannot_name_as_a_number`, `::test_a_failed_run_shows_its_recorded_error_and_the_invariant_that_failed`, `::test_an_ok_run_shows_no_problems_at_all`, `::test_every_verdict_the_database_can_hold_has_a_word_for_it` -- two clauses of the panel's row are not built and are not claimed: the same banner on the feed, which has no page yet, and a traceback in a `<details>`, for which `runs` has no column -- the row's recorded error stands in its place (M2) |
| UI-32 | `/healthz` shape and pill parity | route | M2 | P1 | planned | |
| UI-33 | Add subreddit: validate is one request, errors mapped | behavior | M2 | P0 | planned | |
| UI-34 | Pause / resume, comment mode, remove-keep, re-add | behavior | M2 | P1 | planned | |
| UI-35 | Remove-and-delete behind the server-side gate | behavior | M2 | P0 | planned | `backups` table in rev 1 makes the gate live at M2; purge recorded on the run row; FTS via `_docsize` |
| UI-36 | Regex validation inside the rule row | route | M2 | P0 | planned | |
| UI-37 | Preview uses the CLI's matcher, shows denominators | behavior | M2 | P0 | planned | |
| UI-38 | Save re-tags preserving timestamps; stale badge | behavior | M2 | P0 | changed | re-tag always runs as the CLI subprocess with a run row (no inline path); the UI polls the run |
| UI-39 | Config YAML export/import round trip | behavior | M2 | P1 | planned | |
| UI-40 | Export zip integrity | behavior | M2 | P0 | changed | no raw sidecar (cut 2026-09-13), live-content JSONL only; exports older than 7 days are swept |
| UI-41 | Archive import behind gate; zip-slip and integrity refusals | behavior | M2 | P1 | planned | import from a server-side path |
| UI-42 | `/system` renders every doctor check; notification test | template | M2 | P0 | changed | the delivery record is best-effort, not a proof (A4); check-row assertions unchanged |
| UI-43 | Apply pending migration backs up first; maintenance mode | behavior | M2 | P0 | planned | |
| UI-44 | Backups page: create, stored verify, restore gate | behavior | M2 | P0 | planned | live at M2 (rev-1 `backups` table); `Confirmation` object |
| UI-45 | Maintenance actions spawn the right CLI with run rows | behavior | M2 | P1 | planned | |
| UI-46 | Setup wizard writes credentials safely, never echoes them | behavior | M2 | P0 | planned | loopback-only on the LAN unless password set: pending Wes |
| UI-47 | Test connection: one API request, mapped errors, live reload | behavior | M2 | P0 | planned | |
| UI-48 | Credential canary across the delivery surface | behavior | M2 | P0 | planned | |
| UI-49 | Deleted-text canary on the delivery surface | behavior | M2 | P0 | planned | |
| UI-50 | Operator-complete gate | gate | M2 | P0 | planned | exclusions `serve`, `probe`, `db init`, `db downgrade` with reasons |
| UI-51 | Accessibility basics on every page | template | M2 | P1 | shipped | the first web slice, 2026-09-16: one `h1`, the four landmarks, the skip link first in the DOM and pointing at something, every input labelled, `aria-expanded` only on a button, no `href="#"`, and an `aria-current` link, asserted over whatever the page contains rather than over the controls these two pages happen to have, so the same check keeps biting as the M2 pages land. `tests/web/test_app.py::test_every_page_keeps_the_accessibility_basics`, `::test_an_empty_page_keeps_the_accessibility_basics` |
| UI-52 | Playwright smoke flows | e2e | M2 | P2 | planned | local-only, never in CI |
| UI-53 | Appearance settings | route | M2 | P2 | planned | |
| UI-54 | Sidebar and theme counts carry denominators, shared with digest | template | M2 | P1 | planned | |
| UI-55 | Comment permalink page | route | M2 | P1 | planned | |
| UI-56 | digest_route_renders_the_assembled_model | route | M1a | P0 | shipped | the first web slice, 2026-09-16: `/reports/{date}` renders the model `services.report` assembles, ranked by `rank_posts` and headed by the window it covers; a section whose stage is not built shows its real denominator beside a sentence naming what was not collected; a post scrubbed after collection is in neither the list nor its denominator, which is the reason the digest is a route and never a file; a date with no finished run is a 404 naming the day and an unusable date a 422. `tests/web/test_report_page.py::test_the_page_renders_the_assembled_model`, `::test_the_top_posts_are_ranked_and_the_heading_names_its_window`, `::test_an_unstaged_section_shows_a_zero_against_a_real_denominator`, `::test_each_unbuilt_stage_says_what_was_not_collected`, `::test_a_post_scrubbed_after_collection_leaves_nothing_on_the_page`, `::test_a_date_with_no_finished_run_is_a_404_naming_the_day`, `::test_an_unusable_date_is_refused_rather_than_raised` |

Gaps the adversarial review named that have no spec ID yet (write them as tests when the stage lands): an **edited post** matrix row (B5; RC-02 covers the mechanism), the **deleted link post** probe and state row (B3; P-18 in the probe-day checklist, runbook § 9), **megathread** handling for bot exclusion (B10), and a route test for **`Popen` failure** leaving an orphan `queued` row (B9; UI-26 covers the launcher-raises path).

## 4. What ships first

**M0 shipped gate set** (plan, "M0 foundation tranche"; ledger rows in `runbook/GUARDS.md`): import-linter layering (G04, G05) · network block (G06) · schema snapshot (G15, DB-01) · models-vs-DDL (G16, DB-02, DB-03) · data-directory isolation in-process and across the subprocess seam (G19, DB-18, DB-19, CF-04) · pragma behavioral test (G31, DB-12) · upsert and PK stability (DB-20; GT-02 through `run` at M1a) · coverage and suppression ratchets with the three-way compare and loosening protocol (G11, G10, G08, G09, G13) · exception lint policy (G01) · `-W error` (G07) · pre-commit ruff and gitleaks (G29) · two hard-block hooks (G23, G24) · `make check` summary (G25). Positive controls, split per the adversarial review: post-run invariants through `run --gateway fake`; CI ratchets by a unit test of the compare function; external controls (branch protection, pre-commit, portability, hooks) by a dated "last seen red" line. If the two-day box overruns, G26, G35, G36 defer to M1.

**M1a invariant set** (proven through `threaddigest run --gateway fake` with a planted violation, GT-01/G30): compliance canary (SC-01, SC-02, DB-32) · counters-versus-deltas (DB-54) · structural population floors (DB-50, DB-51, NM-03a) · per-source freshness (FR-01). Severity decides: counters-versus-deltas and the no-other-running-rows check are failures; the floors and freshness are warnings, `partial`/amber, and no clock promotes them (the promotion question is pending Wes; plan § Silent-failure controls). Also wired at M1a without flipping status: PK stability (GT-02), FTS membership via `_docsize` (DB-26), normalizer-version stamping (DB-48), reconcile-age per tier (RC-06, from M1c).

## 5. Guard design rules (plan § Robustness; source `WHY_THE_GUARDS_EXIST.md`)

1. Scan a structural shape, never police a hand-maintained list (ratchets count what a tool finds in the whole tree).
2. Key on the invariant, not a proxy (query the real thing through the connection path the app uses; `count(*) FROM posts_fts` was the proxy that could never go red).
3. A gate that cannot fail is not a gate: construct the bad state and assert red — required for post-run invariants, a compare-function unit test for ratchets, a "last seen red" line for external controls.
4. Structural markers, not comment proximity: justifications live in syntax.
5. Assert on the delivery surface; a field with two guards is single-sourced.
6. Fail, never skip, inside the required gate; the only skips are the opt-in live tests, which are deselected, not skipped.
7. Zero-suppression baseline; every exception is printed on every run.
8. Hold the count: a new guard only for a recurring class, after checking whether an existing one can be widened; `GUARDS.md` records birth, control, and derived firings; reviewed quarterly.
9. Derive state, never narrate it (Runs page, digest, `make check` summary, "catches since" all come from tool output).
10. Show the denominator: every count carries its population; one metric function shared by UI, digest, export.
11. Probe each item the way a real record presents it: fixtures come through `probe`, tombstones through the real scrub stage (M1c), bot rows through `normalize_post()` and `normalize_comment()`.

## 6. Owner questions still open (deduplicated across the five panels and the plan; recommendations in parentheses; questions the plan already answered are omitted)

Enforcement and GitHub (enforcement §G, adversarial A2/E1/E8):
1. GitHub plan: does it allow branch protection, rulesets, and environment reviewers on a private repo (Free does not)? Agent token: full during M0, then a fine-grained PAT without `administration` and `workflows`? (Yes to both.)
2. Loosening approval: one-click environment approval, or visibility-only (auto-issue) when the plan lacks reviewers? Perimeter width: `.ratchets/*` and GitHub settings only, or also `tests/gates/**`, `tests/conftest.py`, `tools/ratchet.py`, `.claude/settings.json`?
3. Pre-push: full `make check` or the ~30 s fast subset (ruff, dmypy, ratchet measure, `tests/gates`)? (Fast subset; CI is required anyway.)
4. Git authorship: an `Agent:` trailer or a second identity so audits can tell agent from human commits?
5. CI minutes: accept `py314` on `main` pushes only and macOS weekly, or upgrade to Pro (3,000 min)? Notification channel for scheduled-job failures and the weekly audit: GitHub issues assigned to Wes (recommended) or email?
6. Zero-context second review for deletion/scrub/migration/`repo.py` PRs: `CLAUDE.md` practice, PR-body section check, or drop? Quarterly thresholds (four UNPROVEN quarters, 5 s runtime) as proposed?
7. Confirm live credentials never enter GitHub secrets, so the PRAW-bump live smoke stays a manual step on the Mac.
8. G12: keep the assert-count floor under the loosening protocol while the collected-test floor is cut, as the plan's two statements imply?

Compliance and data (DB §F, ingest §E, adversarial B1/D3/E18, plan open items 2–4):
9. Confirm the compliance bounds as re-derived under D-30: no backup older than 14 d (the sweep unbuilt until M1c, plan § Release), no export older than 7 d, per-tier reconcile ages 120 h / 8 d / 35 d (KI-026), and a purge window for items under 30 days of up to two scheduled gaps plus the run after (about seven to eight days at Monday/Thursday), because an `info()` absence needs two omissions before the scrub (`core/deletion.py`).
10. Per-run JSONL sidecar: **cut, decided 2026-09-13.** JS-01/02 and DB-34/35 are cut; the JSONL clauses in DB-31, DB-54, SC-01, RL-07, GT-01 are dropped.
11. Purge semantics for "stop and delete captured data": hard delete with a recorded purge run (recommended) or mark-and-hide? Decides DB-55.
12. Scrub latency for items confirmed only by `info()` absence: decided 2026-09-16, reconcile re-checks first misses at the end of the same run (RC-03), so the window is one scheduled gap plus the run after.
13. Unknown `removed_by_category` with a `[removed]` body: which removed state, and may `removed_by_reddit` return to live on an intact payload? (Every `removed_*` may return; only `deleted_by_author` is terminal.)
14. Reprocess boundary: may `reprocess` change `next_check_at`/`check_stage`, or are they owned by the ladder only? (Ladder only.)
15. Automated weekly restore drill via launchd into a temp dir, recorded in `backups`? (Yes.) Fixture DBs kept under 1 MB by design rather than exempting the path? (Yes.)
16. Commercial-use stance: settled on 2026-09-15 by D-32, all use is personal and non-commercial.

Collector (ingest §E):
17. Exit codes 0 ok / 1 failed / 3 partial / 4 rate-limited / 75 locked / 78 config / 130 cancelled, with `partial` a digest line rather than a notification? Does `--dry-run` write a `runs` row (adversarial D12 says no)?
18. Per-post expansion cap: per fetch for huge threads (recommended) or cumulative across revisits? Budget scope: do token refreshes count? (Count every HTTP response.)
19. Zero-new threshold: K = 3 consecutive runs per subreddit; is r/editors exempt on weekends?
20. `--gateway fake` refused against the default data dir, or require an explicit `--data-dir`? (Refuse.) Cancel latency: stop at the next request boundary and roll back the in-flight tree? (Yes.)

UI and LAN (UI §E, adversarial B11):
21. On the LAN without a password, do `/setup` POST and the destructive gates require a loopback client or `THREADDIGEST_UI_PASSWORD`? (Loopback-only unless the password is set; threat model "operator error" recorded in `DECISIONS.md`.)
22. Allowed-Host list: from `THREADDIGEST_ALLOWED_HOSTS` or derived from the bind address? Add **Regenerate digest** and **Download config** buttons so the operator-complete gate has nothing to exclude beyond the four commands?

Fixtures and probes (ingest §E, DB §F, plan "Things only Wes can do"):
23. Create the personal restricted test subreddit (account-age rules permitting); P-01, P-02, P-04–P-06, P-09–P-12 and every cassette depend on it. Is probing public examples acceptable for Reddit-removed posts (P-03) and account-deleted authors (P-13), given the saved payload is already `[removed]` or body-blanked?
24. Fixture scrubbing: decided and built 2026-09-16. `core.fixture_scrub` replaces every author name and account id on save, and the identifier gate refuses any fixture outside the hand-written synthetic set, or any cassette, that still carries a real one; the probe saves what the scrub returns, never the wire payload.
25. Cassette directory: `tests/adapters/cassettes/`, excluded from the review packet by prefix like the fixtures, so recorded Reddit content never reaches an external reviewer, at the cost that the adapter suite is not runnable from a packet; decided on 2026-09-16 as the working default, say if you want the reverse.
26. Live-suite escape: built 2026-09-16. The live suite's conftest keeps the three `THREADDIGEST_REDDIT_*` variables the root fixture otherwise strips, and `make test-live` loads `.env`, selects the marker, and lifts the network block for Reddit's hosts only.
27. Can the earlier project's issue register, database integrity reference, breakage-pattern catalogue, and update-semantics note be shared? They would settle purge semantics and the field-ownership sets from precedent.

Deferred to a milestone, not to Wes: fetch trees via `reddit.request()` and delete the second wire shape, the parity test, and the ownership table (decide at M1b after the probes); Docker CI matrix at M4; trailing-median alarms at M3.

## Added 2026-09-13 (late): workspace lifecycle and curation controls (M2, schema revision 2)

Specs written before code, per the layered policy. Revision 2 is the first migration to exercise the per-revision fixture path (DB-44/45): the fixture for revision 1 must be generated from pre-change code before the migration is written.

| ID | Test name | Layer | Given | When | Then | Positive control | Phase | Pri |
|---|---|---|---|---|---|---|---|---|
| WS-01 | rev2_migration_adds_columns_with_fixture | migration | revision-1 fixture DB with two workspaces sharing r/premiere | `db upgrade` | `workspaces.archived_at`, `post_themes.origin` (default `rule`), `posts.watch_until` exist; every prior row keeps pk; FTS docsize == live; golden `schema.sql` updated in the same PR | fixture missing for rev 1 → DB-45 red; NOT NULL without backfill → DB-44 red | M2 | H |
| WS-02 | archive_workspace_keeps_data_stops_polling | e2e (fake) | workspace B with one exclusive subreddit and 30 posts | archive B; run | B absent from switcher/digest; its sources not fetched (zero gateway calls for them); all 30 posts and comments still present; compliance reconcile still checks them | archive deletes rows → red; a fetch call for B's sub → red | M2 | H |
| WS-03 | delete_workspace_only_removes_exclusive_data | e2e | A and B both monitor r/premiere; B alone monitors r/editors; a post in r/premiere reached via both | delete B through the gate | r/editors posts and comments gone (FTS via triggers), r/premiere posts kept with A's source rows; B's themes and tags gone; purge counts on the run row; row-count invariant green | deleting the shared post → red; invariant red when purge unrecorded | M2 | H |
| WS-04 | delete_workspace_requires_gate_and_offers_export | route | no verified backup / stale backup / fresh backup | POST delete without word, with word, with both | 422 / refused naming the gate / proceeds; export link shown before confirmation; nothing deleted on refusal (table checksums equal) | gate bypassed by disabling the button → direct POST proves red | M2 | H |
| WS-05 | move_source_between_workspaces | e2e | subreddit in B | move to A | source row re-pointed; captured posts untouched; per-workspace unique honored (moving into a workspace that already has it → 409) | duplicate allowed → red | M2 | M |
| WS-06 | workspace_switcher_scopes_every_page | route | two workspaces with distinct themes | switch and crawl feed, themes, digest, settings, export | no row from the other workspace appears; export manifest names the workspace | a query missing the scope → red | M2 | H |
| CU-01 | manual_tag_survives_retag | e2e | post tagged manually with theme T; rules of T changed so the post no longer matches | re-tag | manual row (`origin=manual`) kept; rule rows recomputed; UI shows the manual badge | retag deletes manual rows → red | M2 | H |
| CU-02 | manual_untag_overrides_rule | e2e | rule-tagged post; user removes the tag | re-tag | a manual exclusion (`origin=manual_removed`) prevents the rule from re-adding it | rule re-adds → red | M2 | H |
| CU-03 | watched_thread_stays_on_ladder | e2e (fake, clock) | post older than 30 d with `watch_until` in the future | run at +60 d | tree refetched; `next_check_at` advanced within the watch window; after `watch_until` passes, normal tiers resume | ladder ignores watch → red | M2 | H |
| CU-04 | promote_rising_phrase_to_rule | route | digest shows phrase "export hangs" | click promote | theme editor opens with a whole-word keyword rule pre-filled; preview shows "N of M posts" using the same matcher as the CLI; nothing saved until Save | promotion saving silently → red | M2 | M |
| CU-05 | theme_rename_and_merge | e2e | themes T1, T2 with tags | rename T1; merge T2 into T1 | slug updated and old slug 301-redirects; T2's `post_themes` re-pointed without duplicates; manual tags preserved; merge recorded on the run row | duplicates after merge → red | M2 | M |
| CU-06 | adhoc_search_reddit_actions | route (fake gateway) | search box query | submit; click "monitor" on a subreddit; click "collect" on a thread | exactly one API search request; monitor adds the source (validated, one request); collect spawns the CLI for that post with a queued run row; zero API calls on page render | search on GET → red; two requests per click → red | M2 | M |
| CU-07 | tag_feedback_is_operator_signal_not_precision | route | tags on posts | thumbs up/down | feedback row stored; theme page shows "operator feedback: k of n judged"; digest carries it; the two views use one metric function; no string rendered from the feedback table in UI, digest, or export contains "precision" (corrected 2026-09-13: anchored feedback is an operating signal, never the grade; precision comes from the M3 blind packet) | a template rendering "precision" from feedback rows → red | M2 | M |
| CU-08 | curation_controls_are_operator_complete | gate | typer command tree and routes | run the operator-complete gate | archive/delete/move workspace, manual tag, watch, promote, rename/merge, ad-hoc search each have a marked UI test | new command without a marked test → red | M2 | H |
| CU-09 | manual_tags_and_watches_scrub_with_the_item | e2e | watched, manually tagged post deleted on Reddit | reconcile | tags removed, watch cleared, tombstone rendered; canary absent everywhere | manual tag survives scrub → red | M2 | H |
| CU-10 | export_import_round_trips_curation | e2e | manual tags, watches, feedback | export then import on a fresh data dir | all curation rows restored with origins intact | origins reset to `rule` → red | M2 | M |

Failure-matrix additions (plan): deleting a workspace must never remove data another workspace still reaches; re-tagging must never remove a manual tag; a watched thread must never fall off the ladder while its watch is active.
