"""Revision 0002: upgrade/downgrade correctness and the §10.4 batch-recreate cascade.

Only the upgrade/downgrade/cascade half of this module lands in step 1; the
revision-query helpers (``current``/``head``/``is_at_head``/``pending``) that will live in
``db/migrate.py`` arrive in step 2 and get their own tests there.

Every test here drives Alembic directly through ``schema_dump.alembic_config`` /
``migrate_to_head`` rather than through ``db.migrate`` (which does not exist yet), and
builds every row through ``Base.metadata.tables[...]`` Core statements -- ``tests/db/**``
is on the ``TID251`` ignore list, but nothing here needs ``text()`` for DML.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, func, insert, select, text

from insightminer.db.engine import engine_for
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
