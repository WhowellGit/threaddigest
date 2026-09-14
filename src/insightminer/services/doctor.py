"""The no-network check list and the ``Check`` contract ``/system`` will share.

Twelve checks (design-round5 §15.2), each a function of its own so both branches -- ok and
not-ok -- are reachable from a test without staging a whole invocation. *A check with only
an ok branch tested is not a check*, so every function here answers one question and returns
one :class:`Check` rather than folding several into a verdict.

A thirteenth, :func:`check_hooks_installed`, follows the same contract and is the last row
:func:`run_checks` appends to every report, WARNING severity, so an uninstalled ``pre-commit``
hook shows up in the operator report exactly where the other twelve do. ``make check`` also
calls it directly (through ``tools/hooks_status.py``) for its own closing line; see its own
section below for why it answers "no git repository" as an ok state on an installed wheel.

**Zero HTTP is structural, not a promise.** ``no_network`` defaults to ``True`` and
:func:`run_checks` never touches ``gateway`` on that path: the parameter exists so the M1c
connectivity check has a seam to land in, and CF-01 proves the tranche-A default by handing
``run_checks`` a routeless :class:`~insightminer.adapters.reddit_fake.FakeRedditGateway` and
asserting it recorded nothing.

Severity is the severity of a **failed** check and is ignored when it passes.
:attr:`DoctorReport.ok` is false only when an ``ERROR``-severity check failed, which is why
``schema_fingerprint`` (G18) and "no successful run yet" (Wes's Q5) are ``WARNING``: a drift
worth surfacing and a fresh install must not make ``doctor`` exit 1.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import ValidationError
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import DatabaseError

from insightminer.core.retry import MAX_RATE_LIMIT_WAIT_SECONDS
from insightminer.db import backup as db_backup
from insightminer.db import migrate as db_migrate
from insightminer.db import repo
from insightminer.db.engine import db_path_for, engine_for
from insightminer.db.schema_dump import SCHEMA_SQL, dump_schema, fingerprint
from insightminer.ports import Clock, RedditGateway
from insightminer.services import lock
from insightminer.settings import DataDirRefusedError, Settings, settings_fingerprint

__all__ = [
    "MIN_FREE_BYTES",
    "RATE_WAIT_RE",
    "TCC_RELATIVE_PATHS",
    "Check",
    "CheckSeverity",
    "DoctorReport",
    "check_alembic_at_head",
    "check_credentials_present",
    "check_data_dir_outside_tcc",
    "check_data_dir_writable",
    "check_database_present",
    "check_free_disk",
    "check_hooks_installed",
    "check_last_run_age",
    "check_lock_not_stale",
    "check_no_stale_running_rows",
    "check_quick_check",
    "check_schema_fingerprint",
    "check_settings_valid",
    "parse_duration",
    "repo_root_from",
    "run_checks",
]

#: Free-space floor, a constant here and deliberately **not** a settings key (Wes's Q6): an
#: operator who can lower it has removed the check rather than answered it.
MIN_FREE_BYTES: Final = 1024**3

#: The stage a run writes while it is deliberately paused on a 429 (§12.4). Clause D2 of
#: ``lock_not_stale`` reads it, which is why the stage is written unconditionally on change.
RATE_WAIT_RE: Final = re.compile(r"rate_wait:\d+s")

#: macOS TCC-protected locations, relative to ``$HOME``. The last one is the iCloud Drive
#: mirror, whose ``com~apple~CloudDocs`` subtree is what a "Desktop & Documents in iCloud"
#: machine actually resolves those folders to.
TCC_RELATIVE_PATHS: Final[tuple[Path, ...]] = (
    Path("Desktop"),
    Path("Documents"),
    Path("Downloads"),
    Path("Library") / "Mobile Documents",
)

#: ``repo.running_runs`` excludes one pk; ``doctor`` is a reader with no run of its own, so
#: it excludes a pk no row can have. (Autoincrement pks start at 1.)
_NO_RUN_PK: Final = 0

#: The keyword arguments :func:`check_settings_valid` passes to ``Settings()``: none.
#: It exists only so mypy sees a ``**kwargs`` call. ``Settings.static`` is filled by the
#: ``config/settings.yaml`` settings source, which pydantic-settings installs at runtime and
#: mypy cannot see, so a bare ``Settings()`` reads to mypy as a missing required argument
#: even though passing one is exactly what production code must never do.
_FROM_ENVIRONMENT: Final[dict[str, Any]] = {}

_DURATION_RE: Final = re.compile(r"(\d+)([smhd])")
_DURATION_UNITS: Final[dict[str, int]] = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class CheckSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Check:
    """One diagnosis. ``severity`` describes a FAILED check and is ignored when ``ok``."""

    name: str
    ok: bool
    detail: str
    severity: CheckSeverity


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        """True unless some ``ERROR``-severity check failed."""
        return not any(
            not check.ok and check.severity is CheckSeverity.ERROR for check in self.checks
        )

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def parse_duration(text: str) -> int:
    """``"36h"`` / ``"90m"`` / ``"2d"`` / ``"45s"`` -> seconds; :class:`ValueError` otherwise.

    Deliberately strict: no sign, no decimal point, no bare number, exactly one unit. An
    ``--alert-if-stale`` that silently means something other than what was typed is worse
    than one that refuses.
    """
    match = _DURATION_RE.fullmatch(text)
    if match is None:
        msg = f"cannot parse duration {text!r}: expected <whole number><s|m|h|d>, e.g. 36h"
        raise ValueError(msg)
    return int(match.group(1)) * _DURATION_UNITS[match.group(2)]


def _last_seen(row: repo.RunRow) -> int:
    """``coalesce(heartbeat_at, started_at, created_at)`` -- §12.2's liveness timestamp."""
    if row.heartbeat_at is not None:
        return row.heartbeat_at
    return row.started_at if row.started_at is not None else row.created_at


# --- the twelve checks, in the order §15.2 lists them ---------------------------------------


def check_settings_valid() -> Check:
    """``Settings()`` resolves from the live environment and its fingerprint computes.

    Constructed **here**, not taken as a parameter: an operator's broken ``settings.yaml`` or
    ``INSIGHTMINER_*`` value must be reported by ``doctor``, and a ``Settings`` that some
    caller already built successfully proves nothing about the one a real command would.
    """
    name = "settings_valid"
    try:
        resolved = Settings(**_FROM_ENVIRONMENT)
        digest = settings_fingerprint(resolved)
    except (ValidationError, DataDirRefusedError, yaml.YAMLError, OSError, TypeError) as exc:
        return Check(
            name=name,
            ok=False,
            detail=f"settings did not resolve: {exc.__class__.__name__}: {exc}",
            severity=CheckSeverity.ERROR,
        )
    return Check(
        name=name,
        ok=True,
        detail=f"settings resolved; fingerprint {digest[:12]}",
        severity=CheckSeverity.ERROR,
    )


def check_data_dir_writable(data_dir: Path) -> Check:
    """The data directory exists and a temporary file lands in it, then is removed.

    **Diagnostic-only** (round5 doctor-panel finding): the old implementation called
    ``data_dir.mkdir(parents=True, exist_ok=True)`` before probing, which means ``doctor``
    -- a command RL-04 lists as writing nothing -- was creating an operator's entire data
    directory tree just to report on it. A missing directory is reported as not writable,
    never created on the operator's behalf; the probe file itself is created and removed
    inside the same ``with`` block, so a passing check leaves no residue either.
    """
    name = "data_dir_writable"
    if not data_dir.is_dir():
        return Check(
            name=name,
            ok=False,
            detail=f"{data_dir} does not exist",
            severity=CheckSeverity.ERROR,
        )
    try:
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".doctor-", suffix=".probe"):
            pass
    except OSError as exc:
        return Check(
            name=name,
            ok=False,
            detail=f"{data_dir} is not writable: {exc.__class__.__name__}: {exc}",
            severity=CheckSeverity.ERROR,
        )
    return Check(name=name, ok=True, detail=f"{data_dir} is writable", severity=CheckSeverity.ERROR)


def check_data_dir_outside_tcc(data_dir: Path) -> Check:
    """The data directory is not under a macOS TCC-protected or iCloud-mirrored path.

    A database in ``~/Documents`` is a database a background collector loses access to the
    first time macOS decides the prompt expired, and an iCloud-mirrored one is a database two
    machines can evict mid-write.
    """
    name = "data_dir_outside_tcc"
    resolved = data_dir.expanduser().resolve()
    home = Path.home().expanduser().resolve()
    for relative in TCC_RELATIVE_PATHS:
        protected = home / relative
        if resolved == protected or protected in resolved.parents:
            return Check(
                name=name,
                ok=False,
                detail=f"{resolved} is under the protected path {protected}",
                severity=CheckSeverity.ERROR,
            )
    return Check(
        name=name,
        ok=True,
        detail=f"{resolved} is outside the protected paths",
        severity=CheckSeverity.ERROR,
    )


def check_database_present(db_path: Path) -> Check:
    """The database file exists and opens through ``engine_for``.

    The existence test comes first on purpose: ``engine_for`` would *create* the file, and a
    diagnosis that fabricates the thing it is diagnosing is not a diagnosis.
    """
    name = "database_present"
    if not db_path.is_file():
        return Check(
            name=name,
            ok=False,
            detail=f"no database at {db_path}; run `insightminer db init`",
            severity=CheckSeverity.ERROR,
        )
    engine = engine_for(db_path)
    try:
        with engine.connect():
            pass
    except DatabaseError as exc:
        return Check(
            name=name,
            ok=False,
            detail=f"{db_path} would not open: {exc.__class__.__name__}",
            severity=CheckSeverity.ERROR,
        )
    finally:
        engine.dispose()
    return Check(name=name, ok=True, detail=f"{db_path} opens", severity=CheckSeverity.ERROR)


def check_alembic_at_head(engine: Engine) -> Check:
    """The database is stamped at the head revision; the detail names both revisions."""
    current = db_migrate.current_revision(engine)
    head = db_migrate.head_revision()
    at_head = current == head
    detail = f"current {current or '(none)'}, head {head}"
    if not at_head:
        detail = f"{detail}; run `insightminer db upgrade`"
    return Check(name="alembic_at_head", ok=at_head, detail=detail, severity=CheckSeverity.ERROR)


def check_quick_check(db_path: Path) -> Check:
    """``PRAGMA quick_check`` returns ``ok``.

    ``db.backup.quick_check`` reports a driver-level ``DatabaseError`` as its text rather
    than raising (§10.1), so the corrupt branch of this check is reachable.
    """
    verdict = db_backup.quick_check(db_path)
    return Check(
        name="quick_check",
        ok=verdict == "ok",
        detail=f"PRAGMA quick_check: {verdict}",
        severity=CheckSeverity.ERROR,
    )


def check_schema_fingerprint(engine: Engine) -> Check:
    """The live schema fingerprints equal to the packaged ``schema.sql``.

    **WARNING, never ERROR** (G18 / adversarial A9): drift is worth surfacing, but a golden
    file that lags a migration by one commit must not make ``doctor`` report a healthy
    database as broken.
    """
    live = fingerprint(dump_schema(engine))
    packaged = fingerprint(SCHEMA_SQL.read_text(encoding="utf-8"))
    matches = live == packaged
    detail = (
        f"schema matches schema.sql ({live[:12]})"
        if matches
        else f"live schema {live[:12]} != schema.sql {packaged[:12]}; run `make schema`"
    )
    return Check(
        name="schema_fingerprint", ok=matches, detail=detail, severity=CheckSeverity.WARNING
    )


def check_free_disk(data_dir: Path) -> Check:
    """At least :data:`MIN_FREE_BYTES` free where the database lives."""
    name = "free_disk"
    try:
        free = shutil.disk_usage(data_dir).free
    except OSError as exc:
        return Check(
            name=name,
            ok=False,
            detail=f"free space unreadable at {data_dir}: {exc.__class__.__name__}",
            severity=CheckSeverity.WARNING,
        )
    return Check(
        name=name,
        ok=free >= MIN_FREE_BYTES,
        detail=f"{free} bytes free (floor {MIN_FREE_BYTES})",
        severity=CheckSeverity.WARNING,
    )


def check_last_run_age(conn: Connection, *, now: int, max_age_seconds: int) -> Check:
    """The newest successful ``run`` is younger than ``--alert-if-stale``.

    **"No successful run yet" is a WARNING** (Wes's Q5): a fresh install has not run, and
    reporting that as an error would make ``doctor`` red on the one day nothing is wrong.
    """
    name = "last_run_age"
    row = repo.last_successful_run(conn)
    if row is None:
        return Check(
            name=name,
            ok=False,
            detail="no successful run yet",
            severity=CheckSeverity.WARNING,
        )
    age = now - _last_seen(row)
    return Check(
        name=name,
        ok=age <= max_age_seconds,
        detail=f"last successful run pk={row.pk} finished {age} s ago (alert after "
        f"{max_age_seconds} s)",
        severity=CheckSeverity.ERROR,
    )


def check_lock_not_stale(
    conn: Connection, *, lock_path: Path, now: int, stale_after_seconds: int
) -> Check:
    """A single-observation predicate over the flock and the ``running`` rows (§15.2).

    Clause A: the lock is free. Otherwise clause B: exactly one ``running`` row exists;
    clause C: its pid is alive; clause D1: it beat inside the stale window, or clause D2: it
    declared a ``rate_wait:Ns`` stage and is still inside that pause's own bound, so a run
    legitimately sleeping 300 s for a 429 is not reported stale while a *hung* one still goes
    red after ``MAX_RATE_LIMIT_WAIT_SECONDS + stale_after_seconds``.

    ``lock.is_held`` probes **shared**, so an hourly ``doctor`` cannot make a scheduled
    collector report ``skipped_locked`` (§12.2).
    """
    name = "lock_not_stale"
    severity = CheckSeverity.WARNING
    if not lock.is_held(lock_path):
        return Check(name=name, ok=True, detail="lock free", severity=severity)
    rows = repo.running_runs(conn, exclude_pk=_NO_RUN_PK)
    if len(rows) != 1:
        found = "no `running` run row" if not rows else f"{len(rows)} `running` run rows"
        return Check(name=name, ok=False, detail=f"lock held, but {found}", severity=severity)
    row = rows[0]
    if row.pid is None or not lock.pid_alive(row.pid):
        return Check(
            name=name,
            ok=False,
            detail=f"lock held; running run pk={row.pk} has a dead pid {row.pid}",
            severity=severity,
        )
    age = now - _last_seen(row)
    if age <= stale_after_seconds:
        detail = f"lock held; running run pk={row.pk} beat {age} s ago"
        return Check(name=name, ok=True, detail=detail, severity=severity)
    rate_wait_bound = int(MAX_RATE_LIMIT_WAIT_SECONDS) + stale_after_seconds
    if RATE_WAIT_RE.fullmatch(row.stage or "") and age <= rate_wait_bound:
        detail = f"lock held; running run pk={row.pk} is in a declared {row.stage} ({age} s ago)"
        return Check(name=name, ok=True, detail=detail, severity=severity)
    return Check(
        name=name,
        ok=False,
        detail=f"lock held; last heartbeat {age} s ago (stale after {stale_after_seconds} s)",
        severity=severity,
    )


def check_credentials_present(settings: Settings) -> Check:
    """The three Reddit credentials are non-empty. **Presence only, never validated** --
    validating them is a network call, and this list makes none."""
    name = "credentials_present"
    missing = [
        field
        for field, value in (
            ("reddit_client_id", settings.reddit_client_id),
            ("reddit_client_secret", settings.reddit_client_secret.get_secret_value()),
            ("reddit_username", settings.reddit_username),
        )
        if not value.strip()
    ]
    return Check(
        name=name,
        ok=not missing,
        detail="all three credentials are set" if not missing else f"not set: {', '.join(missing)}",
        severity=CheckSeverity.WARNING,
    )


def check_no_stale_running_rows(conn: Connection, *, now: int, stale_after_seconds: int) -> Check:
    """The reader-side mirror of §12.2: no ``running`` row with a dead pid or an old beat.

    A read, never a write: ``doctor`` diagnoses, and only a command holding the collector
    flock is allowed to stamp a row ``crashed``.
    """
    name = "no_stale_running_rows"
    stale = [
        row
        for row in repo.running_runs(conn, exclude_pk=_NO_RUN_PK)
        if row.pid is None
        or not lock.pid_alive(row.pid)
        or now - _last_seen(row) > stale_after_seconds
    ]
    if not stale:
        return Check(
            name=name, ok=True, detail="no stale `running` rows", severity=CheckSeverity.WARNING
        )
    listed = ", ".join(f"pk={row.pk} pid={row.pid}" for row in stale)
    return Check(
        name=name,
        ok=False,
        detail=f"{len(stale)} stale `running` row(s): {listed}",
        severity=CheckSeverity.WARNING,
    )


# --- the developer checkout: hooks_installed, the thirteenth check -----------------------------
#
# ``hooks_installed`` diagnoses the *checkout a change is made in*, not only the installation
# an operator runs -- an installed wheel or a container has no hooks to install, which is why
# "no git repository" is one of its ok states rather than a skip. It is a ``Check`` like the
# twelve above -- same contract, same shape -- and :func:`run_checks` appends it last, WARNING
# severity, so the operator report carries it too. ``make check`` also calls it directly
# through ``tools/hooks_status.py`` so its own closing line is derived, never narrated.


#: The file that marks the repository root when walking up from this package.
ROOT_MARKER: Final = "pyproject.toml"

#: What pre-commit's generated hook says about itself; a hand-written or sample hook does not.
HOOK_MARKER: Final = "pre-commit"


def repo_root_from(start: Path) -> Path | None:
    """The nearest directory at or above ``start`` that holds a ``pyproject.toml``."""
    base = start if start.is_dir() else start.parent
    for candidate in (base, *base.parents):
        if (candidate / ROOT_MARKER).is_file():
            return candidate
    return None


def _git_hooks_dir(root: Path) -> Path | None:
    """``root``'s git hooks directory, or ``None`` when ``root`` is not a git checkout.

    A linked worktree's ``.git`` is a *file* naming that worktree's git directory, whose
    ``commondir`` points at the shared one -- and the shared one is where the hooks that run
    for every worktree live. Following it is the difference between reporting the truth and
    reporting "no git repository" to every agent that works in a worktree.
    """
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git / "hooks"
    if not dot_git.is_file():
        return None
    pointer = dot_git.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not pointer.startswith(prefix):
        return None
    git_dir = Path(pointer[len(prefix) :].strip())
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    common = git_dir / "commondir"
    if common.is_file():
        git_dir = git_dir / common.read_text(encoding="utf-8").strip()
    return git_dir.resolve() / "hooks"


#: The two git hook stages pre-commit installs here (``default_install_hook_types``).
HOOK_STAGES = ("pre-commit", "pre-push")


def check_hooks_installed(start: Path | None = None) -> Check:
    """The checkout's ``pre-commit`` and ``pre-push`` hooks are installed, so the gates run.

    Three states, all of them real answers:

    * **ok** -- ``<git dir>/hooks/pre-commit`` and ``<git dir>/hooks/pre-push`` both exist and
      name pre-commit (the push hook runs ``make check``, since a remote is a backup and never
      the gate; added 2026-09-14);
    * **not ok** -- there is a git repository and either hook is missing or is something else
      (git's own ``pre-commit.sample`` is not installed: git never runs it);
    * **ok, "no git repository"** -- an installed wheel or a container has nothing to
      install hooks into. That is a healthy state, not a skipped check.

    ``start`` is the walk-up's starting point (a temp tree in the tests); it defaults to this
    package, so the answer is about the checkout this code was imported from.
    """
    name = "hooks_installed"
    root = repo_root_from(start if start is not None else Path(__file__).resolve().parent)
    hooks_dir = None if root is None else _git_hooks_dir(root)
    if hooks_dir is None:
        return Check(name=name, ok=True, detail="no git repository", severity=CheckSeverity.WARNING)
    hooks = [hooks_dir / stage for stage in HOOK_STAGES]
    installed = all(
        hook.is_file() and HOOK_MARKER in hook.read_text(encoding="utf-8", errors="replace")
        for hook in hooks
    )
    return Check(
        name=name,
        ok=installed,
        detail=f"{hooks[0]} and {hooks[1].name} run pre-commit" if installed else "run make hooks",
        severity=CheckSeverity.WARNING,
    )


# --- the report -------------------------------------------------------------------------------


def _unreadable(name: str, severity: CheckSeverity, reason: str) -> Check:
    """The placeholder a database-dependent check becomes when there is no usable database.

    It is still a row, and still named: a report that silently drops six of twelve checks
    when the file is missing would read as a shorter healthy report.
    """
    return Check(
        name=name,
        ok=False,
        detail=f"not checked: {reason}",
        severity=severity,
    )


def _checks_without_a_database(settings: Settings, db_path: Path) -> list[Check]:
    return [
        _unreadable("alembic_at_head", CheckSeverity.WARNING, f"no database at {db_path}"),
        _unreadable("quick_check", CheckSeverity.WARNING, f"no database at {db_path}"),
        _unreadable("schema_fingerprint", CheckSeverity.WARNING, f"no database at {db_path}"),
        check_free_disk(settings.data_dir),
        _unreadable("last_run_age", CheckSeverity.WARNING, f"no database at {db_path}"),
        _unreadable("lock_not_stale", CheckSeverity.WARNING, f"no database at {db_path}"),
        check_credentials_present(settings),
        _unreadable("no_stale_running_rows", CheckSeverity.WARNING, f"no database at {db_path}"),
    ]


def _checks_with_an_unusable_database(settings: Settings, db_path: Path) -> list[Check]:
    """The same eight rows for a file that exists but will not open (round5-findings.json
    panel P1).

    ``quick_check`` is the **real** check here, not a placeholder: ``db.backup.quick_check``
    reports a driver-level ``DatabaseError`` as its text rather than raising (§10.1), so it is
    corruption-safe by design and it is the one row that actually diagnoses this file. Every
    other database-dependent check needs an ``engine.connect()``, and that is precisely what
    raises: before this branch existed, ``doctor --no-network`` on a corrupt database exited 1
    with an unhandled ``DatabaseError`` and printed **zero** check rows -- the
    ``database_present`` and ``quick_check`` rows that exist to diagnose a corrupt file were
    unreachable in the one case they are for.
    """
    reason = f"{db_path} would not open"
    return [
        _unreadable("alembic_at_head", CheckSeverity.WARNING, reason),
        check_quick_check(db_path),
        _unreadable("schema_fingerprint", CheckSeverity.WARNING, reason),
        check_free_disk(settings.data_dir),
        _unreadable("last_run_age", CheckSeverity.WARNING, reason),
        _unreadable("lock_not_stale", CheckSeverity.WARNING, reason),
        check_credentials_present(settings),
        _unreadable("no_stale_running_rows", CheckSeverity.WARNING, reason),
    ]


def _checks_with_a_database(
    engine: Engine,
    *,
    settings: Settings,
    db_path: Path,
    lock_path: Path,
    now: int,
    stale_after_seconds: int,
    max_age_seconds: int,
) -> list[Check]:
    with engine.connect() as conn:
        return [
            check_alembic_at_head(engine),
            check_quick_check(db_path),
            check_schema_fingerprint(engine),
            check_free_disk(settings.data_dir),
            check_last_run_age(conn, now=now, max_age_seconds=max_age_seconds),
            check_lock_not_stale(
                conn, lock_path=lock_path, now=now, stale_after_seconds=stale_after_seconds
            ),
            check_credentials_present(settings),
            check_no_stale_running_rows(conn, now=now, stale_after_seconds=stale_after_seconds),
        ]


def _with_hooks_check(checks: list[Check]) -> DoctorReport:
    """Append the thirteenth check -- ``hooks_installed``, WARNING severity -- and close out
    the report. The single call site for both of :func:`run_checks`'s return points, so a
    bad or missing database still gets the same closing check as a healthy one.
    """
    checks.append(check_hooks_installed())
    return DoctorReport(checks=tuple(checks))


def run_checks(
    *,
    settings: Settings,
    clock: Clock,
    gateway: RedditGateway | None = None,
    alert_if_stale: str = "36h",
    no_network: bool = True,
) -> DoctorReport:
    """Every §15.2 check, in the order that table lists them, plus ``hooks_installed``.

    ``gateway`` and ``no_network`` are the seam the M1c connectivity check lands in. In
    tranche A ``no_network`` is always true on every shipped path and **this function never
    touches ``gateway``** -- CF-01 proves it by passing a routeless fake and asserting it
    recorded no request and no call.

    **``database_present`` short-circuits the list, and both of its failure modes do**
    (round5-findings.json panel P1). Branching on ``db_path.is_file()`` covered only the
    missing file: a file that exists and is *corrupt* fell through to
    :func:`_checks_with_a_database`, whose ``engine.connect()`` raises ``DatabaseError`` --
    which ``cli.doctor`` (``ConfigError`` only) and ``cli._doctor_report`` (``ValueError``
    only) do not catch, so ``doctor`` died with a traceback and printed nothing at all. The
    branch is now on the ``Check`` itself, so "doctor lists its checks" holds for every
    database this installation can have.
    """
    del gateway, no_network  # tranche A makes no request; see the docstring and CF-01.
    # Parsed once, up front, before ``database_present`` gets a chance to short-circuit the
    # list (round5 doctor-panel finding): the old call site sat inside
    # ``_checks_with_a_database``, so ``doctor --alert-if-stale banana`` on a data dir with
    # no database yet never reached it and exited 1 (from ``database_present`` failing)
    # instead of the documented 78. A bad duration is a config error on every path.
    max_age_seconds = parse_duration(alert_if_stale)
    now = clock.now()
    db_path = db_path_for(settings.data_dir)
    lock_path = settings.data_dir / "locks" / "collector.lock"
    present = check_database_present(db_path)
    checks: list[Check] = [
        check_settings_valid(),
        check_data_dir_writable(settings.data_dir),
        check_data_dir_outside_tcc(settings.data_dir),
        present,
    ]
    if not present.ok:
        checks.extend(
            _checks_without_a_database(settings, db_path)
            if not db_path.is_file()
            else _checks_with_an_unusable_database(settings, db_path)
        )
        return _with_hooks_check(checks)
    engine = engine_for(db_path)
    try:
        checks.extend(
            _checks_with_a_database(
                engine,
                settings=settings,
                db_path=db_path,
                lock_path=lock_path,
                now=now,
                stale_after_seconds=settings.static.run.stale_after_minutes * 60,
                max_age_seconds=max_age_seconds,
            )
        )
    finally:
        engine.dispose()
    return _with_hooks_check(checks)
