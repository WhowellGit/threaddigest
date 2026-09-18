"""Deployment gate: the launchd agents in deploy/launchd install and behave as docs/PLAN.md says.

Everything here runs the real artefacts (`plutil`, `/bin/bash`, the wrapper scripts) against
fake repository roots under ``tmp_path``. ``osascript``, ``caffeinate`` and ``launchctl`` are
replaced by recorders on PATH and ``threaddigest`` by a stub module on PYTHONPATH, so nothing
reaches Notification Center, ~/Library/LaunchAgents, or the real data directory.

macOS-only by design: a missing ``plutil`` is a failure with a clear message, never a skip.

**What this module does not prove.** The stub on ``PYTHONPATH`` supplies the ``__main__``
module the wrapper's ``-m threaddigest`` needs, so every test here passes whether or not the
real package has one: these are tests of the wrapper's plumbing, never of the entry point it
calls. ``tests/deploy/test_entry_point.py`` runs the real interpreter against the real package
for that (KI-045, the 2026-09-17 code panel's seat B finding B1).
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.macos

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHD_DIR = REPO_ROOT / "deploy" / "launchd"
RUN_LABEL = "io.github.whowellgit.threaddigest.run"
DOCTOR_LABEL = "io.github.whowellgit.threaddigest.doctor"
LABELS = (RUN_LABEL, DOCTOR_LABEL)
EXECUTABLE_SCRIPTS = ("run.sh", "install.sh", "uninstall.sh")
SCRIPTS = ("common.sh", *EXECUTABLE_SCRIPTS)
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
UI = "http://127.0.0.1:8765"
TIMESTAMPED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4} \[(?:run|doctor)\] ", re.M)

# Exit codes the wrapper must handle, grouped by the action docs/PLAN.md assigns to them.
NOTIFY = {1: "failed", 78: "config error", 2: "unexpected exit 2"}
RETRY = {4: "rate limited", 5: "network"}
# 3 (partial) is quiet since 2026-09-16: an amber run is read in the digest and on the Runs
# page, and alerting on it would train the operator to ignore the alert (the code's own
# rule in services/collect.py, which the wrapper had contradicted).
QUIET = {0: "ok", 75: "lock", 130: "cancelled", 3: "partial"}

STUB_MAIN = '''\
"""Stand-in for `python -m threaddigest`: records how it was called, exits as told."""
import json
import os
import sys

record = os.path.join(os.environ["STUB_RECORD_DIR"], "threaddigest.json")
with open(record, "w", encoding="utf-8") as fh:
    json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ)}, fh)
print("stub threaddigest: hello from stdout")
print("stub threaddigest: hello from stderr", file=sys.stderr)
sys.exit(int(os.environ.get("STUB_EXIT_CODE", "0")))
'''

# Recorders: each writes its arguments (one per line) into $STUB_RECORD_DIR.
STUB_OSASCRIPT = """\
#!/bin/sh
printf '%s\\n' "$@" > "$STUB_RECORD_DIR/osascript.args"
exit "${STUB_OSASCRIPT_EXIT:-0}"
"""
STUB_CAFFEINATE = """\
#!/bin/sh
printf '%s\\n' "$@" > "$STUB_RECORD_DIR/caffeinate.args"
[ "$1" = "-i" ] && shift
exec "$@"
"""
STUB_LAUNCHCTL = """\
#!/bin/sh
printf '%s\\n' "$@" >> "$STUB_RECORD_DIR/launchctl.args"
echo "stub launchctl: a dry run must never reach launchctl" >&2
exit 1
"""


def _plutil() -> str:
    found = shutil.which("plutil")
    assert found is not None, (
        "plutil is not on PATH. These deployment tests need macOS (plutil ships in /usr/bin); "
        "they fail rather than skip so a broken plist can never pass unnoticed."
    )
    return found


def _run(argv: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
        timeout=120,
    )


def _bash(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run(["/bin/bash", str(script), *args], env=env)


def _render(label: str, root: Path, dest_dir: Path) -> Path:
    """Substitute ``__ROOT__`` the way install.sh does and return the rendered copy."""
    text = (LAUNCHD_DIR / f"{label}.plist").read_text(encoding="utf-8")
    assert "__ROOT__" in text, f"{label}.plist has no __ROOT__ placeholder to substitute"
    dest = dest_dir / f"{label}.plist"
    dest.write_text(text.replace("__ROOT__", str(root)), encoding="utf-8")
    return dest


def _load(label: str, root: Path, dest_dir: Path) -> dict[str, object]:
    with _render(label, root, dest_dir).open("rb") as fh:
        data = plistlib.load(fh)
    assert isinstance(data, dict)
    return data


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _listing(directory: Path) -> set[str]:
    return {entry.name for entry in directory.iterdir()} if directory.is_dir() else set()


def _recorders(tmp_path: Path) -> tuple[Path, Path]:
    """A bin dir of recorder stubs and the directory they record into."""
    record = tmp_path / "record"
    record.mkdir()
    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    _write_executable(stub_bin / "osascript", STUB_OSASCRIPT)
    _write_executable(stub_bin / "caffeinate", STUB_CAFFEINATE)
    _write_executable(stub_bin / "launchctl", STUB_LAUNCHCTL)
    return stub_bin, record


def _real_env_with_recorders(stub_bin: Path, record: Path) -> dict[str, str]:
    """The developer's own environment, with the recorders shadowing the real tools."""
    env = dict(os.environ)
    env["PATH"] = f"{stub_bin}:{env.get('PATH', '/usr/bin:/bin')}"
    env["STUB_RECORD_DIR"] = str(record)
    return env


@dataclass(frozen=True)
class FakeDeploy:
    """A copy of deploy/launchd inside a fake repo root under a fake HOME, plus recorders."""

    home: Path
    root: Path
    record: Path
    stub_bin: Path
    stub_pkg: Path

    @property
    def launchd(self) -> Path:
        return self.root / "deploy" / "launchd"

    @property
    def python(self) -> Path:
        return self.root / ".venv" / "bin" / "python"

    def env(self, exit_code: int = 0, **extra: str) -> dict[str, str]:
        base = {
            "HOME": str(self.home),
            "PATH": f"{self.stub_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "PYTHONPATH": str(self.stub_pkg),
            "STUB_RECORD_DIR": str(self.record),
            "STUB_EXIT_CODE": str(exit_code),
            "LANG": "en_US.UTF-8",
        }
        base.update(extra)
        return base

    def recorded(self, tool: str) -> list[str] | None:
        path = self.record / f"{tool}.args"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else None

    def stub_call(self) -> dict[str, object]:
        with (self.record / "threaddigest.json").open(encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, dict)
        return data

    def log(self, job: str) -> str:
        return (self.root / "data" / "logs" / f"launchd-{job}.log").read_text(encoding="utf-8")


def _fake_deploy(tmp_path: Path, root_rel: str, *, venv: bool = True) -> FakeDeploy:
    home = tmp_path / "home"
    root = home / root_rel
    shutil.copytree(LAUNCHD_DIR, root / "deploy" / "launchd")
    if venv:
        (root / ".venv" / "bin").mkdir(parents=True)
        # A symlink runs as the base interpreter (venv detection keys on the symlink's own
        # directory), which is exactly what lets PYTHONPATH's stub shadow the real package.
        (root / ".venv" / "bin" / "python").symlink_to(sys.executable)
    stub_bin, record = _recorders(tmp_path)
    stub_pkg = tmp_path / "stub-pkg"
    (stub_pkg / "threaddigest").mkdir(parents=True)
    (stub_pkg / "threaddigest" / "__init__.py").write_text("", encoding="utf-8")
    (stub_pkg / "threaddigest" / "__main__.py").write_text(STUB_MAIN, encoding="utf-8")
    return FakeDeploy(home=home, root=root, record=record, stub_bin=stub_bin, stub_pkg=stub_pkg)


@pytest.fixture
def deploy(tmp_path: Path) -> FakeDeploy:
    """A fake repo at <home>/repos/insightminer: outside every TCC-protected folder."""
    return _fake_deploy(tmp_path, "repos/insightminer")


# --- plists -----------------------------------------------------------------------------------


def test_both_plists_lint_after_placeholder_substitution(tmp_path: Path) -> None:
    plutil = _plutil()
    for label in LABELS:
        rendered = _render(label, REPO_ROOT, tmp_path)
        assert "__ROOT__" not in rendered.read_text(encoding="utf-8")
        result = _run([plutil, "-lint", str(rendered)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.rstrip().endswith(": OK"), result.stdout


@pytest.mark.gate
def test_plutil_lint_goes_red_on_a_broken_plist(tmp_path: Path) -> None:
    broken = tmp_path / "broken.plist"
    broken.write_text('<plist version="1.0"><dict><key>Label</key></dict></plist>\n', "utf-8")
    result = _run([_plutil(), "-lint", str(broken)])
    assert result.returncode != 0
    assert "OK" not in result.stdout


@pytest.mark.parametrize("label", LABELS)
def test_program_arguments_run_the_wrapper_with_bash_never_python3(
    tmp_path: Path, label: str
) -> None:
    raw = (LAUNCHD_DIR / f"{label}.plist").read_text(encoding="utf-8")
    assert "python3" not in raw
    data = _load(label, REPO_ROOT, tmp_path)
    assert data["Label"] == label
    args = data["ProgramArguments"]
    assert isinstance(args, list)
    assert args[0] == "/bin/bash"
    assert args[1] == str(LAUNCHD_DIR / "run.sh")
    assert Path(args[1]).is_file(), "the plist points at a run.sh that does not exist"
    assert args[2] == label.rsplit(".", 1)[1]  # "run" or "doctor"
    assert len(args) == 3
    assert "python" not in " ".join(args), (
        "the interpreter is chosen inside run.sh, by absolute path"
    )


@pytest.mark.parametrize("label", LABELS)
def test_plist_runtime_settings(tmp_path: Path, label: str) -> None:
    data = _load(label, REPO_ROOT, tmp_path)
    assert data["RunAtLoad"] is False
    assert data["ProcessType"] == "Background"
    assert data["WorkingDirectory"] == str(REPO_ROOT)
    logs = REPO_ROOT / "data" / "logs"
    for key in ("StandardOutPath", "StandardErrorPath"):
        path = data[key]
        assert isinstance(path, str)
        assert Path(path).parent == logs, f"{key} must live under data/logs: {path}"
    env = data["EnvironmentVariables"]
    assert isinstance(env, dict)
    path_entries = env["PATH"].split(":")
    venv_bin = str(REPO_ROOT / ".venv" / "bin")
    assert venv_bin in path_entries
    assert "/opt/homebrew/bin" in path_entries
    assert path_entries.index(venv_bin) < path_entries.index("/usr/bin")


def test_run_schedule_is_monday_and_thursday_at_0630(tmp_path: Path) -> None:
    """D-30 (2026-09-15): twice a week, Monday (Weekday 1) and Thursday (Weekday 4) at 06:30."""
    data = _load(RUN_LABEL, REPO_ROOT, tmp_path)
    schedule = data["StartCalendarInterval"]
    assert isinstance(schedule, list)
    assert len(schedule) == 2
    assert [(e["Weekday"], e["Hour"], e["Minute"]) for e in schedule] == [(1, 6, 30), (4, 6, 30)]
    assert data["ExitTimeOut"] == 10800


def test_doctor_schedule_is_hourly(tmp_path: Path) -> None:
    data = _load(DOCTOR_LABEL, REPO_ROOT, tmp_path)
    schedule = data["StartCalendarInterval"]
    assert isinstance(schedule, dict), "hourly is one dict with only Minute, not an array"
    assert set(schedule) == {"Minute"}
    assert schedule["Minute"] != 30, "the doctor must not start together with the run job"


# --- scripts ----------------------------------------------------------------------------------


def test_scripts_parse_under_bash_n_and_are_executable() -> None:
    for name in SCRIPTS:
        script = LAUNCHD_DIR / name
        result = _run(["/bin/bash", "-n", str(script)])
        assert result.returncode == 0, f"{name}: {result.stderr}"
    for name in EXECUTABLE_SCRIPTS:
        assert os.access(LAUNCHD_DIR / name, os.X_OK), f"{name} is not executable"
    # shellcheck is not part of the toolchain (nothing installs it); when present, it counts.
    shellcheck = shutil.which("shellcheck")
    if shellcheck is not None:
        result = _run([shellcheck, "-x", *(str(LAUNCHD_DIR / n) for n in SCRIPTS)])
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("folder", ["Desktop", "Documents", "Downloads"])
def test_run_refuses_a_repo_inside_a_tcc_protected_folder(tmp_path: Path, folder: str) -> None:
    fake = _fake_deploy(tmp_path, f"{folder}/threaddigest")
    assert f"/{folder}/" in str(fake.root)
    result = _bash(fake.launchd / "run.sh", "run", env=fake.env())
    assert result.returncode == 78, result.stderr
    assert "TCC-protected" in result.stderr
    assert str(fake.home / folder) in result.stderr
    assert "launchd" in result.stderr
    assert not (fake.root / "data").exists(), "refused before touching anything"
    assert not (fake.record / "threaddigest.json").exists()
    assert fake.recorded("osascript") is None


def test_run_refuses_without_the_venv_interpreter(tmp_path: Path) -> None:
    fake = _fake_deploy(tmp_path, "repos/insightminer", venv=False)
    result = _bash(fake.launchd / "run.sh", "run", env=fake.env())
    assert result.returncode == 78, result.stderr
    assert ".venv/bin/python" in result.stderr
    assert "make setup" in result.stderr


def test_run_rejects_an_unknown_job(deploy: FakeDeploy) -> None:
    result = _bash(deploy.launchd / "run.sh", "serve", env=deploy.env())
    assert result.returncode == 64
    assert "usage" in result.stderr
    assert not (deploy.record / "threaddigest.json").exists()


@pytest.mark.parametrize("code", sorted(NOTIFY | RETRY | QUIET))
def test_run_maps_each_exit_code_to_its_action(deploy: FakeDeploy, code: int) -> None:
    result = _bash(deploy.launchd / "run.sh", "run", env=deploy.env(code))
    assert result.returncode == code, result.stderr  # passed through unchanged

    call = deploy.stub_call()
    assert call["argv"] == ["run"]
    assert Path(str(call["cwd"])).resolve() == deploy.root.resolve()
    # caffeinate -i wraps the venv interpreter called by absolute path; never `python3`.
    assert deploy.recorded("caffeinate") == ["-i", str(deploy.python), "-m", "threaddigest", "run"]

    log = deploy.log("run")
    assert TIMESTAMPED.search(log), log
    assert f"[run] exit {code}" in log
    assert "stub threaddigest: hello from stdout" in log
    assert "stub threaddigest: hello from stderr" in log
    assert ("will retry at the next interval" in log) == (code in RETRY)

    osascript = deploy.recorded("osascript")
    if code not in NOTIFY:
        assert osascript is None, osascript
        assert "notification posted" not in log
        return
    assert osascript is not None, log
    assert osascript[:2] == ["-e", "on run argv"], "text must travel as argv, never as script"
    message, title, status = osascript[osascript.index("--") + 1 :]
    assert title == "Thread Digest"
    assert status == NOTIFY[code]
    assert str(code) in message
    assert f"{UI}/runs" in message
    assert f"notification posted: {status}" in log


def test_a_failed_notification_never_changes_the_job_status(deploy: FakeDeploy) -> None:
    result = _bash(deploy.launchd / "run.sh", "run", env=deploy.env(1, STUB_OSASCRIPT_EXIT="1"))
    assert result.returncode == 1
    assert deploy.recorded("osascript") is not None
    assert "notification failed (osascript exit 1)" in deploy.log("run")


def test_doctor_job_runs_doctor_with_the_stale_alert_flag(deploy: FakeDeploy) -> None:
    result = _bash(deploy.launchd / "run.sh", "doctor", env=deploy.env(0))
    assert result.returncode == 0, result.stderr
    assert deploy.stub_call()["argv"] == ["doctor", "--alert-if-stale", "5d"]
    assert deploy.recorded("caffeinate") is not None
    assert "[doctor] doctor ok" in deploy.log("doctor")
    assert not (deploy.root / "data" / "logs" / "launchd-run.log").exists()


def test_doctor_failure_points_at_the_system_page(deploy: FakeDeploy) -> None:
    result = _bash(deploy.launchd / "run.sh", "doctor", env=deploy.env(1))
    assert result.returncode == 1
    osascript = deploy.recorded("osascript")
    assert osascript is not None
    message = osascript[osascript.index("--") + 1]
    assert "doctor" in message
    assert f"{UI}/system" in message


def test_env_file_is_loaded_without_echoing_values(deploy: FakeDeploy) -> None:
    (deploy.root / ".env").write_text(
        "# comment\n"
        '  THREADDIGEST_REDDIT_CLIENT_SECRET="hunter2-secret"\n'
        "export THREADDIGEST_REDDIT_USERNAME='wes'\n"
        "THREADDIGEST_UI_URL=http://127.0.0.1:9999\n"
        "UNRELATED=must-not-be-exported\n"
        "THREADDIGEST_BAD-KEY=not-an-identifier\n"
        'echo sourced > "$STUB_RECORD_DIR/sourced"\n',
        encoding="utf-8",
    )
    result = _bash(deploy.launchd / "run.sh", "run", env=deploy.env(1))
    assert result.returncode == 1, result.stderr
    env = deploy.stub_call()["env"]
    assert isinstance(env, dict)
    assert env["THREADDIGEST_REDDIT_CLIENT_SECRET"] == "hunter2-secret"
    assert env["THREADDIGEST_REDDIT_USERNAME"] == "wes"
    assert "UNRELATED" not in env
    assert "THREADDIGEST_BAD-KEY" not in env
    assert not (deploy.record / "sourced").exists(), ".env was sourced, not parsed"
    log = deploy.log("run")
    assert "exported 3 THREADDIGEST_* key(s)" in log
    for surface in (log, result.stdout, result.stderr):
        assert "hunter2-secret" not in surface
        assert "wes" not in surface.replace("wesmax", "")  # the developer's login is not a leak
    osascript = deploy.recorded("osascript")
    assert osascript is not None
    assert "http://127.0.0.1:9999/runs" in osascript[osascript.index("--") + 1]


# --- install / uninstall ----------------------------------------------------------------------


def test_install_dry_run_prints_substituted_paths_and_writes_nothing(tmp_path: Path) -> None:
    stub_bin, record = _recorders(tmp_path)
    before = _listing(LAUNCH_AGENTS)
    result = _bash(
        LAUNCHD_DIR / "install.sh", "--dry-run", env=_real_env_with_recorders(stub_bin, record)
    )
    after = _listing(LAUNCH_AGENTS)
    assert result.returncode == 0, result.stdout + result.stderr
    assert after == before
    assert not (record / "launchctl.args").exists(), "a dry run called launchctl"
    out = result.stdout
    assert "__ROOT__" not in out
    assert str(LAUNCHD_DIR / "run.sh") in out
    assert str(REPO_ROOT / "data" / "logs" / "launchd-run.stdout.log") in out
    uid = os.getuid()
    for label in LABELS:
        # plutil lints the rendered copy in install.sh's scratch dir, before anything is written.
        assert f"/{label}.plist: OK" in out, "the rendered copy was not linted"
        assert f"write {LAUNCH_AGENTS / label}.plist" in out
        assert f"launchctl bootstrap gui/{uid} {LAUNCH_AGENTS / label}.plist" in out
    assert f"launchctl print gui/{uid}/{RUN_LABEL}" in out


def test_install_refuses_a_tcc_protected_root_even_in_dry_run(tmp_path: Path) -> None:
    fake = _fake_deploy(tmp_path, "Documents/threaddigest")
    result = _bash(fake.launchd / "install.sh", "--dry-run", env=fake.env())
    assert result.returncode == 78, result.stderr
    assert "TCC-protected" in result.stderr
    assert not (fake.home / "Library").exists()
    assert fake.recorded("launchctl") is None


def test_uninstall_dry_run_removes_nothing(tmp_path: Path) -> None:
    stub_bin, record = _recorders(tmp_path)
    before = _listing(LAUNCH_AGENTS)
    result = _bash(
        LAUNCHD_DIR / "uninstall.sh", "--dry-run", env=_real_env_with_recorders(stub_bin, record)
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert _listing(LAUNCH_AGENTS) == before
    assert not (record / "launchctl.args").exists(), "a dry run called launchctl"
    for label in LABELS:
        assert f"launchctl bootout gui/{os.getuid()}/{label}" in result.stdout
