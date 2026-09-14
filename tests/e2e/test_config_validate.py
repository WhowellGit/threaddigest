"""``config validate`` end to end: the CLI half of panel P2-8 (design-round5.md section
11.4, section 12.5).

The command is on RL-04's exclusion list and ``tests/gates/test_mutating_commands.py``
proves it writes nothing and exits 0. What matters here is the other direction: that a
misspelled ``INSIGHTMINER_*`` variable makes it *fail*, at the documented exit 78, with the
variable named in the output -- the whole point of the validator, since the CLI's stderr is
where an operator finds out about a typo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from insightminer import cli


def test_config_validate_accepts_recognised_variables(
    cli_runner, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A nested static override and a sanctioned non-field variable, both recognised."""
    monkeypatch.setenv("INSIGHTMINER_STATIC__BUDGET__PER_RUN_REQUESTS", "7")
    monkeypatch.setenv("INSIGHTMINER_UI_URL", "http://127.0.0.1:8765")

    result = cli_runner.invoke(cli.app, ["config", "validate"])

    assert result.exit_code == 0, result.output
    assert "settings: ok" in result.output
    assert str(isolated_data_dir) in result.output


def test_config_validate_refuses_an_unknown_variable_naming_it(
    cli_runner, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 78 (section 12.5's config/precondition code) with the variable in the output.

    Before the validator this exited 0 and printed the default data directory: nothing in
    the system ever mentioned the typo. A *nested* typo whose first segment does name a field
    (``INSIGHTMINER_STATIC__BUDGET__PER_RUN_REQUESTZ``) was already refused by
    ``extra="forbid"``, naming the key rather than the variable; that half is pinned in
    ``tests/unit/test_settings.py``.
    """
    monkeypatch.setenv("INSIGHTMINER_DATA_DIRR", str(isolated_data_dir))

    result = cli_runner.invoke(cli.app, ["config", "validate"])

    assert result.exit_code == 78, result.output
    assert "INSIGHTMINER_DATA_DIRR" in result.output


def test_config_validate_never_echoes_a_secret_it_refused(
    cli_runner, isolated_data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``hide_input_in_errors``: a refused load's message carries no input values.

    ``cli`` echoes ``str(exc)`` for a settings failure and ``doctor`` quotes the same string
    into its ``settings_valid`` row. Pydantic's default rendering appends the offending input
    -- for a model-level validator, the whole raw input mapping, in which ``ui_password`` and
    ``reddit_client_secret`` are still plain strings. "Never log credentials" is
    unconditional, so this asserts the refusal path with real-looking secrets set.
    """
    monkeypatch.setenv("INSIGHTMINER_UI_PASSWORD", "open-sesame-1234")
    monkeypatch.setenv("INSIGHTMINER_REDDIT_CLIENT_SECRET", "hunter2-secret-value")
    monkeypatch.setenv("INSIGHTMINER_TYPO", "1")

    result = cli_runner.invoke(cli.app, ["config", "validate"])

    assert result.exit_code == 78, result.output
    assert "INSIGHTMINER_TYPO" in result.output
    assert "open-sesame-1234" not in result.output
    assert "hunter2-secret-value" not in result.output
