"""G39: every rule in CLAUDE.md names an enforcer that exists, or is labelled review-only.

Birth incident (Wes, 2026-09-13): written rules are not enforcement. The working agreement's
"Rules and what enforces them" table is the project's own claim about which rules are mechanical,
and nothing checked the claim: a cell could name a hook, a test or a make target that had been
renamed, deleted, or never written, and the table would still read as a wall of enforcement.

The check resolves each backticked token in the "Enforced by" cell against the tree -- a path
that exists (a test, a hook script, a tool, a config file), a pytest marker declared in
``pyproject.toml``, a selected ruff rule code, or a ``make`` target the Makefile defines. A row
with at least one resolving token is enforced. A row with none must say "review", which labels it
review-only; the count of those is a ceiling in ``.ratchets/review_only_rules.txt`` that
``make ratchet-bump`` maintains and that only goes down, so the weakest column can shrink but
never quietly grow. A row that neither resolves nor says "review" is red here.

Precedence note: a row that resolves *and* mentions review counts as enforced. What makes a rule
review-only is having nothing mechanical behind it; counting the belt-and-braces rows would
inflate the ceiling and leave room for a genuinely unenforced rule to slip in under it.

The classifier lives in ``tools/ratchet.py`` so the ratchet's count and this gate cannot drift
apart: they are the same code, called from the measurement and from the assertion.

What this gate cannot check, and what therefore stays review: that the named enforcer actually
enforces the rule. A cell naming a real file that checks something else still passes, and deleting
a whole row still removes a rule silently. It closes the cheapest hole -- a citation that does not
resolve at all -- and prints the review-only rows on every run so the weak column stays visible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.ratchet import (
    ENFORCED,
    REVIEW_ONLY,
    RULES_DOC,
    UNENFORCED,
    classify_rules,
    measure_rules,
    read_family_values,
    rules_with,
)

ROOT = Path(__file__).resolve().parents[2]
CEILING = "review_only_rules"

SYNTHETIC = """\
# working agreement

## Rules and what enforces them

| Rule | Enforced by |
|---|---|
| Named test exists | `tests/gates/test_real.py` |
| Named test does not exist | `tests/gates/test_ghost.py` |
| Marker | the `gate` marker |
| Make target | `make check` before every PR |
| Nothing mechanical | review by a human or an independent agent |
| Bare claim | the collector is careful |

## Routing: read before you touch

| If you are about to… | Read first |
|---|---|
| Read past the table | this row is in another section and is not a rule |
"""


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "tests" / "gates").mkdir(parents=True)
    (tmp_path / "tests" / "gates" / "test_real.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers = ["gate: a positive control"]\n', encoding="utf-8"
    )
    (tmp_path / "Makefile").write_text("check:\n\techo hi\n", encoding="utf-8")
    (tmp_path / RULES_DOC).write_text(SYNTHETIC, encoding="utf-8")
    return tmp_path


def test_every_rule_names_an_enforcer_that_exists_or_says_review() -> None:
    unenforced = rules_with(classify_rules(ROOT), UNENFORCED)
    assert not unenforced, "rules naming no enforcer that resolves:\n" + "\n".join(
        f"{rule.describe()} -> {rule.enforcer}" for rule in unenforced
    )


def test_the_rules_table_is_parsed_and_is_mostly_mechanical() -> None:
    """A parser that found nothing, or a table gone all-review, would pass the check above."""
    rules = classify_rules(ROOT)
    assert len(rules) >= 10, f"only {len(rules)} rule rows parsed from {RULES_DOC}"
    assert len(rules_with(rules, ENFORCED)) > len(rules_with(rules, REVIEW_ONLY))


def test_the_review_only_count_is_at_or_under_the_committed_ceiling() -> None:
    ceiling = read_family_values(ROOT, CEILING).get("count")
    assert ceiling is not None, f".ratchets/{CEILING}.txt has no count; run make ratchet-bump"
    review_only = rules_with(classify_rules(ROOT), REVIEW_ONLY)
    assert len(review_only) <= ceiling, (
        f"{len(review_only)} review-only rules against a ceiling of {ceiling}; the ceiling only "
        "goes down (make ratchet-loosen, which needs approval and a GUARDS.md row):\n"
        + "\n".join(rule.describe() for rule in review_only)
    )
    assert measure_rules(ROOT, [], []) == len(review_only)


@pytest.mark.gate("G39")
def test_positive_control_an_enforcer_that_does_not_exist_is_red(tmp_path: Path) -> None:
    rules = classify_rules(_tree(tmp_path))

    assert [rule.rule for rule in rules_with(rules, UNENFORCED)] == [
        "Named test does not exist",
        "Bare claim",
    ]
    assert [rule.rule for rule in rules_with(rules, ENFORCED)] == [
        "Named test exists",
        "Marker",
        "Make target",
    ]


@pytest.mark.gate("G39")
def test_positive_control_a_review_row_is_counted_not_failed(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    hits: list[str] = []

    assert [rule.rule for rule in rules_with(classify_rules(root), REVIEW_ONLY)] == [
        "Nothing mechanical"
    ]
    assert measure_rules(root, hits, []) == 1
    assert hits == [f"{RULES_DOC}:11 Nothing mechanical [review-only]"]
