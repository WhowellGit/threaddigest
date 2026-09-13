<!-- Extracted 2026-09-13 from the panel agent transcript (final assistant message; a one-line conversational lead-in before the heading was dropped, HTML entities unescaped, nothing else touched). -->
<!-- Status: raw, unedited panel report; immutable reference copy (docs/reference/ policy: add, never edit). -->
<!-- Scope: test-strategy panel on database integrity and migrations (upsert semantics, PK stability, FTS sync and rebuild, Alembic batch mode, backup/restore gate, schema snapshot and fingerprint, DATA_DIR isolation). -->

# Panel report: database integrity and migrations

**Sources read:** plan (Data model, Collector steps 0/4–6, Robustness, Release/migration, Testing), `DB_LEARNINGS_APPLIED_2026-09-12.md`, collector review §1.2/1.4/4, `WHY_THE_GUARDS_EXIST.md`, plus the cited incident rows in reviewer reports A (#11, 12, 17, 18, 41, 42, 44, 48, 53, 54) and B (S2–S6, I1, I2, F2–F5, E6, E11, B8).

**Verified empirically today (SQLite 3.53.4, in-memory, no files written) because they change the specs:**

1. On an FTS5 external-content table, `SELECT count(*) FROM posts_fts` returns the **content table's** row count, not index membership. With 2 live + 1 tombstone rows it returned 3; after scrubbing one live row it still returned 3. The plan's "FTS row counts equal live row counts" invariant, implemented that way, can never go red. `SELECT count(*) FROM posts_fts_docsize` tracked the truth (2 → 1).
2. With `content='posts'` and live-gated triggers, FTS5's own `integrity-check` (default arg) reports `database disk image is malformed` by design (tombstones exist in content, not in index), and `'rebuild'` **re-indexes tombstone rowids** (docsize 1 → 3, `MATCH 'deleted'` hit the tombstone). The plan's rule "run the FTS rebuild in the same migration" therefore breaks the FTS invariant, or leaks marker text, under the plan's own FTS design. Pointing `content=` at a live-only **view** (`posts_live`) fixes all three: rebuild indexes live rows only, `integrity-check` passes, and naive counts at least equal live counts.
3. Alembic batch recreate (`DROP TABLE posts` + `ALTER TABLE _alembic_tmp_posts RENAME TO posts`) **fails** when a view references `posts` (`error in view posts_live: no such table: main.posts`) unless `PRAGMA legacy_alter_table=ON`, or the view is dropped before the batch and recreated after. Triggers on the table are lost in every variant; the FTS index survives because `pk` values are copied.

These drive rows DB-10, 26–30, 37, 44 and section E items 1–3.

---

## A. Test specification table

Layer: unit / db / migration / e2e / gate. PC = positive control (the constructed bad state that must make the test go red). Cost S/M/L, Priority H/M/L.

### A1. Schema revision 1 shape

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-01 | schema_sql_golden_matches_head | migration | empty temp DB | `alembic upgrade head`; dump normalized DDL (see §D) | dump == committed `db/schema.sql` byte-for-byte; failure prints unified diff | none | M0 | run comparator against a DB with one extra index → diff names the index → red | S | H |
| DB-02 | models_match_ddl_with_fts_filter | migration | migrated temp DB + SA metadata | pytest-alembic `test_model_definitions_match_ddl` with `include_object` excluding `%_fts` virtual tables, `%_fts_%` shadow tables, and `%_live` views | autogenerate diff empty | none | M0 | (a) model column with no migration → red; (b) remove the filter → autogenerate proposes `DROP posts_fts_data` → red (proves the filter is load-bearing) | S | H |
| DB-03 | single_head_and_up_down_consistency | migration | versions dir | pytest-alembic `test_single_head_revision`, `test_upgrade`, `test_up_down_consistency` | all pass | none | M0 | two heads in a temp versions dir → red; downgrade that leaves a column → red | S | H |
| DB-04 | every_reddit_keyed_table_has_rowid_alias_pk | db | migrated DB | scan `sqlite_master` for every table that has a `reddit_id` column (structural, not a table list) | `PRAGMA table_info`: exactly one pk column, declared type exactly `INTEGER`, `pk=1`; `reddit_id` `notnull=1` with a single-column UNIQUE index; table not `WITHOUT ROWID` | none | M0 | schema variant with `reddit_id TEXT PRIMARY KEY` (the original sketch) → red | S | H |
| DB-05 | timestamp_columns_are_integer_epoch | db+unit | SA metadata + migrated DB | scan every column named `*_utc` / `*_at` | DDL type `INTEGER`, SA type `Integer`; no `DateTime` anywhere in metadata; repo round-trip of `created_utc=1757000000` reads back `int` | none | M0 | model with `DateTime(timezone=True)` on an `_at` column → DDL type `DATETIME` → red | S | H |
| DB-06 | next_check_at_not_null_enforced | db | migrated DB seeded with due and future posts | insert a post with `next_check_at=None` via repo; run due-query `WHERE next_check_at <= :now` | IntegrityError; `table_info` `notnull=1`; due-query returns every past-dated row (no row can be "never due") | none | M1a | nullable variant + one NULL row → never selected by due-query → red | S | H |
| DB-07 | derived_enums_closed_upstream_enums_open | db | migrated DB | insert `content_state='foo'`, `author_state='bar'`, `runs.status='weird'`; then insert `removed_by_category='brand_new'`, `post_hint='hologram'` | first three raise CHECK IntegrityError; last two accepted raw | none | M1a | schema without CHECK → `'foo'` accepted → red | S | H |
| DB-08 | hot_queries_use_declared_indexes | db | DB seeded ~10k posts / 50k comments | `EXPLAIN QUERY PLAN` for due-posts, sub feed, author page, tree, theme feed, snapshots, content_state filter | each plan contains `USING INDEX`, none contains `SCAN posts` / `SCAN comments` | seeded corpus (hypothesis) | M1a; weekly at M1d | drop one declared index → `SCAN` → red | M | M |
| DB-09 | every_column_has_a_comment | unit | SA metadata | iterate all tables/columns | `comment` non-empty; DATA_DICTIONARY section of `schema.sql` contains every `table.column` | none | M0 | column with `comment=None` → red | S | M |
| DB-10 | fts_definition_shape | db | migrated DB | parse `CREATE VIRTUAL TABLE` args for `posts_fts`/`comments_fts` | `content_rowid='pk'`; `content='posts_live'`/`'comments_live'` (views over `content_state='live'`); tokenizer `porter unicode61`; `columnsize` not 0 (so `_docsize` exists); `posts_live` view present | none | M1a | `columnsize=0` variant → `posts_fts_docsize` absent → DB-26 unmeasurable → red; `content='posts'` variant → DB-30 red | S | H |

### A2. Connection chokepoint and pragmas (rank 10)

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-11 | create_engine_only_in_db_engine | gate | source tree | import-linter forbidden-import contract + ruff `banned-api` for `sqlalchemy.create_engine`, `sqlite3.connect`, `aiosqlite` outside `insightminer.db.engine` | lint clean | none | M0 | temp `services/_bad.py` calling `sqlite3.connect` → red | S | H |
| DB-12 | pragmas_effective_on_public_write_connection | db | engine from `db.engine.engine_for(settings)` on a tmp **file** DB, read-write (never `mode=ro`/`immutable`, the earlier project's inert WAL guard) | force two pool checkouts; read pragmas on each | `journal_mode='wal'`, `foreign_keys=1`, `secure_delete=1`, `busy_timeout=30000`, `synchronous=1`, `temp_store=2` on both connections | tmp DB | M0 | connect-event listener removed → `journal_mode='delete'` → red | S | H |
| DB-13 | foreign_keys_enforced_behaviorally | db | migrated DB | insert comment with `post_pk=999999` through the public path; `foreign_key_check` after a full fake run | IntegrityError; `foreign_key_check` empty | tmp DB | M1a | connection with `foreign_keys=OFF` → insert accepted → red | S | H |
| DB-14 | busy_timeout_waits_then_fails_cleanly | db | two engines on one tmp DB; test setting `busy_timeout=1000` | B holds `BEGIN IMMEDIATE`; A upserts a page in a thread; (a) B commits at 200 ms; (b) B never commits | (a) A succeeds; (b) A raises `OperationalError: database is locked` after ≥1 s; no partial page: `run_subreddits` and watermark untouched | threads | M1a | `busy_timeout=0` → (a) fails immediately → red | M | M |
| DB-15 | secure_delete_leaves_no_canary_bytes | db | tmp file DB via public path | insert 64-char canary in `selftext`; scrub; `wal_checkpoint(TRUNCATE)`; read `.db` and `-wal` bytes | canary absent from both; also absent from a `VACUUM INTO` copy | tmp DB | M1c | `secure_delete=OFF` → canary present in freed pages → red | M | H |
| DB-16 | read_only_paths_cannot_write | db/web | web read session; Datasette launcher args | attempt INSERT via web read session; inspect launcher | `OperationalError: attempt to write a readonly database`; URI has `mode=ro`; launcher never passes `--immutable` (WAL DB with live writer) | tmp DB | M2 | read dependency built without `mode=ro` → insert succeeds → red | S | H |
| DB-17 | wal_truncated_at_end_of_run | e2e | fake run on tmp DB | `run` exits 0 | `-wal` size 0 or absent | fake | M1a | checkpoint step removed → wal > 0 → red | S | L |

### A3. DATA_DIR isolation (rank 1)

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-18 | settings_refuse_default_data_dir_under_pytest | unit/gate | pytest loaded; `INSIGHTMINER_ALLOW_REAL_DATA_DIR` unset | construct `Settings()` with no DATA_DIR override | raises `DataDirRefused` before any path is created; default dir listing before == after | none | M0 | the `tests/gates/` test *is* the mis-pointed test; negative control: opt-in var set in a non-pytest subprocess → constructs | S | H |
| DB-19 | only_data_dir_is_writable_during_tests | gate/e2e | pytest session with CWD and HOME on read-only tmp dirs (`chmod 0o500`), DATA_DIR on a writable tmp; harness self-test at session start proves a write into CWD fails (else session errors: fail, never skip, e.g. when running as root in Docker) | full `run --gateway fake`, `report`, `export`, `db backup` | zero `PermissionError`; every `raw_files.path`, `backups.path`, `runs.log_path`, report/export path is under `realpath(DATA_DIR)` | fake | M0 harness, M1a run | sink writing `./raw/x.jsonl` relative to CWD → `PermissionError` → red (the earlier project's "reads honored the test dir, writes did not") | M | H |

### A4. Upsert semantics, PK stability, field ownership (ranks 3, 4)

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-20 | pk_stability_across_reruns | e2e | fake scenario: 300 posts / 2k comments, overlapping pages, one page containing the same id twice, score changes | `run` 3× with clock advanced | per `reddit_id`: `pk` and `first_seen_at` unchanged; `max(pk) == count(*)` on posts and comments; `count(*) FROM posts_fts_docsize == live count`; duplicate-in-page → one row, no IntegrityError | fake | M1a | repo variant using `INSERT OR REPLACE` → pk churn, `max(pk) > count(*)`, FTS detached → red | S | H |
| DB-21 | field_ownership_per_ingest_path | db | one post at `check_stage=2`, `next_check_at=X`, `first_seen_at=Y`, `score=10` | apply each writer (sweep, tree, `info`, search) with a payload that changes every field | actual before/after row diff ⊆ `FIELD_OWNERSHIP[path]`; sweep changed only `score`, `num_comments`, `edited_utc`; no path touches `pk`/`first_seen_at`; closed-world: `set(posts.columns) == ∪ owned ∪ DERIVED` so a new column cannot be silently unowned | none | M1a | sweep writer also sets `next_check_at` → unowned delta → red; new column added to the model only → closed-world assertion red | S | H |
| DB-22 | upsert_never_resurrects_terminal_content | db+e2e | post scrubbed as `deleted_by_author` | a later sweep page / `info` result carries the full original content (stale listing) | content columns stay NULL, `raw_json` stays tombstone, `content_state` and `scrubbed_at` unchanged, FTS `MATCH canary` empty | fake `delete()` then `replay_stale_page()` | M1c | upsert without the terminal-state guard → content restored → red | S | H |
| DB-23 | moderator_removed_returns_to_live_reindexes | db | post at `removed_by_moderator` | fetch presents content with `removed_by_category` NULL | `content_state='live'`, content repopulated, `MATCH` finds it, `post_themes` re-tagged in the same run | fake `remove()` then `approve()` | M1c | update trigger lacking the insert branch → state live but `MATCH` empty → red | S | M |
| DB-24 | orphan_parent_comment_without_fk | db | comment whose `parent_fullname` (`t1_zzz`) was a skipped `more` | insert; later insert `zzz` and run `resolve_parents(post_pk)` | first insert OK with `parent_comment_pk NULL`; `PRAGMA foreign_key_list(comments)` has no entry for `parent_comment_pk`; second pass resolves it | none | M1b | FK declared on `parent_comment_pk` → orphan insert fails → red | S | M |
| DB-25 | unknown_enum_values_stored_raw_and_counted | e2e | fake payload with `removed_by_category='brand_new_reason'`, `post_hint='hologram'`, `subreddit_type='weird'` | `run` | columns hold the raw strings; `runs.counters.unknown_enum_values == 3` with per-column breakdown; `content_state` for a `[removed]` body with unknown category is not `'live'` (fail-closed); digest shows the count with denominator | fake | M1a | normalizer coercing unknown → NULL or nearest known → counter 0 → red | S | H |

### A5. FTS5 external-content sync

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-26 | fts_membership_equals_live_via_run | gate/e2e | fake run yields N live + K scrubbed posts and comments | run 1; then index-only corruption `INSERT INTO posts_fts(posts_fts,rowid,…) VALUES('delete',pk,…)` for one live row; run 2 | run 1 `ok` with `counters.fts_posts == live_posts` measured as `count(*) FROM posts_fts_docsize`; run 2 `status='failed'`, `error` names `fts_posts_mismatch`; the test additionally asserts the naive `SELECT count(*) FROM posts_fts` did **not** move (documents why it is banned) | fake | M1a | invariant implemented with the naive count → run 2 stays `ok` → red | M | H |
| DB-27 | fts_insert_gated_on_live | db | none | insert live post with canary; insert first-sight tombstone (`deleted_by_author`, NULL text) | `MATCH canary` → 1 row; docsize count 1 | none | M1a | trigger without `WHEN new.content_state='live'` → docsize 2 → red | S | H |
| DB-28 | fts_scrub_removes_entry_and_snippets | db | live indexed post with canary | scrub via the single function | `MATCH canary` → 0; docsize decremented; a search matching a term only the old text had → 0 rows; `snippet()` over any result never yields NULL/`[deleted]` | none | M1c | update trigger's `'delete'` branch missing → `MATCH` still hits → red | S | H |
| DB-29 | fts_author_scrub_reindexes_without_author | db | live post by `canaryuser` with `author` an indexed FTS column | `account_deleted` transition (content stays) | `MATCH 'canaryuser'` → 0; body canary still → 1 | none | M1c | trigger declared `AFTER UPDATE OF selftext` (column-scoped) → author not re-indexed → red | S | H |
| DB-30 | fts_rebuild_indexes_live_only_and_integrity_check_passes | migration/db | DB with live + scrubbed rows | `INSERT INTO posts_fts(posts_fts) VALUES('rebuild')` (the command every batch migration runs); then FTS `integrity-check` (default arg) | docsize == live count; `MATCH '[deleted]'` / `'[removed]'` → 0; integrity-check ok | fixture rev DB | M1a | table-backed `content='posts'` variant → docsize == total rows and integrity-check raises `malformed` → red (verified 2026-09-13) | S | H |

### A6. Scrub as one function; raw files (ranks 10, 25)

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-31 | scrub_touches_four_surfaces_in_one_call | e2e | live post with canary, tagged by a theme, present in one plain and one gz JSONL in retention | `reconcile` through `run` calls `services.scrub.scrub_item(pk)` once | in one call: content/author/URL columns NULL; `raw_json` == tombstone object; `post_themes` rows gone; `MATCH` empty; every retained JSONL line for the id rewritten to tombstone atomically (no `.tmp` left; gz re-verified line count); `scrubbed_at` set | fake `delete()` | M1c | four PCs: remove any one effect from the function → that surface's assertion red | M | H |
| DB-32 | compliance_canary_absent_everywhere_incl_backup | e2e/gate | unique phrase in title, selftext, a comment body, and an author name | delete in fake; `reconcile`; `export`; `report`; run finish makes daily backup | byte-scan of DATA_DIR after checkpoint (DB, `-wal`, `raw/`, `reports/`, `exports/` zip members, `logs/`, `backups/daily-*.db` from this run) → zero hits | fake | M1c | skip JSONL rewrite → hit in `raw/` → red; skip checkpoint → hit in `-wal` → red | M | H |
| DB-33 | scrubbed_rows_have_no_content_columns (post-run invariant) | gate | fake run with scrubbed rows | run finish | `count(*) WHERE scrubbed_at IS NOT NULL AND (title IS NOT NULL OR selftext IS NOT NULL OR author IS NOT NULL …) == 0`; live rows have required columns; violation → `status='failed'` | fake | M1c | hand-set `selftext` on a scrubbed row between runs → failed naming the invariant | S | H |
| DB-34 | compressed_jsonl_verified_before_plain_deleted | unit/e2e | run JSONL with N lines | compression step; then a gz chopped by 200 bytes | gz re-read line count == `raw_files.item_count` before plain removed; truncated gz raises `RawFileCorrupt`, plain retained, run `partial` | tmp_path | M1c | verify step removed → truncated gz accepted and plain deleted → red | S | M |
| DB-35 | partial_trailing_jsonl_line_tolerated_db_authoritative | unit | JSONL with a half-written last line | scrub rewrite / reprocess / retention read it | yields N-1 records + one warning counter; never raises; JSONL is never used to recreate DB rows (`raw_files.item_count` vs DB rows compared and reported, not repaired) | tmp_path | M1c | reader raising on the partial line → red; reader emitting it as a record → red | S | M |

### A7. Backups, restore, destructive gate (rank 16)

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-36 | daily_vacuum_into_backup_recorded_and_verified | e2e | fake run | run finish | `backups/daily-<date>.db` exists; `backups` row with path, size, sha256 of file, `integrity_check='ok'`, per-table row counts equal to source at that instant; copy opened `mode=ro` yields those counts | fake | M1c | file written but no `backups` row → DB-39 refuses → red; corrupted copy → `integrity_check != 'ok'` recorded → red | M | H |
| DB-37 | pre_migrate_backup_order_and_post_checks | migration/e2e | fixture DB at rev N-1 | `insightminer db upgrade` | observed order: `pre-migrate-<from>-<to>-<utc>.db` via `Connection.backup()` + `quick_check` **before** Alembic runs; after: `integrity_check` ok, `foreign_key_check` empty, `alembic_version == head`, `backups` row `kind='pre-migrate'`; `PRAGMA foreign_keys` reads 0 inside the migration (set outside the transaction, where the pragma is not a no-op) | fixture revs | M1a | migration raising midway → DB restored byte-identical (sha256) from the copy, exit non-zero, `alembic_version` unchanged | M | H |
| DB-38 | transaction_per_migration_no_half_state | migration | fixture at N-1; two pending revisions, the second a temp revision that raises after a batch op | `alembic upgrade head` | `alembic_version` == first revision; DDL == that revision's golden; no `_alembic_tmp_*` table; `integrity_check` ok | fixture + temp failing revision | M1a | env.py without transactional DDL (pysqlite default isolation) → `_alembic_tmp_posts` left and version/schema disagree → red | M | H |
| DB-39 | destructive_ops_require_recent_verified_backup | gate/e2e | tmp DB with no `backups` row within N h | each of `db restore`, `db downgrade`, `db reprocess`, `subs remove --delete-data`, retention sweep via CLI with `--yes` | exit 78; per-table checksums unchanged; message names the gate; with a fresh verified row + `--yes` → proceeds | fake | M1c basic, M3 UI | row with `integrity_check='failed'` → refuses; row older than N h → refuses; row whose file is missing or sha256 mismatches → refuses (gate checks the file, not just the row) | M | H |
| DB-40 | restore_is_atomic_under_lock | e2e | live DB A (counts a), backup B (counts b) | `db restore B` while another process holds the flock; then without | exit 75 and A unchanged; then counts == b, stale `-wal`/`-shm` of A gone, `doctor` ok, fingerprint matches | tmp | M2/M3 | failure injected between temp write and `os.replace` → A intact (sha256 equal), else red | M | H |
| DB-41 | online_backup_consistent_under_concurrent_writes | db | writer thread upserting pages continuously | `Connection.backup()` and `VACUUM INTO` concurrently | copies pass `integrity_check`; each copy's posts count equals some committed page boundary (every `run_subreddits` page count matches its rows), never a partial page | threads | M1c | raw `shutil.copy` of `.db` while writing → fails `integrity_check` or misses WAL content → red | M | M |
| DB-42 | import_export_roundtrip_preserves_and_refuses | e2e | export zip from DB with counts a and a scrubbed canary | `insightminer import <zip>` into fresh DATA_DIR; then a zip whose `insightminer.db` fails `integrity_check` | `doctor` ok, counts == a, head + fingerprint ok, canary absent; bad zip → refused, target untouched | export fixture | M2 | integrity step removed → bad zip imported → red | M | M |

### A8. Snapshot golden, fingerprint, fixtures, reprocess, stamping (ranks 12, 15)

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-43 | runtime_fingerprint_agreement | e2e/gate | migrated tmp DB | `run`, `serve` startup, `doctor` | `fingerprint(live sqlite_master) == fingerprint(packaged schema.sql)` (one normalizer function, §D); `runs.schema_rev == alembic_version`, `app_version`, `praw_version` stamped | tmp DB | M0 | `ALTER TABLE posts ADD COLUMN junk INT` by hand → `run` exits 78 before any `runs` row; `doctor` red naming the fingerprint and the differing object | S | H |
| DB-44 | fixture_db_per_revision_upgrades_clean | migration | every `tests/fixtures/db/*.sqlite` found by glob | `alembic upgrade head` on a copy of each | `integrity_check` ok; `foreign_key_check` empty; each seeded `reddit_id` keeps its `pk`; docsize == live; `MATCH manifest.live_term` hits; scrubbed canary absent from file bytes; final DDL == `schema.sql`; per-table counts == manifest; columns NOT NULL at head have zero NULLs (backfill worked) | fixtures + manifests | M1a→ | fixture with NULLs in a column the new rev makes NOT NULL without backfill → migration fails → red; a table left unmigrated → DDL mismatch → red | M | H |
| DB-45 | fixture_set_equals_revision_set_and_every_table_seeded | gate | versions dir, fixtures dir | compare `alembic history` ids minus head with fixture stems; for each fixture iterate its `sqlite_master` tables | sets equal; every non-shadow table has ≥1 row (a new table never seeded is not tested with data) | none | M1a | add a migration without a fixture for the previous head → red; fixture with an empty table → red | S | H |
| DB-46 | downgrade_one_and_back_preserves_data | migration | head fixture with data | `downgrade -1` then `upgrade head` | counts, `pk`/`reddit_id` equal; docsize == live; DDL == golden; data the downgrade must drop is asserted absent explicitly (documented loss, not silent) | fixture | M1a | downgrade dropping a populated table without the documented-loss assertion → count mismatch → red | M | M |
| DB-47 | reprocess_from_raw_json_byte_identical | e2e | DB after fake run, all rows at `normalizer_version=N` | `db reprocess --all` | dump of normalized columns (all except `raw_json`, `pk`, `first_seen_at`, `last_fetched_at`, `scrubbed_at`, `next_check_at`, `check_stage`, `misses`) `ORDER BY pk` identical before/after; `normalizer_version` stamped; tombstone rows untouched | fake | M1a | one-character normalizer change (`.strip()` on title) → diff → red; reprocess touching a tombstone → red | M | H |
| DB-48 | rows_written_this_run_carry_current_normalizer_version | gate | fake run | post-run invariant | `count(*) WHERE last_fetched_at >= run.started_at AND normalizer_version IS NOT :current == 0` for posts and comments; `NORMALIZER_VERSION` assigned exactly once in the tree (AST scan) and all rows agree with it | fake | M1a | `info()` writer omitting the version → NULL rows → failed naming the column (the earlier project's 12,231 `schema_version=None` rows); second literal in a repo call → rows disagree → red | S | H |
| DB-49 | settings_fingerprint_changes_only_on_non_secret_change | e2e | runs 1–2 identical settings; run 3 budget changed; run 4 only `client_secret` changed | compare `runs.settings_fingerprint`; read digest 3 | r1 == r2; r3 != r2; r4 == r3; digest 3 names the changed key from the stored resolved-settings diff, not a template | fake | M1d | fingerprint including the secret → r4 != r3 → red; fingerprint ignoring budget → r3 == r2 → red | S | M |

### A9. Population floors, writer map, count invariants (ranks 5, 12)

| ID | Test name | Layer | Given | When | Then | Fixture / scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| DB-50 | population_floors_fail_the_run_and_name_the_column | gate/e2e | fake payload with `author_fullname` nested under a different key so the normalizer reads None | `run` | rows written; floor `author_fullname` non-null share < 95% → `status='failed'`, `error` names the column, share, and denominator; `selftext_html` on every self post and `permalink` on every row floors likewise | reshaped fixture | M1a | one floor disabled → `ok` → red | M | H |
| DB-51 | floors_scoped_by_normalizer_version_and_empty_population_fails | gate | fixture with 1k rows at `normalizer_version=1` lacking new column X; invariant "X present" introduced at version 2 | run under version 2; then `reprocess`; then a run where the scoped population is empty | invariant evaluates only rows `>= 2` → `ok`; after reprocess scope widens and still `ok`; denominator 0 → reported as `failed: no population`, never `ok` | fixture | M1a/M1c | unscoped invariant → day-one red where the test demands `ok`; empty population treated as pass → red | M | H |
| DB-52 | web_writer_map_enforced | gate/web | web engine with a `before_cursor_execute` listener (no `mock.patch`) | run the full route suite; parse target table of every INSERT/UPDATE/DELETE | targets ⊆ {subreddits, searches, themes, theme_rules, post_themes, ui_state, runs}; `runs` writes only insert `status='queued'` | TestClient suite | M2 | a route updating `posts.title` → red; a route setting `runs.status='ok'` → red | M | H |
| DB-53 | authors_counters_match_count | gate | fake run with authors, reruns, one account deletion | post-run invariant | per `authors` row: `post_count == count(live posts by author_fullname)`, `comment_count` likewise; `account_deleted` → no `authors` row; violation → failed | fake | M1c | counter incremented on every upsert (rerun) → drift → red | S | M |
| DB-54 | counters_equal_table_deltas | gate | fake run | post-run | `posts_new + posts_updated` == rows with `last_fetched_at >= start`; `comments_harvested` per post == actual; `raw_files.item_count` == JSONL line count; violation → failed | fake | M1a | counter incremented before a page commit that later fails → mismatch → failed | S | H |
| DB-55 | row_counts_never_decrease_without_recorded_purge | gate | two runs; between them `subs remove --delete-data` recording `rows_deleted` per table on its run row | post-run | decrease matched by a purge record → ok; unmatched decrease (rows deleted by hand) → failed | fake | M1c/M2 | hand `DELETE` between runs → failed | S | M |

**Rank coverage:** 1 → DB-18, 19 · 3 → DB-20–22 · 4 → DB-06, 07, 25 · 5 → DB-50, 51 · 7 → PC column on every row; DB-26, 39, 43 are gate rows · 10 → DB-11–16, 31 · 12 → DB-30, 37, 38, 44, 51 · 15 → DB-47–49 · 16 → DB-16, 36, 39, 40 · 25 → DB-34, 35.

---

## B. Fixture-database plan

**Where:** `tests/fixtures/db/<rev>.sqlite` + `<rev>.manifest.json`, one pair per Alembic revision except head. Discovered by glob (DB-44); the set is checked against `alembic history` (DB-45), so no hand-maintained list of fixtures exists.

**How generated:** `make fixture` runs `tests/fixtures/db/make_fixture.py` **from the codebase as it stands before the new migration is written**, i.e. when the current head is about to become "previous":
1. temp DATA_DIR; `alembic upgrade head` (the soon-to-be-old head);
2. `insightminer run --gateway fake --scenario fixture --seed 1234` twice with the clock advanced (so reruns, revisits, snapshots, and a scrub all happen through the real writer path: guard rule 5, probe as a real record presents);
3. `reconcile` with two items deleted and one account deleted in the fake; `tag`; one run left as stale `running`;
4. `wal_checkpoint(TRUNCATE)`; copy the DB to `<rev>.sqlite`; write the manifest.

The scenario is versioned (`fixture_v1`) and frozen; a new scenario version is added only when a new rev needs states the old one cannot express, and the old fixtures are never regenerated (they are historical artifacts, like the migrations).

**What each fixture contains** (asserted by DB-45's every-table-seeded scan and by the manifest):
- posts in every `content_state`, including a first-sight tombstone, a scrubbed `deleted_by_author` with tombstone `raw_json`, `removed_by_moderator`, `removed_by_reddit`, `gone_unconfirmed` (`misses=1`), `gone`; a live post whose author is `account_deleted`; a crosspost; a `stickied`; one row with an unknown `removed_by_category` value stored raw;
- comments: a tree of depth ≥ 4, an orphan (`parent_comment_pk NULL`), a `comment_more` stub, a scrubbed leaf;
- `post_sources` of both types; `item_snapshots` for revisited posts; `authors`; three themes with keyword/regex/flair rules and `post_themes`; `runs` in every status incl. stale `running`; `run_subreddits` with every `stop_reason`; `raw_files`, `raw_rejects`, `ui_state`, `backups` (rev 1 onward, §E.8);
- FTS populated; ~120 posts / ~600 comments, total file < 1 MB so the pre-commit size rule holds (a manifest field records size; DB-44 asserts it).

**Manifest:** `{rev, generated_at, sqlite_version, app_version, scenario, seed, table_counts{…}, canaries{live_term, scrubbed_term, deleted_author}, sha256, size_bytes}`. DB-44 uses `table_counts` and `canaries`; the scrubbed canary must be absent from the upgraded file's bytes, the live one must hit via `MATCH`.

**Not in the fixture:** raw JSONL files (`raw_files.path` targets do not exist). The upgrade test runs `db upgrade` + `db check` + `doctor --no-network`, never `run`, so the raw-file-exists invariant is out of scope there by design.

---

## C. Migration checklist (PR template block)

Each line names the test that verifies it.

1. `[ ]` Fixture for the current head generated from **pre-change** code and committed with its manifest — DB-44, DB-45
2. `[ ]` Migration is reversible, single chain, `render_as_batch` — DB-03
3. `[ ]` Batch op on `posts`/`comments`: `DROP VIEW posts_live` before, recreate view + the three triggers after, then FTS `'rebuild'` — DB-30, DB-44 (docsize == live, `MATCH` hits)
4. `[ ]` New NOT NULL column is expand/contract: nullable + backfill from `raw_json` (or two releases) — DB-44 zero-NULL assertion
5. `[ ]` `make schema` run; `schema.sql` diff reviewed in this PR — DB-01; fingerprint follows — DB-43
6. `[ ]` Models updated to match; `include_object` still excludes FTS/shadow/view — DB-02
7. `[ ]` Downgrade exercised with data; documented loss asserted explicitly — DB-46
8. `[ ]` `foreign_keys=OFF` issued outside the transaction; `foreign_key_check` empty after — DB-37
9. `[ ]` Any new invariant is scoped by `normalizer_version` or backfill flag; empty population fails — DB-51
10. `[ ]` Column semantics changed → `normalizer_version` bump and reprocess golden update in a **separate** PR — DB-47, DB-48
11. `[ ]` `db upgrade` run on a copy of the production DB; pre-migrate backup appeared first; `make check` summary pasted — DB-37 (manual drill line)
12. `[ ]` CHANGELOG line, SemVer minor bump, DATA_DICTIONARY regenerated — doc-currency test
13. `[ ]` Changed files under `tests/` listed with one-line reasons — working agreement

---

## D. `schema.sql`, the runtime fingerprint, and startup disagreement

**Generation (`make schema` → `python -m insightminer.db.schema_dump`):** fresh temp DB → `alembic upgrade head` using the real `env.py` → read `sqlite_master` rows with `type IN ('table','view','index','trigger')`, excluding `sqlite_%`, `_alembic_tmp_%`, and FTS shadow tables (`%_fts_data|_idx|_content|_docsize|_config`; their DDL is emitted by the FTS5 module and can vary by SQLite version, which would produce false alarms after a SQLite upgrade). Keep the virtual table's own `CREATE VIRTUAL TABLE`. Order: table → view → index → trigger, then name. Normalize whitespace outside quotes only; SQLite stores DDL text as written, so nothing else is rewritten. Header: `-- head: <rev>`. Because SQLite discards column comments, append a second section `-- COLUMN COMMENTS` emitted from SA metadata (`table.column: comment`); without it the "doubles as the data dictionary" claim is false (DB-09).

**Diff:** DB-01 regenerates and compares with `difflib.unified_diff`; the failure message is the diff. `schema.sql` is package data, shipped in the wheel/image.

**Fingerprint:** `sha256(normalize_ddl(rows))` where `normalize_ddl` is the **same function** the dump uses (single-sourced; a second implementation would be two guards on one field). Computed at runtime from the live DB and from the packaged `schema.sql`; no stored constant, so there is no second source to drift (the earlier project's schema-version literal copied into six producers). `runs.schema_rev` records the Alembic revision; `doctor` and `/healthz` print revision, live fingerprint, and expected fingerprint.

**Startup sequence (`run`, `serve`, `doctor`, every mutating command):**
1. open DB through `db.engine`; read `alembic_version`;
2. `alembic_version != head` → exit 78: "migrations pending; run `insightminer db upgrade` (backs up first)"; UI: `/system` shows **Apply pending migration**;
3. `== head` but fingerprint differs → exit 78 with the object-level diff in the log (names only in the notification): "schema does not match app version X: hand-edited or half-migrated. `db check --explain` · restore latest verified backup"; never auto-repair;
4. `serve` should not simply refuse (the operator surface would vanish): start in **maintenance-only mode** — red banner, `/system`, `/system/backups`, and `/healthz` only, all reads `mode=ro` — so a non-terminal operator can apply the migration or restore. `run` refuses outright.

---

## E. Judgements on the plan's database design

| # | Item | Verdict | Reason (one sentence) | Recommendation |
|---|---|---|---|---|
| 1 | "FTS row counts equal live row counts" invariant | Under-specified, currently a proxy | Verified: `SELECT count(*) FROM posts_fts` on an external-content table returns the content table's count and cannot go red. | **Add:** measure via `count(*) FROM posts_fts_docsize` (requires `columnsize` on) or a `MATCH` probe; DB-26 asserts the naive count stays green while the real one goes red. |
| 2 | `content='posts'` + live-gated triggers + "rebuild in the same migration" | Contradictory | Verified: `'rebuild'` re-indexes tombstone rowids and FTS `integrity-check` reports `malformed` under that design. | **Add:** `content='posts_live'` (view over `content_state='live'`), keep triggers on `posts`; rebuild and integrity-check become safe (DB-10, DB-30). |
| 3 | Batch migrations on `posts`/`comments` | Under-specified given #2 | Verified: the batch rename fails when a view references the table unless the view is dropped first or `legacy_alter_table=ON`. | **Add** checklist item 3 and DB-44's DDL assertion; prefer drop/recreate over the legacy pragma. |
| 4 | `max(pk) == count(*)` as a runtime post-run invariant | Over-reaching | It breaks after the first `subs remove --delete-data` and stays red forever. | **Simplify:** keep it in DB-20 (no purges in scenario); at runtime assert `max(pk) − count(*)` is non-increasing except in a run that records a purge (DB-55). |
| 5 | Fingerprint "recorded for the app version" | Under-specified, implies a stored constant | A stored constant is a second source of truth beside `schema.sql`. | **Simplify:** derive both sides from one normalizer (§D). |
| 6 | `PRAGMA foreign_keys=OFF during batch migrations` | Under-specified | The pragma is a no-op inside a transaction, and `transaction_per_migration=True` wraps each migration. | **Add:** env.py issues it before `begin_transaction()`; DB-37 asserts it reads 0 inside a migration. |
| 7 | "Deleted text must not survive anywhere" vs 7 daily + 4 weekly backups, 30-day JSONL, 3 pre-migrate copies | Contradictory | Backups made before a scrub hold the deleted content for up to ~4 weeks and nothing rewrites them. | **Owner decision (F.1):** document a backup retention window as the compliance bound, or shorten retention; DB-32 checks only the current run's backup. |
| 8 | `backups` table arrives with the "full" gate at M3 | Under-specified sequencing | A gate keyed on file existence between M1c and M3 is the proxy the guard rules forbid. | **Add:** `backups` table in schema rev 1; M1c gate keys on it from day one (DB-36, DB-39). |
| 9 | Column comments "so `schema.sql` doubles as the data dictionary" | Under-specified | SQLite does not persist comments, so a `sqlite_master` dump has none. | **Add:** metadata-derived comment section in the dump (§D, DB-09). |
| 10 | `raw_rejects.raw_json` | Under-specified | Rejects lack the id that would let scrub find them, so deleted content can persist there indefinitely. | **Add:** same 30-day retention as JSONL; sweep recorded on the run row. |
| 11 | `authors` counters "checked against COUNT(*)" | Under-specified | Live-only or all rows changes whether scrub must decrement. | **Add:** live-only (DB-53). |
| 12 | Coverage counters "amber vs trailing 7-run median" | Under-specified | The first seven runs have no median, so the check either silently passes or fails on day one. | **Add:** floors only until seven runs exist; state that in the digest. |
| 13 | `include_object` excludes `%_fts%` shadow tables | Under-specified | SA reflects the FTS virtual table itself as a table too, and views are reflected on some paths. | **Add:** exclude `%_fts`, `%_fts_%`, and `%_live` (DB-02 PC b). |
| 14 | Integer PK without `AUTOINCREMENT` | Judgement call | After a purge SQLite may reuse a freed rowid, and a stale FTS entry would then match a new row. | **Add** `AUTOINCREMENT` on `posts`/`comments` (cheap; owner confirm, F.3). |
| 15 | Stress scenario at 50k/500k weekly | Keep, lightly | The value is the `EXPLAIN QUERY PLAN` assertions (DB-08), not scale. | Keep. |
| 16 | Quarterly manual restore drill | Under-powered | A manual drill is the one gate here with no positive control and no CI run. | **Add:** `db restore --drill` into a temp dir weekly via launchd, result recorded in `backups` (DB-40/42 make it cheap). |

---

## F. Open questions for the owner

1. **Backup retention vs deletion compliance (E.7):** accept that `daily-*`/`weekly-*`/`pre-migrate-*` backups may hold deleted content for up to ~4 weeks (like the 30-day JSONL), shorten backup retention, or scrub-and-rewrite backups on reconcile (expensive)?
2. **Purge semantics for `subs remove --delete-data`:** hard-delete rows (frees rowids, changes the PK invariant per E.4) or mark-and-hide? This decides DB-55's shape.
3. **`AUTOINCREMENT` on `posts`/`comments` (E.14):** acceptable?
4. **`serve` under a fingerprint mismatch (§D.4):** maintenance-only mode, or refuse to start and rely on the CLI (contradicting "no routine operation requires a terminal")?
5. **Fixture size:** keep every fixture under the 1 MB pre-commit limit by design (small scenario), or exempt `tests/fixtures/db/` (a path list) — I recommend the former.
6. **Automated weekly restore drill (E.16):** approve a launchd job that restores the latest backup into a temp dir and records the result?
7. **Reprocess boundary (DB-47):** should `reprocess` be allowed to change `next_check_at`/`check_stage`, or are those strictly owned by the revisit ladder?
8. **`raw_rejects` retention (E.10):** 30 days like JSONL?
9. Do the earlier project's `DATABASE_SYSTEM_AND_INTEGRITY_REFERENCE.md` and `UPDATE_SEMANTICS.md` exist to share? They would likely settle F.2 and DB-21's ownership sets from precedent rather than judgement.
