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
point the database at ``settings.data_dir / "threaddigest.db"`` -- the same file a real
``threaddigest doctor`` invocation would open.
"""

from __future__ import annotations

import os
import shlex
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from threaddigest.adapters.clock import FakeClock
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.db import migrate as db_migrate
from threaddigest.db import repo
from threaddigest.db.engine import checkpoint_truncate, engine_for
from threaddigest.db.schema_dump import SCHEMA_SQL, migrate_to_head
from threaddigest.ports import AuthFailed
from threaddigest.services import doctor, lock
from threaddigest.settings import Settings

STALE_AFTER_SECONDS = 180  # settings.static.run.stale_after_minutes (3) * 60
MAX_RATE_LIMIT_WAIT_SECONDS = 300  # core.retry.MAX_RATE_LIMIT_WAIT_SECONDS, mirrored here


# --- local db_path / engine: inside settings.data_dir, not an arbitrary temp path -------------


@pytest.fixture
def db_path(settings: Settings) -> Path:
    return settings.data_dir / "threaddigest.db"


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


def test_check_sqlite_version_is_ok_on_the_runtime_library() -> None:
    """KI-009, rev 0004: the runtime SQLite (3.53 here, well past 3.42) satisfies the
    secure-delete format floor."""
    check = doctor.check_sqlite_version()
    assert check.ok is True
    assert check.name == "sqlite_version"
    assert check.severity == doctor.CheckSeverity.ERROR


def test_check_sqlite_version_is_an_error_below_the_secure_delete_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: an older SQLite cannot read a secure-delete FTS5 index, so it is an ERROR,
    not drift."""
    monkeypatch.setattr(doctor.db_backup, "sqlite_version", lambda: (3, 41, 0))
    check = doctor.check_sqlite_version()
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR
    assert "3.41.0" in check.detail and "3.42" in check.detail


def test_check_settings_valid_is_not_ok_for_a_broken_static_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The check constructs its own ``Settings()`` from the live environment, so a bad
    static key is caught here -- the same failure an operator would hit -- rather than only
    by whatever already built a ``Settings`` before ``doctor`` ran."""
    monkeypatch.setenv("THREADDIGEST_STATIC__RUN__STALE_AFTER_MINUTES", "-1")
    check = doctor.check_settings_valid()
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


# --- data_dir_writable: ERROR --------------------------------------------------------------


def test_check_data_dir_writable_is_ok_for_the_isolated_data_dir(settings: Settings) -> None:
    check = doctor.check_data_dir_writable(settings.data_dir)
    assert check.ok is True
    assert check.name == "data_dir_writable"


def test_check_data_dir_writable_is_not_ok_when_it_cannot_be_created(tmp_path: Path) -> None:
    """A file where a directory needs to be: this path can never be a directory regardless
    of permission bits, which keeps this test meaningful even when tests run as root.
    ``check_data_dir_writable`` no longer creates ``data_dir`` before probing it (see the
    "does not exist" test below), so this exercises the same not-a-directory branch as a
    path that was simply never created -- both are answered without any filesystem mutation.
    """
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    unwritable = blocker / "data"

    check = doctor.check_data_dir_writable(unwritable)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR


def test_check_data_dir_writable_is_not_ok_for_a_missing_directory_and_does_not_create_it(
    tmp_path: Path,
) -> None:
    """Round5 doctor-panel finding: the old implementation called ``data_dir.mkdir(parents=
    True, exist_ok=True)`` before probing, so a diagnostic command RL-04 lists as writing
    nothing was creating an operator's entire data directory tree just to report on it. A
    missing directory is now reported as not writable, never created."""
    missing = tmp_path / "does-not-exist-yet"

    check = doctor.check_data_dir_writable(missing)

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR
    assert not missing.exists()


def test_check_data_dir_writable_is_not_ok_when_the_probe_itself_fails(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The directory exists (unlike the two tests above), so this is the other not-ok
    branch: the probe file itself fails to write -- a full disk, a read-only bind mount, an
    ACL a permission bit can't express. Monkeypatched rather than ``chmod``'d, following
    ``test_check_free_disk_is_not_ok_when_free_space_cannot_be_read``'s own convention: a
    permission-bit test is not meaningful when tests run as root.
    """

    def _refuse(*_args: object, **_kwargs: object) -> object:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(doctor.tempfile, "NamedTemporaryFile", _refuse)

    check = doctor.check_data_dir_writable(settings.data_dir)

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
        Path("Desktop", "threaddigest"),
        Path("Documents", "threaddigest"),
        Path("Downloads", "threaddigest"),
        Path("Library", "Mobile Documents", "com~apple~CloudDocs", "threaddigest"),
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
    monkeypatch.setenv("THREADDIGEST_REDDIT_CLIENT_ID", "abc")
    monkeypatch.setenv("THREADDIGEST_REDDIT_CLIENT_SECRET", "def")
    monkeypatch.setenv("THREADDIGEST_REDDIT_USERNAME", "wes")
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


# --- enabled_sources: KI-017, the check that notices a collector with nothing to collect ---


def test_check_enabled_sources_warns_when_no_source_is_configured(engine: Engine) -> None:
    with engine.connect() as conn:
        check = doctor.check_enabled_sources(conn)
    assert not check.ok and check.severity is doctor.CheckSeverity.WARNING
    assert "no source configured" in check.detail


def test_check_enabled_sources_is_ok_with_one_enabled_source(engine: Engine, now: int) -> None:
    with engine.begin() as conn:
        repo.seed_subreddits(
            conn, workspace_pk=repo.default_workspace_pk(conn), names=["premiere"], now=now
        )
    with engine.connect() as conn:
        check = doctor.check_enabled_sources(conn)
    assert check.ok, check.detail


def test_check_enabled_sources_is_an_error_when_every_source_is_disabled(
    engine: Engine, now: int
) -> None:
    subreddits = sa.Table("subreddits", sa.MetaData(), autoload_with=engine)
    with engine.begin() as conn:
        repo.seed_subreddits(
            conn,
            workspace_pk=repo.default_workspace_pk(conn),
            names=["premiere", "editors"],
            now=now,
        )
        conn.execute(sa.update(subreddits).values(enabled=False))
    with engine.connect() as conn:
        check = doctor.check_enabled_sources(conn)
    assert not check.ok and check.severity is doctor.CheckSeverity.ERROR
    assert "every one of 2 sources is disabled" in check.detail


def test_check_enabled_sources_is_an_error_when_every_enabled_source_is_forbidden(
    engine: Engine, now: int
) -> None:
    """KI-017 forbidden-enabled gap (external round one panel, 2026-09-15): a private
    (`forbidden`) or gone (`not_found`) source never auto-disables (`disable_at=None`), so it
    stays `enabled=True` while collecting nothing. Counting only the enabled flag stayed green;
    the check now counts collectable sources and goes red immediately, not after the stale
    window."""
    subreddits = sa.Table("subreddits", sa.MetaData(), autoload_with=engine)
    with engine.begin() as conn:
        repo.seed_subreddits(
            conn,
            workspace_pk=repo.default_workspace_pk(conn),
            names=["premiere", "editors"],
            now=now,
        )
        conn.execute(
            sa.update(subreddits).values(status="forbidden")
        )  # enabled, but never collects
    with engine.connect() as conn:
        check = doctor.check_enabled_sources(conn)
    assert not check.ok and check.severity is doctor.CheckSeverity.ERROR
    assert "private or gone" in check.detail


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
    fake: FakeRedditGateway, settings: Settings, clock: FakeClock, engine: Engine, now: int
) -> None:
    """§15.2 closing paragraph: ``run_checks`` never touches ``gateway`` when
    ``no_network=True`` (the default on every shipped path) -- proven against a routeless fake.

    **Extended for the tranche-B auth ping** (the ping is the first thing here that would
    touch the gateway). The three assertions are the ones this test shipped with; what is new
    above them is a database holding a collectable source, and that source registered on the
    fake. Without it, the report had nothing to ping and the gateway went untouched for the
    wrong reason: deleting the ``no_network`` guard from ``run_checks`` left this test green,
    which is a proof that had stopped discriminating.
    """
    with engine.begin() as conn:
        repo.seed_subreddits(
            conn, workspace_pk=repo.default_workspace_pk(conn), names=["premiere"], now=now
        )
    fake.add_subreddit("premiere")

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
    """The §15.2 twelve in order, ``enabled_sources`` after ``last_run_age`` (KI-017), and
    ``hooks_installed`` last."""
    _plant_ok_run(engine, now=now, finished_at=now)

    report = doctor.run_checks(settings=settings, clock=clock, gateway=None, no_network=True)

    names = [check.name for check in report.checks]
    assert names == [
        "settings_valid",
        "sqlite_version",
        "data_dir_writable",
        "data_dir_outside_tcc",
        "database_present",
        "alembic_at_head",
        "quick_check",
        "schema_fingerprint",
        "free_disk",
        "last_run_age",
        "enabled_sources",
        "lock_not_stale",
        "credentials_present",
        "no_stale_running_rows",
        "hooks_installed",
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


# --- RL-04: doctor writes nothing to the filesystem either (round5 doctor-panel finding) ------
#
# The RL-04 gate (tests/gates/test_mutating_commands.py) only diffs database *table* digests,
# so ``check_lock_not_stale -> lock.is_held`` conjuring ``data/locks/collector.lock`` into
# existence, and ``check_data_dir_writable`` creating the whole data directory tree before
# probing it, both went unnoticed: neither touches a table. These tests diff the filesystem
# itself instead.


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root``, keyed by its path relative to ``root``, with its exact
    bytes -- so a diagnostic run that creates or touches so much as one file is caught."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_run_checks_on_a_fresh_database_less_data_dir_leaves_it_byte_for_byte_unchanged(
    settings: Settings, clock: FakeClock
) -> None:
    """A freshly created, still-empty data directory (no database, no locks dir, nothing):
    ``doctor --no-network`` is a read-only diagnostic (RL-04's own claim), so it must leave
    every byte of it exactly as found, not merely leave the (nonexistent) database alone."""
    before = _tree_snapshot(settings.data_dir)
    assert before == {}, "the isolated data dir fixture should start genuinely empty"

    doctor.run_checks(settings=settings, clock=clock, gateway=None, no_network=True)

    assert _tree_snapshot(settings.data_dir) == before


def test_run_checks_with_a_database_never_creates_the_locks_directory(
    engine: Engine, settings: Settings, clock: FakeClock, lock_path: Path
) -> None:
    """The exact round5 doctor-panel repro: a data dir with a real, migrated database and no
    collector run yet has no ``locks/`` directory. ``check_lock_not_stale -> lock.is_held``
    must report the lock free without creating one just to check (a full byte-for-byte diff
    of this data dir is not meaningful here -- SQLite's WAL/SHM files legitimately change
    bytes on every connection this report opens, so the directed assertion below is the
    thing that would actually have caught the original bug).
    """
    assert not lock_path.parent.exists()

    doctor.run_checks(settings=settings, clock=clock, gateway=None, no_network=True)

    assert not lock_path.parent.exists()
    assert not lock_path.exists()


# --- alert_if_stale is parsed once, up front (round5 doctor-panel finding) ---------------------


def test_run_checks_raises_for_a_bad_duration_without_a_database(
    settings: Settings, clock: FakeClock
) -> None:
    """The duration used to be parsed only deep inside ``_checks_with_a_database``, so
    ``doctor --alert-if-stale banana`` on a data dir with no database yet never reached it
    and exited 1 (from ``database_present`` failing) instead of the documented 78. It is now
    parsed once at the top of ``run_checks``, before ``database_present`` even runs."""
    with pytest.raises(ValueError, match=r".+"):
        doctor.run_checks(settings=settings, clock=clock, gateway=None, alert_if_stale="banana")


def test_run_checks_raises_for_a_bad_duration_with_a_database(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    """The same bad duration, but with a database present -- the path that already raised
    before this fix; proves moving the parse did not disturb it."""
    with pytest.raises(ValueError, match=r".+"):
        doctor.run_checks(settings=settings, clock=clock, gateway=None, alert_if_stale="banana")


def test_run_checks_still_accepts_a_good_duration_without_a_database(
    settings: Settings, clock: FakeClock
) -> None:
    """A valid duration must not be treated as a config error just because it is now parsed
    eagerly, on the one path (no database yet) that never used to reach the parse at all."""
    report = doctor.run_checks(settings=settings, clock=clock, gateway=None, alert_if_stale="36h")
    assert isinstance(report, doctor.DoctorReport)


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


# --- a database that exists and will not open (round5-findings.json panel P1) ------------------

#: The §15.2 twelve, ``enabled_sources`` and ``hooks_installed``, in order -- restated here
#: so a corrupt-database
#: report is compared against the SAME list the healthy one is, and a short report cannot
#: read as healthy.
EVERY_CHECK_NAME = [
    "settings_valid",
    "sqlite_version",
    "data_dir_writable",
    "data_dir_outside_tcc",
    "database_present",
    "alembic_at_head",
    "quick_check",
    "schema_fingerprint",
    "free_disk",
    "last_run_age",
    "enabled_sources",
    "lock_not_stale",
    "credentials_present",
    "no_stale_running_rows",
    "hooks_installed",
]


def _corrupt_the_schema_page(engine: Engine, db_path: Path) -> None:
    """Overwrite page 1 after the 100-byte file header -- the mechanism
    ``test_check_quick_check_is_not_ok_for_a_corrupt_file`` measured: a 256-byte nibble lands
    in free space and corrupts nothing, the schema page proper is what SQLite calls malformed.
    """
    checkpoint_truncate(engine)
    engine.dispose()
    with db_path.open("r+b") as handle:
        handle.seek(100)
        handle.write(b"\xff" * 4096)


def test_run_checks_reports_every_check_for_a_corrupt_database(
    engine: Engine, settings: Settings, clock: FakeClock, db_path: Path
) -> None:
    """``run_checks`` branched on ``db_path.is_file()``, so a file that exists and is corrupt
    fell through to ``_checks_with_a_database``, whose ``engine.connect()`` raises
    ``DatabaseError``. Nothing caught it (``cli.doctor`` catches ``ConfigError``,
    ``cli._doctor_report`` ``ValueError``), so ``doctor --no-network`` exited 1 with an
    unhandled traceback and printed ZERO check rows -- the ``database_present`` and
    ``quick_check`` rows that exist precisely to diagnose a corrupt file were unreachable in
    the one case they are for, and "doctor lists its checks" failed.
    """
    _corrupt_the_schema_page(engine, db_path)

    report = doctor.run_checks(settings=settings, clock=clock, gateway=None, no_network=True)

    assert [check.name for check in report.checks] == EVERY_CHECK_NAME
    by_name = {check.name: check for check in report.checks}
    # The two rows that actually diagnose this file both ran and both say so.
    assert by_name["database_present"].ok is False
    assert by_name["database_present"].severity == doctor.CheckSeverity.ERROR
    assert by_name["quick_check"].ok is False
    assert "malformed" in by_name["quick_check"].detail or "not a database" in (
        by_name["quick_check"].detail
    )
    # The checks that need a connection are named placeholders, never silently dropped.
    assert by_name["alembic_at_head"].ok is False
    assert str(db_path) in by_name["alembic_at_head"].detail
    # The two that need neither a connection nor the file still ran for real.
    assert by_name["free_disk"].ok is True
    assert by_name["credentials_present"].name == "credentials_present"
    assert report.ok is False
    assert report.exit_code == 1


# --- hooks_installed: the developer checkout, wired into run_checks as the 13th check ----------
#
# Answers "do commits in THIS checkout run the gates?" -- a question about a working tree, not
# only about an installation, which is why "no git repository" is one of its ok states. Tested
# here at the granular, per-function level like the twelve above; ``run_checks`` appends it last
# (see the two list-equality tests above, which pin its membership) and ``make check`` also
# calls it directly through ``tools/hooks_status.py``.

#: What pre-commit's generated hook looks like at the top; git's own ``pre-commit.sample``
#: (the not-ok case below) names neither pre-commit nor anything that runs it.
PRE_COMMIT_HOOK = "#!/usr/bin/env bash\n# File generated by pre-commit: https://pre-commit.com\n"
SAMPLE_HOOK = "#!/bin/sh\n# An example hook script to verify what is about to be committed.\n"


def _checkout(
    tmp_path: Path,
    *,
    git: bool,
    hook: str | None = None,
    stages: tuple[str, ...] = ("pre-commit", "pre-push"),
) -> Path:
    """A temp tree shaped like a checkout: ``pyproject.toml`` at the root, ``src/`` below it,
    and a ``.git/hooks`` directory holding ``hook`` when one is given.
    """
    root = tmp_path / "checkout"
    (root / "src" / "threaddigest" / "services").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    if git:
        hooks = root / ".git" / "hooks"
        hooks.mkdir(parents=True)
        if hook is not None:
            for stage in stages:
                (hooks / stage).write_text(hook, encoding="utf-8")
    return root


def test_check_hooks_installed_is_ok_when_the_hook_is_precommits(tmp_path: Path) -> None:
    """The ok state, reached by the real walk-up: the start path is the package directory,
    four levels below the ``pyproject.toml`` that marks the root.
    """
    root = _checkout(tmp_path, git=True, hook=PRE_COMMIT_HOOK)

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is True
    assert str(root / ".git" / "hooks" / "pre-commit") in check.detail


@pytest.mark.parametrize("hook", [None, SAMPLE_HOOK], ids=["absent", "gits_own_sample"])
def test_check_hooks_installed_is_not_ok_without_precommits_hook(
    tmp_path: Path, hook: str | None
) -> None:
    """The not-ok state, and the reason it is two cases: ``pre-commit.sample`` sits in every
    fresh ``.git/hooks``, and git never runs it. A check that only tested "a file is there"
    would call an uninstalled checkout healthy.
    """
    root = _checkout(tmp_path, git=True, hook=hook)

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is False
    assert check.detail == "run make hooks"


def test_check_hooks_installed_is_not_ok_with_only_the_commit_hook(tmp_path: Path) -> None:
    """Half an install is not an install: the push hook is what makes a remote safe to push to,
    and ``make hooks`` installs both stages together (2026-09-14)."""
    root = _checkout(tmp_path, git=True, hook=PRE_COMMIT_HOOK, stages=("pre-commit",))

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is False
    assert check.detail == "run make hooks"


def test_check_hooks_installed_is_ok_without_a_git_directory(tmp_path: Path) -> None:
    """The third state is an answer, not a skip: an installed wheel or a container has no
    repository to install hooks into, and reporting that as a failure would make the check
    noise on every machine that is not a developer checkout.
    """
    root = _checkout(tmp_path, git=False)

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is True
    assert check.detail == "no git repository"


def _worktree(
    tmp_path: Path, *, pointer: str, hook: str | None = None, commondir: bool = True
) -> Path:
    """A temp tree shaped like a linked git worktree: the checkout's ``.git`` is a FILE
    naming that worktree's git directory, whose ``commondir`` points at the shared one --
    and the shared one is where the hooks that run for every worktree live.

    ``commondir=False`` is the other shape a ``.git`` file has: a submodule, whose git
    directory holds its own ``hooks/``. The hook, when asked for, is written wherever git
    would run it from in that layout.

    ``pointer`` is the literal ``.git`` file content, with ``{gitdir}`` substituted.
    """
    main_git = tmp_path / "main" / ".git"
    (main_git / "hooks").mkdir(parents=True)
    worktree_git = main_git / "worktrees" / "wt"
    worktree_git.mkdir(parents=True)
    hooks = main_git / "hooks"
    if commondir:
        (worktree_git / "commondir").write_text("../..\n", encoding="utf-8")
    else:
        hooks = worktree_git / "hooks"
        hooks.mkdir()
    if hook is not None:
        for stage in ("pre-commit", "pre-push"):
            (hooks / stage).write_text(hook, encoding="utf-8")
    root = tmp_path / "wt"
    (root / "src" / "threaddigest" / "services").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (root / ".git").write_text(pointer.format(gitdir=worktree_git), encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "pointer",
    ["gitdir: {gitdir}\n", "gitdir: ../main/.git/worktrees/wt\n"],
    ids=["absolute", "relative"],
)
def test_check_hooks_installed_follows_a_worktrees_git_file(tmp_path: Path, pointer: str) -> None:
    """Agents work in linked worktrees, where ``.git`` is a file and the hooks sit in the
    main checkout's shared git directory. Reading only ``<root>/.git/hooks`` would report
    "no git repository" to every one of them -- a false all-clear about the one thing this
    check exists to answer. Both spellings git writes (absolute and relative) are followed.
    """
    root = _worktree(tmp_path, pointer=pointer, hook=PRE_COMMIT_HOOK)

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is True
    assert str((tmp_path / "main" / ".git" / "hooks" / "pre-commit").resolve()) in check.detail


def test_check_hooks_installed_treats_an_unreadable_git_file_as_no_repository(
    tmp_path: Path,
) -> None:
    """A ``.git`` file that is not a ``gitdir:`` pointer is not something to guess about:
    the check reports the honest "no git repository" rather than inventing a hooks path.
    """
    root = _worktree(tmp_path, pointer="bookkeeping of some kind, not a gitdir pointer\n")

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is True
    assert check.detail == "no git repository"


def test_check_hooks_installed_reads_a_git_directory_without_a_commondir(tmp_path: Path) -> None:
    """The other ``.git``-as-a-file layout: a submodule, whose git directory has no
    ``commondir`` and holds its own ``hooks/``. Without this branch the check would resolve
    a path one level up and miss an installed hook.
    """
    root = _worktree(tmp_path, pointer="gitdir: {gitdir}\n", hook=PRE_COMMIT_HOOK, commondir=False)

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is True
    assert "worktrees" in check.detail


def test_check_hooks_installed_is_ok_where_there_is_no_repository_root(tmp_path: Path) -> None:
    """An installed wheel: no ``pyproject.toml`` above the package, so there is no checkout
    to ask about. Same answer as "no ``.git``", because it is the same situation.
    """
    check = doctor.check_hooks_installed(tmp_path)

    assert check.ok is True
    assert check.detail == "no git repository"


# --- hooks_installed: installed is not the same as able to run (KI-038) ------------------------
#
# Birth incident, 2026-09-16: a branch was built in a linked git worktree and the worktree was
# removed afterwards. pre-commit templates the *absolute* interpreter of the environment it was
# installed from into every hook it writes, and these hooks are shared by every worktree, so the
# shared `pre-commit` and `pre-push` were left naming a `.venv/bin/python` that no longer
# existed. The generated script falls through to a bare `pre-commit` on `PATH`, found none, and
# exited 1, so not one commit in the checkout could run the gates -- while this check reported
# them installed, because a file was there and it said "pre-commit" inside.


def _templated_hook(interpreter: Path | str) -> str:
    """A generated hook the way pre-commit writes it: the marker comment, then the templated
    block whose ``INSTALL_PYTHON`` is the absolute interpreter, quoted as ``shlex.quote``
    leaves it (so a path holding a space arrives quoted, as it does on a real machine).
    """
    return (
        f"{PRE_COMMIT_HOOK}\n# start templated\n"
        f"INSTALL_PYTHON={shlex.quote(str(interpreter))}\n"
        "ARGS=(hook-impl --config=.pre-commit-config.yaml --hook-type=pre-commit)\n"
        "# end templated\n"
    )


def _runnable_interpreter(tmp_path: Path) -> Path:
    """A file that exists and carries the execute bit, standing in for `.venv/bin/python`."""
    interpreter = tmp_path / "venv-python"
    interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    interpreter.chmod(0o755)
    return interpreter


def test_check_hooks_installed_is_not_ok_when_the_hook_names_a_missing_interpreter(
    tmp_path: Path,
) -> None:
    """The incident itself: both hooks are there and both name pre-commit, and neither can run,
    because the interpreter they were templated with was removed with its worktree. The check
    says so and names the remedy, rather than reporting the checkout gated.
    """
    gone = tmp_path / "removed-worktree" / ".venv" / "bin" / "python"
    root = _checkout(tmp_path, git=True, hook=_templated_hook(gone))

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is False
    assert str(gone) in check.detail
    assert "make hooks" in check.detail


def test_check_hooks_installed_is_not_ok_when_the_interpreter_cannot_be_executed(
    tmp_path: Path,
) -> None:
    """The other half of "can run": the path is there but carries no execute bit, so the
    generated hook's own ``[ -x "$INSTALL_PYTHON" ]`` test fails exactly as it does for a path
    that is gone. Existence alone is not the question.
    """
    interpreter = _runnable_interpreter(tmp_path)
    interpreter.chmod(0o644)
    root = _checkout(tmp_path, git=True, hook=_templated_hook(interpreter))

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is False
    assert str(interpreter) in check.detail
    assert "make hooks" in check.detail


def test_check_hooks_installed_is_ok_when_the_interpreter_is_runnable(tmp_path: Path) -> None:
    """The pass case keeps its existing semantics and its existing wording: a templated hook
    whose interpreter exists and is executable is installed, and the detail still names the
    hook paths rather than the interpreter.
    """
    interpreter = _runnable_interpreter(tmp_path)
    root = _checkout(tmp_path, git=True, hook=_templated_hook(interpreter))

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is True
    assert check.detail == f"{root / '.git' / 'hooks' / 'pre-commit'} and pre-push run pre-commit"


def test_check_hooks_installed_reads_the_push_hooks_interpreter_too(tmp_path: Path) -> None:
    """Both stages are asked, not only the first: the push hook is the one that runs the whole
    `make check` before anything leaves the machine, and it is templated separately.
    """
    interpreter = _runnable_interpreter(tmp_path)
    gone = tmp_path / "removed-worktree" / ".venv" / "bin" / "python"
    root = _checkout(tmp_path, git=True, hook=_templated_hook(interpreter))
    (root / ".git" / "hooks" / "pre-push").write_text(_templated_hook(gone), encoding="utf-8")

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is False
    assert "pre-push" in check.detail
    assert str(gone) in check.detail


@pytest.mark.parametrize(
    "line",
    ["", "INSTALL_PYTHON=\n", "INSTALL_PYTHON='unbalanced\n"],
    ids=["no_install_python_line", "empty_value", "unparsable_quoting"],
)
def test_check_hooks_installed_stays_ok_when_no_interpreter_can_be_read(
    tmp_path: Path, line: str
) -> None:
    """A hook this check cannot read an interpreter out of is not evidence of a broken hook:
    a hand-written wrapper, or a future pre-commit template, need not carry the line at all,
    and the fallback path (`command -v pre-commit`) is a real way to run. The check answers
    only the question it can answer, and a malformed line never raises out of a diagnosis.
    """
    root = _checkout(tmp_path, git=True, hook=f"{PRE_COMMIT_HOOK}{line}")

    check = doctor.check_hooks_installed(root / "src" / "threaddigest" / "services")

    assert check.ok is True


# --- auth_ping: the one check that makes a request, and it makes exactly one -------------------
#
# Tranche B wires `doctor --network` to a single `about` plus a free `limits()` read. The rows
# below cover every outcome the check can produce (ok with headers, ok before any header has
# been seen, no source, auth failed, rate limited, any other gateway error) at the
# per-function level, plus the `run_checks` wiring: present on the network path, absent on the
# default one. The two-HTTP-call claim itself is proven against the REAL adapter in
# tests/adapters/test_praw_gateway.py::test_the_auth_ping_costs_exactly_two_http_calls -- the
# fake counts simulated round-trips, and a simulation cannot prove a wire cost.


def test_check_auth_ping_costs_one_about_and_one_free_limits_read(
    fake: FakeRedditGateway,
) -> None:
    """The ping is a gateway method pair, not a new port: one ``about``, then ``limits()``,
    and nothing else. Asserted on the recorded call list, not inferred from the request
    count, so a check that also fetched a listing "while it was there" is caught."""
    fake.add_subreddit("premiere", subscribers=120_000)
    fake.set_limits(993, 7)

    check = doctor.check_auth_ping(fake, subreddit="premiere")

    assert [call.method for call in fake.calls] == ["about", "limits"]
    assert fake.requests_made == 1  # limits() costs nothing; the port promises it
    assert check.ok is True
    assert check.severity == doctor.CheckSeverity.ERROR
    assert check.detail == "r/premiere read; rate limit: 993 remaining, 7 used"


def test_check_auth_ping_reports_unseen_headers_as_ok_not_as_a_failure(
    fake: FakeRedditGateway,
) -> None:
    """``praw.models.Auth.limits`` starts at ``{"remaining": None, "used": None}`` and stays
    there until a response has been parsed. Reading that as a failed ping would make the
    first ``doctor --network`` of every installation red for a value PRAW documents as its
    starting state."""
    fake.add_subreddit("premiere")
    fake.set_limits(None, None)

    check = doctor.check_auth_ping(fake, subreddit="premiere")

    assert check.ok is True
    assert check.detail == (
        "r/premiere read; rate-limit headers not seen yet (remaining and used are both unset)"
    )


def test_check_auth_ping_without_a_source_is_a_warning_and_touches_the_gateway(
    fake: FakeRedditGateway,
) -> None:
    """Mirrors ``enabled_sources``' "no source configured yet" (KI-017): a fresh install has
    no subreddit to ping, which is a state to report, not an incident to alert on. The
    gateway is not touched at all, so ``doctor --network`` on a fresh install still makes
    zero requests."""
    check = doctor.check_auth_ping(fake, subreddit=None)

    assert check.name == "auth_ping"
    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.WARNING
    assert check.detail == "no source to ping"
    assert fake.calls == []
    assert fake.requests_made == 0


def test_check_auth_ping_names_the_credentials_without_echoing_one(
    fake: FakeRedditGateway,
) -> None:
    """KI-003's precedent: a validation error once printed the client secret. The adapter
    builds its ``AuthFailed`` message out of prawcore's own exception text, which is a
    response repr this project does not control -- so the check names the failure and where
    to fix it and discards the message. Interpolating the exception here would put whatever
    Reddit echoed back into an operator report and into ``--json`` output."""
    fake.add_subreddit("premiere")
    fake.fail_next(AuthFailed("credentials rejected: 401 client_secret=s3cret-value-abc"))

    check = doctor.check_auth_ping(fake, subreddit="premiere")

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR
    assert "credentials" in check.detail
    assert ".env" in check.detail
    assert "/setup" in check.detail
    assert "s3cret-value-abc" not in check.detail


def test_check_auth_ping_names_the_wait_when_reddit_rate_limits_the_ping(
    fake: FakeRedditGateway,
) -> None:
    """A 429 on the cheapest call the system makes is worth naming with its wait: it is the
    operator's evidence that something else is spending the quota."""
    fake.add_subreddit("premiere")
    fake.rate_limit_next(retry_after=120.0)

    check = doctor.check_auth_ping(fake, subreddit="premiere")

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR
    assert check.detail == "rate limited by Reddit; it asked us to wait 120 s"


def test_check_auth_ping_says_so_when_a_429_carries_no_retry_after(
    fake: FakeRedditGateway,
) -> None:
    """``RateLimited.retry_after`` is None when the header was absent or unparseable
    (``adapters.reddit_praw._seconds``). "wait None s" would be worse than saying so."""
    fake.add_subreddit("premiere")
    fake.rate_limit_next(retry_after=None)

    check = doctor.check_auth_ping(fake, subreddit="premiere")

    assert check.ok is False
    assert check.detail == "rate limited by Reddit; no Retry-After header to say for how long"


def test_check_auth_ping_names_the_class_of_any_other_gateway_error(
    fake: FakeRedditGateway,
) -> None:
    """Every other failure is one of the port's named outcomes, and the class name is the
    diagnosis: a private subreddit reads differently from an edge block. ``services/`` never
    catches ``Exception`` and never sees a PRAW exception (the adapter translates)."""
    fake.add_subreddit("premiere")
    fake.set_status("premiere", "forbidden")

    check = doctor.check_auth_ping(fake, subreddit="premiere")

    assert check.ok is False
    assert check.severity == doctor.CheckSeverity.ERROR
    assert check.detail == "the ping failed: SubredditForbidden"


# --- run_checks wiring: the row is on the network path and nowhere else ------------------------


def test_run_checks_appends_the_auth_ping_when_the_network_is_allowed(
    engine: Engine, settings: Settings, clock: FakeClock, fake: FakeRedditGateway, now: int
) -> None:
    """``--network`` adds exactly one row, second to last (``hooks_installed`` stays the
    closing check), and it pings the first enabled, collectable source -- the one a run would
    poll first, read through the same repository call ``enabled_sources`` counts with."""
    with engine.begin() as conn:
        repo.seed_subreddits(
            conn, workspace_pk=repo.default_workspace_pk(conn), names=["premiere"], now=now
        )
    fake.add_subreddit("premiere")

    report = doctor.run_checks(settings=settings, clock=clock, gateway=fake, no_network=False)

    names = [check.name for check in report.checks]
    assert names == [*EVERY_CHECK_NAME[:-1], "auth_ping", "hooks_installed"]
    assert fake.fullnames_requested("about") == ["premiere"]


def test_run_checks_pings_no_disabled_or_uncollectable_source(
    engine: Engine, settings: Settings, clock: FakeClock, fake: FakeRedditGateway, now: int
) -> None:
    """A source Reddit will never serve (private, or gone) is not a credentials test: pinging
    it would report a red ``auth_ping`` for working credentials, which is the alert that
    trains an operator to ignore the alert. With no collectable source left, the ping has
    nothing to ask about and says so."""
    subreddits = sa.Table("subreddits", sa.MetaData(), autoload_with=engine)
    with engine.begin() as conn:
        repo.seed_subreddits(
            conn, workspace_pk=repo.default_workspace_pk(conn), names=["premiere"], now=now
        )
        conn.execute(sa.update(subreddits).values(status="forbidden"))

    report = doctor.run_checks(settings=settings, clock=clock, gateway=fake, no_network=False)

    ping = next(check for check in report.checks if check.name == "auth_ping")
    assert ping.detail == "no source to ping"
    assert fake.calls == []


def test_run_checks_without_a_database_still_reports_the_ping_row(
    settings: Settings, clock: FakeClock, fake: FakeRedditGateway
) -> None:
    """No database means no source list, so there is nothing to ping -- but the row is still
    named, like every other check a missing database makes unanswerable. A report that
    silently drops a row reads as a shorter healthy report."""
    report = doctor.run_checks(settings=settings, clock=clock, gateway=fake, no_network=False)

    ping = next(check for check in report.checks if check.name == "auth_ping")
    assert ping.ok is False
    assert ping.severity == doctor.CheckSeverity.WARNING
    assert fake.requests_made == 0


def test_run_checks_appends_no_ping_row_on_the_default_path(
    engine: Engine, settings: Settings, clock: FakeClock, fake: FakeRedditGateway
) -> None:
    """The other half of CF-01: ``no_network=True`` is the default on every shipped path, and
    the row it must not produce is the only one that could reach Reddit."""
    report = doctor.run_checks(settings=settings, clock=clock, gateway=fake, no_network=True)

    assert "auth_ping" not in [check.name for check in report.checks]


def test_run_checks_appends_no_ping_row_without_a_gateway(
    engine: Engine, settings: Settings, clock: FakeClock
) -> None:
    """``--network`` with nothing to ping through is not a failure to report: ``cli`` builds
    the gateway or exits 78, so a None here is a caller that asked for a check it did not
    supply the collaborator for."""
    report = doctor.run_checks(settings=settings, clock=clock, gateway=None, no_network=False)

    assert "auth_ping" not in [check.name for check in report.checks]
