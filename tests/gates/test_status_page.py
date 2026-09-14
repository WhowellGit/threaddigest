"""G45: ``docs/recent/STATUS.md`` is a dated, capped resume surface that restates no counts.

Birth incident (2026-09-14, found by a fresh-context audit): the status page, the first thing a
resuming session reads, was stale within a day of being rewritten -- three workstreams listed as
in flight had merged, an install it said was pending had happened, and all three numbers in its
green-on-main line were wrong. The documentation-practices assessment had already ruled the page
"rewritten, never appended, capped at about fifty lines" with a staleness check, and the ruling
sat unenforced. The earlier project's status file became a changelog the same way.

What is enforced: a hard line cap; an opening ``**As of YYYY-MM-DD`` stamp no more than two days
older than ``HEAD``'s commit date, so a commit that leaves the page untouched for long goes red
and someone re-attests the whole page (the assessment's rule: re-verify the whole file or do not
stamp it); the four headings 46 independent handoffs converged on (in flight; next, numbered; what
a resuming session must not undo; what is waiting on the operator); and no restated test counts,
coverage figures, or ratchet tallies -- those have one home, the ``make check`` output, and a copy
here was the first thing to drift. What stays review: whether the words are true.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATUS = Path("docs") / "recent" / "STATUS.md"
MAX_LINES = 60
MAX_STAMP_AGE_DAYS = 2
STAMP = re.compile(r"^\*\*As of (\d{4}-\d{2}-\d{2})")
REQUIRED_HEADINGS = ("## In flight", "## Next", "## Do not undo", "## Waiting on Wes")
RESTATED_COUNT = re.compile(
    r"\b\d[\d,]*\s+(?:tests?|passed|collected|asserts?)\b"
    r"|\bcoverage\b[^\n]{0,24}\d"
    r"|\bratchets?\s+\d+\s+ok\b",
    re.IGNORECASE,
)


def head_date(root: Path) -> dt.date:
    out = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--format=%cs"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    return dt.date.fromisoformat(out)


def problems(text: str, head: dt.date) -> list[str]:
    """Every way the page fails its contract, one line each."""
    found: list[str] = []
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        found.append(f"{len(lines)} lines; the cap is {MAX_LINES}")
    body = [line for line in lines[1:] if line.strip()]
    stamp = STAMP.match(body[0]) if body else None
    if stamp is None:
        found.append("the first paragraph must open with '**As of YYYY-MM-DD'")
    else:
        stamped = dt.date.fromisoformat(stamp.group(1))
        if (head - stamped).days > MAX_STAMP_AGE_DAYS:
            found.append(
                f"stamped {stamped} but HEAD is dated {head}: re-verify the page and re-stamp it"
            )
    found += [
        f"missing heading {heading!r}"
        for heading in REQUIRED_HEADINGS
        if not any(line.rstrip() == heading for line in lines)
    ]
    found += [
        f"line {n}: restated count {m.group(0)!r} (numbers live in the make check output)"
        for n, line in enumerate(lines, start=1)
        if (m := RESTATED_COUNT.search(line))
    ]
    return found


def test_the_status_page_keeps_its_contract() -> None:
    text = (ROOT / STATUS).read_text(encoding="utf-8")
    found = problems(text, head_date(ROOT))
    assert not found, f"{STATUS}:\n" + "\n".join(found)


GOOD = """\
# STATUS

**As of 2026-09-14.** Everything is fine; numbers live in `make check`.

## In flight
- nothing

## Next
1. a step

## Do not undo
- a fact

## Waiting on Wes
- a ruling
"""


@pytest.mark.gate("G45")
def test_positive_control_a_clean_page_is_green() -> None:
    assert problems(GOOD, dt.date(2026, 9, 15)) == []


@pytest.mark.gate("G45")
def test_positive_control_each_failure_is_named() -> None:
    stale = problems(GOOD, dt.date(2026, 9, 17))
    assert stale == [
        "stamped 2026-09-14 but HEAD is dated 2026-09-17: re-verify the page and re-stamp it"
    ]
    unstamped = GOOD.replace("**As of 2026-09-14.**", "As of yesterday.")
    assert problems(unstamped, dt.date(2026, 9, 14)) == [
        "the first paragraph must open with '**As of YYYY-MM-DD'"
    ]
    missing = GOOD.replace("## Do not undo", "## Undo")
    assert problems(missing, dt.date(2026, 9, 14)) == ["missing heading '## Do not undo'"]
    counted = GOOD.replace("- nothing", "- 1,425 tests pass; coverage floor 98.22; ratchet 10 ok")
    found = problems(counted, dt.date(2026, 9, 14))
    assert [c.split(": ", 1)[0] for c in found] == ["line 6"] and "1,425 tests" in found[0]
    long = problems(GOOD + "- filler\n" * MAX_LINES, dt.date(2026, 9, 14))
    assert long[0].endswith(f"the cap is {MAX_LINES}")
