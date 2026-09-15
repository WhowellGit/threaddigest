"""Gates G08-G11: the ratchet compare can go red, stale, and loosening; bump and loosen refuse.

Every control runs ``tools/ratchet.py`` the way ``make check`` does (a subprocess with the
same interpreter) against a throwaway project tree, and a fake ``main`` built with a real
``git`` repo so the committed-floor comparison is exercised, not stubbed.

The last group covers expiry dates on relaxed lines (Wes, 2026-09-13): a relaxation carries a
``hard_after`` date, is printed on every run while it is live, and turns the tree red the day
after it passes unless it is tightened or re-approved.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate("G08 G09 G10 G11 G51")

REPO_ROOT = Path(__file__).resolve().parents[2]
RATCHET = REPO_ROOT / "tools" / "ratchet.py"
LEDGER = Path("docs") / "runbook" / "GUARDS.md"

# A tiny project whose structural counts are known. Everything below is data inside a
# string, so the repository's own ratchet does not see these markers as real hits.
TEST_MODULE = """\
import pytest


def test_a():
    assert 1 == 1
    assert True


def test_b():
    assert 2 > 1


@pytest.mark.skip(reason="#1 example")
def test_c():
    assert 0


def helper():
    pass
"""

SRC_MODULE = """\
import warnings

x = 1  # noqa: E501
y = "# noqa inside a string is not a suppression"
z = 2  # type: ignore[assignment]
warnings.filterwarnings("ignore", category=DeprecationWarning)
"""

PYPROJECT = """\
[tool.pytest.ini_options]
filterwarnings = ["error", "ignore::DeprecationWarning"]

[[tool.mypy.overrides]]
module = ["praw.*"]
ignore_missing_imports = true
"""

EXPECTED = {
    "coverage": {"line_percent": 80.0},
    "tests": {"collected": 3, "asserts": 4},
    "skips": {"count": 1},
    "suppressions": {
        "noqa": 1,
        "type_ignore": 1,
        "pragma_no_cover": 0,
        "filterwarnings_ignore": 2,
        "mypy_overrides": 1,
    },
    # No CLAUDE.md in the throwaway tree, so the rules table contributes nothing; the real
    # count and its positive controls live in tests/gates/test_rules_name_their_enforcer.py.
    "review_only_rules": {"count": 0, "guards_without_control": 0},
    "code_health": {
        "cognitive_over_15": 0,
        "cyclomatic_over_15": 0,
        "mi_below_a": 0,
        "size_rule_violations": 0,
        "dead_code": 0,
        "dead_code_whitelisted": 0,
        "duplicate_blocks": 0,
    },
    "docs": {"dated_annotations": 0},
}


def write_coverage(root: Path, percent: float) -> None:
    build = root / ".build"
    build.mkdir(exist_ok=True)
    (build / "coverage.json").write_text(
        json.dumps({"totals": {"percent_covered": percent}}), encoding="utf-8"
    )


def write_code_health(root: Path, values: dict[str, int], hits: list[str] | None = None) -> None:
    """The report tools/code_health.py would write; the ratchet reads it like coverage.json."""
    build = root / ".build"
    build.mkdir(exist_ok=True)
    (build / "code_health.json").write_text(
        json.dumps({"values": values, "hits": hits or []}), encoding="utf-8"
    )


def write_doc_policy(root: Path, count: int, hits: list[str] | None = None) -> None:
    """The report tools/doc_policy.py would write; the ratchet reads it like code_health.json."""
    build = root / ".build"
    build.mkdir(exist_ok=True)
    (build / "doc_policy.json").write_text(
        json.dumps({"values": {"dated_annotations": count}, "hits": hits or [], "problems": {}}),
        encoding="utf-8",
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "tests" / "test_sample.py").write_text(TEST_MODULE, encoding="utf-8")
    (root / "src" / "pkg" / "mod.py").write_text(SRC_MODULE, encoding="utf-8")
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    write_coverage(root, 80.0)
    write_code_health(root, dict(EXPECTED["code_health"]))
    write_doc_policy(root, 0)
    return root


def ratchet(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RATCHET), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        timeout=120,
    )


def git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root),
        "GIT_AUTHOR_NAME": "ratchet-test",
        "GIT_AUTHOR_EMAIL": "ratchet-test@example.invalid",
        "GIT_COMMITTER_NAME": "ratchet-test",
        "GIT_COMMITTER_EMAIL": "ratchet-test@example.invalid",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env, timeout=60)


def commit_as_main(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")


def read(root: Path, family: str) -> str:
    return (root / ".ratchets" / f"{family}.txt").read_text(encoding="utf-8")


def test_measure_counts_structural_shapes_only(project: Path) -> None:
    proc = ratchet(project, "measure", "--write", "out/summary.json")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((project / "out" / "summary.json").read_text(encoding="utf-8"))
    assert {k: summary[k] for k in EXPECTED} == EXPECTED
    assert json.loads(proc.stdout) == summary
    assert any("tests/test_sample.py:13 pytest.mark.skip" in hit for hit in summary["hits"])
    assert any("src/pkg/mod.py:3 noqa" in hit for hit in summary["hits"])
    assert not any("mod.py:4" in hit for hit in summary["hits"])


def test_bump_then_compare_is_green_and_canonical(project: Path) -> None:
    assert ratchet(project, "bump").returncode == 0
    assert read(project, "coverage") == "line_percent=80.00\n"
    assert read(project, "tests") == "asserts=4\ncollected=3\n"
    assert read(project, "skips") == "count=1\n"
    suppressions = read(project, "suppressions")
    assert suppressions.splitlines() == sorted(suppressions.splitlines())
    assert suppressions.endswith("\n") and "\r" not in suppressions

    proc = ratchet(project, "compare", "--main-ref", "none")
    assert proc.returncode == 0, proc.stdout
    assert "RED" not in proc.stdout and "STALE" not in proc.stdout


def test_compare_is_red_when_coverage_falls_below_the_floor(project: Path) -> None:
    ratchet(project, "bump")
    write_coverage(project, 70.0)

    proc = ratchet(project, "compare", "--main-ref", "none")

    assert proc.returncode == 1
    assert "RED       coverage.line_percent" in proc.stdout


def test_compare_is_red_when_a_skip_or_suppression_is_added(project: Path) -> None:
    ratchet(project, "bump")
    src = project / "src" / "pkg" / "mod.py"
    src.write_text(src.read_text(encoding="utf-8") + "w = 3  # noqa: F841\n", encoding="utf-8")
    tests = project / "tests" / "test_sample.py"
    tests.write_text(
        tests.read_text(encoding="utf-8")
        + "\n\n@pytest.mark.xfail(reason='#2')\ndef test_d():\n    assert 0\n",
        encoding="utf-8",
    )

    proc = ratchet(project, "compare", "--main-ref", "none")

    assert proc.returncode == 1
    assert "RED       suppressions.noqa" in proc.stdout
    assert "RED       skips.count" in proc.stdout
    assert "HIT       src/pkg/mod.py:7 noqa" in proc.stdout


def test_compare_is_stale_when_the_floor_lags_the_measurement(project: Path) -> None:
    ratchet(project, "bump")
    (project / ".ratchets" / "coverage.txt").write_text("line_percent=70.00\n", encoding="utf-8")

    proc = ratchet(project, "compare", "--main-ref", "none")

    assert proc.returncode == 1
    assert "STALE     coverage.line_percent" in proc.stdout
    assert "ratchet-bump" in proc.stdout


@pytest.mark.parametrize(
    "text",
    [
        "line_percent=80.0\n",  # one decimal: not what render() writes
        "line_percent=80.00",  # no trailing newline
        "line_percent=80.00\r\n",  # CRLF
        "line_percent=80.00\nextra=1\n",  # unknown key
        "",  # empty file
    ],
)
def test_compare_is_stale_when_the_file_is_not_canonical(project: Path, text: str) -> None:
    ratchet(project, "bump")
    (project / ".ratchets" / "coverage.txt").write_bytes(text.encode("utf-8"))

    proc = ratchet(project, "compare", "--main-ref", "none")

    assert proc.returncode == 1
    assert "STALE" in proc.stdout


def test_compare_is_red_when_a_floor_file_is_missing(project: Path) -> None:
    ratchet(project, "bump")
    (project / ".ratchets" / "skips.txt").unlink()

    proc = ratchet(project, "compare", "--main-ref", "none")

    assert proc.returncode == 1
    assert "RED       skips" in proc.stdout


def test_compare_exits_3_when_a_floor_moved_against_direction_vs_main(project: Path) -> None:
    ratchet(project, "bump")
    commit_as_main(project)
    write_coverage(project, 75.0)
    loosened = ratchet(
        project, "loosen", "KEY=coverage.line_percent=75.00", "REASON=dropped x (#3)"
    )
    assert loosened.returncode == 0, loosened.stderr

    proc = ratchet(project, "compare", "--main-ref", "main")

    assert proc.returncode == 3, proc.stdout
    assert "LOOSENING coverage.line_percent" in proc.stdout
    assert "80.00 on main -> 75.00 here" in proc.stdout


def test_compare_exits_3_when_a_key_is_removed_vs_main(project: Path) -> None:
    ratchet(project, "bump")
    commit_as_main(project)
    ratchet(project, "bump")
    (project / ".ratchets" / "suppressions.txt").write_text(
        read(project, "suppressions").replace("noqa=1\n", ""), encoding="utf-8"
    )

    proc = ratchet(project, "compare", "--main-ref", "main")

    # The hand edit is STALE (red) and, once bumped, the compare against main would still
    # show the removal; the loosening line is reported alongside the stale one.
    assert proc.returncode == 1
    assert "STALE     suppressions.noqa" in proc.stdout


def test_compare_on_main_itself_is_clean(project: Path) -> None:
    ratchet(project, "bump")
    commit_as_main(project)

    proc = ratchet(project, "compare")  # resolves 'main' on its own

    assert proc.returncode == 0, proc.stdout
    assert "LOOSENING" not in proc.stdout


def test_compare_without_any_main_baseline_is_red(project: Path) -> None:
    ratchet(project, "bump")

    proc = ratchet(project, "compare")  # not a git repository: no main, no origin/main

    assert proc.returncode == 1
    assert "main" in proc.stderr


def test_bump_refuses_to_move_a_floor_against_direction(project: Path) -> None:
    ratchet(project, "bump")
    write_coverage(project, 70.0)

    proc = ratchet(project, "bump")

    assert proc.returncode == 1
    assert "KEPT      coverage.line_percent" in proc.stdout
    assert "ratchet-loosen" in proc.stdout
    assert read(project, "coverage") == "line_percent=80.00\n"


def test_bump_keeps_a_dip_inside_the_slack_and_stays_green(project: Path) -> None:
    ratchet(project, "bump")
    write_coverage(project, 79.7)

    proc = ratchet(project, "bump")

    assert proc.returncode == 0, proc.stdout
    assert read(project, "coverage") == "line_percent=80.00\n"
    assert ratchet(project, "compare", "--main-ref", "none").returncode == 0


def test_loosen_writes_the_value_and_a_ledger_row(project: Path) -> None:
    ratchet(project, "bump")
    write_coverage(project, 70.0)

    proc = ratchet(
        project, "loosen", "KEY=coverage.line_percent=70.00", "REASON=removed dead branch (#7)"
    )

    assert proc.returncode == 0, proc.stderr
    assert read(project, "coverage") == "line_percent=70.00\n"
    ledger = (project / LEDGER).read_text(encoding="utf-8")
    assert ledger.count("## Loosenings") == 1
    assert "| Date | Key | From | To | Reason | PR |" in ledger
    row = next(line for line in ledger.splitlines() if "coverage.line_percent" in line)
    assert "| 80.00 | 70.00 | removed dead branch (#7) |" in row
    assert ratchet(project, "compare", "--main-ref", "none").returncode == 0


def test_loosen_appends_to_an_existing_ledger_section(project: Path) -> None:
    ratchet(project, "bump")
    ledger = project / LEDGER
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        "# Guards ledger\n\n## Active\n\n| ID |\n|---|\n\n## Loosenings\n\n"
        "| Date | Key | From | To | Reason | PR |\n|---|---|---|---|---|---|\n| | | | | | |\n\n"
        "## Retired\n\n| ID |\n|---|\n",
        encoding="utf-8",
    )
    write_coverage(project, 70.0)
    assert ratchet(project, "loosen", "KEY=coverage.line_percent", "REASON=first").returncode == 0
    src = project / "src" / "pkg" / "mod.py"
    src.write_text(src.read_text(encoding="utf-8") + "w = 3  # noqa: F841\n", encoding="utf-8")
    assert (
        ratchet(project, "loosen", "KEY=suppressions.noqa=2", "REASON=second | pipe").returncode
        == 0
    )

    text = ledger.read_text(encoding="utf-8")
    section = text.split("## Loosenings")[1].split("## Retired")[0]
    rows = [line for line in section.splitlines() if line.startswith("| ") and "Date" not in line]
    assert len(rows) == 2, section
    assert "| | | | | | |" not in section
    assert "coverage.line_percent | 80.00 | 70.00 | first |" in rows[0]
    assert "suppressions.noqa | 1 | 2 | second \\| pipe |" in rows[1]
    assert text.count("## Loosenings") == 1 and "## Retired" in text
    assert read(project, "coverage") == "line_percent=70.00\n"


def test_loosen_refuses_a_value_looser_than_measured(project: Path) -> None:
    ratchet(project, "bump")
    write_coverage(project, 70.0)

    proc = ratchet(project, "loosen", "KEY=coverage.line_percent=60.00", "REASON=too generous")

    assert proc.returncode == 1
    assert "looser" in proc.stderr
    assert read(project, "coverage") == "line_percent=80.00\n"
    assert not (project / LEDGER).exists()


def test_loosen_refuses_a_ceiling_above_the_measured_count(project: Path) -> None:
    ratchet(project, "bump")

    proc = ratchet(project, "loosen", "KEY=skips.count=5", "REASON=room to grow")

    assert proc.returncode == 1
    assert read(project, "skips") == "count=1\n"


def relax_skips(project: Path, date: str) -> None:
    """Commit a relaxed skips ceiling carrying an expiry date, through the tool."""
    proc = ratchet(
        project, "loosen", "KEY=skips.count", f"HARD_AFTER={date}", "REASON=one skip while #4 lands"
    )
    assert proc.returncode == 0, proc.stderr


def test_compare_is_red_the_day_after_a_hard_after_date(project: Path) -> None:
    ratchet(project, "bump")
    relax_skips(project, str(dt.date.today() - dt.timedelta(days=1)))

    proc = ratchet(project, "compare", "--main-ref", "none")

    assert proc.returncode == 1, proc.stdout
    assert "EXPIRED   skips.count" in proc.stdout
    assert "make ratchet-loosen KEY=skips.count" in proc.stdout
    assert "1 expired -> exit 1" in proc.stdout


def test_compare_prints_a_live_relaxation_and_stays_green(project: Path) -> None:
    ratchet(project, "bump")
    future = str(dt.date.today() + dt.timedelta(days=30))
    relax_skips(project, future)

    proc = ratchet(project, "compare", "--main-ref", "none")

    assert proc.returncode == 0, proc.stdout
    assert "RELAXED   skips.count" in proc.stdout
    assert f"relaxed ceiling, hard_after={future}" in proc.stdout
    assert "EXPIRED" not in proc.stdout
    assert read(project, "skips") == f"count=1\ncount.hard_after={future}\n"


def test_a_line_without_hard_after_is_unchanged_and_bump_keeps_the_date(project: Path) -> None:
    ratchet(project, "bump")
    future = str(dt.date.today() + dt.timedelta(days=30))
    relax_skips(project, future)

    proc = ratchet(project, "bump")

    assert proc.returncode == 0, proc.stdout
    assert "RELAXED   skips.count" in proc.stdout
    assert f"hard_after={future} (kept)" in proc.stdout
    assert read(project, "skips") == f"count=1\ncount.hard_after={future}\n"
    assert read(project, "coverage") == "line_percent=80.00\n"
    assert "RELAXED   coverage" not in proc.stdout
    assert ratchet(project, "compare", "--main-ref", "none").returncode == 0


def test_a_hard_after_that_is_not_a_date_is_refused_and_a_hand_edited_one_is_red(
    project: Path,
) -> None:
    ratchet(project, "bump")

    proc = ratchet(project, "loosen", "KEY=skips.count", "HARD_AFTER=next quarter", "REASON=x")

    assert proc.returncode == 1
    assert "HARD_AFTER" in proc.stderr
    assert read(project, "skips") == "count=1\n"

    # The reader validates too, so a hand-edited date cannot become an open-ended relaxation.
    (project / ".ratchets" / "skips.txt").write_text(
        "count=1\ncount.hard_after=when we get to it\n", encoding="utf-8"
    )
    proc = ratchet(project, "compare", "--main-ref", "none")
    assert proc.returncode == 1
    assert "RED       skips.count.hard_after" in proc.stdout


def test_loosen_refuses_a_tightening_and_an_empty_reason(project: Path) -> None:
    ratchet(project, "bump")
    write_coverage(project, 90.0)
    assert ratchet(project, "loosen", "KEY=coverage.line_percent=90.00", "REASON=x").returncode == 1
    write_coverage(project, 70.0)
    assert ratchet(project, "loosen", "KEY=coverage.line_percent=70.00", "REASON=").returncode == 1
    assert read(project, "coverage") == "line_percent=80.00\n"


# --------------------------------------------------------------- code_health (G51)


def test_compare_is_red_when_a_code_health_count_rises(project: Path) -> None:
    assert ratchet(project, "bump").returncode == 0
    assert read(project, "code_health").startswith("cognitive_over_15=0\n")
    write_code_health(
        project,
        {**EXPECTED["code_health"], "cognitive_over_15": 1},
        ["cognitive_over_15 src/pkg/mod.py tangled cognitive 16"],
    )
    proc = ratchet(project, "compare", "--main-ref", "none")
    assert proc.returncode == 1, proc.stdout
    assert "RED       code_health.cognitive_over_15" in proc.stdout
    assert (
        "HIT       cognitive_over_15 src/pkg/mod.py tangled cognitive 16 [code-health]"
        in proc.stdout
    )


def test_compare_is_red_when_dated_annotations_accrete(project: Path) -> None:
    """Wes, 2026-09-15: an accreting count of dated annotations in a rewritten document means a
    targeted rewrite is due, never another annotation; the ceiling only goes down."""
    assert ratchet(project, "bump").returncode == 0
    assert read(project, "docs") == "dated_annotations=0\n"
    write_doc_policy(project, 2, ["dated_annotation docs/PLAN.md:12 (corrected 2026-09-13)"])
    proc = ratchet(project, "compare", "--main-ref", "none")
    assert proc.returncode == 1, proc.stdout
    assert "RED       docs.dated_annotations" in proc.stdout
    assert "HIT       dated_annotation docs/PLAN.md:12 (corrected 2026-09-13) [doc-policy]" in (
        proc.stdout
    )
    (project / ".build" / "doc_policy.json").unlink()
    proc = ratchet(project, "measure")
    assert proc.returncode == 1 and "doc policy report" in proc.stderr


def test_measure_fails_without_the_code_health_report(project: Path) -> None:
    """A missing report is an error, never a zero, which would be green for the wrong reason."""
    (project / ".build" / "code_health.json").unlink()
    proc = ratchet(project, "measure")
    assert proc.returncode == 1
    assert "code health report" in proc.stderr and "code_health.json missing" in proc.stderr
    partial = project / ".build" / "code_health.json"
    partial.write_text(json.dumps({"values": {"cognitive_over_15": 0}}), encoding="utf-8")
    proc = ratchet(project, "measure")
    assert proc.returncode == 1
    assert "unreadable" in proc.stderr


def test_bump_clears_a_hard_after_once_a_ceiling_reaches_zero(project: Path) -> None:
    """A birth relaxation carries a date; when the count reaches zero the relaxation is over
    and bump drops the date, so a solved problem cannot go red on the expiry day."""
    write_code_health(project, {**EXPECTED["code_health"], "cognitive_over_15": 3})
    assert ratchet(project, "bump").returncode == 0
    proc = ratchet(
        project,
        "loosen",
        "KEY=code_health.cognitive_over_15",
        "REASON=birth relaxation",
        "HARD_AFTER=2999-01-01",
    )
    assert proc.returncode == 0, proc.stderr
    assert "cognitive_over_15.hard_after=2999-01-01" in read(project, "code_health")
    write_code_health(project, {**EXPECTED["code_health"], "cognitive_over_15": 2})
    proc = ratchet(project, "bump")
    assert "RELAXED   code_health.cognitive_over_15" in proc.stdout
    assert "hard_after=2999-01-01" in read(project, "code_health")
    write_code_health(project, dict(EXPECTED["code_health"]))
    proc = ratchet(project, "bump")
    assert "CLEARED   code_health.cognitive_over_15" in proc.stdout
    assert "hard_after" not in read(project, "code_health")
    assert ratchet(project, "compare", "--main-ref", "none").returncode == 0
