"""``services/doctor.py``: the no-network check list and the ``Check``/``DoctorReport``
contract ``/system`` will share (design-round5.md §3.3, §15, round5-findings.json G18).

``services/doctor.py`` does not exist yet -- every test here is expected to fail on
``ModuleNotFoundError`` until step 6 implements it.

Each of the twelve §15.2 checks is tested at the granular, per-check-function level (an "ok"
test and a "not-ok" test) so a check with only one branch tested is caught, per §15.2's own
closing sentence. ``lock_not_stale``'s six branches use the exact names §15.2 lists. A few
``run_checks``-level tests sit at the bottom for the CF-01 zero-HTTP contract and the doctor
report shape.

Local ``db_path`` / ``engine`` fixtures override ``tests/services/conftest.py``'s: doctor
reads a real data directory (``settings.data_dir``), not an arbitrary temp path, so these
point the database at ``settings.data_dir / "insightminer.db"`` -- the same file a real
``insightminer doctor`` invocation would open.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from insightminer.adapters.clock import FakeClock
from insightminer.adapters.reddit_fake import FakeRedditGateway
from insightminer.db import migrate as db_migrate
from insightminer.db import repo
from insightminer.db.engine import checkpoint_truncate, engine_for
from insightminer.db.schema_dump import SCHEMA_SQL, migrate_to_head
from insightminer.services import doctor, lock
from insightminer.settings import Settings

STALE_AFTER_SECONDS = 180  # settings.static.run.stale_after_minutes (3) * 60
MAX_RATE_LIMIT_WAIT_SECONDS = 300  # core.retry.MAX_RATE_LIMIT_WAIT_SECONDS, mirrored here


# --- local db_path / engine: inside settings.data_dir, not an arbitrary temp path -------------


@pytest.fixture
def db_path(settings: Settings) -> Path:
    return settings.data_dir / "insightminer.db"


@pytest.fixture
def engine(db_path: Path) -> Iterator[Engine]:
    eng = engine_for(db_path)
    try:
        migrate_to_head(eng)
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def lock_path(settings: Settings) -> Path:
    return settings.data_dir / "locks" / "collector.lock"


def _plant_run(
    engine: Engine,
    *,
    status: str,
    now: int,
    pid: int | None = None,
    heartbeat_at: int | None = None,
    stage: str | None = None,
    kind: str = "run",
) -> int:
    """Insert one ``runs`` row through ``repo.insert_run`` -- the same function the
    production lifecycle uses, never a raw ``INSERT`` (§2.3)."""
    run = repo.RunInsert(
        kind=kind,
        trigger="cli",
        status=status,
        created_at=now,
        started_at=now,
        pid=pid,
        stage=stage,
        options_json=None,
        app_version=None,
        praw_version=None,
        schema_rev=None,
        settings_fingerprint=None,
        log_path=None,
    )
    with engine.begin() as conn:
        pk = repo.insert_run(conn, run)
        if heartbeat_at is not None:
            repo.touch_run(conn, run_pk=pk, heartbeat_at=heartbeat_at, stage=stage)
    return pk


def _plant_ok_run(engine: Engine, *, now: int, finished_at: int) -> int:
    pk = _plant_run(engine, status="running", now=now)
    with engine.begin() as conn:
        repo.finish_run(
            conn,
            run_pk=pk,
            status="ok",
            finished_at=finished_at,
            counters_json="{}",
            api_requests=0,
            error=None,
            violations_json=None,
        )
    return pk


# --- Check / DoctorReport, and parse_duration (§3.3, §15.1) -----------------------------------


def test_doctor_report_ok_is_true_only_when_no_error_severity_check_failed() -> None:
    healthy = doctor.DoctorReport(
        checks=(
            doctor.Check(name="a", ok=True, detail="fine", severity=doctor.CheckSeverity.ERROR),
            doctor.Check(name="b", ok=False, detail="meh", severity=doctor.CheckSeverity.WARNING),
        )
    )
    assert healthy.ok is True
    assert healthy.exit_code == 0

    broken = doctor.DoctorReport(
        checks=(
            doctor.Check(name="a", ok=False, detail="bad", severity=doctor.CheckSeverity.ERROR),
        )
    )
    assert broken.ok is False
    assert broken.exit_code == 1


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("36h", 36 * 3600), ("90m", 90 * 60), ("2d", 2 * 86400), ("45s", 45)],
)
def test_parse_duration_reads_the_documented_units(text: str, seconds: int) -> None:
    assert doctor.parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "36", "h36", "36x", "-5h", "36.5h"])
def test_parse_duration_rejects_anything_else(text: str) -> None:
    with pytest.raises(ValueError, match=r".+"):
        doctor.parse_duration(text)


# --- settings_valid: ERROR (§15.2) -------------------------------------------------------------


def test_check_settings_valid_is_ok_for_a_good_environment() -> None:
    check = doctor.check_settings_valid()
    assert check.ok is True
    assert check.name == "settings_valid"
    assert check.severity == doctor.CheckSeverity.ERROR


def test_check_settings_valid_is_not_ok_for_a_broken_static_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check constructs its own ``Settings()`` from the live environment, so a bad
    static key is caught here -- the same failure an operator would hit -- rather than only
    by whatever already built a ``Settings`` before ``doctor`` ran."""
    monkeypatch.setenv("INSIGHTMINER_STATIC__RUN__STALE_AFTER_MINUTES", "-1")
    check = doctor.check_settings_valid()
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


# --- data_dir_writable: ERROR --------------------------------------------------------------


def test_check_data_dir_writable_is_ok_for_the_isolated_data_dir(settings: Settings) -> None:
    check = doctor.check_data_dir_writable(settings.data_dir)
    assert check.ok is True
    assert check.name == "data_dir_writable"


def test_check_data_dir_writable_is_not_ok_when_it_cannot_be_created(tmp_path: Path) -> None:
    """A file where a directory needs to be: ``mkdir`` fails regardless of permission bits,
    which keeps this test meaningful even when tests run as root."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    unwritable = blocker / "data"

    check = doctor.check_data_dir_writable(unwritable)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


# --- data_dir_outside_tcc: ERROR ------------------------------------------------------------


def test_check_data_dir_outside_tcc_is_ok_for_an_ordinary_path(settings: Settings) -> None:
    check = doctor.check_data_dir_outside_tcc(settings.data_dir)
    assert check.ok is True
    assert check.name == "data_dir_outside_tcc"


@pytest.mark.parametrize(
    "relative",
    [
        Path("Desktop", "insightminer"),
        Path("Documents", "insightminer"),
        Path("Downloads", "insightminer"),
        Path("Library", "Mobile Documents", "com~apple~CloudDocs", "insightminer"),
    ],
)
def test_check_data_dir_outside_tcc_is_not_ok_under_a_protected_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: Path
) -> None:
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))
    data_dir = fake_home / relative
    data_dir.mkdir(parents=True)

    check = doctor.check_data_dir_outside_tcc(data_dir)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


# --- database_present: ERROR -----------------------------------------------------------------


def test_check_database_present_is_ok_for_a_migrated_database(
    engine: Engine, db_path: Path
) -> None:
    check = doctor.check_database_present(db_path)
    assert check.ok is True
    assert check.name == "database_present"


def test_check_database_present_is_not_ok_when_the_file_is_missing(tmp_path: Path) -> None:
    check = doctor.check_database_present(tmp_path / "no-such.db")
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


# --- alembic_at_head: ERROR -------------------------------------------------------------------


def test_check_alembic_at_head_is_ok_at_head(engine: Engine) -> None:
    check = doctor.check_alembic_at_head(engine)
    assert check.ok is True
    assert check.name == "alembic_at_head"


def test_check_alembic_at_head_is_not_ok_one_revision_behind(engine: Engine) -> None:
    db_migrate.downgrade_one(engine)
    check = doctor.check_alembic_at_head(engine)
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR
    assert db_migrate.head_revision() in check.detail


# --- quick_check: ERROR -----------------------------------------------------------------------


def test_check_quick_check_is_ok_for_a_healthy_database(engine: Engine, db_path: Path) -> None:
    checkpoint_truncate(engine)
    check = doctor.check_quick_check(db_path)
    assert check.ok is True
    assert check.name == "quick_check"


def test_check_quick_check_is_not_ok_for_a_corrupt_file(engine: Engine, db_path: Path) -> None:
    """The whole of page 1 after the 100-byte file header, not a 256-byte nibble of it.

    Measured on this tree: overwriting bytes 200..456 leaves ``PRAGMA quick_check``
    reporting ``ok`` -- that region is free space inside the schema page, so the nibble
    corrupts nothing and the test would pass against a check that always answered ``ok``.
    Overwriting the schema page proper is what SQLite actually calls malformed.
    """
    checkpoint_truncate(engine)
    engine.dispose()
    with db_path.open("r+b") as handle:
        handle.seek(100)
        handle.write(b"\xff" * 4096)

    check = doctor.check_quick_check(db_path)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


# --- schema_fingerprint: WARNING (G18) ---------------------------------------------------------


def test_check_schema_fingerprint_is_ok_at_head(engine: Engine) -> None:
    check = doctor.check_schema_fingerprint(engine)
    assert check.ok is True
    assert check.name == "schema_fingerprint"
    assert check.severity == doctor.CheckSeverity.WARNING


def test_schema_fingerprint_mismatch_is_a_warning_not_an_error(engine: Engine) -> None:
    """G18 (round5-findings.json / adversarial A9): a schema drift is surfaced, but it must
    never make ``doctor`` exit 1 on its own -- ``schema_fingerprint`` is WARNING-severity."""
    assert SCHEMA_SQL.is_file()
    probe = sa.Table("_doctor_probe", sa.MetaData(), sa.Column("id", sa.Integer))
    with engine.begin() as conn:
        conn.execute(sa.schema.CreateTable(probe))

    check = doctor.check_schema_fingerprint(engine)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING
    report = doctor.DoctorReport(checks=(check,))
    assert report.ok is True
    assert report.exit_code == 0


# --- free_disk: WARNING, 1 GiB constant (Wes's Q6) ---------------------------------------------


def test_check_free_disk_is_ok_with_plenty_of_room(tmp_path: Path) -> None:
    check = doctor.check_free_disk(tmp_path)
    assert check.ok is True
    assert check.severity == doctor.CheckSeverity.WARNING


def test_check_free_disk_is_not_ok_below_one_gibibyte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Usage:
        total = 10**12
        used = 10**12 - 1
        free = 1024  # far below MIN_FREE_BYTES

    monkeypatch.setattr(shutil, "disk_usage", lambda _path: _Usage())

    check = doctor.check_free_disk(tmp_path)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING


def test_min_free_bytes_is_one_gibibyte_and_not_a_settings_key() -> None:
    """Wes's Q6: free disk is a constant in ``doctor.py``, not a settings key."""
    assert doctor.MIN_FREE_BYTES == 1024**3


# --- last_run_age: ERROR, except "no successful run yet" (Wes's Q5) ---------------------------


def test_check_last_run_age_is_ok_within_the_window(engine: Engine, now: int) -> None:
    _plant_ok_run(engine, now=now, finished_at=now - 3600)
    with engine.connect() as conn:
        check = doctor.check_last_run_age(conn, now=now, max_age_seconds=36 * 3600)
    assert check.ok is True
    assert check.name == "last_run_age"
    assert check.severity == doctor.CheckSeverity.ERROR


def test_check_last_run_age_is_not_ok_when_stale(engine: Engine, now: int) -> None:
    _plant_ok_run(engine, now=now - 40 * 3600, finished_at=now - 40 * 3600)
    with engine.connect() as conn:
        check = doctor.check_last_run_age(conn, now=now, max_age_seconds=36 * 3600)
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


def test_check_last_run_age_with_no_successful_run_is_a_warning_not_an_error(
    engine: Engine, now: int
) -> None:
    """Wes's Q5: a fresh install has no successful run yet, and that must not report
    ``doctor`` as failing -- so this one branch of an ERROR-severity check is WARNING."""
    with engine.connect() as conn:
        check = doctor.check_last_run_age(conn, now=now, max_age_seconds=36 * 3600)
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING
    report = doctor.DoctorReport(checks=(check,))
    assert report.ok is True


# --- credentials_present: WARNING, presence only ------------------------------------------------


def test_check_credentials_present_is_ok_when_all_three_are_set(
    monkeypatch: pytest.MonkeyPatch, isolated_data_dir: Path
) -> None:
    monkeypatch.setenv("INSIGHTMINER_REDDIT_CLIENT_ID", "abc")
    monkeypatch.setenv("INSIGHTMINER_REDDIT_CLIENT_SECRET", "def")
    monkeypatch.setenv("INSIGHTMINER_REDDIT_USERNAME", "wes")
    filled = Settings()

    check = doctor.check_credentials_present(filled)

    assert check.ok is True
    assert check.severity == doctor.CheckSeverity.WARNING


def test_check_credentials_present_is_not_ok_when_any_is_blank(settings: Settings) -> None:
    """``settings`` resolves with empty credentials by default (§conftest); presence is
    checked, never validity."""
    check = doctor.check_credentials_present(settings)
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING


# --- no_stale_running_rows: WARNING, the reader-side mirror of §12.2 ---------------------------


def test_check_no_stale_running_rows_is_ok_with_none_running(engine: Engine, now: int) -> None:
    with engine.connect() as conn:
        check = doctor.check_no_stale_running_rows(
            conn, now=now, stale_after_seconds=STALE_AFTER_SECONDS
        )
    assert check.ok is True
    assert check.severity == doctor.CheckSeverity.WARNING


def test_check_no_stale_running_rows_is_ok_for_a_fresh_live_pid(engine: Engine, now: int) -> None:
    _plant_run(engine, status="running", now=now, pid=1, heartbeat_at=now)
    with engine.connect() as conn:
        check = doctor.check_no_stale_running_rows(
            conn, now=now, stale_after_seconds=STALE_AFTER_SECONDS
        )
    assert check.ok is True


def test_check_no_stale_running_rows_is_not_ok_for_a_dead_pid(engine: Engine, now: int) -> None:
    _plant_run(engine, status="running", now=now, pid=2**31 - 1, heartbeat_at=now)
    with engine.connect() as conn:
        check = doctor.check_no_stale_running_rows(
            conn, now=now, stale_after_seconds=STALE_AFTER_SECONDS
        )
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING


def test_check_no_stale_running_rows_is_not_ok_for_an_old_heartbeat(
    engine: Engine, now: int
) -> None:
    _plant_run(engine, status="running", now=now, pid=1, heartbeat_at=now - STALE_AFTER_SECONDS - 1)
    with engine.connect() as conn:
        check = doctor.check_no_stale_running_rows(
            conn, now=now, stale_after_seconds=STALE_AFTER_SECONDS
        )
    assert check.ok is False


# --- lock_not_stale: the six named branches (§15.2, exactly as spelled there) ------------------


def test_lock_not_stale_is_ok_when_the_lock_is_free(
    engine: Engine, lock_path: Path, now: int
) -> None:
    with engine.connect() as conn:
        check = doctor.check_lock_not_stale(
            conn, lock_path=lock_path, now=now, stale_after_seconds=STALE_AFTER_SECONDS
        )
    assert check.ok is True
    assert check.name == "lock_not_stale"
    assert check.severity == doctor.CheckSeverity.WARNING


def test_lock_not_stale_is_ok_while_a_live_run_holds_it(
    engine: Engine, lock_path: Path, now: int
) -> None:
    _plant_run(engine, status="running", now=now, pid=os.getpid(), heartbeat_at=now)

    with lock.acquire(lock_path):
        with engine.connect() as conn:
            check = doctor.check_lock_not_stale(
                conn, lock_path=lock_path, now=now, stale_after_seconds=STALE_AFTER_SECONDS
            )

    assert check.ok is True


def test_lock_not_stale_is_ok_during_a_declared_rate_wait(
    engine: Engine, lock_path: Path, now: int
) -> None:
    """Clause D2: a heartbeat older than the stale window but still inside the
    ``MAX_RATE_LIMIT_WAIT_SECONDS`` bound, carrying a ``rate_wait:Ns`` stage, is not stale."""
    age = STALE_AFTER_SECONDS + 50  # past D1's window, well inside D2's wider bound
    assert age < MAX_RATE_LIMIT_WAIT_SECONDS + STALE_AFTER_SECONDS
    _plant_run(
        engine,
        status="running",
        now=now,
        pid=os.getpid(),
        heartbeat_at=now - age,
        stage="rate_wait:120s",
    )

    with lock.acquire(lock_path):
        with engine.connect() as conn:
            check = doctor.check_lock_not_stale(
                conn, lock_path=lock_path, now=now, stale_after_seconds=STALE_AFTER_SECONDS
            )

    assert check.ok is True


def test_lock_held_without_a_running_row_is_not_ok(
    engine: Engine, lock_path: Path, now: int
) -> None:
    with lock.acquire(lock_path):
        with engine.connect() as conn:
            check = doctor.check_lock_not_stale(
                conn, lock_path=lock_path, now=now, stale_after_seconds=STALE_AFTER_SECONDS
            )

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING


def test_lock_held_by_a_dead_pid_is_not_ok(engine: Engine, lock_path: Path, now: int) -> None:
    dead_pid = 2**31 - 1
    _plant_run(engine, status="running", now=now, pid=dead_pid, heartbeat_at=now)

    with lock.acquire(lock_path):
        with engine.connect() as conn:
            check = doctor.check_lock_not_stale(
                conn, lock_path=lock_path, now=now, stale_after_seconds=STALE_AFTER_SECONDS
            )

    assert check.ok is False
    assert str(dead_pid) in check.detail


def test_lock_held_with_a_stale_heartbeat_is_not_ok_and_names_the_age(
    engine: Engine, lock_path: Path, now: int
) -> None:
    age = STALE_AFTER_SECONDS + 232
    _plant_run(engine, status="running", now=now, pid=os.getpid(), heartbeat_at=now - age)

    with lock.acquire(lock_path):
        with engine.connect() as conn:
            check = doctor.check_lock_not_stale(
                conn, lock_path=lock_path, now=now, stale_after_seconds=STALE_AFTER_SECONDS
            )

    assert check.ok is False
    assert str(age) in check.detail


# --- CF-01 (doctor half): zero HTTP, structurally ----------------------------------------------


def test_doctor_no_network_makes_zero_http(
    fake: FakeRedditGateway, settings: Settings, clock: FakeClock
) -> None:
    """§15.2 closing paragraph: ``run_checks`` never touches ``gateway`` when
    ``no_network=True`` (the tranche-A default) -- proven against a routeless fake."""
    report = doctor.run_checks(settings=settings, clock=clock, gateway=fake, no_network=True)

    assert isinstance(report, doctor.DoctorReport)
    assert fake.requests_made == 0
    assert fake.calls == []


def test_config_validate_makes_zero_http(fake: FakeRedditGateway, settings: Settings) -> None:
    """``config validate`` runs only ``settings_valid`` (§15.1); the check takes no gateway
    parameter at all, so a routeless fake sitting untouched in the test proves it."""
    check = doctor.check_settings_valid()

    assert check.name == "settings_valid"
    assert fake.requests_made == 0
    assert fake.calls == []


# --- run_checks: the whole list, in the order §15.2 gives it -----------------------------------


def test_run_checks_covers_every_documented_check_name(
    engine: Engine, settings: Settings, clock: FakeClock, now: int
) -> None:
    _plant_ok_run(engine, now=now, finished_at=now)

    report = doctor.run_checks(settings=settings, clock=clock, gateway=None, no_network=True)

    names = [check.name for check in report.checks]
    assert names == [
        "settings_valid",
        "data_dir_writable",
        "data_dir_outside_tcc",
        "database_present",
        "alembic_at_head",
        "quick_check",
        "schema_fingerprint",
        "free_disk",
        "last_run_age",
        "lock_not_stale",
        "credentials_present",
        "no_stale_running_rows",
    ]


def test_run_checks_is_ok_for_a_freshly_initialized_data_dir(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    """A `db init`-then-nothing-else data dir: no successful run, no credentials, no stale
    rows, lock free. Every failing check here must be WARNING, never ERROR (Wes's Q5)."""
    report = doctor.run_checks(settings=settings, clock=clock, gateway=None, no_network=True)

    failing_error_checks = [
        check.name
        for check in report.checks
        if not check.ok and check.severity == doctor.CheckSeverity.ERROR
    ]
    assert failing_error_checks == []
    assert report.ok is True
    assert report.exit_code == 0


# --- free_disk's other not-ok branch: a filesystem that will not answer ----------------------


def test_check_free_disk_is_not_ok_when_free_space_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse(_path: Path) -> object:
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(shutil, "disk_usage", _refuse)

    check = doctor.check_free_disk(tmp_path)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING
