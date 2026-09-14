# Known issues — fixed bugs and their regression tests

> Policy (plan § Reference corpus, working agreement): every bug fix starts with a failing test, and every fixed bug lands one row here pointing at that test. The `Regression test` column must resolve to a collected pytest node id; the doc-currency test checks it. Rows are never deleted; a regressed issue gets a new row citing the old id. Open issues that have no fix yet may be listed with status `open` and an empty test column until the failing test exists.
>
> Status vocabulary: `open` (reproduced, no fix), `fixed` (test green on `main`), `regressed` (re-opened; cite the new row), `wontfix` (reason in root cause).

| ID | Date | Symptom | Root cause | Regression test (node id) | Status |
|---|---|---|---|---|---|
| KI-001 | 2026-09-13 | A fresh clone's `make check` printed green while `dmypy` type-checked the *original* repo | `.dmypy.json` (daemon state holding the original tree's absolute path) was tracked in git, so the fresh clone's daemon attached to the wrong tree | tests/gates/test_no_tracked_daemon_state.py::test_dmypy_state_is_not_tracked_and_is_ignored | fixed |
| KI-002 | 2026-09-13 | `db upgrade` on an empty data folder created a blank database and died with an unhandled traceback instead of refusing cleanly with exit 78 | `_upgrade_locked` opened/created the database through `ctx_factory` before checking whether a database already existed, so a fresh data dir got a 0-byte phantom `insightminer.db` and then crashed (commit `3b64b2a`) | tests/e2e/test_db_commands.py::test_db_upgrade_with_no_database_exits_78_and_fabricates_nothing | fixed |
| KI-003 | 2026-09-13 | A settings validation error printed the raw input to the terminal, including the Reddit client secret and the UI password, in plain text | a model-level validator's `ValidationError` renders pydantic's whole raw input mapping by default, and `hide_input_in_errors` was not set, so a single typo'd setting could print a live secret to stderr (commit `3818fa9`) | tests/e2e/test_config_validate.py::test_config_validate_never_echoes_a_secret_it_refused | fixed |
| KI-004 | 2026-09-13 | A misspelled `INSIGHTMINER_*` environment variable (a typo'd field, a key under a leaf field, or an unknown nested key) was silently ignored, and `config validate` still reported ok | `extra="forbid"` does not see environment variables at all; pydantic-settings matches `INSIGHTMINER_*` against known field names only and drops everything else, so a typo'd override ran silently against the default instead (commit `3818fa9`) | tests/unit/test_settings.py::test_an_unknown_environment_variable_is_rejected_naming_it | fixed |
| KI-005 | 2026-09-13 | A power loss during or right after a backup could leave a `backups` row and a recorded sha256 pointing at a file that was empty, truncated, or absent, and could lose a restore halfway through recovery | `os.replace` is atomic for readers but says nothing about durability, and neither `online_backup` nor `restore` synced the staged file and its directory around the rename (commit `6b4ed48`) | tests/db/test_backup.py::test_online_backup_fsyncs_the_copy_and_its_directory | fixed |
| KI-006 | 2026-09-13 | The pre-migration backup pruner deleted whatever file an untrusted `backups` row pointed to, including a path outside the data folder, and deleted the file before its row inside the same transaction | `prune_pre_migrate_backups` unlinked any path a row named with no check that it resolved under `backups_dir(settings)`, and `unlink` is not transactional, so a rolled-back prune could leave a row pointing at a file that no longer existed (commit `246fd34`) | tests/services/test_migrate_service.py::test_prune_leaves_a_backup_row_pointing_outside_the_backups_directory_alone | fixed |
| KI-007 | 2026-09-13 | The second rate-limit (429) response in a run slept up to five minutes before ending the run, instead of ending it at once as the spec and the code's own docstring required | the run's `rate_limited` abort was already decided, but the code still planned the wait, wrote the heartbeat, and slept before raising it (commit `457a76b`) | tests/services/test_sweep_errors.py::test_second_rate_limit_ends_the_run_rate_limited | fixed |
| KI-008 | 2026-09-13 | A syntactically broken seed file left the `db init` run row `running` forever with an unhandled traceback, instead of finishing the row `failed` | `_seed`'s except tuple did not include `yaml.YAMLError`, so a YAML parse error in `config/seed.yaml` escaped the handler entirely (commit `246fd34`) | tests/services/test_migrate_service.py::test_a_seed_failure_finishes_the_db_init_run_row_failed | fixed |

<!-- Format example (do not count as a row):
| KI-0XX | 2026-10-01 | Post page 500 on a scrubbed post with no permalink | template built the deep link from `permalink` instead of `reddit_id` | tests/web/test_post_page.py::test_tombstone_deep_link_uses_id | fixed |
-->

## Swept: investigated, no issue found

A suspicion investigated and found not to be a bug is recorded here with how it was checked, so no later session re-investigates it (practice carried from the earlier project, 2026-09-13).

| Date | Question | How verified | Answer |
|---|---|---|---|
| 2026-09-13 | Does any code reference the per-run JSONL sidecar that was cut? | `grep -rn -i jsonl src/ tests/ tools/` | No; only documents did, and they were swept in commit `2dd8567` |
| 2026-09-13 | one `make check` run measured coverage 98.12 instead of 98.16 (66/42 missed vs 65/41); five later runs stable | re-ran `make check` five times | no reproducible cause found; the 0.5 slack absorbed it; watch for recurrence |
