"""G34: a retired mechanism must not be stated as live anywhere in the curated documents.

Birth incident (2026-09-13): the plan's gates table listed eight gates as live, each with fail
behaviour, sixty lines above the prose that retired them, and ``DECISIONS.md`` disagreed with the
plan on every one. The earlier project named this its number-one drift bug: a fact changed in one
place must propagate to every mirror in the same pass.

The check is deliberately small. The retired phrases live in one home, the "Retired claims" table
in ``docs/decisions/DECISIONS.md``, each row citing the decision that retired it. Any line of a
live document that mentions a retired phrase must carry a retirement marker on the same line (a
``D-NN``/``N-NN`` id or a word such as cut, retired, superseded, downgraded, dropped, deferred,
declined). Historical material (``reference/``, ``insights/``) and the decisions log itself are
outside the scan: they are allowed to describe the past. Backticks are stripped before a phrase
is matched (widened 2026-09-16, drift finding 24: the retired backup statement was written with
backticks around it, which a literal match would have read as a different claim).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DECISIONS_REL = "decisions/DECISIONS.md"
SECTION = "## Retired claims"
ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$")
DECISION_ID = re.compile(r"\b[DN]-\d{2}\b")
MARKER = re.compile(
    r"\b[DN]-\d{2}\b|\bcut\b|retired|superseded|downgraded|dropped|deferred|declined"
    r"|no longer|replac",
    re.IGNORECASE,
)
EXCLUDED_PREFIXES = ("reference/", "insights/", DECISIONS_REL)


def retired_claims(decisions_text: str) -> list[tuple[str, str]]:
    """Return ``(phrase, retired_by)`` rows from the Retired claims table."""
    if SECTION not in decisions_text:
        return []
    section = decisions_text.split(SECTION, 1)[1].split("\n## ", 1)[0]
    rows = [m for line in section.splitlines() if (m := ROW.match(line))]
    return [(m.group(1), m.group(2)) for m in rows if m.group(1).lower() != "phrase"]


def live_documents(docs: Path) -> list[Path]:
    return sorted(
        p
        for p in docs.rglob("*.md")
        if not p.relative_to(docs).as_posix().startswith(EXCLUDED_PREFIXES)
    )


def violations(docs: Path) -> list[str]:
    """Every live-document line that states a retired phrase without a retirement marker."""
    claims = retired_claims((docs / DECISIONS_REL).read_text(encoding="utf-8"))
    found: list[str] = []
    for path in live_documents(docs):
        rel = path.relative_to(docs).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lowered = line.replace("`", "").lower()
            for phrase, _ in claims:
                if phrase.lower() in lowered and not MARKER.search(line):
                    found.append(f"{rel}:{number}: states retired claim `{phrase}`")
    return found


#: Source and deploy files scanned the same way (widened 2026-09-15: the plan-version-two review
#: found the retired daily schedule alive in a code comment, a constant, and a wrapper header).
SOURCE_GLOBS = ("src/**/*.py", "deploy/**/*.sh", "deploy/**/*.plist", "deploy/**/*.md")


def source_violations(root: Path) -> list[str]:
    """Every source or deploy line that states a retired phrase without a retirement marker."""
    claims = retired_claims((root / "docs" / DECISIONS_REL).read_text(encoding="utf-8"))
    found: list[str] = []
    for pattern in SOURCE_GLOBS:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                lowered = line.replace("`", "").lower()
                for phrase, _ in claims:
                    if phrase.lower() in lowered and not MARKER.search(line):
                        found.append(f"{rel}:{number}: states retired claim `{phrase}`")
    return found


def unresolved_decision_ids(decisions_text: str) -> list[str]:
    """Ids cited in the Retired claims table that appear nowhere else in the decisions log."""
    claims = retired_claims(decisions_text)
    table_start = decisions_text.find(SECTION)
    outside = decisions_text[:table_start]
    cited = {cid for _, by in claims for cid in DECISION_ID.findall(by)}
    return sorted(cid for cid in cited if cid not in outside)


def test_retired_claims_table_exists_and_cites_real_decisions() -> None:
    text = (DOCS / DECISIONS_REL).read_text(encoding="utf-8")
    assert retired_claims(text), "DECISIONS.md has no Retired claims table"
    assert not unresolved_decision_ids(text), (
        f"cited ids not in the log: {unresolved_decision_ids(text)}"
    )


def test_no_live_document_states_a_retired_claim() -> None:
    found = violations(DOCS)
    assert not found, "retired claims stated as live:\n" + "\n".join(found)


def test_no_source_or_deploy_file_states_a_retired_claim() -> None:
    """KI-025: `core/retry.py` kept the daily three-slot schedule (a constant, a comment citing
    the plan for the three times, a deferral rule) after D-30 retired it, because the scan
    covered documents only. Code comments and constants are mirrors too."""
    found = source_violations(ROOT)
    assert not found, "retired claims stated in source or deploy files:\n" + "\n".join(found)


def _docs_tree(tmp_path: Path, live_line: str) -> Path:
    docs = tmp_path / "docs"
    (docs / "decisions").mkdir(parents=True)
    (docs / "decisions" / "DECISIONS.md").write_text(
        "# d\n\n| N-99 | 2026-01-01 | No widget | reason | never |\n\n"
        f"{SECTION}\n\n| Phrase | Retired by | Since |\n|---|---|---|\n"
        "| `widget` | N-99 | 2026-01-01 |\n",
        encoding="utf-8",
    )
    (docs / "PLAN.md").write_text(f"# p\n\n{live_line}\n", encoding="utf-8")
    return docs


@pytest.mark.gate
def test_positive_control_stale_claim_is_red_and_annotated_claim_is_green(tmp_path: Path) -> None:
    stale = _docs_tree(tmp_path / "a", "The widget runs nightly.")
    assert violations(stale) == ["PLAN.md:3: states retired claim `widget`"]
    annotated = _docs_tree(tmp_path / "b", "The widget runs nightly (cut 2026-01-01, N-99).")
    assert violations(annotated) == []
    # Backticks around the phrase, or inside it, are not a different claim (2026-09-16).
    ticked = _docs_tree(tmp_path / "c", "One `widget` per run.")
    assert violations(ticked) == ["PLAN.md:3: states retired claim `widget`"]


@pytest.mark.gate
def test_positive_control_a_retired_phrase_in_source_is_red(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _docs_tree(root, "clean")
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "mod.py").write_text(
        "#: the widget fires at dawn\nSLOTS = 3\n", encoding="utf-8"
    )
    (root / "deploy").mkdir()
    (root / "deploy" / "run.sh").write_text("# widget (retired, N-99)\n", encoding="utf-8")
    assert source_violations(root) == ["src/pkg/mod.py:1: states retired claim `widget`"]


@pytest.mark.gate
def test_positive_control_unknown_decision_id_is_red() -> None:
    text = (
        f"# d\n\n{SECTION}\n\n| Phrase | Retired by | Since |\n|---|---|---|\n"
        "| `x` | N-42 | 2026-01-01 |\n"
    )
    assert unresolved_decision_ids(text) == ["N-42"]
