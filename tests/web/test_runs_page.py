"""The Runs pages themselves: what a reader can and cannot learn from a run row.

Spec row UI-31's shippable half: the verdict and the error text are derived from the run row
-- its status, its recorded error, its invariant verdicts -- and never from a flag beside it,
which is that row's own negative control. Also the per-source outcomes, the 404, the cursor
paging, and the rule that no number reaches a page without the population it came out of.

Assertions are on structure: a row is found by ``data-run``, a measure by ``data-measure``, a
source by ``data-source``. Nothing here asserts on a whole-page snapshot.
"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser
from sqlalchemy import Engine
from starlette.testclient import TestClient

from tests.web.conftest import (
    FAILURE_DETAIL,
    FAILURE_INVARIANT,
    RECORDED_WARNINGS,
    RUN_ERROR,
    UNNAMED_WARNINGS,
    WARNING_DETAIL,
    WARNING_INVARIANT,
    History,
)
from threaddigest.db.schema import Base
from threaddigest.services import runs_view
from threaddigest.web.routes.runs import PAGE_SIZE, UNMAPPED_VERDICT, VERDICT_FOR_STATUS

#: ``12 of 60 items seen (20%)``: a number, the population it came out of, and nothing that
#: could be a bare total. The percentage is optional because an empty population has none.
COUNT_SHAPE = re.compile(r"^\d[\d,]* of \d[\d,]* \S.*?(?: \(\d+%\))?$")


def _tree(client: TestClient, url: str) -> HTMLParser:
    response = client.get(url)
    assert response.status_code == 200, f"{url}: {response.status_code}"
    return HTMLParser(response.text)


def _row(tree: HTMLParser, run_pk: int) -> str:
    rows = tree.css(f'tr.run[data-run="{run_pk}"]')
    assert len(rows) == 1, f"run #{run_pk} appears {len(rows)} times on the history"
    return rows[0].html or ""


def _measure(tree: HTMLParser, label: str) -> str:
    cells = tree.css(f'tr[data-measure="{label}"] td')
    assert cells, f"the run page shows no measure called {label!r}"
    return (cells[0].text() or "").strip()


# ------------------------------------------------------------------ the history


def test_the_history_lists_the_newest_runs_first(client: TestClient, history: History) -> None:
    tree = _tree(client, "/runs")
    shown = [int(row.attributes["data-run"] or "0") for row in tree.css("tr.run")]
    assert shown == sorted(shown, reverse=True), "the history is not newest first"
    assert len(shown) == PAGE_SIZE, f"a full first page is {PAGE_SIZE} rows, got {len(shown)}"
    assert shown[0] == history.running_pk, "the newest run is not at the top"
    assert history.oldest_on_first_page_pk == shown[-1]


def test_the_history_pages_by_the_last_row_it_showed(client: TestClient, history: History) -> None:
    """The cursor is a pk and is exclusive, so a second page never repeats a row."""
    first = _tree(client, "/runs")
    pager = first.css("p.pager a")
    assert pager, "a history longer than one page offers no link to the older runs"
    href = pager[0].attributes["href"] or ""
    assert f"before={history.oldest_on_first_page_pk}" in href

    second = _tree(client, href)
    older = [int(row.attributes["data-run"] or "0") for row in second.css("tr.run")]
    assert older == sorted(older, reverse=True)
    assert max(older) < history.oldest_on_first_page_pk, "the second page repeated a row"
    assert len(older) == history.total_runs - PAGE_SIZE
    assert not second.css("p.pager a"), "the last page offers a link to a page that is not there"


def test_every_verdict_the_database_can_hold_has_a_word_for_it() -> None:
    """The status vocabulary is the database's, so the page cannot quietly miss a new one.

    ``runs.status`` carries a CHECK constraint; reading the allowed values off the model is
    what makes this a scan of a structural shape rather than a second hand-kept list. A
    status the map does not know still reads as a problem, never as green, which is what
    :data:`UNMAPPED_VERDICT` is for.
    """
    check = next(
        constraint
        for constraint in Base.metadata.tables["runs"].constraints
        if getattr(constraint, "name", "") == "ck_runs_status"
    )
    allowed = set(re.findall(r"'([a-z_]+)'", str(check.sqltext)))
    assert allowed, "the status CHECK constraint could not be read"
    assert allowed <= set(VERDICT_FOR_STATUS), (
        f"statuses the pages have no word for: {sorted(allowed - set(VERDICT_FOR_STATUS))}"
    )
    assert UNMAPPED_VERDICT != "ok", "an unknown status would read as green"


# ------------------------------------------------------------------ why a run is not green


def test_a_partial_run_names_the_warning_that_made_it_amber(
    client: TestClient, history: History
) -> None:
    row = _row(_tree(client, "/runs"), history.partial_pk)
    assert 'data-verdict="warn"' in row
    page = _tree(client, f"/runs/{history.partial_pk}")
    problems = [item.text().strip() for item in page.css("ul.problems li")]
    assert any(WARNING_INVARIANT in text and WARNING_DETAIL in text for text in problems), problems


def test_a_run_from_before_0005_reports_the_warnings_it_cannot_name_as_a_number(
    client: TestClient, history: History
) -> None:
    """One warning named of three counted: the gap is stated, not hidden by showing one.

    This row predates the column that keeps a warning's name, and the page still owes its
    reader the number the run actually counted rather than the number it can print.
    """
    page = _tree(client, f"/runs/{history.partial_pk}")
    assert _measure(page, "Warnings named").startswith(f"1 of {UNNAMED_WARNINGS + 1} ")
    problems = " ".join(item.text() for item in page.css("ul.problems li"))
    assert f"{UNNAMED_WARNINGS} warning(s) this run counted and did not name" in problems


def test_a_run_names_the_warnings_it_recorded_itself(client: TestClient, history: History) -> None:
    """Revision 0005: an amber run whose warnings came from ``RunContext.warn`` names every
    one of them, and the page's count says none is missing."""
    page = _tree(client, f"/runs/{history.named_warning_pk}")
    problems = " ".join(item.text() for item in page.css("ul.problems li"))
    for name, detail in RECORDED_WARNINGS:
        assert name in problems and detail in problems, problems
    assert "did not name" not in problems, "nothing is unnamed on a row written since 0005"
    assert _measure(page, "Warnings named").startswith(
        f"{len(RECORDED_WARNINGS)} of {len(RECORDED_WARNINGS)} "
    )


def test_a_failed_run_shows_its_recorded_error_and_the_invariant_that_failed(
    client: TestClient, history: History
) -> None:
    row = _row(_tree(client, "/runs"), history.failed_pk)
    assert 'data-verdict="error"' in row
    page = _tree(client, f"/runs/{history.failed_pk}")
    problems = " ".join(item.text() for item in page.css("ul.problems li"))
    assert FAILURE_INVARIANT in problems and FAILURE_DETAIL in problems
    assert RUN_ERROR in problems, "the error the run recorded is not on its page"


def test_an_ok_run_shows_no_problems_at_all(client: TestClient, history: History) -> None:
    row = _row(_tree(client, "/runs"), history.ok_pk)
    assert 'data-verdict="ok"' in row
    page = _tree(client, f"/runs/{history.ok_pk}")
    assert not page.css("ul.problems"), "a green run listed a problem"


def test_a_run_whose_invariants_left_no_verdict_says_so(
    client: TestClient, history: History
) -> None:
    """``violations_json`` NULL is not the same as ``[]``: nothing ran, so nothing passed."""
    page = _tree(client, f"/runs/{history.running_pk}")
    assert "left no verdict" in page.css_first("p.verdict").text()


# ------------------------------------------------------------------ counts and their populations


def test_no_number_reaches_a_page_without_its_population(
    client: TestClient, history: History
) -> None:
    urls = ["/runs", f"/runs/{history.ok_pk}", f"/runs/{history.failed_pk}"]
    seen = 0
    for url in urls:
        for node in _tree(client, url).css("span.count"):
            text = (node.text() or "").strip()
            assert COUNT_SHAPE.match(text), f"{url}: {text!r} is not a count with a population"
            seen += 1
    assert seen, "no count was rendered anywhere, so this proves nothing"


def test_the_run_page_counts_new_posts_against_what_its_sources_saw(
    client: TestClient, history: History
) -> None:
    """The denominator is the digest's: ``items seen``, summed over the run's own sources."""
    page = _tree(client, f"/runs/{history.ok_pk}")
    assert _measure(page, "New posts").startswith("12 of 80 items seen")
    assert _measure(page, "Updated posts").startswith("40 of 80 items seen")
    # No tree is fetched before M1b: `0 of 0` says the stage did not run.
    assert _measure(page, "New comments").startswith("0 of 0 comments seen")
    assert _measure(page, "Requests").startswith("312 of 1,500 budgeted requests")
    assert _measure(page, "Items seen") == "80"


def test_a_run_with_no_recorded_budget_shows_no_percentage(
    client: TestClient, history: History
) -> None:
    """A row that recorded no budget prints an empty population rather than inventing one."""
    page = _tree(client, f"/runs/{history.running_pk}")
    assert _measure(page, "Requests") == "0 of 0 budgeted requests"


# ------------------------------------------------------------------ the sources, and the 404


def test_the_run_page_lists_every_source_it_swept(client: TestClient, history: History) -> None:
    page = _tree(client, f"/runs/{history.ok_pk}")
    sources = {node.attributes["data-source"]: node.text() for node in page.css("tr.source")}
    assert set(sources) == {"premiere", "editors"}
    assert "12 of 60 items seen" in (sources["premiere"] or "")
    assert "2 of 20 items seen" in (sources["editors"] or "")


def test_a_source_that_failed_shows_its_reason_and_its_error(
    client: TestClient, history: History
) -> None:
    page = _tree(client, f"/runs/{history.failed_pk}")
    row = page.css_first('tr.source[data-source="premiere"]').text()
    assert "error" in row and RUN_ERROR in row


def test_a_run_with_no_sources_says_it_swept_nothing(client: TestClient, history: History) -> None:
    page = _tree(client, f"/runs/{history.running_pk}")
    assert page.css(".empty"), "a run with no per-source row rendered an empty table instead"


def test_an_unknown_run_id_is_404(client: TestClient, history: History) -> None:
    response = client.get(f"/runs/{history.total_runs + 1}")
    assert response.status_code == 404


def test_the_pages_never_write(client: TestClient, seeded_engine: Engine, history: History) -> None:
    """Spec row UI-23 in the small: a GET leaves the run rows exactly as it found them.

    Read through the same repository the pages read, before and after every route: a write
    from a read route would change a row's parsed view even where the row count did not move.
    """

    def snapshot() -> list[object]:
        return [line.run for line in runs_view.recent(seeded_engine, limit=1000)]

    before = snapshot()
    for url in ("/runs", f"/runs/{history.ok_pk}", f"/runs/{history.partial_pk}"):
        assert client.get(url).status_code == 200
    assert snapshot() == before
