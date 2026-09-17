"""Command-line entry point: automation, containers, tests, and break-glass recovery.

Every command is a thin wrapper over a service function the web UI also calls, and this
module is the only place in production where a collaborator is constructed: the engine, the
gateway, the clock, the notifier and ``Settings`` (design-round5 §1, §11.1).

Two declared departures from "``cli`` constructs everything", both bounded and both written
down in §11.6 / §11.8 rather than improvised:

* :data:`GATEWAY_FACTORY` is **the** injection seam. Production never assigns to it;
  ``tests/e2e/conftest.py`` sets it with ``monkeypatch`` and it is restored at teardown.
  RL-04's command walk runs with the seam *not* installed, so the default construction path
  is covered rather than bypassed.
* :func:`build_clock` and :func:`build_notifier` branch on the environment at **call** time,
  never at import: a :class:`GuardClock` that refuses to sleep under pytest, and the log
  notifier rather than a desktop notification. Neither is a seam -- no test assigns to
  anything -- and the guard is what makes "no end-to-end test sleeps" mechanical.

Exit codes (§11.2): 0 ok, 1 failed/crashed, 2 Typer usage error, 3 partial, 4 rate_limited,
5 network, 75 lock held, 78 config/auth/precondition, 130 cancelled. Every command exits
through ``raise typer.Exit(code=...)``; never ``sys.exit``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import typer
import uvicorn
import yaml
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import DatabaseError

from threaddigest import __version__
from threaddigest.adapters.clock import SystemClock
from threaddigest.adapters.notify import LogNotifier, MacNotifier
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.adapters.reddit_praw import PrawConfig, PrawGateway
from threaddigest.core.budget import Budget
from threaddigest.core.retry import ExitCode
from threaddigest.db import migrate as db_migrate
from threaddigest.db import repo
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.ports import Clock, GatewayError, Notifier, RedditGateway
from threaddigest.services import collect as collect_service
from threaddigest.services import doctor as doctor_service
from threaddigest.services import invariants, lock, runs
from threaddigest.services import migrate as migrate_service
from threaddigest.services import probe as probe_service
from threaddigest.settings import (
    DataDirRefusedError,
    Settings,
    default_data_dir,
    settings_fingerprint,
    user_agent,
)
from threaddigest.web.app import create_app

__all__ = [
    "GATEWAY_FACTORY",
    "ConfigError",
    "GatewayFactory",
    "GatewaySpec",
    "GuardClock",
    "app",
    "build_clock",
    "build_notifier",
    "default_gateway_factory",
]

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Thread Digest CLI")
db_app = typer.Typer(no_args_is_help=True, help="Database lifecycle: init, upgrade, current.")
config_app = typer.Typer(no_args_is_help=True, help="Configuration: validate.")
probe_app = typer.Typer(no_args_is_help=True, help="Dump Reddit's wire JSON (the probe day).")
app.add_typer(db_app, name="db")
app.add_typer(config_app, name="config")
app.add_typer(probe_app, name="probe")

#: The lock every mutating command takes, relative to the data directory (§12.2).
LOCK_RELATIVE_PATH: Final = Path("locks") / "collector.lock"

_LOCK_HELD_MESSAGE: Final = "another process holds the collector lock; nothing was collected"


class ConfigError(RuntimeError):
    """A precondition that exits 78 (§12.5).

    Raised for everything §8 maps to ``CONFIG``: invalid settings, a refused data directory,
    a missing database, pending migrations, a gateway this build cannot construct. Caught
    once per command body, which maps it to ``typer.Exit(ExitCode.CONFIG)``.
    """


# --- the gateway seam (§11.6) ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GatewaySpec:
    """Everything the factory needs to build a gateway, and nothing it does not."""

    kind: str
    fixture: Path | None
    settings: Settings


type GatewayFactory = Callable[[GatewaySpec], RedditGateway]


def default_gateway_factory(spec: GatewaySpec) -> RedditGateway:
    """Build the gateway ``--gateway`` names. The only construction site in production."""
    if spec.kind == "fake":
        if spec.fixture is not None:
            return FakeRedditGateway.from_fixture(spec.fixture)
        return FakeRedditGateway()
    if spec.kind == "praw":
        # Plain values, never the ``Settings`` object: the adapter takes what PRAW needs and
        # nothing else, which is also what makes it a one-line construction in a test. The
        # secret is unwrapped here, at the last possible moment, and nowhere else.
        return PrawGateway(
            PrawConfig(
                client_id=spec.settings.reddit_client_id,
                client_secret=spec.settings.reddit_client_secret.get_secret_value(),
                user_agent=user_agent(spec.settings, __version__),
            )
        )
    msg = f"unknown gateway {spec.kind!r}; --gateway takes praw or fake"
    raise ConfigError(msg)


#: THE injection seam for end-to-end tests. Production code never assigns to this name;
#: ``tests/e2e/conftest.py`` sets it and restores it. Everything else in ``cli`` calls it
#: rather than constructing a gateway directly.
GATEWAY_FACTORY: GatewayFactory = default_gateway_factory


# --- the clock and the notifier (§11.8) -------------------------------------------------------


class GuardClock:
    """A system clock that refuses to sleep. Installed by ``cli`` under pytest.

    ``now()`` is the real clock, so timestamps in an end-to-end run are ordinary.
    ``sleep()`` is the thing a test must never reach: a service that wants to wait under
    test has a ``FakeClock`` injected as a parameter, and an end-to-end test that reaches a
    sleep has planted a scenario the CLI path cannot serve without burning wall time.
    """

    def now(self) -> int:
        return int(time.time())

    def sleep(self, seconds: float) -> None:
        msg = (
            f"an end-to-end test asked the CLI to sleep {seconds}s; plant a fatal error, "
            f"or drive the service directly with a FakeClock"
        )
        raise AssertionError(msg)


def _under_pytest() -> bool:
    """Read at CALL time, never at import (§11.3's rule for the same variable)."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def build_clock() -> Clock:
    """:class:`SystemClock` in production, :class:`GuardClock` under pytest."""
    if _under_pytest():
        return GuardClock()
    return SystemClock()


def build_notifier() -> Notifier:
    """The macOS Notification Center on a real Mac; the log otherwise, and always in a test.

    The same call-time environment branch :func:`build_clock` uses, for the same reason: a
    test run must not put banners on the developer's desktop.
    """
    if _under_pytest() or sys.platform != "darwin":
        return LogNotifier()
    return MacNotifier()


# --- shared plumbing ---------------------------------------------------------------------------


#: The keyword arguments :func:`_settings` passes to ``Settings()``: none. It exists only so
#: mypy sees a ``**kwargs`` call -- ``Settings.static`` is filled by the ``config/settings.yaml``
#: settings source, which pydantic-settings installs at runtime and mypy cannot see, so a bare
#: ``Settings()`` reads as a missing required argument even though passing one is exactly what
#: production code must never do. The same constant exists in ``services/doctor.py``.
_FROM_ENVIRONMENT: Final[dict[str, Any]] = {}


def _settings() -> Settings:
    """Resolve settings, turning every refusal into a 78 (§11.3 step 1).

    The catch list is ``doctor.check_settings_valid``'s: the same four failure modes of the
    same load, so ``doctor`` reporting a broken configuration and ``run`` refusing to start
    on it cannot disagree about what "broken" means.
    """
    try:
        return Settings(**_FROM_ENVIRONMENT)
    except (ValidationError, DataDirRefusedError, yaml.YAMLError, OSError, TypeError) as exc:
        msg = f"settings did not resolve: {exc.__class__.__name__}: {exc}"
        raise ConfigError(msg) from exc


def _lock_path(settings: Settings) -> Path:
    return settings.data_dir / LOCK_RELATIVE_PATH


def _create_data_tree(data_dir: Path) -> None:
    """Create ``data/`` and its subdirectories **before** the lock decision.

    round5-findings.json's P0 "lock acquisition versus directory creation": the lock file
    lives inside the tree, so a data directory whose ``locks/`` is missing (a fresh install,
    a restore that skipped empty directories) would otherwise die with a ``FileNotFoundError``
    traceback instead of the documented 75/78. Creating directories inside the data dir is
    not a mutation of shared state, so it does not need the lock.
    """
    migrate_service.create_data_tree(data_dir)


def _exit(code: int) -> None:
    raise typer.Exit(code=code)


def _echo_error(message: str) -> None:
    typer.echo(message, err=True)


# --- run (§11.3) -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _RunOptions:
    """The parsed ``run`` invocation, so the ordering functions take one parameter."""

    gateway: str
    fixture: Path | None
    budget: int | None
    dry_run: bool
    no_comments: bool
    allow_fake_against_real_data: bool
    reason: str | None
    trigger: str


@app.command()
def run(
    gateway: str = typer.Option("praw", "--gateway", help="praw | fake."),
    fixture: Path | None = typer.Option(
        None, "--fixture", help="Scenario JSON for --gateway fake."
    ),
    budget: int | None = typer.Option(
        None, "--budget", min=0, help="Request budget; clamped to the configured hard cap."
    ),
    dry_run: bool = typer.Option(False, "--dry-run/--no-dry-run", help="Fetch, write nothing."),
    no_comments: bool = typer.Option(
        False, "--no-comments", help="Skip comments (needs --reason)."
    ),
    allow_fake_against_real_data: bool = typer.Option(
        False,
        "--allow-fake-against-real-data",
        help="Let --gateway fake write into a database that holds real runs (needs --reason).",
    ),
    reason: str | None = typer.Option(None, "--reason", help="Recorded in runs.options_json."),
    trigger: str = typer.Option("cli", "--trigger", help="cli | ui | schedule."),
) -> None:
    """Sweep every enabled source once and record the run."""
    if no_comments and reason is None:
        msg = "--no-comments requires --reason"
        raise typer.BadParameter(msg)
    if allow_fake_against_real_data and reason is None:
        msg = "--allow-fake-against-real-data requires --reason"
        raise typer.BadParameter(msg)
    options = _RunOptions(
        gateway=gateway,
        fixture=fixture,
        budget=budget,
        dry_run=dry_run,
        no_comments=no_comments,
        allow_fake_against_real_data=allow_fake_against_real_data,
        reason=reason,
        trigger=trigger,
    )
    try:
        code = _run_ordered(options)
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(code)


def _run_ordered(options: _RunOptions) -> int:
    """§11.3's table, in order: settings, the two gateway guards, the database, the tree,
    the lock decision, and only then an engine."""
    settings = _settings()
    _guard_gateway(options.gateway, settings)
    db_path = db_path_for(settings.data_dir)
    if not db_path.is_file():
        # One sentence for both commands: `db upgrade` refuses the same precondition through
        # `migrate_service.DatabaseMissingError`, built from this same function (§8).
        raise ConfigError(migrate_service.database_missing_message(db_path))
    _create_data_tree(settings.data_dir)
    lock_path = _lock_path(settings)
    if options.dry_run:
        # A dry run PROBES the lock and never acquires it: acquiring would make a read-only
        # command a mutator of shared state and block the scheduled collector (§11.3).
        if lock.is_held(lock_path):
            _echo_error(_LOCK_HELD_MESSAGE)
            return int(ExitCode.SKIPPED_LOCKED)
        return _collect_through(options, settings=settings, db_path=db_path)
    try:
        with lock.acquire(lock_path):
            return _collect_through(options, settings=settings, db_path=db_path)
    except lock.LockHeldError:
        _record_skipped_locked(settings, options.trigger)
        _echo_error(_LOCK_HELD_MESSAGE)
        return int(ExitCode.SKIPPED_LOCKED)


def _guard_gateway(kind: str, settings: Settings) -> None:
    """§11.3 steps 2 and 3: the fake is refused against the real data directory, and a
    network gateway is refused under pytest. Both exit 78 with no run row.

    This clause is **location**-based and therefore not sufficient on its own: doctor's
    ``data_dir_outside_tcc`` check pushes operators to relocate the data directory, and a
    relocated one used to be completely unprotected (round5-findings.json panel P1).
    :func:`_guard_fake_against_real_data` is the content-based half; both must hold.
    """
    if kind == "fake" and settings.data_dir == default_data_dir().resolve():
        msg = (
            f"--gateway fake is refused against the default data directory {settings.data_dir}; "
            "point THREADDIGEST_DATA_DIR at a scratch directory"
        )
        raise ConfigError(msg)
    if kind != "fake" and _under_pytest():
        msg = f"refusing --gateway {kind} under pytest; only --gateway fake may run in a test"
        raise ConfigError(msg)


def _recorded_gateway(options_json: str) -> str | None:
    """The ``gateway`` key one ``runs.options_json`` recorded, or ``None`` when unreadable.

    Unreadable is treated as "not the fake" by the caller: a row whose options this build
    cannot parse is not evidence that the database is a scratch one.
    """
    try:
        payload = json.loads(options_json)
    except json.JSONDecodeError:
        return None
    kind = payload.get("gateway") if isinstance(payload, dict) else None
    return kind if isinstance(kind, str) else None


def _guard_fake_against_real_data(engine: Engine, options: _RunOptions) -> None:
    """Refuse ``--gateway fake`` when this database already holds a real collection run.

    The content-based half of the D-10 guard (round5-findings.json panel P1). The location
    clause in :func:`_guard_gateway` only knows the default directory, so
    ``THREADDIGEST_DATA_DIR=/Volumes/data threaddigest run --gateway fake --fixture demo.json``
    -- the line an operator copy-pastes out of ``make run`` -- wrote fabricated posts, sources,
    snapshots and author aggregates into a live collection, with ``first_seen_at`` and the pks
    fixed forever after.

    The evidence is the ``gateway`` key ``_options_json`` records on every collection run: a
    ``kind='run'`` row whose recorded gateway is anything but ``fake`` means real data. A
    ``NULL`` ``options_json`` is a ``skipped_locked`` row, which wrote nothing, so it is not
    evidence either way. ``--allow-fake-against-real-data --reason "…"`` is the explicit
    opt-in, and it is recorded in ``options_json`` like every other bypass flag.
    """
    if options.gateway != "fake" or options.allow_fake_against_real_data:
        return
    with engine.connect() as conn:
        recorded = [
            _recorded_gateway(payload) for payload in repo.run_options(conn) if payload is not None
        ]
    real = sorted({kind or "(unreadable)" for kind in recorded if kind != "fake"})
    if not real:
        return
    msg = (
        f"--gateway fake is refused against a database that already holds real collection "
        f"runs (gateways recorded: {', '.join(real)}); point THREADDIGEST_DATA_DIR at a "
        f"scratch directory, or pass --allow-fake-against-real-data --reason '<why>'"
    )
    raise ConfigError(msg)


def _record_skipped_locked(settings: Settings, trigger: str) -> None:
    """§11.3 step 5's best-effort row: the Runs page shows the attempt, never a gap.

    The insert is the one place a repo call may legitimately meet a database below head
    (the lock's holder may be mid-migration), so a ``DatabaseError`` here is expected, named,
    echoed and survived -- the exit code is 75 on both paths.
    """
    now = build_clock().now()
    engine = engine_for(db_path_for(settings.data_dir))
    try:
        with engine.begin() as conn:
            run_pk = repo.insert_run(
                conn,
                repo.RunInsert(
                    kind="run",
                    trigger=trigger,
                    status="skipped_locked",
                    created_at=now,
                    started_at=now,
                    pid=os.getpid(),
                    stage=None,
                    options_json=None,
                    app_version=__version__,
                    praw_version=None,
                    schema_rev=None,
                    settings_fingerprint=None,
                    log_path=None,
                ),
            )
            repo.finish_run(
                conn,
                run_pk=run_pk,
                status="skipped_locked",
                finished_at=now,
                counters_json=runs.Counters().to_json(),
                api_requests=0,
                error="another process holds the collector lock",
                violations_json=None,
                # A run that never started recorded nothing, which NULL says and `[]`
                # would not: `[]` is a run that looked and found no warning.
                warnings_json=None,
            )
    except DatabaseError as exc:
        _echo_error(
            f"lock held and the database is busy ({exc.__class__.__name__}); no run row recorded"
        )
    finally:
        engine.dispose()


def _collect_through(options: _RunOptions, *, settings: Settings, db_path: Path) -> int:
    """Steps 6-10: the engine, ``require_head``, the collaborators, ``collect``, the summary.

    The engine is disposed on every path, including the one SW-04 depends on, where
    ``CrashInjected`` escapes uncaught through this ``finally`` and out of the process.
    """
    engine = engine_for(db_path, read_only=options.dry_run)
    try:
        _require_head(engine)
        # The content half of the D-10 guard needs the database the location half cannot see.
        # It runs before GATEWAY_FACTORY, so RL-02's "zero gateway calls" still holds, and
        # before `collect`, so a refusal still writes no run row.
        _guard_fake_against_real_data(engine, options)
        budget = _budget_for(settings, options.budget)
        gateway = GATEWAY_FACTORY(
            GatewaySpec(kind=options.gateway, fixture=options.fixture, settings=settings)
        )
        outcome = collect_service.collect(
            engine,
            settings=settings,
            clock=build_clock(),
            gateway=gateway,
            notifier=build_notifier(),
            trigger=options.trigger,
            dry_run=options.dry_run,
            budget=budget,
            options_json=_options_json(options, budget),
        )
        _print_run_summary(outcome)
        return outcome.exit_code
    finally:
        engine.dispose()


def _require_head(engine: Engine) -> None:
    """§11.3 step 7. A plain ``SELECT``, so it works on the dry run's ``mode=ro`` engine."""
    try:
        db_migrate.require_head(engine)
    except db_migrate.MigrationsPendingError as exc:
        raise ConfigError(str(exc)) from exc


def _budget_for(settings: Settings, requested: int | None) -> Budget:
    """§11.5, once and explicitly.

    The ``reserve`` line is not decoration: ``Budget`` refuses a reserve larger than its
    limit, so ``--budget 50`` without this clamp is a traceback instead of one affordable
    request.
    """
    static = settings.static.budget
    limit = static.per_run_requests if requested is None else requested
    limit = min(max(limit, 0), static.hard_cap)
    reserve = min(static.reserve, max(limit - 1, 0))
    return Budget(limit=limit, reserve=reserve, hard_cap=static.hard_cap)


def _options_json(options: _RunOptions, budget: Budget) -> str:
    """``runs.options_json``: the bypass flags verbatim, and the budget actually in force.

    The clamp is recorded rather than inferred, so ``--budget 999999`` leaves evidence of
    what the run was allowed to spend (CF-02).
    """
    payload = {
        "gateway": options.gateway,
        "fixture": None if options.fixture is None else str(options.fixture),
        "dry_run": options.dry_run,
        "no_comments": options.no_comments,
        "allow_fake_against_real_data": options.allow_fake_against_real_data,
        "reason": options.reason,
        "budget": {
            "limit": budget.limit,
            "reserve": budget.reserve,
            "hard_cap": budget.hard_cap,
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _print_run_summary(outcome: collect_service.CollectOutcome) -> None:
    """One block on stdout: the status, the request cost, the counters, every source.

    A dry run's ``posts_new`` / ``posts_updated`` are structurally 0 (nothing is written),
    so the line says so rather than letting "0 new" read as a finding about Reddit
    (round5-findings.json, ``P1-dry-run-swallows-failures``).
    """
    counters = outcome.counters
    typer.echo(f"status: {outcome.status.value} (exit {outcome.exit_code})")
    typer.echo(f"api_requests: {counters.api_requests}  pages: {counters.pages}")
    typer.echo(
        f"posts_new: {counters.posts_new}  posts_updated: {counters.posts_updated}  "
        f"rejects: {counters.rejects}  warnings: {counters.warnings}"
    )
    if outcome.run_pk is None:
        # Precise about the guarantee (KI, external round one, finding 12): a dry run writes no
        # row to any table and no run row; it does create the data directories and the
        # read-only engine's -wal/-shm sidecar files, so it does not claim "nothing was written."
        typer.echo(
            "dry run: no database rows written; posts_new and posts_updated are always 0 here"
        )
    if outcome.sweep is not None:
        for source in outcome.sweep.subreddits:
            error = "" if source.error is None else f" error={source.error}"
            typer.echo(
                f"  r/{source.name_lower}: pages={source.pages} items={source.items_seen} "
                f"new={source.new_items} updated={source.updated_items} "
                f"status={source.status}{error}"
            )
    if outcome.violations:
        typer.echo(invariants.render(outcome.violations))


# --- doctor (§15) ------------------------------------------------------------------------------


@app.command()
def doctor(
    no_network: bool = typer.Option(
        True,
        "--no-network/--network",
        help="Make no request (the default). --network adds the auth ping: one `about` "
        "plus a free rate-limit read, two HTTP calls in total.",
    ),
    alert_if_stale: str = typer.Option(
        doctor_service.DEFAULT_ALERT_IF_STALE,
        "--alert-if-stale",
        help='Last-run age that counts as stale, e.g. "5d", "36h"; the default outlasts the '
        "longest gap between scheduled runs.",
    ),
    json_output: bool = typer.Option(False, "--json/--no-json", help="Machine-readable output."),
) -> None:
    """Check this installation and report every check by name."""
    try:
        settings = _settings()
        report = _doctor_report(settings, alert_if_stale=alert_if_stale, no_network=no_network)
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    if json_output:
        # Nothing else may reach stdout on this path: the payload IS the output.
        typer.echo(
            json.dumps(
                {"ok": report.ok, "checks": [dataclasses.asdict(c) for c in report.checks]},
                indent=2,
            )
        )
    else:
        for check in report.checks:
            mark = "ok " if check.ok else check.severity.value[:3].upper()
            typer.echo(f"[{mark}] {check.name}: {check.detail}")
    _exit(report.exit_code)


#: The gateway ``doctor --network`` builds. Named once so the guard and the factory cannot
#: drift apart, and so the refusal an operator reads names the kind they would recognise.
_DOCTOR_GATEWAY: Final = "praw"


def _doctor_gateway(settings: Settings, *, no_network: bool) -> RedditGateway | None:
    """The gateway the auth ping speaks through, or ``None`` on the default no-network path.

    :func:`_guard_gateway` runs **first**, exactly as it does in ``run`` and ``probe``: under
    pytest it raises before ``GATEWAY_FACTORY`` is called at all, so the one ``doctor`` path
    that can reach Reddit is unreachable from a test and exits 78 with a message.

    A gateway this build cannot construct -- credentials PRAW refuses to build a client from,
    say -- is the case :class:`ConfigError` already names, so the port's error is translated
    here rather than escaping as a traceback out of a command whose job is to report.
    """
    if no_network:
        return None
    _guard_gateway(_DOCTOR_GATEWAY, settings)
    try:
        return GATEWAY_FACTORY(GatewaySpec(kind=_DOCTOR_GATEWAY, fixture=None, settings=settings))
    except GatewayError as exc:
        msg = f"cannot build the {_DOCTOR_GATEWAY} gateway for the auth ping: {exc}"
        raise ConfigError(msg) from exc


def _doctor_report(
    settings: Settings, *, alert_if_stale: str, no_network: bool
) -> doctor_service.DoctorReport:
    """``--alert-if-stale`` is parsed by the service; a bad duration is a config error, not a
    traceback. ``--network`` additionally builds the gateway the auth ping speaks through;
    ``--no-network``, the default, builds nothing."""
    gateway = _doctor_gateway(settings, no_network=no_network)
    try:
        return doctor_service.run_checks(
            settings=settings,
            clock=build_clock(),
            gateway=gateway,
            alert_if_stale=alert_if_stale,
            no_network=no_network,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


# --- serve (plan § Web UI; the first web slice) ------------------------------------------------


#: The UI's address, and the one the launchd wrapper's failure notification already links to
#: (``deploy/launchd/run.sh``). There is no ``--host``: the plan's command line is
#: ``serve [--port 8765]``, and binding anywhere but loopback is a decision (D-20, the LAN at
#: M4), not a flag.
SERVE_HOST: Final = "127.0.0.1"

_SERVE_UNDER_PYTEST = (
    "refusing to start a web server under pytest; the suite drives the application in-process "
    "through Starlette's TestClient, which opens no socket"
)


def _refuse_a_server_under_pytest() -> None:
    """The last precondition, deliberately last.

    Checked after the database preconditions rather than first: from the top this guard
    would shadow them, and the tests that prove a missing or behind-head database is refused
    could never reach them (they run under pytest by definition). What the guard buys is that
    no test ever opens a socket, and it buys that just as completely from the line before
    ``uvicorn.run``.
    """
    if _under_pytest():
        raise ConfigError(_SERVE_UNDER_PYTEST)


def _serve_preconditions() -> Settings:
    """Settings, a database that exists, and a schema at head -- every refusal a 78.

    ``run`` refuses the same two database preconditions with the same words, because an
    operator who has just been told by ``run`` that the database is missing must not be told
    something different by ``serve``. Maintenance-only mode (serve ``/system`` so a pending
    migration can be applied from the page) is deliberately not built here: ``/system``
    arrives at M2, and a maintenance mode with nowhere to go is the UI panel's § D finding 1
    in reverse.
    """
    settings = _settings()
    db_path = db_path_for(settings.data_dir)
    if not db_path.is_file():
        raise ConfigError(migrate_service.database_missing_message(db_path))
    engine = engine_for(db_path, read_only=True)
    try:
        _require_head(engine)
    finally:
        engine.dispose()
    return settings


@app.command()
def serve(
    port: int = typer.Option(8765, "--port", min=1, max=65535, help="TCP port on 127.0.0.1."),
) -> None:
    """Serve the web UI on 127.0.0.1 (the run history, one run, the digest; the rest at M2)."""
    try:
        settings = _serve_preconditions()
        _refuse_a_server_under_pytest()
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    uvicorn.run(create_app(settings=settings), host=SERVE_HOST, port=port)


# --- db (§10.3) --------------------------------------------------------------------------------


type _Lifecycle = Callable[..., migrate_service.MigrationOutcome]


def _lifecycle(lifecycle: _Lifecycle) -> int:
    """Run one database lifecycle with the collaborators ``cli`` owns.

    Both lifecycles take the collector lock themselves (RL-04), so a held lock arrives here
    as :class:`~threaddigest.services.lock.LockHeldError` and exits 75; a database below head
    that ``db init`` refuses to migrate arrives as ``MigrationsPendingError`` and exits 78.

    Two more named preconditions exit 78 the same way (round5-findings.json panel P0/P1):
    ``DatabaseMissingError`` -- ``db upgrade`` before ``db init``, or after a restore that lost
    the file -- and ``UnknownRevisionError``, a database stamped ahead of this build. Both are
    raised before any run row exists, which is exactly what §8 says a 78 means.
    """
    settings = _settings()
    clock = build_clock()

    def ctx_factory(engine: Engine, kind: str) -> runs.RunContext:
        return runs.start_run(engine, kind=kind, trigger="cli", clock=clock, settings=settings)

    try:
        outcome = lifecycle(ctx_factory, settings=settings, clock=clock, notifier=build_notifier())
    except lock.LockHeldError as exc:
        _echo_error(str(exc))
        return int(ExitCode.SKIPPED_LOCKED)
    except (
        db_migrate.MigrationsPendingError,
        db_migrate.UnknownRevisionError,
        migrate_service.DatabaseMissingError,
    ) as exc:
        raise ConfigError(str(exc)) from exc
    _print_migration(outcome)
    return int(ExitCode.FAILED) if outcome.error is not None else int(ExitCode.OK)


def _print_migration(outcome: migrate_service.MigrationOutcome) -> None:
    typer.echo(f"schema: {outcome.from_revision} -> {outcome.to_revision}")
    if outcome.backup_path is not None:
        typer.echo(f"backup: {outcome.backup_path}")
    if outcome.restored:
        typer.echo("restored: the database is back at its pre-migration revision")
    if outcome.error is not None:
        _echo_error(outcome.error)


@db_app.command("init")
def db_init() -> None:
    """Create the data directory tree, bring the schema to head and seed the sources."""
    try:
        code = _lifecycle(migrate_service.db_init)
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(code)


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Back up, migrate to head, verify, and restore the backup if the migration fails."""
    try:
        code = _lifecycle(migrate_service.db_upgrade)
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(code)


@db_app.command("current")
def db_current() -> None:
    """Print the database's revision and the revision this build expects."""
    try:
        settings = _settings()
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    current, head = migrate_service.db_current(settings=settings)
    typer.echo(f"current: {current}")
    typer.echo(f"head: {head}")
    _exit(int(ExitCode.OK))


# --- config ------------------------------------------------------------------------------------


@config_app.command("validate")
def config_validate() -> None:
    """Resolve the settings and report them; secrets are never printed."""
    try:
        settings = _settings()
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    typer.echo("settings: ok")
    typer.echo(f"data_dir: {settings.data_dir}")
    typer.echo(f"settings_file: {settings.settings_file}")
    typer.echo(f"fingerprint: {settings_fingerprint(settings)}")
    _exit(int(ExitCode.OK))


# --- probe (plan § CLI; the credentialed probe day, runbook § 9) -------------------------------
#
# `probe` writes no database row and takes no lock (RL-04 excludes it: tests/gates/
# test_mutating_commands.py's EXCLUDED_COMMANDS), so it has none of `run`'s lock/db/engine
# steps -- just the two gateway guards, one gateway, one capture, and an optional save.
#
# `--gateway`/`--fixture` (identical to `run`'s) are declared once, on the `probe` group's own
# callback, rather than repeated on all five sub-commands: it resolves and guards the gateway
# exactly once per invocation, before any sub-command body runs, and hands it down through a
# module-level slot (`_probe_ctx`) instead of five copies of the same two parameters --
# `click.get_current_context()` was tried first and does not work here: Typer 0.15 calls a
# sub-command's function directly rather than through `ctx.invoke`, so no click context is
# active by the time a sub-command body runs, even though the group's own callback just set
# one. The CLI is one synchronous invocation per process, so a module-level slot set once by
# `probe_main` and read once by the sub-command that follows it is safe. `--save-fixture`/
# `--blank-bodies` (services/probe.py's `save`) stay on each sub-command, where CONTRACT item 4
# places them.


def _strip_leading(text: str, prefix: str) -> str:
    return text[len(prefix) :] if text.lower().startswith(prefix) else text


def _subreddit_name(raw: str) -> str:
    """Accept ``r/<sub>`` or a bare ``<sub>``."""
    return _strip_leading(raw, "r/")


def _listing_target(raw: str) -> str:
    """Accept ``r/<sub>/new``, ``<sub>/new``, or a bare ``<sub>``."""
    name = _subreddit_name(raw)
    return name[: -len("/new")] if name.lower().endswith("/new") else name


@dataclass(frozen=True, slots=True)
class _ProbeContext:
    """What ``probe_main`` resolves once and every sub-mode reuses: the settings, and the
    already-guarded, already-constructed gateway."""

    settings: Settings
    gateway: RedditGateway


#: Set once by ``probe_main`` (the group callback), read once by the sub-command that follows
#: it in the same process. See the module note above for why this is a plain slot and not
#: ``click``'s context.
_probe_ctx_holder: _ProbeContext | None = None


def _probe_ctx() -> _ProbeContext:
    """The context ``probe_main`` resolved for this invocation.

    Fetched rather than taken as a parameter so each sub-command keeps only its own
    mode-specific options and the two universal ones (``--save-fixture``/``--blank-bodies``),
    which is what keeps every sub-command at or under five arguments (the size ratchet).
    """
    assert _probe_ctx_holder is not None  # set by probe_main, which always runs first
    return _probe_ctx_holder


def _emit_capture(
    capture: probe_service.Capture,
    *,
    settings: Settings,
    save_fixture: str | None,
    blank_bodies: bool,
) -> None:
    """Print the scrubbed payload -- what is printed is what would be saved -- then, when
    ``--save-fixture`` is given, save it and print the promotion command it returns."""
    typer.echo(json.dumps(capture.payload, indent=2, sort_keys=True))
    typer.echo(f"requests_used: {capture.requests_used}")
    if save_fixture is None:
        return
    try:
        path = probe_service.save(
            capture, data_dir=settings.data_dir, name=save_fixture, blank_bodies=blank_bodies
        )
    except probe_service.FixtureExistsError as exc:
        raise ConfigError(str(exc)) from exc
    typer.echo(f"wrote {path}")
    typer.echo(probe_service.promotion_command(path, save_fixture))


_SAVE_FIXTURE_HELP: Final = "Save the scrubbed capture under <data_dir>/probe/<name>.json."
_BLANK_BODIES_HELP: Final = "Blank selftext/body/selftext_html/body_html before saving."


def _probe_gateway(kind: str, fixture: Path | None, settings: Settings) -> RedditGateway:
    """The gateway ``probe`` speaks through, with a construction failure named, not raised.

    A gateway this build cannot construct -- credentials PRAW refuses to build a client from, a
    client that came back read-write, an injected client without its counting session -- is the
    case :class:`ConfigError` already names, so the port's error is translated here rather than
    escaping as a traceback out of the one command whose job is to report what Reddit answers
    (KI-029). ``doctor --network`` translates the same error at its own seam
    (:func:`_doctor_gateway`), and this keeps the two paths the same shape.
    """
    try:
        return GATEWAY_FACTORY(GatewaySpec(kind=kind, fixture=fixture, settings=settings))
    except GatewayError as exc:
        msg = f"cannot build the {kind} gateway for the probe: {exc}"
        raise ConfigError(msg) from exc


@probe_app.callback()
def probe_main(
    gateway: str = typer.Option("praw", "--gateway", help="praw | fake."),
    fixture: Path | None = typer.Option(
        None, "--fixture", help="Scenario JSON for --gateway fake."
    ),
) -> None:
    """Dump Reddit's wire JSON for the probe day (runbook § 9): ``about``, ``listing``,
    ``tree``, ``info``, ``search``, each with ``--save-fixture``/``--blank-bodies``."""
    global _probe_ctx_holder
    try:
        settings = _settings()
        _guard_gateway(gateway, settings)
        reddit_gateway = _probe_gateway(gateway, fixture, settings)
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _probe_ctx_holder = _ProbeContext(settings=settings, gateway=reddit_gateway)


@probe_app.command("about")
def probe_about(
    subreddit: str = typer.Argument(..., help="r/<sub> or <sub>."),
    save_fixture: str | None = typer.Option(None, "--save-fixture", help=_SAVE_FIXTURE_HELP),
    blank_bodies: bool = typer.Option(False, "--blank-bodies", help=_BLANK_BODIES_HELP),
) -> None:
    """Dump ``/r/<sub>/about`` as scrubbed JSON."""
    probe_ctx = _probe_ctx()
    try:
        capture = probe_service.capture_about(probe_ctx.gateway, _subreddit_name(subreddit))
        _emit_capture(
            capture,
            settings=probe_ctx.settings,
            save_fixture=save_fixture,
            blank_bodies=blank_bodies,
        )
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(int(ExitCode.OK))


@probe_app.command("listing")
def probe_listing(
    target: str = typer.Argument(..., help="r/<sub>/new (or <sub>/new, or <sub>)."),
    limit: int = typer.Option(25, "--limit", min=1, help="Items to collect, across pages."),
    save_fixture: str | None = typer.Option(None, "--save-fixture", help=_SAVE_FIXTURE_HELP),
    blank_bodies: bool = typer.Option(False, "--blank-bodies", help=_BLANK_BODIES_HELP),
) -> None:
    """Dump up to ``--limit`` items of ``/r/<sub>/new``, paging as needed, cursors recorded."""
    probe_ctx = _probe_ctx()
    try:
        capture = probe_service.capture_listing(
            probe_ctx.gateway, _listing_target(target), limit=limit
        )
        _emit_capture(
            capture,
            settings=probe_ctx.settings,
            save_fixture=save_fixture,
            blank_bodies=blank_bodies,
        )
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(int(ExitCode.OK))


@probe_app.command("tree")
def probe_tree(
    post_id: str = typer.Argument(..., help="A post id or fullname (t3_...)."),
    more_limit: int = typer.Option(
        16,
        "--more-limit",
        min=0,
        help="`more` stubs to expand (comments.replace_more_limit's shipped default).",
    ),
    save_fixture: str | None = typer.Option(None, "--save-fixture", help=_SAVE_FIXTURE_HELP),
    blank_bodies: bool = typer.Option(False, "--blank-bodies", help=_BLANK_BODIES_HELP),
) -> None:
    """Dump a comment tree: the post, the flattened comments, and the `more` stubs."""
    probe_ctx = _probe_ctx()
    try:
        capture = probe_service.capture_tree(probe_ctx.gateway, post_id, more_limit=more_limit)
        _emit_capture(
            capture,
            settings=probe_ctx.settings,
            save_fixture=save_fixture,
            blank_bodies=blank_bodies,
        )
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(int(ExitCode.OK))


@probe_app.command("info")
def probe_info(
    fullnames: str = typer.Argument(..., help="Comma-separated fullnames, e.g. t3_abc,t1_def."),
    save_fixture: str | None = typer.Option(None, "--save-fixture", help=_SAVE_FIXTURE_HELP),
    blank_bodies: bool = typer.Option(False, "--blank-bodies", help=_BLANK_BODIES_HELP),
) -> None:
    """Dump one ``/api/info`` batch."""
    probe_ctx = _probe_ctx()
    try:
        names = [name.strip() for name in fullnames.split(",") if name.strip()]
        capture = probe_service.capture_info(probe_ctx.gateway, names)
        _emit_capture(
            capture,
            settings=probe_ctx.settings,
            save_fixture=save_fixture,
            blank_bodies=blank_bodies,
        )
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(int(ExitCode.OK))


@probe_app.command("search")
def probe_search(
    query: str = typer.Argument(..., help="Search query."),
    sort: str = typer.Option("new", "--sort", help="Reddit's search sort."),
    time_filter: str = typer.Option("week", "--time-filter", help="Reddit's search window."),
    save_fixture: str | None = typer.Option(None, "--save-fixture", help=_SAVE_FIXTURE_HELP),
    blank_bodies: bool = typer.Option(False, "--blank-bodies", help=_BLANK_BODIES_HELP),
) -> None:
    """Dump ``/r/all/search`` pages for one saved-search query."""
    probe_ctx = _probe_ctx()
    try:
        capture = probe_service.capture_search(
            probe_ctx.gateway, query, sort=sort, time_filter=time_filter
        )
        _emit_capture(
            capture,
            settings=probe_ctx.settings,
            save_fixture=save_fixture,
            blank_bodies=blank_bodies,
        )
    except ConfigError as exc:
        _echo_error(str(exc))
        raise typer.Exit(code=ExitCode.CONFIG) from exc
    _exit(int(ExitCode.OK))


# --- the app callback --------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"threaddigest {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Print the version."
    ),
) -> None:
    """Thread Digest command-line interface."""


if __name__ == "__main__":  # pragma: no cover
    app()
