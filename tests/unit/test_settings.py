"""Settings: precedence, strictness, fingerprint, and user agent."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from threaddigest.settings import (
    SANCTIONED_ENVIRONMENT_VARIABLES,
    Settings,
    default_settings_file,
    non_secret_settings,
    settings_fingerprint,
    settings_json,
    unknown_environment_variables,
    user_agent,
)


def _shipped_yaml() -> dict[str, Any]:
    with default_settings_file().open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    assert isinstance(loaded, dict)
    return loaded


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_shipped_settings_yaml_validates(settings: Settings) -> None:
    assert settings.settings_file == default_settings_file().resolve()
    assert settings.static.budget.per_run_requests == _shipped_yaml()["budget"]["per_run_requests"]


def test_shipped_display_timezone_is_a_zone_the_digest_can_resolve(settings: Settings) -> None:
    """KI-011: the shipped ``display_timezone`` must be a zone ``core.digest`` can load. The
    old shipped value ``local`` was not, so the first digest weeks into M1d would have failed;
    now it is ``UTC`` and settings validation rejects any unresolvable value at load."""
    from threaddigest.core.digest import known_display_timezone

    known_display_timezone(settings.static.display_timezone)  # does not raise


def test_settings_reject_an_unresolvable_display_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: the exact class of value KI-011 shipped ('local', and any bad zone) now
    fails at settings load rather than silently at the first digest."""
    for bad in ("local", "Mars/Olympus", "US/Nowhere"):
        monkeypatch.setenv("THREADDIGEST_STATIC__DISPLAY_TIMEZONE", bad)
        with pytest.raises(ValidationError):
            Settings()
        monkeypatch.delenv("THREADDIGEST_STATIC__DISPLAY_TIMEZONE")


def test_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_value = _shipped_yaml()["budget"]["per_run_requests"]
    assert yaml_value != 7
    monkeypatch.setenv("THREADDIGEST_STATIC__BUDGET__PER_RUN_REQUESTS", "7")

    assert Settings().static.budget.per_run_requests == 7


def test_yaml_overrides_nothing_but_supplies_static_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = _shipped_yaml()
    data["budget"]["per_run_requests"] = 42
    monkeypatch.setenv("THREADDIGEST_SETTINGS_FILE", str(_write_yaml(tmp_path / "s.yaml", data)))

    resolved = Settings()

    assert resolved.static.budget.per_run_requests == 42
    assert resolved.settings_file == (tmp_path / "s.yaml").resolve()


def test_defaults_apply_when_env_and_yaml_are_silent(settings: Settings) -> None:
    assert settings.reddit_client_id.get_secret_value() == ""
    assert settings.reddit_client_secret.get_secret_value() == ""
    assert settings.reddit_username.get_secret_value() == ""
    assert settings.ui_password is None


def test_env_supplies_operator_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # The account name is a distinctive value rather than a short login: it is asserted absent
    # from the rendered object (KI-046), and the developer's own login is a substring of every
    # temp path in the rendering, which would make a three-letter name a false positive.
    monkeypatch.setenv("THREADDIGEST_REDDIT_USERNAME", "account-name-Qx45")
    monkeypatch.setenv("THREADDIGEST_REDDIT_CLIENT_SECRET", "hunter2")
    monkeypatch.setenv("THREADDIGEST_UI_PASSWORD", "open-sesame")

    resolved = Settings()

    assert resolved.reddit_username.get_secret_value() == "account-name-Qx45"
    assert resolved.reddit_client_secret.get_secret_value() == "hunter2"
    assert isinstance(resolved.ui_password, SecretStr)
    assert resolved.ui_password.get_secret_value() == "open-sesame"
    rendered = f"{resolved!r} {resolved!s} {resolved.model_dump()}"
    assert "hunter2" not in rendered
    assert "open-sesame" not in rendered
    assert "account-name-Qx45" not in rendered, "the account name is credential material too"


def test_unknown_yaml_key_fails_naming_it(tmp_path: Path) -> None:
    data = _shipped_yaml()
    data["bogus_key"] = 1
    with pytest.raises(ValidationError, match="bogus_key"):
        Settings(settings_file=_write_yaml(tmp_path / "s.yaml", data))


def test_unknown_nested_yaml_key_fails_naming_it(tmp_path: Path) -> None:
    data = _shipped_yaml()
    data["budget"]["per_run_request"] = 5  # misspelled: singular
    with pytest.raises(ValidationError, match="per_run_request"):
        Settings(settings_file=_write_yaml(tmp_path / "s.yaml", data))


def test_missing_yaml_key_fails_naming_it(tmp_path: Path) -> None:
    data = _shipped_yaml()
    del data["retention"]
    with pytest.raises(ValidationError, match="retention"):
        Settings(settings_file=_write_yaml(tmp_path / "s.yaml", data))


def test_unknown_setting_is_rejected() -> None:
    unknown: dict[str, Any] = {"bogus": 1}
    with pytest.raises(ValidationError, match="bogus"):
        Settings(**unknown)


#: Misspellings ``extra="forbid"`` cannot see, because pydantic-settings never offers an
#: unmatched environment variable to the model at all: a typo'd operator field, a variable
#: under a leaf field, and a nested key whose FIRST segment already names nothing.
UNKNOWN_ENVIRONMENT_VARIABLES = [
    "THREADDIGEST_DATA_DIRR",
    "THREADDIGEST_DATA_DIR__DEEPER",
    "THREADDIGEST_BUDGET__PER_RUN_REQUESTS",
]


@pytest.mark.parametrize("name", UNKNOWN_ENVIRONMENT_VARIABLES)
def test_an_unknown_environment_variable_is_rejected_naming_it(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Panel P2-8: the module docstring claimed ``extra="forbid"`` made a misspelled key fail,
    which was true of ``settings.yaml`` and false of the environment -- pydantic-settings
    matches ``THREADDIGEST_*`` against the field names and silently drops the rest, so
    ``THREADDIGEST_DATA_DIRR=/tmp/x`` ran against the DEFAULT data directory while the
    operator believed it was overridden.

    The stronger option was implemented rather than the docstring corrected: a validator over
    ``os.environ``. The message names the variable, so ``config validate`` and every command
    exit 78 pointing at the typo.
    """
    monkeypatch.setenv(name, "7")

    with pytest.raises(ValidationError, match=name):
        Settings()

    assert unknown_environment_variables() == [name]


def test_a_misspelled_nested_static_key_is_still_rejected_by_forbid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the pair: when the first segment DOES name a field, the variable
    reaches the model and ``extra="forbid"`` on the nested model rejects it, naming the key.
    Both mechanisms are needed and neither covers the other's case.
    """
    monkeypatch.setenv("THREADDIGEST_STATIC__BUDGET__PER_RUN_REQUEST", "7")  # singular

    with pytest.raises(ValidationError, match="per_run_request"):
        Settings()


def test_every_recognised_environment_variable_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The negative control for the scan: a validator that rejected something real would
    break every command, so each shape that must stay recognised is asserted here -- an
    operator field, a path field, a nested static key, and the two sanctioned variables that
    are deliberately not fields (``tests/conftest.py``'s autouse fixture sets the data dir,
    ``tests/gates/test_data_dir_isolation.py`` sets the opt-in, and
    ``deploy/launchd/run.sh`` reads the UI URL).
    """
    monkeypatch.setenv("THREADDIGEST_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("THREADDIGEST_REDDIT_USERNAME", "wes")
    monkeypatch.setenv("THREADDIGEST_SETTINGS_FILE", str(default_settings_file()))
    monkeypatch.setenv("THREADDIGEST_STATIC__BUDGET__PER_RUN_REQUESTS", "7")
    monkeypatch.setenv("THREADDIGEST_ALLOW_REAL_DATA_DIR", "1")
    monkeypatch.setenv("THREADDIGEST_UI_URL", "http://127.0.0.1:8765")

    assert unknown_environment_variables() == []
    assert Settings().static.budget.per_run_requests == 7
    assert SANCTIONED_ENVIRONMENT_VARIABLES == frozenset(
        {
            "THREADDIGEST_ALLOW_REAL_DATA_DIR",
            "THREADDIGEST_UI_URL",
        }
    )


def test_budget_above_hard_cap_is_rejected(tmp_path: Path) -> None:
    data = _shipped_yaml()
    data["budget"]["per_run_requests"] = data["budget"]["hard_cap"] + 1
    with pytest.raises(ValidationError, match="hard_cap"):
        Settings(settings_file=_write_yaml(tmp_path / "s.yaml", data))


def test_fingerprint_ignores_secrets(settings: Settings) -> None:
    a = Settings(
        reddit_client_id="id-a",
        reddit_client_secret="a",
        reddit_username="user-a",
        ui_password="p1",
    )
    b = Settings(
        reddit_client_id="id-b",
        reddit_client_secret="b",
        reddit_username="user-b",
        ui_password="p2",
    )
    assert settings_fingerprint(a) == settings_fingerprint(b) == settings_fingerprint(settings)
    assert len(settings_fingerprint(a)) == 64


# ------------------------------------------------------------------ KI-046: credential material

#: One planted value per credential field, each unmistakable wherever it surfaces. The 2026-09-17
#: code panel (seat B, finding B2) found two of these four fields annotated `str`, so they were
#: outside ``non_secret_settings``'s structural definition of "secret" and therefore inside the
#: mapping every run row stores (``runs.settings_json``, revision 0005) and the digest diffs.
CREDENTIAL_SENTINELS: dict[str, str] = {
    "reddit_client_id": "SENTINEL-CLIENT-ID-Qx41",
    "reddit_client_secret": "SENTINEL-CLIENT-SECRET-Qx42",
    "reddit_username": "SENTINEL-ACCOUNT-NAME-Qx43",
    "ui_password": "SENTINEL-UI-PASSWORD-Qx44",
}


def _with_sentinel_credentials() -> Settings:
    return Settings(**CREDENTIAL_SENTINELS)


def test_every_credential_field_is_typed_secret() -> None:
    """The annotation is the mechanism: ``non_secret_settings`` excludes ``SecretStr`` fields
    and nothing else, so a credential declared ``str`` is stored and rendered by default.

    An account identifier is credential material under irreversible rule 2 -- the OAuth client
    id and the Reddit account name identify the operator's app and the operator -- so all four
    fields are held to the same type rather than to a second, hand-kept list of names.
    """
    for name in CREDENTIAL_SENTINELS:
        annotation = Settings.model_fields[name].annotation
        assert annotation is SecretStr or SecretStr in get_args(annotation), (
            f"{name} is annotated {annotation!r}, so it is not a secret to anything here"
        )


def test_no_credential_reaches_the_stored_settings_or_the_fingerprint_input() -> None:
    """With all four planted, none appears in what a run row stores or what is hashed."""
    resolved = _with_sentinel_credentials()
    stored = settings_json(resolved)
    covered = non_secret_settings(resolved)

    for name, sentinel in CREDENTIAL_SENTINELS.items():
        assert name not in covered, f"{name} is inside the mapping the fingerprint covers"
        assert sentinel not in stored, f"{name}'s value is in runs.settings_json: {stored}"
        assert sentinel not in json.dumps(covered)
    # The fingerprint is the SHA-256 of exactly that string (settings.settings_json's contract),
    # so proving the string is clean proves the hash's input is.
    assert settings_fingerprint(resolved) == hashlib.sha256(stored.encode("utf-8")).hexdigest()


def test_no_credential_survives_a_rendered_settings_object() -> None:
    """``repr``, ``str`` and ``model_dump`` are the three ways a settings object reaches a log
    line, an error message, or a page; ``SecretStr`` masks the value in all three."""
    rendered = (
        f"{(resolved := _with_sentinel_credentials())!r} {resolved!s} {resolved.model_dump()}"
    )
    for name, sentinel in CREDENTIAL_SENTINELS.items():
        assert sentinel not in rendered, f"{name}'s value survives being rendered"


def test_fingerprint_changes_when_budget_changes(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = settings_fingerprint(settings)
    monkeypatch.setenv("THREADDIGEST_STATIC__BUDGET__PER_RUN_REQUESTS", "7")
    assert settings_fingerprint(Settings()) != before


def test_user_agent_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THREADDIGEST_REDDIT_USERNAME", "wes")
    monkeypatch.setenv("THREADDIGEST_STATIC__USER_AGENT_APP_ID", "com.example.miner")
    assert user_agent(Settings(), "1.2.3") == "python:com.example.miner:v1.2.3 (by /u/wes)"
