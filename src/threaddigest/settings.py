"""Runtime settings for Thread Digest.

Two kinds of settings live here:

* **Operator settings** (credentials, ``data_dir``, the UI password) are fields on
  :class:`Settings` and come from ``THREADDIGEST_*`` environment variables.
* **Static settings** (budget, comments, revisit ladder, reconcile, retention, run,
  user agent app id, display timezone) mirror ``config/settings.yaml`` key for key and
  land in ``Settings.static``.

Precedence, highest first:

1. Constructor keyword arguments (tests only; production code never passes them).
2. Environment variables ``THREADDIGEST_<FIELD>``. Nested static keys use ``__`` as the
   path separator, e.g. ``THREADDIGEST_STATIC__BUDGET__PER_RUN_REQUESTS=500``.
3. ``config/settings.yaml`` (path overridable with ``THREADDIGEST_SETTINGS_FILE``); this
   file is the *defaults layer* for every static key, so every static key is required
   there and none has a fallback in code.
4. Field defaults declared on :class:`Settings` for operator settings (empty
   credentials, ``<repo>/data``, no UI password).

A misspelled key fails at construction instead of silently doing nothing, and it takes
two mechanisms to make that true of both layers:

* ``extra="forbid"`` on every model rejects an unknown key in ``config/settings.yaml``
  and an unknown constructor argument. It does **not** see environment variables:
  pydantic-settings matches ``THREADDIGEST_*`` against the field names and simply
  ignores every variable that matches nothing, so ``extra="forbid"`` alone lets
  ``THREADDIGEST_DATA_DIRR=/tmp/x`` pass as silently as if it were never set.
* :func:`unknown_environment_variables` closes that gap: a validator refuses to build
  :class:`Settings` while any ``THREADDIGEST_*`` variable names no field of this model
  (nested static keys included), naming the offenders, so ``config validate`` and every
  command exit 78 on a typo rather than running with a default the operator thought
  they had overridden. The two variables that are deliberately not fields are listed in
  :data:`SANCTIONED_ENVIRONMENT_VARIABLES`.

No ``.env`` file is read implicitly: the launcher exports it
(``uv run --env-file .env ...``) so tests never inherit real credentials.

Data-directory isolation (learning rank 1): when pytest is loaded (``pytest`` in
``sys.modules``, or ``PYTEST_CURRENT_TEST`` set for child processes) and the resolved
``data_dir`` is the real default directory, construction raises :class:`DataDirRefused`
before anything touches the filesystem, unless ``THREADDIGEST_ALLOW_REAL_DATA_DIR`` is
set. The autouse fixture in ``tests/conftest.py`` points ``THREADDIGEST_DATA_DIR`` at a
temp directory, so ordinary tests never see the refusal.

Settings are read from the settings object at call time; never capture a value at
import.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

__all__ = [
    "SANCTIONED_ENVIRONMENT_VARIABLES",
    "BudgetSettings",
    "CommentsSettings",
    "DataDirRefused",
    "ReconcileSettings",
    "RetentionSettings",
    "RunSettings",
    "Settings",
    "StaticSettings",
    "TierMaxAgeHours",
    "default_data_dir",
    "default_settings_file",
    "non_secret_settings",
    "settings_fingerprint",
    "unknown_environment_variables",
    "user_agent",
]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALLOW_REAL_DATA_DIR = "THREADDIGEST_ALLOW_REAL_DATA_DIR"
_STATIC_KEY = "static"

#: The ``THREADDIGEST_*`` variables that are deliberately **not** fields of
#: :class:`Settings`, so the strict scan below must not reject them. Each is read by
#: something else and each is documented where it is read; anything not a field and not
#: here is a typo.
SANCTIONED_ENVIRONMENT_VARIABLES: Final[frozenset[str]] = frozenset({
    # The data-directory refusal's opt-in, read from `os.environ` a few lines below rather
    # than declared as a field (it is a test/ops escape hatch, not a setting).
    _ALLOW_REAL_DATA_DIR,
    # `deploy/launchd/run.sh`'s health-check URL: the launchd job's own variable, exported
    # to the job from `.env` and never read by this module.
    "THREADDIGEST_UI_URL",
})  # fmt: skip


class DataDirRefusedError(RuntimeError):
    """Raised when a test process would use the real data directory."""


# The plan and the guards ledger name the refusal ``DataDirRefused``; the class carries the
# conventional suffix and this alias keeps the documented name importable.
DataDirRefused = DataDirRefusedError


def default_data_dir() -> Path:
    """The data directory used when ``THREADDIGEST_DATA_DIR`` is not set."""
    return _REPO_ROOT / "data"


def default_settings_file() -> Path:
    """The static settings file used when ``THREADDIGEST_SETTINGS_FILE`` is not set."""
    return _REPO_ROOT / "config" / "settings.yaml"


def _pytest_is_loaded() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BudgetSettings(_Strict):
    per_run_requests: int = Field(gt=0)
    hard_cap: int = Field(gt=0, le=5000)
    reserve: int = Field(ge=0)

    @model_validator(mode="after")
    def _per_run_within_cap(self) -> BudgetSettings:
        if self.per_run_requests > self.hard_cap:
            msg = (
                f"budget.per_run_requests {self.per_run_requests} exceeds hard_cap {self.hard_cap}"
            )
            raise ValueError(msg)
        return self


class CommentsSettings(_Strict):
    replace_more_limit: int = Field(ge=0)
    per_post_expansion_cap: int = Field(ge=0)


class TierMaxAgeHours(_Strict):
    under_30d: int = Field(gt=0)
    under_1y: int = Field(gt=0)
    older: int = Field(gt=0)


class ReconcileSettings(_Strict):
    full_sweep_every_hours: int = Field(gt=0)
    tier_max_age_hours: TierMaxAgeHours


class RetentionSettings(_Strict):
    backups_days: int = Field(gt=0)
    exports_days: int = Field(gt=0)
    raw_rejects_days: int = Field(gt=0)


class RunSettings(_Strict):
    stale_after_minutes: int = Field(gt=0)
    wall_clock_ceiling_hours: int = Field(gt=0)


class StaticSettings(_Strict):
    """Mirror of ``config/settings.yaml``; every key is required there."""

    user_agent_app_id: str = Field(min_length=1)
    display_timezone: str = Field(min_length=1)
    budget: BudgetSettings
    comments: CommentsSettings
    revisit_ladder_days: list[int] = Field(min_length=1)
    reconcile: ReconcileSettings
    retention: RetentionSettings
    run: RunSettings

    @field_validator("revisit_ladder_days")
    @classmethod
    def _ladder_is_increasing(cls, value: list[int]) -> list[int]:
        if any(b <= a for a, b in zip(value, value[1:], strict=False)) or value[0] <= 0:
            msg = f"revisit_ladder_days must be strictly increasing positive days, got {value}"
            raise ValueError(msg)
        return value

    @field_validator("display_timezone")
    @classmethod
    def _resolvable_zone(cls, value: str) -> str:
        """KI-011: the digest resolves ``display_timezone`` as ``UTC`` or an IANA name, so a
        value it cannot load (the shipped ``local`` was one) must fail here at settings load,
        not at the first digest weeks into M1d. Validated with ``zoneinfo`` directly rather
        than importing ``core.digest``, which would pull jinja2 into every settings load."""
        if value == "UTC":
            return value
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = (
                f"display_timezone {value!r} is not 'UTC' or a known IANA zone "
                "(e.g. America/New_York)"
            )
            raise ValueError(msg) from exc
        return value


class _YamlStaticSource(PydanticBaseSettingsSource):
    """Loads ``config/settings.yaml`` into the ``static`` field.

    Sits below init kwargs and environment variables in precedence, so env vars override
    yaml values key by key (pydantic-settings deep-merges nested dictionaries).
    """

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def _settings_file(self) -> Path:
        current = self.current_state.get("settings_file")
        if current is None:
            return default_settings_file()
        return Path(str(current)).expanduser()

    def __call__(self) -> dict[str, Any]:
        path = self._settings_file()
        if not path.is_file():
            return {}
        with path.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            msg = f"{path}: top level must be a mapping, got {type(loaded).__name__}"
            raise TypeError(msg)
        return {_STATIC_KEY: loaded}


class Settings(BaseSettings):
    """Resolved settings; see the module docstring for precedence and isolation rules."""

    model_config = SettingsConfigDict(
        env_prefix="THREADDIGEST_",
        env_nested_delimiter="__",
        env_ignore_empty=True,
        extra="forbid",
        frozen=True,
        # A ``ValidationError`` from this model is echoed to stderr by ``cli`` and quoted in
        # ``doctor``'s ``settings_valid`` row, and pydantic's default error rendering carries
        # the offending *input* -- for a model-level validator, the whole raw input mapping,
        # secrets included (``ui_password`` and ``reddit_client_secret`` arrive as plain
        # strings and are only wrapped in ``SecretStr`` afterwards). "Never log credentials"
        # is unconditional, so the inputs stay out of the message; every error still names
        # its field, which is what the messages are read for.
        hide_input_in_errors=True,
    )

    reddit_client_id: str = ""
    reddit_client_secret: SecretStr = SecretStr("")
    reddit_username: str = ""
    data_dir: Path = Field(default_factory=default_data_dir)
    settings_file: Path = Field(default_factory=default_settings_file)
    ui_password: SecretStr | None = None
    static: StaticSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, _YamlStaticSource(settings_cls))

    @field_validator("data_dir", "settings_file")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @model_validator(mode="after")
    def _refuse_unknown_environment_variables(self) -> Settings:
        """A typo'd ``THREADDIGEST_*`` variable fails the load and is named in the message.

        ``extra="forbid"`` cannot do this: pydantic-settings never offers an unmatched
        environment variable to the model, so there is no extra key for it to forbid.
        """
        unknown = unknown_environment_variables()
        if unknown:
            msg = (
                f"unrecognised environment variable(s): {', '.join(unknown)}. "
                "Every THREADDIGEST_* variable must name a setting "
                f"(nested keys use `__`); sanctioned exceptions: "
                f"{', '.join(sorted(SANCTIONED_ENVIRONMENT_VARIABLES))}."
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _refuse_real_data_dir_under_pytest(self) -> Settings:
        if not _pytest_is_loaded() or os.environ.get(_ALLOW_REAL_DATA_DIR):
            return self
        if self.data_dir == default_data_dir().resolve():
            msg = (
                f"refusing to use the real data directory {self.data_dir} while pytest is "
                "loaded. Set THREADDIGEST_DATA_DIR to a temp directory (the autouse fixture "
                f"in tests/conftest.py does this) or set {_ALLOW_REAL_DATA_DIR}=1 to opt in."
            )
            raise DataDirRefused(msg)
        return self


def _nested_model(annotation: Any) -> type[BaseModel] | None:
    """The settings model an annotation carries (``static``), or ``None`` for a leaf field."""
    for candidate in (annotation, *get_args(annotation)):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _names_a_field(path: Sequence[str]) -> bool:
    """Does ``path`` (an env var's name, split on the nested delimiter) name a real field?

    Walks the model tree the way pydantic-settings resolves the variable, so
    ``static__budget__per_run_requests`` is known, ``static__budget__per_run_request`` is
    not, and ``data_dir__anything`` is not either -- a leaf field has nothing under it.
    """
    model: type[BaseModel] | None = Settings
    for part in path:
        if model is None:
            return False
        field = model.model_fields.get(part)
        if field is None:
            return False
        model = _nested_model(field.annotation)
    return True


def unknown_environment_variables(environ: Mapping[str, str] | None = None) -> list[str]:
    """Every ``THREADDIGEST_*`` variable in ``environ`` that names no setting, sorted.

    ``environ`` defaults to ``os.environ`` and is a parameter only so a caller can scan a
    mapping it is about to export (the launchd job's parsed ``.env``, M2's setup wizard)
    without mutating the process. Case is ignored and the nested delimiter is honoured,
    both read from ``Settings.model_config`` rather than respelled here, so a change to the
    prefix or the delimiter cannot leave this scan matching the old spelling.

    Emptiness is not an excuse: ``env_ignore_empty`` means an empty variable sets nothing,
    but an empty **misspelled** variable is still a misspelling and reporting it costs the
    operator nothing.
    """
    source = os.environ if environ is None else environ
    prefix = str(Settings.model_config.get("env_prefix") or "")
    delimiter = str(Settings.model_config.get("env_nested_delimiter") or "__")
    unknown: list[str] = []
    for name in source:
        upper = name.upper()
        if not upper.startswith(prefix) or upper in SANCTIONED_ENVIRONMENT_VARIABLES:
            continue
        rest = upper[len(prefix) :].lower()
        if not rest or not _names_a_field(rest.split(delimiter)):
            unknown.append(name)
    return sorted(unknown)


def _is_secret(field: FieldInfo) -> bool:
    annotation = field.annotation
    return annotation is SecretStr or SecretStr in get_args(annotation)


def _secret_field_names() -> set[str]:
    return {name for name, field in Settings.model_fields.items() if _is_secret(field)}


def non_secret_settings(settings: Settings) -> dict[str, Any]:
    """The resolved settings the fingerprint covers: every field except the ``SecretStr`` ones.

    One home for "the non-secret settings". :func:`settings_fingerprint` hashes exactly this
    mapping and the digest counts its leaves for the denominator of "settings changed since
    the last run", so the hash and the count can never disagree about what a setting is --
    and a second definition of "secret" cannot appear beside the structural one above.
    """
    return settings.model_dump(mode="json", exclude=_secret_field_names())


def settings_fingerprint(settings: Settings) -> str:
    """SHA-256 over the resolved non-secret settings, stable across key order.

    Every ``SecretStr`` field on :class:`Settings` is excluded structurally, so adding a
    new secret cannot leak into the fingerprint by omission.
    """
    payload = non_secret_settings(settings)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def user_agent(settings: Settings, version: str) -> str:
    """Reddit API user agent: ``python:<app_id>:v<version> (by /u/<username>)``."""
    return (
        f"python:{settings.static.user_agent_app_id}:v{version} (by /u/{settings.reddit_username})"
    )
