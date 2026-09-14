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
import yaml
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import DatabaseError

from insightminer import __version__
from insightminer.adapters.clock import SystemClock
from insightminer.adapters.notify import LogNotifier, MacNotifier
from insightminer.adapters.reddit_fake import FakeRedditGateway
from insightminer.core.budget import Budget
from insightminer.core.retry import ExitCode
from insightminer.db import migrate as db_migrate
from insightminer.db import repo
from insightminer.db.engine import db_path_for, engine_for
from insightminer.ports import Clock, Notifier, RedditGateway
from insightminer.services import collect as collect_service
from insightminer.services import doctor as doctor_service
from insightminer.services import invariants, lock, runs
from insightminer.services import migrate as migrate_service
from insightminer.settings import (
    DataDirRefusedError,
    Settings,
    default_data_dir,
    settings_fingerprint,
)

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

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Insight Miner CLI")
db_app = typer.Typer(no_args_is_help=True, help="Database lifecycle: init, upgrade, current.")
config_app = typer.Typer(no_args_is_help=True, help="Configuration: validate.")
app.add_typer(db_app, name="db")
app.add_typer(config_app, name="config")

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
    msg = f"the {spec.kind} gateway lands in tranche B; only --gateway fake works today"
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
    reason: str | None = typer.Option(None, "--reason", help="Recorded in runs.options_json."),
    trigger: str = typer.Option("cli", "--trigger", help="cli | ui | schedule."),
) -> None:
    """Sweep every enabled source once and record the run."""
    if no_comments and reason is None:
        msg = "--no-comments requires --reason"
        raise typer.BadParameter(msg)
    options = _RunOptions(
        gateway=gateway,
        fixture=fixture,
        budget=budget,
        dry_run=dry_run,
        no_comments=no_comments,
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
        msg = f"no database at {db_path}; run: insightminer db init"
        raise ConfigError(msg)
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
    network gateway is refused under pytest. Both exit 78 with no run row."""
    if kind == "fake" and settings.data_dir == default_data_dir().resolve():
        msg = (
            f"--gateway fake is refused against the default data directory {settings.data_dir}; "
            "point INSIGHTMINER_DATA_DIR at a scratch directory"
        )
        raise ConfigError(msg)
    if kind != "fake" and _under_pytest():
        msg = f"refusing --gateway {kind} under pytest; only --gateway fake may run in a test"
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
        typer.echo("dry run: nothing was written; posts_new and posts_updated are always 0 here")
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
    no_network: bool = typer.Option(True, "--no-network/--network", help="Make no request."),
    alert_if_stale: str = typer.Option("36h", "--alert-if-stale", help='e.g. "36h", "2d".'),
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


def _doctor_report(
    settings: Settings, *, alert_if_stale: str, no_network: bool
) -> doctor_service.DoctorReport:
    """``--alert-if-stale`` is parsed by the service; a bad duration is a config error, not a
    traceback."""
    try:
        return doctor_service.run_checks(
            settings=settings,
            clock=build_clock(),
            alert_if_stale=alert_if_stale,
            no_network=no_network,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


# --- db (§10.3) --------------------------------------------------------------------------------


type _Lifecycle = Callable[..., migrate_service.MigrationOutcome]


def _lifecycle(lifecycle: _Lifecycle) -> int:
    """Run one database lifecycle with the collaborators ``cli`` owns.

    Both lifecycles take the collector lock themselves (RL-04), so a held lock arrives here
    as :class:`~insightminer.services.lock.LockHeldError` and exits 75; a database below head
    that ``db init`` refuses to migrate arrives as ``MigrationsPendingError`` and exits 78.
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
    except db_migrate.MigrationsPendingError as exc:
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


# --- the app callback --------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"insightminer {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Print the version."
    ),
) -> None:
    """Insight Miner command-line interface."""


if __name__ == "__main__":  # pragma: no cover
    app()
