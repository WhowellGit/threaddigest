"""KI-046 on the page: the digest names the settings that changed and never a credential.

The digest's settings line is the one rendering that prints *settings values* to a screen: it
diffs two runs' recorded ``runs.settings_json`` and shows the old and new value of every key
that moved (D-38, spec row DG-03). The 2026-09-17 code panel (seat B, finding B2) rendered the
OAuth client id there by rotating it, because two credential fields were annotated ``str`` and
so sat inside the mapping a run row stores.

This module is the page's half of that fix, and it is deliberately not vacuous: it plants two
runs whose recorded settings are the **real** serialization of a settings object carrying
planted credentials, asserts that the page does print the key that changed -- so the renderer
under test was reached with settings to compare -- and then that no planted credential appears
anywhere in the response.

Its own module, so it owns its temp database (``tests/web/conftest.py`` builds one per module)
and the two runs it plants are the newest in it; no other module's "newest finished run" moves.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import pytest
from selectolax.parser import HTMLParser
from sqlalchemy import Engine
from starlette.testclient import TestClient

from tests.unit.test_settings import CREDENTIAL_SENTINELS
from tests.web.conftest import History
from threaddigest.db import repo
from threaddigest.services.runs import Counters
from threaddigest.settings import Settings, settings_fingerprint, settings_json

#: A day after every run ``build_history`` plants, so ``/reports/<this day>`` resolves to the
#: second of the two runs below and its previous run is the first of them.
_STARTED: Final = int(datetime(2026, 9, 15, 6, 30, tzinfo=UTC).timestamp())
_FINISHED: Final = int(datetime(2026, 9, 15, 6, 41, tzinfo=UTC).timestamp())
REPORT_URL: Final = f"/reports/{date(2026, 9, 15).isoformat()}"

#: The ordinary non-secret key the two runs differ in, so the diff always has something to
#: render and the assertions below cannot pass because the list was empty.
CHANGED_KEY: Final = "data_dir"

#: The second run's credentials: every one rotated, which is precisely the case the panel
#: reproduced -- a rotated client id printed the old and the new value on this page. The
#: digest shows only the keys that *changed*, so a credential that never changes leaks
#: nothing here; rotating all four is what makes this page test a real control.
ROTATED_CREDENTIALS: Final[dict[str, str]] = {
    name: f"ROTATED-{value}" for name, value in CREDENTIAL_SENTINELS.items()
}


def _plant_run(engine: Engine, *, settings: Settings, offset: int) -> int:
    """One finished run carrying the real serialization of ``settings`` on its row."""
    with engine.begin() as conn:
        run_pk = repo.insert_run(
            conn,
            repo.RunInsert(
                kind="run",
                trigger="schedule",
                status="running",
                created_at=_STARTED + offset,
                started_at=_STARTED + offset,
                pid=None,
                stage="sweep",
                options_json='{"gateway": "fake", "budget": {"limit": 1500}}',
                app_version="0.1.0",
                praw_version=None,
                schema_rev="0005",
                settings_fingerprint=settings_fingerprint(settings),
                log_path=None,
            ),
        )
        repo.record_run_settings(conn, run_pk=run_pk, settings_json=settings_json(settings))
        repo.finish_run(
            conn,
            run_pk=run_pk,
            status="ok",
            finished_at=_FINISHED + offset,
            counters_json=Counters(api_requests=12).to_json(),
            api_requests=12,
            error=None,
            violations_json="[]",
            warnings_json="[]",
        )
    return run_pk


@pytest.fixture(scope="module")
def page(
    client: TestClient, seeded_engine: Engine, seeded_data_dir: Path, history: History
) -> HTMLParser:
    """The digest of two consecutive runs whose settings differ in exactly one key."""
    del history  # ordering only: the sources and the older runs exist before these two
    before = Settings(**CREDENTIAL_SENTINELS, data_dir=seeded_data_dir)
    after = Settings(**ROTATED_CREDENTIALS, data_dir=seeded_data_dir / "relocated")
    assert settings_fingerprint(before) != settings_fingerprint(after)
    _plant_run(seeded_engine, settings=before, offset=0)
    _plant_run(seeded_engine, settings=after, offset=3600)

    response = client.get(REPORT_URL)
    assert response.status_code == 200, response.text
    return HTMLParser(response.text)


def _settings_cell(page: HTMLParser) -> str:
    cells = page.css('[data-measure="Settings"]')
    assert len(cells) == 1, f"the digest shows {len(cells)} settings measures"
    return " ".join((cells[0].text() or "").split())


def test_the_page_really_diffs_two_recorded_settings(page: HTMLParser) -> None:
    """The anti-vacuous half: without this the credential assertion below proves nothing.

    A run pair whose settings were not recorded renders the "which keys changed is not
    recorded" sentence instead, and a page that never reached the diff would pass a search for
    a credential trivially.
    """
    cell = _settings_cell(page)
    assert "Changed since the previous run" in cell
    assert "not recorded" not in cell
    assert CHANGED_KEY in cell, cell
    assert "relocated" in cell, "the changed value itself is on the page, old and new"


def test_no_credential_appears_anywhere_on_the_digest(page: HTMLParser, client: TestClient) -> None:
    """Rule 2 on the surface that renders settings values: the whole response, not one cell.

    The page is searched as raw text as well as parsed, so an escaped or attribute-borne copy
    counts as a leak.
    """
    raw = client.get(REPORT_URL).text
    rendered = page.text() or ""
    for name in CREDENTIAL_SENTINELS:
        for value in (CREDENTIAL_SENTINELS[name], ROTATED_CREDENTIALS[name]):
            assert value not in raw, f"{name}'s value is in the digest's HTML"
            assert value not in rendered, f"{name}'s value is in the digest's text"
        assert name not in raw, f"{name} is named on the digest at all"
