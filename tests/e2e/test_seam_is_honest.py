"""section 11.6: the default ``GATEWAY_FACTORY`` is what production runs against, and it
is restored after every e2e test that installs a different one.

No spec id (design-round5.md section 16, "Additional tests with no spec id").
"""

from __future__ import annotations

import pytest

from threaddigest import cli
from threaddigest.adapters.notify import LogNotifier, MacNotifier
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.settings import Settings


def test_default_gateway_factory_is_installed_by_default() -> None:
    """No fixture in this test ever touches the seam: this is the production default."""
    assert cli.GATEWAY_FACTORY is cli.default_gateway_factory


def test_default_gateway_factory_builds_a_fake_carrying_the_fixtures_subreddits(
    settings: Settings, demo_fixture_path: object
) -> None:
    """``default_gateway_factory("fake", <path>, settings)`` is production's only construction
    site for a fake gateway; RL-04 exercises it in its default form (section 11.6, item 4).
    """
    spec = cli.GatewaySpec(kind="fake", fixture=demo_fixture_path, settings=settings)
    gateway = cli.default_gateway_factory(spec)
    assert isinstance(gateway, FakeRedditGateway)
    for name in ("premiere", "VideoEditing", "editors"):
        about = gateway.about(name)  # raises SubredditNotFound if the fixture did not load
        assert about["display_name"].lower() == name.lower()


def test_default_gateway_factory_without_a_fixture_builds_an_empty_gateway(
    settings: Settings,
) -> None:
    spec = cli.GatewaySpec(kind="fake", fixture=None, settings=settings)
    gateway = cli.default_gateway_factory(spec)
    assert isinstance(gateway, FakeRedditGateway)
    assert gateway.requests_made == 0


def test_gateway_factory_is_restored_after_the_seam_is_used(fake: FakeRedditGateway) -> None:
    """Production never assigns to ``GATEWAY_FACTORY``; only ``monkeypatch`` does, and its
    teardown is what makes the default path honest for the next test (section 11.6, item 5).
    """
    original = cli.GATEWAY_FACTORY
    assert original is cli.default_gateway_factory
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cli, "GATEWAY_FACTORY", lambda _spec: fake)
        assert cli.GATEWAY_FACTORY is not original
    assert cli.GATEWAY_FACTORY is original


def test_the_notifier_is_the_log_notifier_under_pytest_and_the_mac_one_outside_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``cli`` is the only place the notifier is constructed, and it branches on the
    environment at CALL time -- the same mechanism as ``build_clock`` (section 11.8).

    Under pytest it must be the ``LogNotifier``, so a test run never puts banners on the
    developer's desktop; on a real Mac it must be the ``MacNotifier``, or section 11.9's
    notifications would go nowhere an operator can see. Constructing one sends nothing.
    """
    assert isinstance(cli.build_notifier(), LogNotifier)

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    assert isinstance(cli.build_notifier(), MacNotifier)

    monkeypatch.setattr(cli.sys, "platform", "linux")
    assert isinstance(cli.build_notifier(), LogNotifier)
