"""G55: the document contract, checked against the tree.

Birth incident (Wes, 2026-09-15): the earlier project's reference corpus grew by ad-hoc requests,
agents appended where a rewrite was due, dated annotations piled up, and nothing tied a changed
fact to the documents that repeated it; here the cadence sweep of the day before missed four
mirrors and two code defaults (KI-024 to KI-026). ``tools/doc_policy.py`` makes the writing side
mechanical. The refute pass on its first build (2026-09-15, record in ``docs/reference/reviews``)
found the append-only rule laundered by a commit, a policy that exempted itself, an empty facts
table passing, a future milestone passing, and controls that called pure functions rather than
the report the gate runs; every control below plants its bad state and reads it through
``report()`` on a real git tree.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tools import doc_policy as dp

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.gate("G55")

FRONT = (
    "---\npurpose: {purpose}\nupdate-policy: {policy}\nmirrors: [{mirrors}]\n"
    "verified-at: {at}\n---\n"
)
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "doc-policy-test",
    "GIT_AUTHOR_EMAIL": "doc-policy-test@example.invalid",
    "GIT_COMMITTER_NAME": "doc-policy-test",
    "GIT_COMMITTER_EMAIL": "doc-policy-test@example.invalid",
}


def _doc(purpose: str, policy: str, at: str = "M1a-A", mirrors: str = "") -> str:
    return FRONT.format(purpose=purpose, policy=policy, mirrors=mirrors, at=at)


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env=GIT_ENV, timeout=60
    )


def _tree(tmp_path: Path, *, status_milestone: str = "M1a-A") -> Path:
    """A small corpus on a git repository: ``main`` holds the baseline, work is on a branch."""
    root = tmp_path / "repo"
    (root / "docs" / "decisions").mkdir(parents=True)
    (root / "docs" / "recent").mkdir()
    (root / "docs" / "reference" / "reviews").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "CLAUDE.md").write_text("# agreement\n\nSee `docs/PLAN.md`.\n", encoding="utf-8")
    (root / "config" / "settings.yaml").write_text("display_timezone: UTC\n", encoding="utf-8")
    (root / "docs" / "INDEX.md").write_text(
        _doc("the router", "prune-stale", mirrors="docs/PLAN.md")
        + "# index\n\n- `PLAN.md` — the plan\n",
        encoding="utf-8",
    )
    (root / "docs" / "PLAN.md").write_text(
        _doc("the plan", "versioned", mirrors="docs/INDEX.md")
        + "# plan\n\nThe zone is UTC. The question is what people say.\n",
        encoding="utf-8",
    )
    (root / "docs" / "recent" / "STATUS.md").write_text(
        "---\npurpose: status\nupdate-policy: rewritten\nmirrors: []\n"
        f"milestone: {status_milestone}\n---\n# status\n\n**As of 2026-09-15.**\n",
        encoding="utf-8",
    )
    (root / "docs" / "decisions" / "DECISIONS.md").write_text(
        "---\npurpose: the log\nupdate-policy: append-only\nmirrors: []\n"
        "exempt-sections: ['## Outcomes']\n---\n"
        "# decisions\n\n- D-01 first\n- D-02 second\n\n## Outcomes\n\n| P-01 | pending |\n\n"
        f"{dp.FACTS_SECTION}\n\n| id | fact | home | literal | mirrors |\n|---|---|---|---|---|\n"
        "| F-01 | the zone | yaml:config/settings.yaml:display_timezone | `UTC` "
        "| `docs/PLAN.md` |\n"
        "| F-02 | the question | text | `what people say` | `docs/PLAN.md` |\n",
        encoding="utf-8",
    )
    (root / "docs" / "reference" / "reviews" / "2026-01-01-record.md").write_text(
        "# a record\n\nwhat the reviewer said\n", encoding="utf-8"
    )
    (root / "docs" / "reference" / "reviews" / "REGISTER.md").write_text(
        "# register\n\n| 2026-01-01 | row one |\n", encoding="utf-8"
    )
    git(root, "init", "-q")
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    git(root, "switch", "-q", "-c", "work")
    return root


def _problems(root: Path) -> list[str]:
    return dp.flat_problems(dp.report(root))


def test_the_real_tree_holds_the_contract() -> None:
    found = _problems(ROOT)
    assert found == [], "\n".join(found)


def test_a_clean_tree_reports_nothing(tmp_path: Path) -> None:
    assert _problems(_tree(tmp_path)) == []


def test_positive_control_a_missing_contract_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "docs" / "PLAN.md").write_text("# plan\n\nno front matter\n", encoding="utf-8")
    assert "docs/PLAN.md: no front matter (purpose, update-policy, mirrors, verified-at)" in (
        _problems(root)
    )
    (root / "docs" / "PLAN.md").write_text(
        _doc("the plan", "generated", at="never", mirrors="docs/GHOST.md") + "# plan\n",
        encoding="utf-8",
    )
    found = _problems(root)
    assert any("update-policy 'generated'" in f for f in found)  # no policy exempts a document
    assert any("mirror 'docs/GHOST.md' does not exist" in f for f in found)
    assert any("verified-at 'never'" in f for f in found)


def test_positive_control_a_one_sided_mirror_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "docs" / "INDEX.md").write_text(
        _doc("the router", "prune-stale") + "# index\n\n- `PLAN.md` — the plan\n",
        encoding="utf-8",
    )
    assert "docs/PLAN.md: declares docs/INDEX.md as a mirror, which does not declare it back" in (
        _problems(root)
    )


def test_positive_control_a_deleted_line_in_an_append_only_document_is_red_even_when_committed(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    log = root / "docs" / "decisions" / "DECISIONS.md"
    text = log.read_text(encoding="utf-8")
    # An appended entry and a dated parenthetical inserted into an existing line are fine.
    log.write_text(
        text.replace("- D-02 second", "- D-02 (superseded 2026-09-15 by D-03) second")
        + "\n- D-03 third\n",
        encoding="utf-8",
    )
    assert _problems(root) == []
    # A deleted line is red uncommitted, and still red after it is committed on the branch.
    log.write_text(text.replace("- D-01 first\n", ""), encoding="utf-8")
    expected = "docs/decisions/DECISIONS.md:9: append-only document lost a line: '- D-01 first'"
    assert expected in _problems(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "launder the deletion")
    assert expected in _problems(root)


def test_positive_control_a_policy_change_cannot_exempt_an_append_only_document(
    tmp_path: Path,
) -> None:
    root = _tree(tmp_path)
    log = root / "docs" / "decisions" / "DECISIONS.md"
    text = log.read_text(encoding="utf-8")
    log.write_text(
        text.replace("update-policy: append-only", "update-policy: prune-stale").replace(
            "- D-01 first\n", ""
        ),
        encoding="utf-8",
    )
    found = _problems(root)
    assert (
        "docs/decisions/DECISIONS.md: append-only at the base; the policy may not be changed "
        "in place"
    ) in found
    assert any("lost a line: '- D-01 first'" in f for f in found)


def test_positive_control_a_moved_hidden_or_rewritten_line_is_a_loss() -> None:
    old = "# log\n\n- D-01 first\n- D-02 second\n"
    # Reordered: the first line is found late, so the second is the one reported missing.
    assert dp.append_only_violations(old, "# log\n\n- D-02 second\n- D-01 first\n", "d") == [
        "d:4: append-only document lost a line: '- D-02 second'"
    ]
    hidden = "# log\n\n<!-- - D-01 first -->\n- D-02 second\n"
    assert dp.append_only_violations(old, hidden, "d") == [
        "d:3: append-only document lost a line: '- D-01 first'"
    ]
    rewritten = "# log\n\n- D-01 first, now wrong\n- D-02 second\n"
    assert dp.append_only_violations(old, rewritten, "d") == []  # a suffix is an extension
    changed = "# log\n\n- D-01 changed\n- D-02 second\n"
    assert dp.append_only_violations(old, changed, "d") == [
        "d:3: append-only document lost a line: '- D-01 first'"
    ]


def test_an_exempt_section_may_be_filled_in(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    log = root / "docs" / "decisions" / "DECISIONS.md"
    log.write_text(
        log.read_text(encoding="utf-8").replace("| P-01 | pending |", "| P-01 | held |"),
        encoding="utf-8",
    )
    assert _problems(root) == []


def test_positive_control_an_edited_reference_record_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    record = root / "docs" / "reference" / "reviews" / "2026-01-01-record.md"
    record.write_text("# a record\n\nwhat the reviewer should have said\n", encoding="utf-8")
    assert (
        "docs/reference/reviews/2026-01-01-record.md: a reference record was edited; records "
        "are added, never edited"
    ) in _problems(root)
    register = root / "docs" / "reference" / "reviews" / "REGISTER.md"
    register.write_text("# register\n\n| 2026-01-02 | row two |\n", encoding="utf-8")
    assert any("REGISTER.md:3: append-only document lost a line" in f for f in _problems(root))


def test_positive_control_a_lagging_or_future_stamped_document_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, status_milestone="M1b")
    found = _problems(root)
    assert (
        "docs/PLAN.md: verified at M1a-A, the status page is at M1b: re-read and rewrite or "
        "re-verify it (lag 2, allowed 1)"
    ) in found
    root2 = _tree(tmp_path / "b", status_milestone="M1a-B")
    assert _problems(root2) == []  # one milestone of lag is allowed
    (root2 / "docs" / "PLAN.md").write_text(
        _doc("the plan", "versioned", at="M5", mirrors="docs/INDEX.md")
        + "# plan\n\nThe zone is UTC. The question is what people say.\n",
        encoding="utf-8",
    )
    assert "docs/PLAN.md: verified at M5, ahead of the status page (M1a-B)" in _problems(root2)


def test_positive_control_a_dangling_reference_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "CLAUDE.md").write_text("See `docs/GONE.md` and `docs/PLAN.md`.\n", encoding="utf-8")
    plan = root / "docs" / "PLAN.md"
    plan.write_text(
        plan.read_text(encoding="utf-8")
        + "Read [it](docs/ALSO_GONE.md); `BARE.md` is not judged.\n",
        encoding="utf-8",
    )
    found = _problems(root)
    assert "CLAUDE.md:1: `docs/GONE.md` does not exist" in found
    assert "docs/PLAN.md:10: `docs/ALSO_GONE.md` does not exist" in found
    assert not any("BARE.md" in f for f in found)


def test_positive_control_a_fact_missing_from_a_mirror_or_its_home_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "docs" / "PLAN.md").write_text(
        _doc("the plan", "versioned", mirrors="docs/INDEX.md")
        + "# plan\n\nThe zone is local.\n<!-- UTC, what people say: kept for the gate -->\n",
        encoding="utf-8",
    )
    found = _problems(root)
    assert "F-01: mirror docs/PLAN.md does not state `UTC`" in found
    assert "F-02: mirror docs/PLAN.md does not state `what people say`" in found
    (root / "config" / "settings.yaml").write_text("display_timezone: local\n", encoding="utf-8")
    assert (
        "F-01: home yaml:config/settings.yaml:display_timezone holds 'local', the table says `UTC`"
    ) in _problems(root)


def test_positive_control_an_absent_empty_or_unparsed_facts_table_is_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    log = root / "docs" / "decisions" / "DECISIONS.md"
    text = log.read_text(encoding="utf-8")
    log.write_text(text.split(dp.FACTS_SECTION)[0], encoding="utf-8")
    assert f"docs/decisions/DECISIONS.md: no {dp.FACTS_SECTION!r} section" in _problems(root)
    header = text.split("| F-01")[0]
    log.write_text(header + "| F-01 | the zone | text | UTC | `docs/PLAN.md` |\n", encoding="utf-8")
    found = _problems(root)
    assert any("unparsed live-facts row" in f for f in found)
    assert "docs/decisions/DECISIONS.md: the live-facts table has no rows" in found


def test_dated_annotations_are_counted_in_prose_only(tmp_path: Path) -> None:
    text = (
        _doc("x", "prune-stale")
        + "# t\n\nA fact (corrected 2026-09-13). Another (D-30 (see 2026-09-15)).\n"
        "Bracketed [as of 2026-09-14] and dashed — since 2026-09-12 — asides count too.\n"
        "```\n(not counted 2026-01-01)\n```\n~~~\n(nor this 2026-01-01)\n~~~\n"
        "| G01 | UNPROVEN (2026-09-15) |\n"
        "a path (`docs/reference/2026-09-11-report.md`) is not an annotation\n"
    )
    found = [snippet for _, snippet in dp.dated_annotations(text)]
    assert found == [
        "(corrected 2026-09-13)",
        "(D-30 (see 2026-09-15))",
        "[as of 2026-09-14]",
        "— since 2026-09-12 —",
    ]
    root = _tree(tmp_path)
    (root / "docs" / "PLAN.md").write_text(
        _doc("the plan", "versioned", mirrors="docs/INDEX.md")
        + "# plan\n\nThe zone is UTC (since 2026-09-15); what people say.\n",
        encoding="utf-8",
    )
    rep = dp.report(root)
    assert rep["values"] == {"dated_annotations": 1}
    hits = rep["hits"]
    assert isinstance(hits, list) and len(hits) == 1
    assert hits[0].startswith("dated_annotation docs/PLAN.md:") and hits[0].endswith(
        " (since 2026-09-15)"
    )


def test_the_command_line_exits_1_only_with_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _tree(tmp_path)
    (root / "CLAUDE.md").write_text("See `docs/GONE.md`.\n", encoding="utf-8")
    out = tmp_path / "dp.json"
    assert dp.main(["--root", str(root), "--write", str(out)]) == 0
    assert dp.main(["--root", str(root), "--write", str(out), "--check"]) == 1
    assert "`docs/GONE.md` does not exist" in capsys.readouterr().out
    assert out.is_file() and '"dated_annotations"' in out.read_text(encoding="utf-8")
