"""UI-56: the digest page renders the assembled model, and says what it could not collect.

The service half of the digest is proven in ``tests/services/test_report_service.py``; this
file is about the page: that the model reaches the template intact, that a thin section shows
its real denominator beside a sentence naming what did not run, that a post scrubbed after it
was collected leaves no trace on the page, and that a date with no run is a 404 rather than an
empty report that would read as a quiet week.

Assertions are on structure -- ``data-section``, ``data-post``, ``data-measure``, ``data-note``
-- so a wording change does not break a test and a missing section does not pass one.

The corpus is planted through ``db/repo.py``, the functions the collector writes with, on the
module's own temp database (``tests/web/conftest.py``): a row shape the production path cannot
produce is never asserted on, and the scrubbed row is written the way the scrub service will
leave it at M1c -- state changed, title and link gone, the row itself still there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest
from selectolax.parser import HTMLParser
from sqlalchemy import Engine
from starlette.testclient import TestClient

from tests.web.conftest import History
from threaddigest.core.models import PostRow
from threaddigest.db import repo
from threaddigest.db.ownership import IngestPath
from threaddigest.db.repo import REDDIT_WEB_HOST
from threaddigest.services.report import MIN_DISTINCT_AUTHORS, WINDOW_DAYS
from threaddigest.services.runs import Counters

#: A second run, a day after the history's, so this module owns the digest it reads: it is the
#: newest finished run in the database, which is also what ``/reports`` resolves to.
STARTED = int(datetime(2026, 9, 14, 6, 30, tzinfo=UTC).timestamp())
FINISHED = int(datetime(2026, 9, 14, 6, 41, tzinfo=UTC).timestamp())
REPORT_DATE: Final = date(2026, 9, 14)
REPORT_URL: Final = f"/reports/{REPORT_DATE.isoformat()}"

#: A day the database holds no run for at all.
QUIET_DATE: Final = date(2026, 1, 1)

#: The three live posts, newest-ranked last: no comment is captured, so the ranking falls
#: through to comment count and then score (``repo.ranked_posts``).
LIVE_POSTS: Final[tuple[tuple[str, int, int], ...]] = (
    ("wp1a", 31, 88),
    ("wp2b", 40, 120),
    ("wp3c", 12, 30),
)
RANKED_ORDER: Final = ("wp2b", "wp1a", "wp3c")

#: The post collected live and scrubbed afterwards. Its title is distinctive so the page can be
#: searched for it: the compliance claim is that no rendering of the digest can quote it.
SCRUBBED_ID: Final = "wp4d"
SCRUBBED_TITLE: Final = "the title an author deleted the next day"

#: ``12 of 60 items seen (20%)``: a number, the population it came out of, and an optional
#: percentage (an empty population has none). The same shape ``test_runs_page.py`` requires.
COUNT_SHAPE = re.compile(r"^\d[\d,]* of \d[\d,]* \S.*?(?: \(\d+%\))?$")

#: What the run's per-source rows say, so every denominator on the page has a known value.
PREMIERE_SEEN: Final = 40
EDITORS_SEEN: Final = 10
NEW_POSTS: Final = 3

_POST_FIELDS: dict[str, Any] = {
    "subreddit_id": "t5_2s9fq",
    "author": "cutting_room",
    "author_fullname": "t2_abcd12",
    "author_flair_text": None,
    "author_is_bot": False,
    "selftext": "",
    "selftext_html": "",
    "url": "https://example.com/x",
    "domain": "example.com",
    "edited_utc": None,
    "upvote_ratio": 0.9,
    "link_flair_text": None,
    "over_18": False,
    "spoiler": False,
    "is_self": True,
    "is_video": False,
    "is_gallery": False,
    "post_hint": None,
    "locked": False,
    "stickied": False,
    "archived": False,
    "distinguished": None,
    "crosspost_parent": None,
    "num_crossposts": 0,
    "removed_by_category": None,
    "source": "subreddit_new",
}


@dataclass(frozen=True)
class Digest:
    """What :func:`digest_run` planted, so a test names a row rather than a number."""

    run_pk: int
    items_seen: int


def _write(
    engine: Engine,
    reddit_id: str,
    *,
    subreddit_pk: int,
    subreddit: str,
    title: str | None,
    permalink: str | None,
    num_comments: int = 0,
    score: int = 0,
    content_state: str = "live",
) -> None:
    """One post through the collector's own upsert, never a raw INSERT.

    Called twice for the scrubbed row: once as the sweep stored it, once as the scrub service
    will leave it. ``title``, ``permalink`` and ``content_state`` are all in the ingest path's
    update columns (``db/ownership.py``), so the second write is a shape the production path
    can produce.
    """
    row = PostRow(
        **_POST_FIELDS,
        reddit_id=reddit_id,
        fullname=f"t3_{reddit_id}",
        subreddit=subreddit,
        title=title,
        permalink=permalink,
        created_utc=FINISHED - 3600,
        score=score,
        num_comments=num_comments,
    )
    write = repo.PostWrite(
        row=row,
        subreddit_pk=subreddit_pk,
        first_seen_at=STARTED,
        last_fetched_at=STARTED + 10,
        next_check_at=STARTED + 86_400,
        check_stage=0,
        content_state=content_state,
        author_state="known",
        misses=0,
        raw_json="{}",
    )
    with engine.begin() as conn:
        repo.upsert_posts(conn, [write], path=IngestPath.SUBREDDIT_NEW)


@pytest.fixture(scope="module")
def digest_run(seeded_engine: Engine, history: History) -> Digest:
    """The run this module reads a digest of, with its posts and one scrubbed row."""
    for reddit_id, num_comments, score in LIVE_POSTS:
        _write(
            seeded_engine,
            reddit_id,
            subreddit_pk=history.premiere_pk,
            subreddit="premiere",
            title=f"a post about {reddit_id}",
            permalink=f"/r/premiere/comments/{reddit_id}/",
            num_comments=num_comments,
            score=score,
        )
    _write(
        seeded_engine,
        SCRUBBED_ID,
        subreddit_pk=history.premiere_pk,
        subreddit="premiere",
        title=SCRUBBED_TITLE,
        permalink=f"/r/premiere/comments/{SCRUBBED_ID}/",
        num_comments=99,
        score=999,
    )
    # The scrub, as M1c will write it: the state moves and the content goes; the row stays, so
    # the deletion is recorded rather than forgotten.
    _write(
        seeded_engine,
        SCRUBBED_ID,
        subreddit_pk=history.premiere_pk,
        subreddit="premiere",
        title=None,
        permalink=None,
        num_comments=99,
        score=999,
        content_state="deleted_by_author",
    )

    options = '{"gateway": "fake", "budget": {"limit": 1500}}'
    with seeded_engine.begin() as conn:
        run_pk = repo.insert_run(
            conn,
            repo.RunInsert(
                kind="run",
                trigger="schedule",
                status="running",
                created_at=STARTED,
                started_at=STARTED,
                pid=None,
                stage="sweep",
                options_json=options,
                app_version="0.1.0",
                praw_version=None,
                schema_rev="0004",
                settings_fingerprint="9f2c" * 4,
                log_path=None,
            ),
        )
        for subreddit_pk, seen, new in (
            (history.premiere_pk, PREMIERE_SEEN, NEW_POSTS),
            (history.editors_pk, EDITORS_SEEN, 0),
        ):
            repo.upsert_run_subreddit(
                conn,
                run_pk=run_pk,
                subreddit_pk=subreddit_pk,
                progress=repo.SweepProgress(
                    pages=2,
                    items_seen=seen,
                    new_items=new,
                    updated_items=1,
                    stop_reason="exhausted",
                    error=None,
                ),
            )
        repo.finish_run(
            conn,
            run_pk=run_pk,
            status="ok",
            finished_at=FINISHED,
            counters_json=Counters(
                posts_new=NEW_POSTS, posts_updated=2, pages=2, api_requests=120
            ).to_json(),
            api_requests=120,
            error=None,
            violations_json="[]",
        )
    return Digest(run_pk=run_pk, items_seen=PREMIERE_SEEN + EDITORS_SEEN)


@pytest.fixture(scope="module")
def page(client: TestClient, digest_run: Digest) -> HTMLParser:
    """The digest page itself, parsed once: nothing in this module writes after it is read."""
    del digest_run  # ordering only: the rows must exist before the page is rendered
    response = client.get(REPORT_URL)
    assert response.status_code == 200, response.text
    return HTMLParser(response.text)


def _section(page: HTMLParser, name: str) -> HTMLParser:
    found = page.css(f'section[data-section="{name}"]')
    assert len(found) == 1, f"the digest shows {len(found)} sections called {name!r}"
    return HTMLParser(found[0].html or "")


def _measure(page: HTMLParser, label: str) -> str:
    """One measured line, label and value together, whitespace normalized.

    A measure is a table row on the summary and a paragraph elsewhere, so the whole element's
    text is returned and the assertions are containments: what matters is that the figure and
    its population are on the line a reader looks at.
    """
    cells = page.css(f'[data-measure="{label}"]')
    assert cells, f"the digest shows no measure called {label!r}"
    return " ".join((cells[0].text() or "").split())


# ------------------------------------------------------------------ the assembled model


def test_the_page_renders_the_assembled_model(page: HTMLParser, digest_run: Digest) -> None:
    """The run's own numbers, each against the population the run measured."""
    assert f"#{digest_run.run_pk}" in _measure(page, "Run")
    assert f"{NEW_POSTS} of {digest_run.items_seen} items seen (6%)" in _measure(page, "New posts")
    assert "120 of 1,500 budgeted requests" in _measure(page, "Requests")
    links = [node.attributes.get("href") for node in page.css("p.back a")]
    assert links == [f"/runs/{digest_run.run_pk}"], "the page does not link to its own run"


def test_the_top_posts_are_ranked_and_the_heading_names_its_window(page: HTMLParser) -> None:
    """One ranking function everywhere (D-09), and a list that says what window it covers."""
    workspace = _section(page, "workspace")
    listed = [node.attributes["data-post"] for node in workspace.css("ol.posts li[data-post]")]
    assert listed[: len(RANKED_ORDER)] == list(RANKED_ORDER)
    heading = workspace.css('h3[data-heading="top-posts"]')
    assert heading, "the top-post list has no heading"
    assert f"last {WINDOW_DAYS} days" in " ".join((heading[0].text() or "").split())


def test_every_post_link_on_the_page_opens_on_reddit(page: HTMLParser) -> None:
    """KI-036: the rendering, not the read. The page's whole purpose is to send a reader to the
    thread, and a stored permalink is a site-relative path, so an unchanged one resolved
    against this server and the link went nowhere. Asserted on the rendered ``href`` because
    that is what a reader clicks; the read's own half is in ``tests/db/test_repo_reads.py``.
    """
    hrefs = [node.attributes.get("href") for node in page.css("ol.posts li[data-post] a")]
    assert hrefs, "the digest listed no post at all"
    off_site = [href for href in hrefs if not (href or "").startswith(f"{REDDIT_WEB_HOST}/r/")]
    assert not off_site, f"post links that do not open on Reddit: {off_site}"


def test_every_number_on_the_page_carries_the_population_it_came_from(page: HTMLParser) -> None:
    printed = [" ".join((node.text() or "").split()) for node in page.css("span.count")]
    assert printed, "the digest printed no count at all"
    bare = [text for text in printed if not COUNT_SHAPE.match(text)]
    assert not bare, f"counts printed without their population: {bare}"


# ------------------------------------------------------------------ what has not been collected


def test_an_unstaged_section_shows_a_zero_against_a_real_denominator(page: HTMLParser) -> None:
    """``0 of 0`` says a stage did not run; ``0 of <posts>`` would claim it ran and found none."""
    backlog = _section(page, "backlog")
    assert "0 of 0 posts due for a comment tree" in _measure(backlog, "Due posts harvested")
    assert backlog.css("[data-note]"), "the backlog says nothing about why it is empty"

    workspace = _section(page, "workspace")
    untagged = [
        " ".join((node.text() or "").split())
        for node in workspace.css("h3")
        if "Untagged" in (node.text() or "")
    ]
    assert untagged, "the untagged section has no heading"
    assert f"at least {MIN_DISTINCT_AUTHORS}" in untagged[0]
    # The denominator is the window's real size: the three live posts, not a zero standing in
    # for a population nobody counted, and not the scrubbed row.
    assert f"0 of {len(LIVE_POSTS)} untagged posts in the last {WINDOW_DAYS} days" in untagged[0]


def test_each_unbuilt_stage_says_what_was_not_collected(page: HTMLParser) -> None:
    """Never blank and never invented: a thin section names the stage that has not run."""
    notes = [node.attributes.get("data-note") or "" for node in page.css("[data-note]")]
    assert any("theme" in note for note in notes), notes
    assert any("comment tree" in note for note in notes), notes
    assert any("reconcile" in note for note in notes), notes
    assert any("phrase extractor" in note for note in notes), notes
    assert all(note.strip() for note in notes), "a note was rendered empty"


# ------------------------------------------------------------------ the deleted title


def test_a_post_scrubbed_after_collection_leaves_nothing_on_the_page(
    page: HTMLParser, client: TestClient
) -> None:
    """The reason the digest is a route and never a file, proven on the rendering.

    A saved copy could quote a title its author deleted afterwards; a page assembled on the way
    out cannot, because the window reads only live rows with a link (``db/repo.py``). The row
    itself is still in the database -- the deletion is recorded, not forgotten -- so this is a
    statement about what the page may show, not about what the store may keep.
    """
    assert SCRUBBED_TITLE not in (client.get(REPORT_URL).text)
    shown = {node.attributes["data-post"] for node in page.css("li[data-post]")}
    assert SCRUBBED_ID not in shown, "the digest listed a scrubbed post"
    assert shown == {reddit_id for reddit_id, _, _ in LIVE_POSTS}


# ------------------------------------------------------------------ the addresses


def test_the_front_door_sends_a_reader_to_the_run_history(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/runs"


def test_the_digest_address_resolves_to_the_newest_finished_run(
    client: TestClient, digest_run: Digest
) -> None:
    """The header link carries no date, so it cannot go stale as runs land."""
    del digest_run  # ordering only: this module's run must be the newest finished one
    response = client.get("/reports", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == REPORT_URL


def test_the_digest_address_says_so_when_no_run_has_finished(empty_client: TestClient) -> None:
    response = empty_client.get("/reports", follow_redirects=False)
    assert response.status_code == 404
    assert "no run has finished" in response.text


# ------------------------------------------------------------------ a date with no run


def test_a_date_with_no_finished_run_is_a_404_naming_the_day(
    client: TestClient, digest_run: Digest
) -> None:
    """Not an empty report: a reader who mistyped a day must not read it as a quiet week."""
    del digest_run
    response = client.get(f"/reports/{QUIET_DATE.isoformat()}")
    assert response.status_code == 404
    assert QUIET_DATE.isoformat() in response.text


@pytest.mark.parametrize("raw", ["2026-13-01", "yesterday", "2026-09-32", "1e9", "2026_09_14"])
def test_an_unusable_date_is_refused_rather_than_raised(client: TestClient, raw: str) -> None:
    """422, never a traceback: the path parameter is a ``date`` before any query runs."""
    assert client.get(f"/reports/{raw}").status_code == 422
