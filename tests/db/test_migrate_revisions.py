"""Revision 0002: upgrade/downgrade correctness and the §10.4 batch-recreate cascade.

Step 1 landed the upgrade/downgrade/cascade half, driving Alembic directly through
``schema_dump.alembic_config`` / ``migrate_to_head``. Step 2 adds the revision-query
helpers -- ``current_revision`` / ``head_revision`` / ``is_at_head`` / ``pending`` -- that
live in ``db/migrate.py`` (design-round5.md §10.2), and the T12 post-restore bookkeeping
that moved there from ``services/migrate.py`` in round 5 (P1-t12-sql-in-services).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, func, insert, select, text
from sqlalchemy.exc import OperationalError

from insightminer.db.backup import BackupResult
from insightminer.db.engine import engine_for
from insightminer.db.migrate import (
    MigrationsPendingError,
    current_revision,
    downgrade_one,
    finish_restored_run,
    head_revision,
    is_at_head,
    pending,
    require_head,
    upgrade_head,
)
from insightminer.db.repo import finish_run
from insightminer.db.schema import Base
from insightminer.db.schema_dump import alembic_config, migrate_to_head

NOW = 1_800_000_000

#: The pre-0002 CHECK constraint text, reproduced here (not imported: a migration test must
#: not depend on the very migration module it is exercising for its expected shape).
_PRE_0002_STATUSES = (
    "queued",
    "running",
    "ok",
    "partial",
    "failed",
    "rate_limited",
    "skipped_locked",
    "crashed",
    "cancelled",
)
_POST_0002_STATUSES = (*_PRE_0002_STATUSES, "network")


def _seed_run_with_children(engine: Engine) -> tuple[int, int, int]:
    """One subreddit-linked run with one ``run_subreddits`` and one ``raw_rejects`` child.

    Returns ``(run_pk, run_subreddits_pk, raw_rejects_pk)``.
    """
    t = Base.metadata.tables
    with engine.begin() as conn:
        workspace_pk = conn.execute(
            select(t["workspaces"].c.pk).where(t["workspaces"].c.slug == "premiere")
        ).scalar_one()
        subreddit_pk = conn.execute(
            insert(t["subreddits"]).values(
                workspace_pk=workspace_pk,
                name_lower="cascade",
                display_name="cascade",
                added_at=NOW,
            )
        ).inserted_primary_key[0]
        run_pk = conn.execute(
            insert(t["runs"]).values(kind="run", trigger="cli", status="running", created_at=NOW)
        ).inserted_primary_key[0]
        rs_pk = conn.execute(
            insert(t["run_subreddits"]).values(
                run_pk=run_pk, subreddit_pk=subreddit_pk, stop_reason="exhausted"
            )
        ).inserted_primary_key[0]
        rr_pk = conn.execute(
            insert(t["raw_rejects"]).values(
                run_pk=run_pk, raw_json="{}", error="missing created_utc", created_at=NOW
            )
        ).inserted_primary_key[0]
    return int(run_pk), int(rs_pk), int(rr_pk)


def _table_count(conn: sa.Connection, name: str) -> int:
    return int(
        conn.execute(select(func.count()).select_from(Base.metadata.tables[name])).scalar_one()
    )


def test_upgrade_0001_to_0002_keeps_every_run_row_and_every_child(tmp_path: Path) -> None:
    """§10.4 step 1 assertion 3: every ``runs``/``run_subreddits``/``raw_rejects`` row and pk
    survives the 0001 -> 0002 upgrade, ``foreign_key_check`` stays empty, and ``ck_runs_trigger``
    is still present and still named -- proof that ``db/migrations/env.py::_set_foreign_keys``
    protects the real upgrade path (the positive control below shows what happens without it).
    """
    engine = engine_for(tmp_path / "upgrade.db")
    try:
        migrate_to_head(engine)  # currently lands on 0001, the only revision that exists
        run_pk, rs_pk, rr_pk = _seed_run_with_children(engine)

        cfg = alembic_config()
        cfg.attributes["connection"] = engine
        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert head == "0002", "revision 0002 has not landed yet"

            assert _table_count(conn, "runs") == 1
            assert _table_count(conn, "run_subreddits") == 1
            assert _table_count(conn, "raw_rejects") == 1
            assert conn.execute(text("SELECT pk FROM runs")).scalar_one() == run_pk
            assert conn.execute(text("SELECT pk FROM run_subreddits")).scalar_one() == rs_pk
            assert conn.execute(text("SELECT pk FROM raw_rejects")).scalar_one() == rr_pk
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []

        insp = sa.inspect(engine)
        check_names = {c["name"] for c in insp.get_check_constraints("runs")}
        assert check_names == {"ck_runs_status", "ck_runs_trigger"}
    finally:
        engine.dispose()


def test_a_batch_recreate_with_foreign_keys_on_would_cascade(tmp_path: Path) -> None:
    """Positive control for the test above and for ``env.py::_set_foreign_keys``.

    Reproduces §10.4 trace A directly: the same ``batch_alter_table`` shape 0002 needs
    (add a nullable column, replace the ``status`` CHECK) run with ``foreign_keys`` left ON
    -- ``engine_for``'s default on every connection -- rather than switched off first, the
    way ``env.py`` does for a real migration. SQLite's batch recreate is CREATE-new ->
    INSERT-SELECT -> DROP-old -> RENAME; ``runs``' two ``ON DELETE CASCADE`` children vanish
    because the DROP cascades, and ``PRAGMA foreign_key_check`` stays clean afterwards
    because they were deleted, not orphaned -- which is exactly why a foreign-key-check-only
    assertion (round 3's) cannot see this defect.
    """
    engine = engine_for(tmp_path / "positive_control.db")
    try:
        migrate_to_head(engine)
        _run_pk, _rs_pk, _rr_pk = _seed_run_with_children(engine)

        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1, (
                "engine_for enables foreign_keys=ON on every connection by default"
            )
            before = {
                name: _table_count(conn, name) for name in ("runs", "run_subreddits", "raw_rejects")
            }

            migration_ctx = MigrationContext.configure(conn)
            ops = Operations(migration_ctx)
            with ops.batch_alter_table("runs") as batch:
                batch.add_column(sa.Column("_cascade_probe", sa.Text(), nullable=True))
                batch.drop_constraint("ck_runs_status", type_="check")
                batch.create_check_constraint(
                    "ck_runs_status",
                    "status IN (" + ", ".join(f"'{v}'" for v in _POST_0002_STATUSES) + ")",
                )
            conn.commit()

            after = {
                name: _table_count(conn, name) for name in ("runs", "run_subreddits", "raw_rejects")
            }
            fk_check = conn.exec_driver_sql("PRAGMA foreign_key_check").all()

        assert before == {"runs": 1, "run_subreddits": 1, "raw_rejects": 1}
        assert after == {"runs": 1, "run_subreddits": 0, "raw_rejects": 0}, (
            "trace A (§10.4): the recreate cascades the CASCADE children even though nothing "
            "explicitly deleted them"
        )
        assert fk_check == [], "the children were deleted, not orphaned -- fk_check cannot see this"
    finally:
        engine.dispose()


def test_downgrade_rewrites_network_rows_to_failed(tmp_path: Path) -> None:
    """DB-46 data half: a ``network`` row reads ``failed`` after downgrade, the row count is
    unchanged, ``violations_json`` is dropped, and re-upgrading does **not** restore
    ``network`` -- the rewrite is one-way, as revision 0002's own docstring says.
    """
    engine = engine_for(tmp_path / "downgrade.db")
    try:
        migrate_to_head(engine)
        cfg = alembic_config()
        cfg.attributes["connection"] = engine
        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert head == "0002", "revision 0002 has not landed yet"

        t = Base.metadata.tables
        with engine.begin() as conn:
            network_pk = conn.execute(
                insert(t["runs"]).values(
                    kind="run",
                    trigger="cli",
                    status="network",
                    created_at=NOW,
                    violations_json='{"counters_equal_table_deltas": "..."}',
                )
            ).inserted_primary_key[0]
            other_pk = conn.execute(
                insert(t["runs"]).values(kind="run", trigger="cli", status="ok", created_at=NOW)
            ).inserted_primary_key[0]

        command.downgrade(cfg, "0001")

        with engine.connect() as conn:
            rows = {
                pk: status for pk, status in conn.execute(text("SELECT pk, status FROM runs")).all()
            }
        assert rows == {network_pk: "failed", other_pk: "ok"}
        assert len(rows) == 2, "the rewrite must not add or remove rows"

        with engine.connect() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(runs)")).all()}
        assert "violations_json" not in cols

        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            restored_status = conn.execute(
                text("SELECT status FROM runs WHERE pk = :pk"), {"pk": network_pk}
            ).scalar_one()
        assert restored_status == "failed", "re-upgrading must not resurrect 'network' (one-way)"
    finally:
        engine.dispose()


# --- db/migrate.py: current / head / is_at_head / pending (step 2, §10.2) ------------------


def test_head_revision_is_0002() -> None:
    """``head_revision`` reads the ScriptDirectory, not a constant somebody can forget."""
    assert head_revision() == "0002"


def test_current_revision_is_none_before_any_migration(tmp_path: Path) -> None:
    engine = engine_for(tmp_path / "fresh.db")
    try:
        assert current_revision(engine) is None
    finally:
        engine.dispose()


def test_current_revision_after_upgrade_equals_head(tmp_path: Path) -> None:
    engine = engine_for(tmp_path / "upgraded.db")
    try:
        upgrade_head(engine)
        assert current_revision(engine) == head_revision() == "0002"
    finally:
        engine.dispose()


def test_is_at_head_reflects_current_state(tmp_path: Path) -> None:
    engine = engine_for(tmp_path / "state.db")
    try:
        assert is_at_head(engine) is False, "no schema at all is not 'at head'"
        upgrade_head(engine)
        assert is_at_head(engine) is True

        cfg = alembic_config()
        cfg.attributes["connection"] = engine
        command.downgrade(cfg, "0001")
        assert is_at_head(engine) is False
    finally:
        engine.dispose()


def test_pending_lists_revisions_between_current_and_head(tmp_path: Path) -> None:
    engine = engine_for(tmp_path / "pending.db")
    try:
        upgrade_head(engine)
        cfg = alembic_config()
        cfg.attributes["connection"] = engine
        command.downgrade(cfg, "0001")

        assert pending(engine) == ["0002"]
        upgrade_head(engine)
        assert pending(engine) == []
    finally:
        engine.dispose()


def test_require_head_raises_migrations_pending_error_when_behind(tmp_path: Path) -> None:
    engine = engine_for(tmp_path / "behind.db")
    try:
        upgrade_head(engine)
        cfg = alembic_config()
        cfg.attributes["connection"] = engine
        command.downgrade(cfg, "0001")

        with pytest.raises(MigrationsPendingError):
            require_head(engine)

        upgrade_head(engine)
        require_head(engine)  # does not raise once at head
    finally:
        engine.dispose()


def test_downgrade_one_steps_back_exactly_one_revision(tmp_path: Path) -> None:
    engine = engine_for(tmp_path / "one_step.db")
    try:
        upgrade_head(engine)
        downgrade_one(engine)
        assert current_revision(engine) == "0001"
    finally:
        engine.dispose()


# --- T12: the post-restore bookkeeping lives here, not in services/ (round-5 P1) -----------


def _database_at_0001(path: Path) -> Engine:
    engine = engine_for(path)
    cfg = alembic_config()
    cfg.attributes["connection"] = engine
    command.upgrade(cfg, "0001")
    return engine


def test_finish_restored_run_writes_only_columns_the_restored_revision_has(
    tmp_path: Path,
) -> None:
    """§10.3 T12. The restored file is at the PRE-migration revision, so the bookkeeping is
    built from ``sa.table``/``sa.column`` naming the four ``runs`` and eight ``backups``
    columns revision 0001 already has -- never from ``db/repo.py``, whose statements are
    built from the head models. The second half is the positive control: ``repo.finish_run``
    against the same file raises ``no such column: violations_json``, which is exactly the
    failure round 4's shape hit on every failed 0001 -> 0002 upgrade, and which -- sharing
    one transaction with the ``backups`` insert -- took the ``backups`` row down with it.
    """
    db_path = tmp_path / "restored.db"
    dest = tmp_path / "pre-migrate-0001-0002-20260913T120000Z.db"
    engine = _database_at_0001(db_path)
    try:
        with engine.begin() as conn:
            run_pk = conn.execute(
                insert(Base.metadata.tables["runs"]).values(
                    kind="db_upgrade", trigger="cli", status="running", created_at=NOW
                )
            ).inserted_primary_key[0]

        backup = BackupResult(path=dest, sha256="a" * 64, size_bytes=4096, integrity="ok")
        finish_restored_run(
            engine,
            run_pk=int(run_pk),
            backup=backup,
            dest=dest,
            frm="0001",
            table_counts_json='{"posts": 0}',
            now=NOW + 5,
        )

        with engine.connect() as conn:
            run_row = conn.execute(
                text("SELECT status, finished_at, error FROM runs WHERE pk = :pk"), {"pk": run_pk}
            ).one()
            backup_row = conn.execute(
                text(
                    "SELECT path, sha256, size_bytes, integrity, kind, created_at, schema_rev, "
                    "table_counts_json FROM backups"
                )
            ).one()
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(runs)")).all()}

        assert "violations_json" not in columns, "the fixture must be at revision 0001"
        assert run_row.status == "failed"
        assert run_row.finished_at == NOW + 5
        assert run_row.error == f"migration failed, restored from {dest}"
        assert backup_row == (
            str(dest),
            "a" * 64,
            4096,
            "ok",
            "pre-migrate",
            NOW + 5,
            "0001",
            '{"posts": 0}',
        )

        # Positive control: the head-model write the rule forbids really does fail here.
        with pytest.raises(OperationalError, match="no such column: violations_json"):
            with engine.begin() as conn:
                finish_run(
                    conn,
                    run_pk=int(run_pk),
                    status="failed",
                    finished_at=NOW + 5,
                    counters_json="{}",
                    api_requests=0,
                    error="x",
                    violations_json=None,
                )
    finally:
        engine.dispose()
