# Test strategy — v1 (2026-09-13)

> A router, not a copy. Every spec below is specified in full (given/when/then, fixture, positive control) in one of the five raw panel reports under `docs/reference/reviews/2026-09-13-*.md`; the plan's `Testing strategy` and `Robustness` sections are canonical for policy. This file lists what exists, where it lives, its layer, phase, priority, and whether the adversarial review or the plan's "Adversarial review: what changed" section cut or altered it. Status vocabulary: `planned` (as specified by the panel), `changed` (kept with the alteration in the last column), `cut` (not built; reason given). Flip `planned` to `shipped` with the node id as tests land. Priority vocabularies are the panels' own: DB and ingest H/M/L; enforcement P1 (M0) / P2 (M1) / P3 (optional); UI P0 (blocks M2 operator-complete) / P1 / P2.

## 1. Policy

Testing is layered, and the layer decides the approach: `core/` is strict TDD (every failure-matrix row is a failing test before the service exists); `services/` is TDD against `FakeRedditGateway` plus a temp DB created by `alembic upgrade head`; the PRAW adapter is probe-first (Reddit's behavior is captured with `probe --save-fixture`, never assumed, and the fixture drives both the cassette and the fake through one schema); migrations are test-first with a per-revision fixture DB and the `schema.sql` golden; web routes are test-with, the DOM assertion written alongside the template. Nothing in the suite touches the network (`--block-network`, extended across the subprocess seam), sleeps (injected `Clock`), or mocks internals (`mock.patch` banned outside `tests/adapters/`); tests run only against a temp data dir. Guards obey the design rules in § 5: shape over list, invariant over proxy, a constructed bad state for every post-run invariant, fail never skip, zero-suppression baseline, hold the count. The shipped gate set starts small (§ 4) and grows only on recurrence; the panels' full tables are the menu.

## 2. Kinds of tests and sweeps

| Kind | What it proves | Tools / where | Source |
|---|---|---|---|
| Unit (`core/`) | normalize, deletion state table, paging/stop/gap, ladder, budget, theme rules incl. regex timeout, digest golden, UA | pytest, hypothesis with stated properties (NM-01) | ingest §B.9, B.12; DB §A1 |
| Service / e2e against the fake | whole `run` and each stage through `CliRunner` with the scenario-builder fake (`add_post`, `delete`, `remove`, `vanish`, `fail_page`, `rate_limit_next`, …; unconsumed injections fail the test) and a temp DB | `FakeRedditGateway`, `FakeClock`, `FakeRawSink`, `FakeNotifier`, `tmp_path` | ingest §A, §B |
| Adapter: cassette + `responses` + contract | happy paths from recorded cassettes (test subreddit only, `--record-mode=none`); failure paths with exact request counts; the same cases against fake and PRAW so the fake stays honest | pytest-recording, `responses`, one fixture schema | ingest §B.14, §C probes P-01…17 |
| Migration with per-revision fixtures | `schema.sql` golden, models == DDL, single head, up/down; every prior revision's fixture DB upgrades clean with FTS (`_docsize`) == live, canaries checked | pytest-alembic, `tests/fixtures/db/<rev>.sqlite` + manifest, generated from pre-change code | DB §A1, §A8, §B, §C |
| Gate positive controls | each CI gate/ratchet made red from a constructed bad state in `tmp_path`, asserting the tool's own message; config-borne gates proven by running pytest as CI runs it | `tests/gates/`, `@pytest.mark.gate("<ID>")` | enforcement §B; adversarial A3 split |
| Workflow tests spanning stages and operator flows | one fake corpus through sweep → trees → revisit → reconcile → tag → digest → backup; setup → first sweep; theme edit → retag; backup → restore drill; pending migration → apply; export → import on a fresh data dir; end state, counters, delivered artifacts | pytest, fake, temp data dir | plan § Testing "Workflow"; UI §B checklist |
| Web route / DOM / middleware | every route on seeded and empty DB, fragment vs page, tombstones, deep links, sanitizer, CSRF and Host, Run now, gates, export, setup wizard, operator-complete gate | FastAPI TestClient + selectolax, hypothesis for query params | UI §A |
| Scheduled production sweeps | post-run invariants after every run (§ 4); per-source freshness; every 2 days the compliance reconcile; weekly: `EXPLAIN QUERY PLAN` assertions (the stress corpus is cut), portability job, restore drill into a temp dir (automation pending Wes); quarterly guard review. Dead-man = Healthchecks.io ping from M1d; notifications best-effort, the UI pill is canonical | launchd + CI schedules; `RUNBOOK.md` § 5–6 | plan § Sweeps; adversarial A4/A5 |
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
| DB-06 | next_check_at_not_null_enforced | db | M1a | H | planned | |
| DB-07 | derived_enums_closed_upstream_enums_open | db | M1a | H | planned | |
| DB-08 | hot_queries_use_declared_indexes | db | M1a | M | planned | the four `EXPLAIN QUERY PLAN` assertions the plan keeps in place of the stress corpus |
| DB-09 | every_column_has_a_comment | unit | M0 | M | planned | |
| DB-10 | fts_definition_shape (live views, `_docsize`) | db | M1a | H | planned | |
| DB-11 | create_engine_only_in_db_engine | gate | M0 | H | changed | symbol ban is ruff `TID251` (`create_engine`, `text(`, `sqlite3.connect`); import-linter confines modules only |
| DB-12 | pragmas_effective_on_public_write_connection | db | M0 | H | planned | |
| DB-13 | foreign_keys_enforced_behaviorally | db | M1a | H | planned | |
| DB-14 | busy_timeout_waits_then_fails_cleanly | db | M1a | M | planned | |
| DB-15 | secure_delete_leaves_no_canary_bytes | db | M1c | H | planned | |
| DB-16 | read_only_paths_cannot_write | db/web | M2 | H | changed | web `mode=ro` read session cut (one rw engine behind the writer-map repository, DB-52); Datasette `mode=ro` launcher assertion kept |
| DB-17 | wal_truncated_at_end_of_run | e2e | M1a | L | planned | |
| DB-18 | settings_refuse_default_data_dir_under_pytest | unit/gate | M0 | H | planned | |
| DB-19 | only_data_dir_is_writable_during_tests | gate/e2e | M0/M1a | H | planned | |
| DB-20 | pk_stability_across_reruns | e2e | M1a | H | changed | `AUTOINCREMENT` on posts/comments; `max(pk)==count(*)` only in this no-purge scenario, never at runtime (adversarial A10) |
| DB-21 | field_ownership_per_ingest_path | db | M1a | H | planned | may be deleted with the second wire shape if trees are fetched via `reddit.request()` (decide M1b) |
| DB-22 | upsert_never_resurrects_terminal_content | db+e2e | M1c | H | planned | |
| DB-23 | moderator_removed_returns_to_live_reindexes | db | M1c | M | planned | |
| DB-24 | orphan_parent_comment_without_fk | db | M1b | M | planned | |
| DB-25 | unknown_enum_values_stored_raw_and_counted | e2e | M1a | H | planned | |
| DB-26 | fts_membership_equals_live_via_run (`_docsize`) | gate/e2e | M1a | H | planned | |
| DB-27 | fts_insert_gated_on_live | db | M1a | H | planned | |
| DB-28 | fts_scrub_removes_entry_and_snippets | db | M1c | H | planned | |
| DB-29 | fts_author_scrub_reindexes_without_author | db | M1c | H | planned | |
| DB-30 | fts_rebuild_indexes_live_only_and_integrity_check_passes | migration/db | M1a | H | planned | |
| DB-31 | scrub_touches_four_surfaces_in_one_call | e2e | M1c | H | changed | the JSONL surface is gone (sidecar cut 2026-09-13); canary also in a title |
| DB-32 | compliance_canary_absent_everywhere_incl_backup | e2e/gate | M1c | H | changed | also asserts no backup older than 14 d and no export older than 7 d (adversarial B1); title canary (B3) |
| DB-33 | scrubbed_rows_have_no_content_columns | gate | M1c | H | planned | |
| DB-34 | compressed_jsonl_verified_before_plain_deleted | unit/e2e | M1c | M | cut | per-run JSONL sidecar cut 2026-09-13 |
| DB-35 | partial_trailing_jsonl_line_tolerated_db_authoritative | unit | M1c | M | cut | per-run JSONL sidecar cut 2026-09-13 |
| DB-36 | daily_vacuum_into_backup_recorded_and_verified | e2e | M1c | H | planned | |
| DB-37 | pre_migrate_backup_order_and_post_checks | migration/e2e | M1a | H | planned | |
| DB-38 | transaction_per_migration_no_half_state | migration | M1a | H | planned | |
| DB-39 | destructive_ops_require_recent_verified_backup | gate/e2e | M1c/M2 | H | changed | gate takes a `Confirmation` value object (UI phrase or CLI flag) checked inside the service; `backups` table ships in rev 1 so the UI gate is live at M2 |
| DB-40 | restore_is_atomic_under_lock | e2e | M2 | H | planned | |
| DB-41 | online_backup_consistent_under_concurrent_writes | db | M1c | M | planned | |
| DB-42 | import_export_roundtrip_preserves_and_refuses | e2e | M2 | M | planned | |
| DB-43 | runtime_fingerprint_agreement | e2e/gate | M0 | H | changed | mismatch is a warning on `doctor` and `/system`, ordinary tables only, never exit 78 (adversarial A9); stamping assertions kept |
| DB-44 | fixture_db_per_revision_upgrades_clean | migration | M1a→ | H | planned | |
| DB-45 | fixture_set_equals_revision_set_and_every_table_seeded | gate | M1a | H | planned | |
| DB-46 | downgrade_one_and_back_preserves_data | migration | M1a | M | planned | |
| DB-47 | reprocess_from_raw_json_byte_identical | e2e | M1a | H | planned | |
| DB-48 | rows_written_this_run_carry_current_normalizer_version | gate | M1a | H | planned | adversarial A15 would fold it into DB-47; the plan did not adopt that |
| DB-49 | settings_fingerprint_changes_only_on_non_secret_change | e2e | M1d | M | planned | |
| DB-50 | population_floors_fail_the_run_and_name_the_column | gate/e2e | M1a | H | changed | structural floors only: 100% on live rows with `author_state=known` (A11, ingest D-13), not 95% over all rows; amber not `failed` for the first 60 days |
| DB-51 | floors_scoped_by_normalizer_version_and_empty_population_fails | gate | M1a/M1c | H | planned | |
| DB-52 | web_writer_map_enforced | gate/web | M2 | H | planned | |
| DB-53 | authors_counters_match_count | gate | M1c | M | planned | |
| DB-54 | counters_equal_table_deltas | gate | M1a | H | changed | the `raw_files.item_count` clause is dropped (sidecar cut 2026-09-13) |
| DB-55 | row_counts_never_decrease_without_recorded_purge | gate | M1c/M2 | M | planned | |

### 3.2 Ingest and collector — `2026-09-13-panel-ingest.md` §B (60); probes §C P-01…17

| ID | Name | Layer | Phase | Pri | Status | Reason if cut/changed |
|---|---|---|---|---|---|---|
| SW-01 | sweep_full_window_forward_after_only | unit+service | M1a | H | planned | |
| SW-02 | sweep_cap_sets_gap_stickies_excluded | unit+service | M1a | H | planned | |
| SW-03 | sweep_overlapping_pages_dedupe | service | M1a | H | planned | |
| SW-04 | sweep_crash_between_pages_one_txn_per_page | e2e | M1a | H | planned | |
| SW-05 | field_ownership_per_ingest_path | unit+service | M1a | H | planned | see DB-21 (M1b decision on the second wire shape) |
| SW-06 | sweep_removal_signal_confirmed_via_info | service | M1a/M1c | H | planned | |
| SW-07 | sweep_empty_or_zero_new_ok | service | M1a | M | planned | its zero-yield counter is the per-source zero-new detection kept in place of the anchor |
| SS-01 | sub_forbidden_others_continue | service | M1a | H | planned | |
| SS-02 | sub_not_found_banned_policy | service | M1c | M | planned | P-16 fixture may be unresolvable |
| SS-03 | sub_redirect_auto_disabled_after_n | service | M1a | M | planned | |
| SS-04 | sub_quarantined_disabled_with_alert | service+adapter | M1a | M | planned | |
| SS-05 | sub_identity_casing_merges_t5_change_aborts | service+CLI | M1a | H | planned | |
| SS-06 | sub_recovery_clears_error_state_after_complete_sweep | service | M1a | M | planned | |
| TE-01 | transient_page_error_outer_retry_backoff | service | M1a | H | planned | |
| TE-02 | rate_limited_and_fatal_gateway_errors | service | M1a | H | planned | |
| TR-01 | tree_skip_when_num_comments_zero | service | M1b | H | planned | |
| TR-02 | tree_more_accounting_and_per_post_cap | service | M1b | H | planned | cap is per fetch (ingest D-3), pending Wes |
| TR-03 | tree_crash_mid_tree_nothing_committed | e2e | M1b | H | planned | |
| TR-04 | tree_budget_reserve_newest_first | service | M1b | H | planned | |
| TR-05 | tree_missing_known_comments_checked_via_info | service | M1c | H | planned | |
| RV-01 | ladder_pure_never_null | unit+hypothesis | M1a | H | changed | ladder gains a 365-day stage; `next_check_at` is never a far-future sentinel |
| RV-02 | ladder_advances_on_complete_refetch_skew_safe | service | M1c | H | planned | clock-skew claim scoped per ingest D-2 |
| RC-01 | deletion_state_table_fail_closed | unit | M1a | H | changed | predicate keys on `removed_by_category='deleted'` first; `author is None` on a link post = deletion pending `info()`; predicates unlocked until probes land (incl. a deleted link post) |
| RC-02 | reconcile_batches_100_match_by_fullname | service | M1c | H | planned | reconcile upserts the full normalized row (edits are an event) |
| RC-03 | reconcile_misses_scrub_second_transient_resets | service | M1c | H | planned | same-run re-check of first misses (D-9) pending Wes |
| RC-04 | author_deletion_terminal_mod_removal_returns | service | M1c | H | planned | |
| RC-05 | account_deletion_scrubs_author_only | service | M1c | H | planned | |
| RC-06 | reconcile_cadence_invariant_and_tier_fallback | service+digest | M1c/M3 | M | changed | invariant is per tier: 60 h ≤ 30 d, 8 d to 1 y, 35 d beyond (replaces 48 h + 12 h grace) |
| SC-01 | scrub_is_one_function_all_surfaces | service | M1c | H | changed | JSONL surface gone (sidecar cut 2026-09-13); canary in a title too |
| SC-02 | compliance_canary_end_to_end | e2e | M1c | H | changed | scans `data/**`; digest is a route (no file); asserts backup/export file ages (B1) |
| FR-01 | per_source_freshness_degraded | e2e | M1a | H | planned | `partial`/amber, not `failed`, for the first 60 days; also iterates disabled-by-error sources (B8) |
| FR-02 | freshness_anchor_uniform_staleness | e2e | M1a | H | cut | anchor cut (adversarial A8: sweep and anchor are the same call); `new_head()` port and `set_live_anchor` go with it; SW-07 zero-yield detection kept |
| PA-01 | shape_parity_listing_tree_info_search | unit+contract | M1a | H | planned | may be deleted with the second shape (M1b decision) |
| PA-02 | reprocess_golden_byte_identical | db/unit | M1a | H | planned | |
| NM-01 | normalize_missing_fields_and_rejects | unit+hypothesis | M1a | H | planned | |
| NM-02 | unknown_enum_stored_raw_and_counted | service | M1a | H | planned | |
| NM-03 | population_floor_and_coverage_median_via_run | gate | M1a | H | changed | part (a) floors at M1a, scoped to live `author_state=known` rows; part (b) trailing-median alarm deferred to M3 after 60 days of baseline |
| RL-01 | preconditions_exit_78_no_running_row | e2e | M0/M1a | H | planned | full exit-code table (0/1/3/4/75/78/130) proposed, pending Wes |
| RL-02 | flock_held_exit_75_zero_calls | e2e | M1a | H | planned | |
| RL-03 | stale_running_row_marked_crashed_at_45m | e2e | M1a | H | changed | threshold is 3 min (shared settings key with the UI); a held flock means alive regardless of heartbeat age; `queued` > 2 min without pid → `failed` |
| RL-04 | every_mutating_command_takes_lock_writes_run_row | gate | M1a | H | planned | |
| RL-05 | wall_clock_ceiling_partial_after_batch | service | M1d | M | planned | |
| RL-06 | sigterm_finishes_batch_cancelled | e2e | M1d | M | planned | cancel at the request boundary (D-16), pending Wes |
| RL-07 | write_side_failures_abort_page_cleanly | e2e | M1a | H | planned | (b)/(c) sink cases dropped (sidecar cut 2026-09-13); (a) DB-locked case stays |
| JS-01 | jsonl_per_run_file_compress_verify_before_delete | unit+service | M1c | H | cut | per-run JSONL sidecar cut 2026-09-13 |
| JS-02 | jsonl_retention_gate_and_partial_trailing_line | service | M1c | M | cut | per-run JSONL sidecar cut 2026-09-13 |
| TH-01 | theme_regex_timeout_and_caps | unit | M1d | H | planned | |
| TH-02 | theme_inputs_bot_exclusion_retag | service | M1d | H | changed | crosspost parent text stripped to `{id, subreddit}` at ingest (no `matched_field=crosspost_parent`); bot flag is a heuristic per author, never inherited |
| DG-01 | digest_golden_denominators_from_state | unit+service | M1d | H | changed | golden gains the M1d sections pulled forward: distinct-author ranking, top untagged (7 d, ≥3 authors), rising title phrases |
| DG-02 | notifier_proof_recorded | service | M1d | M | cut | notifications are best-effort; the UI pill computed from `runs` is the canonical alert (adversarial A4) |
| CF-01 | dry_run_no_network_zero_http_zero_db_writes | gate | M1a | H | changed | `--dry-run` fetches (HTTP counted, zero DB writes); zero-HTTP applies to `doctor --no-network` and `config validate` (ingest D-1) |
| CF-02 | no_bypass_flags_budget_hard_cap | gate | M1a | H | changed | option-name grep dropped (list-policing, A7); budget cap and "reconcile and scrub still run" kept; bypass flags record a reason on the run row; `--gateway fake` refused against the default data dir (D-10) |
| CF-03 | settings_extra_forbid_and_fingerprint | unit | M0 | M | planned | |
| CF-04 | data_dir_isolation_refusal | gate | M0 | H | changed | extended across the subprocess seam: env-var data dir, injectable `ProcessRunner`, CLI refuses under `PYTEST_CURRENT_TEST` without `--gateway fake` (B4) |
| AD-01 | cassette_auth_ping_two_requests_ua_limits | adapter-cassette | M0 | H | planned | |
| AD-02 | responses_failure_paths_exact_counts | adapter-responses | M1a | H | planned | |
| AD-03 | cassette_tree_serialization_no_lazy_fetch | adapter-cassette | M1b | H | planned | |
| AD-04 | contract_suite_fake_vs_praw | contract | M1a–M1c | H | planned | |
| GT-01 | guard_reachability_meta_and_planted_invariants | gate | M0→ | H | planned | sidecar-dependent plantings dropped (sidecar cut 2026-09-13); scope is post-run invariants only (A3 split) |
| GT-02 | pk_stability_three_reruns | gate | M1a | H | changed | drop `max(pk)==count(*)` (A10); `pk`/`first_seen_at` stability kept |

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
| G13 | One-way protocol vs `main` (three comparisons) | gate | M0 | P1 | planned | fallback without environment reviewers: required label + auto-opened issue |
| G14 | Guard-count ceiling | gate | M0 | P2 | planned | |
| G15 | Schema snapshot | gate | M0 | P1 | planned | |
| G16 | Models == DDL | gate | M0 | P1 | planned | |
| G17 | Per-revision fixture DBs | gate | M1a | P2 | changed | "FTS count == live count" is measured via `posts_fts_docsize`, never `count(*) FROM posts_fts` (DB panel verification) |
| G18 | Runtime schema fingerprint | runtime | M1a | P1 | changed | warning on `doctor` and `/system`, ordinary tables only; never refuses (A9) |
| G19 | DATA_DIR isolation | gate | M0 | P1 | changed | across the subprocess seam (B4) |
| G20 | TCC path and interpreter | gate/runtime | M0, M1d | P1 | planned | |
| G21 | Size caps | gate | M0 | P1 | changed | `C901` and `PLR0915` only (plan); the file-length test and `PLR0913` not adopted |
| G22 | Cross-platform | gate | M0, M1 | P1 | planned | |
| G23 | Hard-block hooks | hook | M0 | P1 | changed | two hooks, not three: H1 `no_bypass_git`, H3 `enforcement_files_script_only`; H2 `no_prod_db_writes` cut (command-text list-policing, A6); fail closed on internal error |
| G24 | Hook wiring currency | gate | M0 | P1 | changed | exactly two `PreToolUse` entries |
| G25 | `make check` summary | gate | M0 | P1 | planned | |
| G26 | PR-body gate | CI | M0 | P2 | planned | deferrable to M1 if the two-day box overruns |
| G27 | Changed-tests sticky comment | CI | M0 | P2 | planned | |
| G28 | Portability | CI | M0 | P1 | planned | external control: "last seen red" line in `GUARDS.md` |
| G29 | pre-commit hooks | commit | M0 | P1 | planned | |
| G30 | Guard reachability | gate | M1a | P1 | planned | the required half of the positive-control split |
| G31 | Connection chokepoint (behavioral) | gate | M0 | P1 | planned | |
| G32 | No-bypass proof | gate | M1 | P2 | changed | dry-run fetches; zero-HTTP is for `doctor --no-network` and `config validate` (see CF-01) |
| G33 | Doc currency | gate | M0 | P1 | changed | only the INDEX ↔ `docs/**` bidirectional check remains (plan); `KNOWN_ISSUES` node ids, `GUARDS` ↔ markers, data dictionary, count regex not gates |
| G34 | Guard firings ledger | CI | M0 | P2 | planned | |
| G35 | Weekly enforcement audit | CI | M0–M1 | P2 | planned | deferrable to M1 |
| G36 | Settings-drift check | CI | M0 | P2 | planned | deferrable to M1; agent token drops `administration`/`workflows` after M0 |
| G37 | Weekly stress | CI | M1d | P3 | changed | 50k/500k corpus cut; the `EXPLAIN QUERY PLAN` assertions live in DB-08 |
| G38 | Mutation (informational) | CI | M3 | P3 | cut | optional tool, never a ratchet; no `.ratchets/mutation.txt` (plan) |

### 3.4 Web UI and delivery surface — `2026-09-13-panel-ui.md` §A (55); operator checklist §B; setup threat model §C

| ID | Name | Layer | Phase | Pri | Status | Reason if cut/changed |
|---|---|---|---|---|---|---|
| UI-01 | Every page route renders on seeded and empty DB | route | M2 | P0 | planned | |
| UI-02 | Same URL: fragment vs page, with `Vary` | route | M2 | P0 | planned | |
| UI-03 | Query parameters never 500 | route | M2 | P1 | planned | |
| UI-04 | 422 forms swap and flash OOB wired | template | M2 | P1 | planned | |
| UI-05 | Content safety headers and template scan (CSP) | template | M2 | P1 | planned | |
| UI-06 | Nested comments are DOM descendants at seeded depth | template | M2 | P0 | planned | |
| UI-07 | Depth cap 10, continue-thread swap and permalink | template | M2 | P0 | planned | |
| UI-08 | Load-more pages by top-level with whole subtrees | template | M2 | P1 | planned | |
| UI-09 | Comment sort top / new / old | route | M2 | P2 | planned | |
| UI-10 | Tombstones render honestly by `content_state` | template | M2 | P0 | planned | |
| UI-11 | Tombstones never listed on author pages, search, author filter | route | M2 | P0 | planned | |
| UI-12 | Bot items flagged and excluded from theme counts | template | M2 | P1 | changed | `author_is_bot` is a heuristic surfaced as "suspected bots" with one-click confirm; per author, never inherited by a megathread's comments |
| UI-13 | Coverage line, stubs, "as of", harvest button | template | M2 | P0 | planned | |
| UI-14 | `[NEW]` badge derived from latest completed run | template | M2 | P1 | planned | |
| UI-15 | Deep-link href exactness per item kind | template | M2 | P0 | planned | |
| UI-16 | Markdown safety asserted on the rendered page | behavior | M1a/M2 | P0 | planned | |
| UI-17 | FTS snippet escaping incl. marker chars | behavior | M2 | P0 | planned | |
| UI-18 | Reflected params and cookie escaped | route | M2 | P1 | planned | |
| UI-19 | FTS mini-grammar sanitizer never raises | behavior | M1a/M2 | P0 | planned | |
| UI-20 | Search tabs, counts, grammar semantics | route | M2 | P1 | planned | |
| UI-21 | Cross-site POST rejected | middleware | M2 | P0 | changed | missing `Sec-Fetch-Site` (plain-HTTP LAN) falls back to `Origin`/`Referer` host vs allowed `Host`, instead of rejecting (adversarial D1) |
| UI-22 | Host check on every request | middleware | M2 | P0 | planned | |
| UI-23 | No GET route writes | behavior | M2 | P1 | planned | |
| UI-24 | Basic auth via env var | middleware | M2 | P1 | planned | |
| UI-25 | Web reads `mode=ro`; writes only via the repository | behavior | M2 | P0 | changed | `mode=ro` engine cut; the table-delta assertion against the writer map stays (= DB-52) |
| UI-26 | Run now: queued row before spawn, argv parity with launchd | behavior | M2 | P0 | planned | through the injectable `ProcessRunner` |
| UI-27 | 409 while a run is active | behavior | M2 | P0 | planned | |
| UI-28 | Polling stops when idle | template | M2 | P0 | planned | |
| UI-29 | Stale-run detection | behavior | M2 | P0 | changed | one shared 3-minute key; flock held ⇒ alive; orphan `queued` rows > 2 min without pid → `failed` (B9) |
| UI-30 | Cancel | behavior | M2 | P1 | planned | `cancel_requested_at` polled at batch boundaries (UI D5) |
| UI-31 | Error mapping and status banner derived from run row | template | M2 | P1 | planned | |
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
| UI-51 | Accessibility basics on every page | template | M2 | P1 | planned | |
| UI-52 | Playwright smoke flows | e2e | M2 | P2 | planned | local-only, never in CI |
| UI-53 | Appearance settings | route | M2 | P2 | planned | |
| UI-54 | Sidebar and theme counts carry denominators, shared with digest | template | M2 | P1 | planned | |
| UI-55 | Comment permalink page | route | M2 | P1 | planned | |

Gaps the adversarial review named that have no spec ID yet (write them as tests when the stage lands): an **edited post** matrix row (B5; RC-02 covers the mechanism), the **deleted link post** probe and state row (B3; add to the probe plan as P-18), **megathread** handling for bot exclusion (B10), and a route test for **`Popen` failure** leaving an orphan `queued` row (B9; UI-26 covers the launcher-raises path).

## 4. What ships first

**M0 shipped gate set** (plan, "M0 foundation tranche"; ledger rows in `runbook/GUARDS.md`): import-linter layering (G04, G05) · network block (G06) · schema snapshot (G15, DB-01) · models-vs-DDL (G16, DB-02, DB-03) · data-directory isolation in-process and across the subprocess seam (G19, DB-18, DB-19, CF-04) · pragma behavioral test (G31, DB-12) · upsert and PK stability (DB-20; GT-02 through `run` at M1a) · coverage and suppression ratchets with the three-way compare and loosening protocol (G11, G10, G08, G09, G13) · exception lint policy (G01) · `-W error` (G07) · pre-commit ruff and gitleaks (G29) · two hard-block hooks (G23, G24) · `make check` summary (G25). Positive controls, split per the adversarial review: post-run invariants through `run --gateway fake`; CI ratchets by a unit test of the compare function; external controls (branch protection, pre-commit, portability, hooks) by a dated "last seen red" line. If the two-day box overruns, G26, G35, G36 defer to M1.

**M1a invariant set** (proven through `insightminer run --gateway fake` with a planted violation, GT-01/G30): compliance canary (SC-01, SC-02, DB-32) · counters-versus-deltas (DB-54) · structural population floors (DB-50, DB-51, NM-03a) · per-source freshness (FR-01). Only the first two flip a run to `failed` during the first 60 days; the others are `partial`/amber. Also wired at M1a without flipping status: PK stability (GT-02), FTS membership via `_docsize` (DB-26), normalizer-version stamping (DB-48), reconcile-age per tier (RC-06, from M1c).

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
11. Probe each item the way a real record presents it: fixtures come through `probe`, tombstones through the real `scrub()`, bot rows through `normalize()`.

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
9. Confirm the compliance bounds as written: no backup older than 14 d, no export older than 7 d, per-tier reconcile ages 60 h / 8 d / 35 d, real purge latency 48–72 h for items under 30 days.
10. Per-run JSONL sidecar: **cut, decided 2026-09-13.** JS-01/02 and DB-34/35 are cut; the JSONL clauses in DB-31, DB-54, SC-01, RL-07, GT-01 are dropped.
11. Purge semantics for "stop and delete captured data": hard delete with a recorded purge run (recommended) or mark-and-hide? Decides DB-55.
12. Scrub latency for items confirmed only by `info()` absence: accept up to ~4 days, or re-check first misses at the end of the same run (recommended)?
13. Unknown `removed_by_category` with a `[removed]` body: which removed state, and may `removed_by_reddit` return to live on an intact payload? (Every `removed_*` may return; only `deleted_by_author` is terminal.)
14. Reprocess boundary: may `reprocess` change `next_check_at`/`check_stage`, or are they owned by the ladder only? (Ladder only.)
15. Automated weekly restore drill via launchd into a temp dir, recorded in `backups`? (Yes.) Fixture DBs kept under 1 MB by design rather than exempting the path? (Yes.)
16. Commercial-use stance for a coworker at the company that makes Premiere Pro (the research report calls product-decision insights a grey area).

Collector (ingest §E):
17. Exit codes 0 ok / 1 failed / 3 partial / 4 rate-limited / 75 locked / 78 config / 130 cancelled, with `partial` a digest line rather than a notification? Does `--dry-run` write a `runs` row (adversarial D12 says no)?
18. Per-post expansion cap: per fetch for huge threads (recommended) or cumulative across revisits? Budget scope: do token refreshes count? (Count every HTTP response.)
19. Zero-new threshold: K = 3 consecutive runs per subreddit; is r/editors exempt on weekends?
20. `--gateway fake` refused against the default data dir, or require an explicit `--data-dir`? (Refuse.) Cancel latency: stop at the next request boundary and roll back the in-flight tree? (Yes.)

UI and LAN (UI §E, adversarial B11):
21. On the LAN without a password, do `/setup` POST and the destructive gates require a loopback client or `INSIGHTMINER_UI_PASSWORD`? (Loopback-only unless the password is set; threat model "operator error" recorded in `DECISIONS.md`.)
22. Allowed-Host list: from `INSIGHTMINER_ALLOWED_HOSTS` or derived from the bind address? Add **Regenerate digest** and **Download config** buttons so the operator-complete gate has nothing to exclude beyond the four commands?

Fixtures and probes (ingest §E, DB §F, plan "Things only Wes can do"):
23. Create the personal restricted test subreddit (account-age rules permitting); P-01, P-02, P-04–P-06, P-09–P-12 and every cassette depend on it. Is probing public examples acceptable for Reddit-removed posts (P-03) and account-deleted authors (P-13), given the saved payload is already `[removed]` or body-blanked?
24. Fixture scrubbing on `probe --save-fixture`: automatic username replacement (recommended) or manual review before commit?
25. Can the earlier project's its issue register, its database integrity reference, its breakage-pattern catalogue, and its update-semantics note be shared? They would settle purge semantics and the field-ownership sets from precedent.

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
| CU-06 | adhoc_search_reddit_actions | route (fake gateway) | search box query | submit; click "monitor" on a subreddit; click "harvest" on a thread | exactly one API search request; monitor adds the source (validated, one request); harvest spawns the CLI for that post with a queued run row; zero API calls on page render | search on GET → red; two requests per click → red | M2 | M |
| CU-07 | tag_feedback_is_operator_signal_not_precision | route | tags on posts | thumbs up/down | feedback row stored; theme page shows "operator feedback: k of n judged"; digest carries it; the two views use one metric function; no string rendered from the feedback table in UI, digest, or export contains "precision" (corrected 2026-09-13: anchored feedback is an operating signal, never the grade; precision comes from the M3 blind packet) | a template rendering "precision" from feedback rows → red | M2 | M |
| CU-08 | curation_controls_are_operator_complete | gate | typer command tree and routes | run the operator-complete gate | archive/delete/move workspace, manual tag, watch, promote, rename/merge, ad-hoc search each have a marked UI test | new command without a marked test → red | M2 | H |
| CU-09 | manual_tags_and_watches_scrub_with_the_item | e2e | watched, manually tagged post deleted on Reddit | reconcile | tags removed, watch cleared, tombstone rendered; canary absent everywhere | manual tag survives scrub → red | M2 | H |
| CU-10 | export_import_round_trips_curation | e2e | manual tags, watches, feedback | export then import on a fresh data dir | all curation rows restored with origins intact | origins reset to `rule` → red | M2 | M |

Failure-matrix additions (plan): deleting a workspace must never remove data another workspace still reaches; re-tagging must never remove a manual tag; a watched thread must never fall off the ladder while its watch is active.
