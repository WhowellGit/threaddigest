"""``services/probe.py``: the five ``capture_*`` functions, ``save``, and the `probe` CLI
sub-app (brief B1's CONTRACT).

``capture_*`` is exercised directly against ``FakeRedditGateway`` (it speaks the same wire
dicts the real adapter will); ``--save-fixture``, ``--blank-bodies`` and the two refusals are
exercised through a real ``CliRunner`` against the DEFAULT ``GATEWAY_FACTORY``, the same way
``tests/gates/test_mutating_commands.py`` covers `run` -- so the production construction path
is what these tests actually run, not a seam standing in for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from threaddigest import cli
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.core import fixture_scrub
from threaddigest.core.retry import ExitCode
from threaddigest.services import probe

#: A fixed epoch second (the fake has no clock in these tests, so add_post needs one).
CREATED = 1_757_700_000


@pytest.fixture
def cli_runner() -> CliRunner:
    """A real Typer ``CliRunner`` (in-process), for the probe command surface only."""
    return CliRunner()


# --- capture_* : one port call each, the scrubbed payload, requests_used from the delta -------


def test_capture_about_costs_one_call_and_one_request(fake: FakeRedditGateway) -> None:
    fake.add_subreddit("premiere", subscribers=1)
    capture = probe.capture_about(fake, "premiere")
    assert capture.mode == "about"
    assert capture.target == "premiere"
    assert capture.requests_used == 1
    assert fake.count("about") == 1
    assert capture.payload["display_name"] == "premiere"


def test_capture_listing_fetches_one_page_when_the_limit_fits_in_it(
    seeded: FakeRedditGateway,
) -> None:
    capture = probe.capture_listing(seeded, "premiere", limit=5)
    assert capture.mode == "listing"
    assert capture.target == "premiere"
    assert len(capture.payload["items"]) == 5
    assert capture.requests_used == 1
    assert len(capture.payload["pages"]) == 1


def test_capture_listing_spans_pages_when_the_limit_exceeds_one_page(
    seeded: FakeRedditGateway,
) -> None:
    capture = probe.capture_listing(seeded, "premiere", limit=150)
    assert len(capture.payload["items"]) == 150
    assert capture.requests_used == 2
    assert [p["complete"] for p in capture.payload["pages"]] == [False, False]


def test_capture_tree_returns_the_post_its_comments_and_no_more_stubs(
    fake: FakeRedditGateway,
) -> None:
    post = fake.add_post("premiere", title="t", author="u1", created_utc=CREATED)
    fake.add_comment(post, body="top", author="u2", created_utc=CREATED)
    capture = probe.capture_tree(fake, post, more_limit=16)
    assert capture.mode == "tree"
    assert capture.target == post
    assert capture.payload["post"]["id"] == post.removeprefix("t3_")
    assert len(capture.payload["comments"]) == 1
    assert capture.payload["more"] == []
    assert capture.payload["complete"] is True
    assert capture.requests_used == 1


def test_capture_info_returns_found_items_only_at_one_request(fake: FakeRedditGateway) -> None:
    post = fake.add_post("premiere", title="t", author="u1", created_utc=CREATED)
    capture = probe.capture_info(fake, [post, "t3_zzzzzz"])
    assert capture.mode == "info"
    assert len(capture.payload) == 1
    assert capture.payload[0]["name"] == post
    assert capture.requests_used == 1


def test_capture_search_pages_up_to_the_gateways_own_default_cap(
    seeded: FakeRedditGateway,
) -> None:
    capture = probe.capture_search(seeded, "post", sort="new", time_filter="all")
    assert capture.mode == "search"
    assert capture.target == "post"
    assert len(capture.payload["items"]) == 250  # SEARCH_CAP; every seeded post matches "post"
    assert capture.requests_used == len(capture.payload["pages"]) == 3


# --- save: scrub-on-save (unconditional), blank-bodies, refuse-to-overwrite --------------------


def test_save_writes_a_scrubbed_file_under_the_data_dirs_probe_subdir(
    tmp_path: Path, fake: FakeRedditGateway
) -> None:
    post = fake.add_post("premiere", title="t", author="u1", created_utc=CREATED)
    capture = probe.capture_info(fake, [post])
    path = probe.save(capture, data_dir=tmp_path, name="demo", blank_bodies=False)
    assert path == tmp_path / "probe" / "demo.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert fixture_scrub.offending_values(saved) == []
    assert fixture_scrub.SYNTHETIC_NAME.match(saved[0]["author"])
    assert fixture_scrub.SYNTHETIC_ID.match(saved[0]["author_fullname"])


def test_save_scrubs_even_a_payload_that_was_never_scrubbed_by_a_capture(
    tmp_path: Path,
) -> None:
    """The positive control for ``save``'s own unconditional scrub: a hand-built ``Capture``
    whose payload carries a real-looking author and a real-looking ``t2_`` id, never passed
    through ``capture_*``/``fixture_scrub.scrub`` at all. If ``save`` skipped its own scrub
    (trusting the capture to have already done it), this assertion would be the one to go red.
    """
    payload = {"author": "a_real_person", "author_fullname": "t2_abcdef", "id": "xyz"}
    capture = probe.Capture(mode="info", target="t3_xyz", payload=payload, requests_used=1)
    path = probe.save(capture, data_dir=tmp_path, name="control", blank_bodies=False)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert fixture_scrub.offending_values(saved) == []
    assert saved["author"] != "a_real_person"
    assert saved["author_fullname"] != "t2_abcdef"


def test_save_blank_bodies_empties_body_fields_and_keeps_ids_scores_and_timestamps(
    tmp_path: Path, fake: FakeRedditGateway
) -> None:
    post = fake.add_post(
        "premiere", title="t", author="u1", selftext="secret text", created_utc=CREATED
    )
    capture = probe.capture_info(fake, [post])
    path = probe.save(capture, data_dir=tmp_path, name="blanked", blank_bodies=True)
    saved = json.loads(path.read_text(encoding="utf-8"))
    item = saved[0]
    assert item["selftext"] == ""
    assert item["selftext_html"] == ""
    assert item["id"] == post.removeprefix("t3_")
    assert item["score"] == capture.payload[0]["score"]
    assert item["created_utc"] == capture.payload[0]["created_utc"]


def test_save_refuses_to_overwrite_and_leaves_the_first_file_untouched(
    tmp_path: Path, fake: FakeRedditGateway
) -> None:
    post = fake.add_post("premiere", title="t", author="u1", created_utc=CREATED)
    capture = probe.capture_info(fake, [post])
    path = probe.save(capture, data_dir=tmp_path, name="once", blank_bodies=False)
    original = path.read_bytes()
    with pytest.raises(probe.FixtureExistsError):
        probe.save(capture, data_dir=tmp_path, name="once", blank_bodies=False)
    assert path.read_bytes() == original


# --- target parsing: "r/<sub>", a bare "<sub>", and "r/<sub>/new" (CONTRACT item 4) ------------


def test_subreddit_and_listing_target_parsing_accepts_every_documented_form() -> None:
    assert cli._subreddit_name("r/premiere") == "premiere"
    assert cli._subreddit_name("premiere") == "premiere"
    assert cli._listing_target("r/premiere/new") == "premiere"
    assert cli._listing_target("premiere/new") == "premiere"
    assert cli._listing_target("premiere") == "premiere"


# --- the CLI surface: --save-fixture, --blank-bodies, the two refusals, the promotion line ----


def test_cli_save_fixture_writes_the_file_and_prints_the_promotion_command(
    cli_runner: CliRunner, isolated_data_dir: Path, demo_fixture_path: Path
) -> None:
    result = cli_runner.invoke(
        cli.app,
        [
            "probe",
            "--gateway",
            "fake",
            "--fixture",
            str(demo_fixture_path),
            "about",
            "premiere",  # the bare form, no "r/" prefix
            "--save-fixture",
            "about_premiere",
        ],
    )
    assert result.exit_code == 0, result.output
    saved = isolated_data_dir / "probe" / "about_premiere.json"
    assert saved.is_file()
    assert f"wrote {saved}" in result.output
    assert f"cp {saved} tests/fixtures/json/captures/about_premiere.json" in result.output, (
        result.output
    )


def test_cli_a_second_save_fixture_with_the_same_name_is_refused_at_78(
    cli_runner: CliRunner, isolated_data_dir: Path, demo_fixture_path: Path
) -> None:
    args = [
        "probe",
        "--gateway",
        "fake",
        "--fixture",
        str(demo_fixture_path),
        "about",
        "r/premiere",
        "--save-fixture",
        "dup",
    ]
    first = cli_runner.invoke(cli.app, args)
    assert first.exit_code == 0, first.output
    saved = isolated_data_dir / "probe" / "dup.json"
    original = saved.read_bytes()

    second = cli_runner.invoke(cli.app, args)

    assert second.exit_code == int(ExitCode.CONFIG)
    assert saved.read_bytes() == original


def test_cli_gateway_praw_is_refused_under_pytest_with_no_file_written(
    cli_runner: CliRunner, isolated_data_dir: Path
) -> None:
    result = cli_runner.invoke(
        cli.app, ["probe", "--gateway", "praw", "about", "r/premiere", "--save-fixture", "never"]
    )
    assert result.exit_code == int(ExitCode.CONFIG)
    assert not (isolated_data_dir / "probe").exists()
