"""Settings: precedence, strictness, fingerprint, and user agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import SecretStr, ValidationError

from insightminer.settings import (
    Settings,
    default_settings_file,
    settings_fingerprint,
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


def test_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_value = _shipped_yaml()["budget"]["per_run_requests"]
    assert yaml_value != 7
    monkeypatch.setenv("INSIGHTMINER_STATIC__BUDGET__PER_RUN_REQUESTS", "7")

    assert Settings().static.budget.per_run_requests == 7


def test_yaml_overrides_nothing_but_supplies_static_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data = _shipped_yaml()
    data["budget"]["per_run_requests"] = 42
    monkeypatch.setenv("INSIGHTMINER_SETTINGS_FILE", str(_write_yaml(tmp_path / "s.yaml", data)))

    resolved = Settings()

    assert resolved.static.budget.per_run_requests == 42
    assert resolved.settings_file == (tmp_path / "s.yaml").resolve()


def test_defaults_apply_when_env_and_yaml_are_silent(settings: Settings) -> None:
    assert settings.reddit_client_id == ""
    assert settings.reddit_client_secret.get_secret_value() == ""
    assert settings.reddit_username == ""
    assert settings.ui_password is None


def test_env_supplies_operator_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTMINER_REDDIT_USERNAME", "wes")
    monkeypatch.setenv("INSIGHTMINER_REDDIT_CLIENT_SECRET", "hunter2")
    monkeypatch.setenv("INSIGHTMINER_UI_PASSWORD", "open-sesame")

    resolved = Settings()

    assert resolved.reddit_username == "wes"
    assert resolved.reddit_client_secret.get_secret_value() == "hunter2"
    assert isinstance(resolved.ui_password, SecretStr)
    assert resolved.ui_password.get_secret_value() == "open-sesame"
    rendered = f"{resolved!r} {resolved!s} {resolved.model_dump()}"
    assert "hunter2" not in rendered
    assert "open-sesame" not in rendered


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


def test_budget_above_hard_cap_is_rejected(tmp_path: Path) -> None:
    data = _shipped_yaml()
    data["budget"]["per_run_requests"] = data["budget"]["hard_cap"] + 1
    with pytest.raises(ValidationError, match="hard_cap"):
        Settings(settings_file=_write_yaml(tmp_path / "s.yaml", data))


def test_fingerprint_ignores_secrets(settings: Settings) -> None:
    a = Settings(reddit_client_secret="a", ui_password="p1")
    b = Settings(reddit_client_secret="b", ui_password="p2")
    assert settings_fingerprint(a) == settings_fingerprint(b) == settings_fingerprint(settings)
    assert len(settings_fingerprint(a)) == 64


def test_fingerprint_changes_when_budget_changes(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = settings_fingerprint(settings)
    monkeypatch.setenv("INSIGHTMINER_STATIC__BUDGET__PER_RUN_REQUESTS", "7")
    assert settings_fingerprint(Settings()) != before


def test_user_agent_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTMINER_REDDIT_USERNAME", "wes")
    monkeypatch.setenv("INSIGHTMINER_STATIC__USER_AGENT_APP_ID", "com.example.miner")
    assert user_agent(Settings(), "1.2.3") == "python:com.example.miner:v1.2.3 (by /u/wes)"
