---
paths:
  - "src/insightminer/db/**"
  - "tests/db/**"
---
# Database rules (load when a database file is edited)

Read first: `docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md` §1–§2 and `docs/runbook/RUNBOOK.md` § Migrate.

- Upserts are `INSERT … ON CONFLICT DO UPDATE`, never `INSERT OR REPLACE`; primary keys and `first_seen_at` never change on rerun.
- Every schema change ships a migration, a prior-revision fixture database under `tests/fixtures/db/`, and a regenerated `schema.sql` (`make schema`); batch migrations recreate the live-only views and triggers and rebuild the search index in the same migration.
- Search-index membership is counted from the `_docsize` shadow table, never `count(*)` on the index table.
- `create_engine`, `text()`, and the sqlite module are used only inside `db/`; the connection path sets the pragmas, and the database lives on a local filesystem, never a network share.
- The field-ownership table in `db/ownership.py` is the declaration; a value builder's key set must equal it.
