# Load-bearing claims (machine-read by `tests/gates/test_known_issues_cite_collected_tests.py`)

> The claims the project stakes its correctness on, each with the test that backs it. This is
> where the authors believe the risk is; it is not the scope of a review, and a finding outside
> this list is worth more than one inside it. A review packet carries this file so an outside
> reviewer can try to falsify each claim and judge whether the cited test asserts what the claim
> says. The citation gate checks only that every node id in the "Backed by" column exists in the
> collected suite; whether the test asserts the claim is the reviewer's judgement, not the
> gate's. A claim about a milestone not yet built says so and cites nothing; it moves up when
> its test lands. Each node id is a test function whose source is in the tests or harness part;
> read the test before judging the claim, because the gate does not.

## Built and backed

| # | Claim | Backed by (node id) | Where it lives |
|---|---|---|---|
| C-01 | Every run has a request budget; `--budget` is clamped to the hard cap, and the one stage-skipping flag (`--no-comments`) records a written reason on the run row rather than silently disabling anything | `tests/gates/test_no_bypass.py::test_budget_is_clamped_to_the_hard_cap`, `::test_no_comments_requires_a_reason_and_records_it` | `core/budget.py`, `services/collect.py` |
| C-02 | Reruns never change a primary key or `first_seen_at`; upserts are `INSERT … ON CONFLICT DO UPDATE`, never `INSERT OR REPLACE` | `tests/gates/test_pk_stability.py::test_three_reruns_keep_pk_and_first_seen_at`, `tests/db/test_alembic.py::test_on_conflict_upsert_preserves_pk_and_first_seen_at`, `::test_insert_or_replace_burns_the_pk_and_detaches_fts` | `db/repo.py` |
| C-03 | A run's counters equal the table deltas it caused; a planted extra row fails the run | `tests/gates/test_counters_deltas.py::test_counters_equal_table_deltas_on_a_clean_run`, `::test_planted_extra_row_fails_the_run` | `services/invariants.py` |
| C-04 | Every post-run invariant has a planter, a planted violation flips the run, and an invariant that crashes fails the run rather than leaving it running | `tests/gates/test_invariants_planted.py::test_planted_violation_flips_the_run`, `::test_every_invariant_has_a_planter`, `::test_a_crashing_invariant_fails_the_run_rather_than_leaving_it_running` | `services/invariants.py` |
| C-05 | A dry run writes no row to any table and no run row (it may create the data directories and the read-only engine's sidecar files) | `tests/gates/test_no_bypass.py::test_dry_run_writes_nothing_anywhere`, `tests/e2e/test_run_dry_run.py::test_a_dry_run_whose_source_is_forbidden_exits_3_and_writes_nothing` | `services/collect.py` |
| C-06 | A full run changes no file under the repository root outside the resolved data directory (the test snapshots the repository, not the home directory or the system temp folder) | `tests/e2e/test_data_dir_writes.py::test_a_full_run_changes_no_file_outside_the_data_dir`, `::test_control_a_write_into_a_data_directory_is_detected` | `settings.py`, `services/` |
| C-07 | Tests and the fake gateway never touch the default data directory or a database holding real runs | `tests/gates/test_data_dir_isolation.py::test_refuses_default_data_dir_while_pytest_is_loaded`, `::test_child_process_under_pytest_current_test_refuses`, `tests/gates/test_no_bypass.py::test_fake_gateway_refused_against_the_default_data_dir`, `::test_fake_gateway_refused_against_a_database_holding_real_runs` | `settings.py`, `cli.py` |
| C-08 | A crash between pages loses at most the page in flight; earlier pages are committed and a rerun completes with zero duplicates | `tests/e2e/test_run_happy_path.py::test_crash_between_pages_commits_earlier_pages_and_rerun_completes`, `::test_rerun_after_a_clean_run_reports_zero_new_items` | `services/sweep.py` |
| C-09 | In-process socket use is blocked under pytest (a subprocess a test spawns is outside the block) and warnings are errors | `tests/gates/test_pytest_config.py::test_socket_connect_raises_under_block_network`, `::test_warnings_are_errors_inside_tests` | `pyproject.toml` |
| C-10 | Four layers only, and the Reddit client library is imported only by the real adapter | `tests/gates/test_layering.py::test_layering_contracts_hold`, `::test_gate_goes_red_when_a_contract_is_violated` | `.importlinter` |
| C-11 | Every committed prior-revision fixture database upgrades cleanly to the schema head, and the model definitions equal the DDL | `tests/db/test_alembic.py::test_revision_fixture_upgrades_clean`, `::test_fixture_set_equals_non_head_revisions` | `db/migrations/`, `db/schema.sql` |
| C-12 | Deletion markers are terminal from any prior state, and a scrub followed by `optimize` leaves no term bytes in the index or the file | `tests/unit/test_deletion.py::test_deleted_markers_are_terminal_from_any_prior`, `::test_scrub_states_exclude_holds_and_live`, `tests/db/test_fts.py::test_scrub_removes_the_entry`, `::test_scrub_then_optimize_leaves_no_term_bytes_in_the_index_or_the_file` | `core/deletion.py`, `db/fts.py` |
| C-13 | The hard-block hooks fail closed on malformed input and refuse a commit message carrying an attribution trailer | `tests/gates/test_hooks.py::test_hooks_fail_closed_on_malformed_input`, `::test_positive_control_a_trailer_in_a_message_file_is_red` | `tools/hooks/` |
| C-14 | A ratchet floor moves against its direction only through the loosening path, which lands a ledger row; a relaxation past its date is red | `tests/gates/test_ratchet.py::test_compare_exits_3_when_a_floor_moved_against_direction_vs_main`, `::test_loosen_writes_the_value_and_a_ledger_row`, `::test_compare_is_red_the_day_after_a_hard_after_date` | `tools/ratchet.py`, `.ratchets/` |
| C-15 | Maintainability is measured by analysis, its ceilings only go down, and a missing report is red rather than zero | `tests/gates/test_code_health.py::test_planted_offenders_are_counted_and_named`, `::test_a_missing_analyzer_is_red_not_zero` | `tools/code_health.py` |
| C-16 | An external review packet is built from the committed tree only, excludes secrets, data, and the earlier project's material, and refuses a dirty working tree unless told otherwise | `tests/gates/test_review_packet.py::test_a_packet_holds_only_the_allowlist_from_head`, `::test_a_dirty_tree_is_refused` | `tools/review_packet.py` |

## Planned, not yet backed

| # | Claim | Milestone |
|---|---|---|
| P-01 | Reconcile honours a deletion end to end: after the compliance canary phrase is deleted upstream, the row store, the search index, and a fresh export are clean | M1c |
| P-02 | Comment trees drain newest-first within the budget, one transaction per tree, with `more` accounting that matches the wire | M1b |
| P-03 | The digest ranks by distinct authors with the identity coverage printed beside the list, never by display name | M1d |
| P-04 | The web UI writes only through the repository limited to the writer map; fetching is always the CLI in a subprocess | M2 |
