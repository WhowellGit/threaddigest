"""Gate: the import-linter layering contracts hold, and the gate can go red.

The contracts in ``.importlinter`` are the module map from ``docs/PLAN.md``. The
positive control runs lint-imports against a temporary config whose contract is
violated on the current tree and asserts a non-zero exit, so a broken or silently
no-op lint-imports cannot pass as green.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# threaddigest.cli imports typer by design (the CLI is typer), so forbidding that import
# must fail for as long as the project has a CLI.
MUST_FAIL_CONFIG = """\
[importlinter]
root_package = threaddigest
include_external_packages = True

[importlinter:contract:positive-control]
name = Positive control: cli imports typer, so this contract must be broken
type = forbidden
source_modules =
    threaddigest.cli
forbidden_modules =
    typer
"""


def _lint_imports_executable() -> str:
    beside_python = Path(sys.executable).with_name("lint-imports")
    if beside_python.exists():
        return str(beside_python)
    found = shutil.which("lint-imports")
    assert found is not None, "lint-imports is not installed; run `make setup`"
    return found


def _run_lint_imports(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_lint_imports_executable(), "--no-cache", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=180,
    )


def test_repo_config_exists_and_names_the_root_package() -> None:
    config = (REPO_ROOT / ".importlinter").read_text(encoding="utf-8")
    assert "root_package = threaddigest" in config


def test_layering_contracts_hold() -> None:
    result = _run_lint_imports()
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "kept" in output and "0 broken" in output, output


@pytest.mark.gate
def test_gate_goes_red_when_a_contract_is_violated(tmp_path: Path) -> None:
    config = tmp_path / "importlinter-positive-control.ini"
    config.write_text(MUST_FAIL_CONFIG, encoding="utf-8")
    result = _run_lint_imports("--config", str(config))
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "1 broken" in output, output
    assert "threaddigest.cli -> typer" in output, output


# --- services/ writes to no stdio: no `import typer` below the cli layer ----------------------

SERVICES_ROOT = REPO_ROOT / "src" / "threaddigest" / "services"

#: Third-party modules a `services/` module may not import. `typer` is the CLI's own
#: framework: a service that calls `typer.echo` has written to the CLI's stderr, which M2's
#: web UI never sees, and which makes that service undrivable headlessly (design-round5.md
#: section 1's ground-rule table, round5-findings.json panel P1). `click` is typer's engine and
#: the same leak one import away.
FORBIDDEN_IN_SERVICES = ("typer", "click")


def _imports_of(path: Path) -> set[str]:
    """Every top-level module name ``path`` imports, in either import form."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _offenders(root: Path, forbidden: tuple[str, ...], *, allow: tuple[str, ...] = ()) -> list[str]:
    """``<path> -> <module>`` for every forbidden import outside the allowed files."""
    hits: list[str] = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative in allow:
            continue
        hits.extend(f"{relative} -> {name}" for name in sorted(_imports_of(path) & set(forbidden)))
    return sorted(hits)


def _stdio_offenders(root: Path) -> list[str]:
    return _offenders(root, FORBIDDEN_IN_SERVICES)


def test_no_service_imports_the_cli_framework() -> None:
    """import-linter cannot see this: its layer contract orders ``threaddigest.*`` modules,
    and ``typer`` is third-party, so ``services/migrate.py``'s two ``typer.echo(..., err=True)``
    calls kept the layering gate green for a whole tranche."""
    assert _stdio_offenders(SERVICES_ROOT) == []


@pytest.mark.gate
def test_the_services_stdio_scanner_catches_a_planted_import(tmp_path: Path) -> None:
    """Positive control: a scanner that finds nothing is not proof of anything."""
    fake_services = tmp_path / "services"
    fake_services.mkdir()
    (fake_services / "leaky.py").write_text(
        "import typer\n\n\ndef go() -> None:\n    typer.echo('oops', err=True)\n", encoding="utf-8"
    )
    (fake_services / "from_form.py").write_text("from click import echo\n", encoding="utf-8")
    (fake_services / "clean.py").write_text("import json\n", encoding="utf-8")

    assert _stdio_offenders(fake_services) == ["from_form.py -> click", "leaky.py -> typer"]


# --- `praw` lives in one module: the chokepoint half of G05 that had no planted control ------

PACKAGE_ROOT = REPO_ROOT / "src" / "threaddigest"

#: The HTTP client and its transport. Everything above `adapters/` speaks the plain values in
#: `ports.py`, so a `praw` import anywhere else means a PRAW object (or a PRAW exception) has
#: escaped the adapter into `services/`, `core/` or the web layer.
PRAW_MODULES = ("praw", "prawcore")

#: The one file allowed to import them, relative to the package root.
PRAW_ADAPTER = "adapters/reddit_praw.py"


def test_only_the_adapter_imports_praw() -> None:
    """The scanner's own reading of the contract import-linter checks.

    It exists beside the contract rather than instead of it because the contract's allow-list
    is data in a config file: a typo in the module name there widens the exemption silently,
    while this scanner names the one path and nothing else.
    """
    assert _offenders(PACKAGE_ROOT, PRAW_MODULES, allow=(PRAW_ADAPTER,)) == []


@pytest.mark.gate
def test_the_praw_scanner_catches_a_planted_import(tmp_path: Path) -> None:
    """Positive control: a scanner that finds nothing is not proof of anything (G05)."""
    package = tmp_path / "threaddigest"
    (package / "adapters").mkdir(parents=True)
    (package / "services").mkdir()
    (package / "adapters" / "reddit_praw.py").write_text("import praw\n", encoding="utf-8")
    (package / "services" / "collect.py").write_text(
        "import praw\n\n\ndef go() -> None:\n    praw.Reddit()\n", encoding="utf-8"
    )
    (package / "services" / "sweep.py").write_text(
        "from prawcore.exceptions import NotFound\n", encoding="utf-8"
    )
    (package / "services" / "clean.py").write_text("import json\n", encoding="utf-8")

    assert _offenders(package, PRAW_MODULES, allow=(PRAW_ADAPTER,)) == [
        "services/collect.py -> praw",
        "services/sweep.py -> prawcore",
    ]


# --- no dynamic imports: the door every scanner above is blind to (C-3(b)) -------------------

#: Calls that import a module named by a string at run time. The 2026-09-17 code panel planted
#: `importlib.import_module("praw")` inside `services/collect.py`; `ruff check`, `lint-imports`,
#: `mypy` and the two scanners above were all green, because every one of them reads import
#: *statements* and a string is not one.
#:
#: `importlib.import_module` is also banned by ruff `TID251` (pyproject.toml), which reports the
#: offending line and so is the better message when it fires. This scanner is its twin for the
#: two holes TID251 has: `__import__` is a builtin call rather than an import path, so ruff's
#: banned-api rule cannot name it, and `per-file-ignores` can only lift TID251 as a whole, which
#: `src/threaddigest/db/**` needs for `create_engine` and `text` -- leaving `db/` the one place
#: in the package where ruff would not see a dynamic import at all.
DYNAMIC_IMPORT_CALLS = ("import_module", "__import__")


def _dynamic_import_offenders(root: Path) -> list[str]:
    """``<path>:<line> -> <call>`` for every dynamic-import call under ``root``."""
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in DYNAMIC_IMPORT_CALLS:
                hits.append(f"{path.relative_to(root).as_posix()}:{node.lineno} -> {name}")
    return hits


def test_no_module_in_the_package_imports_by_string() -> None:
    assert _dynamic_import_offenders(PACKAGE_ROOT) == []


@pytest.mark.gate
def test_the_dynamic_import_scanner_catches_both_spellings(tmp_path: Path) -> None:
    """Positive control, including the two spellings only this scanner sees: `__import__`, and
    an `import_module` inside `db/`, where TID251 is lifted for the engine chokepoint."""
    package = tmp_path / "threaddigest"
    (package / "services").mkdir(parents=True)
    (package / "db").mkdir()
    (package / "services" / "collect.py").write_text(
        'import importlib\n\n\ndef go() -> object:\n    return importlib.import_module("praw")\n',
        encoding="utf-8",
    )
    (package / "services" / "sweep.py").write_text(
        'def go() -> object:\n    return __import__("praw")\n', encoding="utf-8"
    )
    (package / "db" / "engine.py").write_text(
        "from importlib import import_module\n\n\ndef go() -> object:\n"
        '    return import_module("praw")\n',
        encoding="utf-8",
    )
    (package / "services" / "clean.py").write_text(
        "import json\n\n\ndef go() -> object:\n    return json.loads('{}')\n", encoding="utf-8"
    )

    assert _dynamic_import_offenders(package) == [
        "db/engine.py:5 -> import_module",
        "services/collect.py:5 -> import_module",
        "services/sweep.py:2 -> __import__",
    ]


def _ruff_executable() -> str:
    beside_python = Path(sys.executable).with_name("ruff")
    if beside_python.exists():
        return str(beside_python)
    found = shutil.which("ruff")
    assert found is not None, "ruff is not installed; run `make setup`"
    return found


def _tid251_findings(path: Path) -> list[str]:
    """``ruff check`` under the repository's own configuration, reduced to its TID251 messages.

    JSON rather than the text output, and matched on the rule *code*: the concise format prints
    the rule's name (``banned-api``) and the full format prints the code, so a format default
    that changed would otherwise quietly empty this list -- the shape of failure a positive
    control exists to make impossible.
    """
    result = subprocess.run(
        [
            _ruff_executable(),
            "check",
            "--no-cache",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            "--output-format",
            "json",
            str(path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.stdout.strip(), result.stderr
    return [str(row["message"]) for row in json.loads(result.stdout) if row.get("code") == "TID251"]


@pytest.mark.gate
def test_ruff_bans_a_dynamic_import_planted_in_a_copy_of_a_services_module(tmp_path: Path) -> None:
    """The lint half of C-3(b), proven the way G05's error contract is: against the real
    configuration, on a copy of the module the panel actually planted the import in.

    Red and green on the same file, so the finding is the planted line and not the module."""
    original = (PACKAGE_ROOT / "services" / "collect.py").read_text(encoding="utf-8")
    clean = tmp_path / "collect.py"
    clean.write_text(original, encoding="utf-8")
    assert _tid251_findings(clean) == []

    planted = tmp_path / "collect_planted.py"
    planted.write_text(
        # Appended, not prepended: `from __future__ import annotations` has to stay the first
        # statement. E402 fires on the trailing import and is filtered out with everything that
        # is not TID251, so the assertion below is about the ban and nothing else.
        original + "\n\nimport importlib\n\n\ndef _planted() -> object:\n"
        '    return importlib.import_module("praw")\n',
        encoding="utf-8",
    )
    findings = _tid251_findings(planted)
    assert len(findings) == 1, findings
    assert "importlib.import_module" in findings[0], findings
