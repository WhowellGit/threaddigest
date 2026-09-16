"""Gate: the import-linter layering contracts hold, and the gate can go red.

The contracts in ``.importlinter`` are the module map from ``docs/PLAN.md``. The
positive control runs lint-imports against a temporary config whose contract is
violated on the current tree and asserts a non-zero exit, so a broken or silently
no-op lint-imports cannot pass as green.
"""

from __future__ import annotations

import ast
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


def _stdio_offenders(root: Path) -> list[str]:
    return sorted(
        f"{path.relative_to(root).as_posix()} -> {name}"
        for path in root.rglob("*.py")
        for name in sorted(_imports_of(path) & set(FORBIDDEN_IN_SERVICES))
    )


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
