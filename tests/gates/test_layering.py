"""Gate: the import-linter layering contracts hold, and the gate can go red.

The contracts in ``.importlinter`` are the module map from ``docs/PLAN.md``. The
positive control runs lint-imports against a temporary config whose contract is
violated on the current tree and asserts a non-zero exit, so a broken or silently
no-op lint-imports cannot pass as green.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# insightminer.cli imports typer by design (the CLI is typer), so forbidding that import
# must fail for as long as the project has a CLI.
MUST_FAIL_CONFIG = """\
[importlinter]
root_package = insightminer
include_external_packages = True

[importlinter:contract:positive-control]
name = Positive control: cli imports typer, so this contract must be broken
type = forbidden
source_modules =
    insightminer.cli
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
    assert "root_package = insightminer" in config


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
    assert "insightminer.cli -> typer" in output, output
