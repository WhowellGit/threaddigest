"""Shared fixtures.

Data-directory isolation (docs/learnings rank 1, guard G19): every test runs with
``THREADDIGEST_DATA_DIR`` pointing at a fresh temp directory and with every other
``THREADDIGEST_*`` variable removed, so a developer's real ``.env`` values never reach a
test and the real ``data/`` directory is never written. ``Settings`` refuses the default
data directory while pytest is loaded, so a test that bypasses this fixture fails instead
of touching live data.

That fixture points the *settings* at a temp directory. It cannot stop code that never reads
the settings, and on 2026-09-17 the code panel proved the difference: a planted write to a
hard-coded path outside any data directory took 37 lines from the suite with every gate green
(finding C-3(c)). :func:`no_write_outside_the_data_dir` is the other half -- the autouse fixture
that wraps the open paths and fails the test on a write outside the allowed tree.

``fake`` / ``seeded`` / ``BASE`` live here (design-round5.md §2.2) rather than under
``tests/adapters/`` so ``tests/services/`` and ``tests/e2e/`` share the one scenario
builder instead of each package inventing its own. ``demo_fixture_path`` joins them for the
same reason: ``tests/e2e/`` and ``tests/gates/`` both collect from the demo corpus, and a
generated corpus must be built once per session, not once per package.
"""

from __future__ import annotations

import builtins
import io
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tools.make_demo_fixture import build_demo_fixture

from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.settings import Settings

ENV_PREFIX = "THREADDIGEST_"
BASE = 1_757_700_000  # 2025-09-12T18:40:00Z; seeded posts are spaced one minute apart from here
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the process at a fresh data directory and clear inherited settings."""
    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv(f"{ENV_PREFIX}DATA_DIR", str(data_dir))
    yield data_dir


# --- G19's second half: no write outside the data directory, from anywhere in the suite -------

#: Mode characters that open a file for writing. ``+`` is here because ``r+`` writes.
WRITE_MODE_CHARS = frozenset("wax+")
#: ``os.open`` flags that open a file for writing. ``O_RDONLY`` is 0, so a read matches none.
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

#: Repository directories the runner, the interpreter and the analysers write into *while a test
#: is running*, each gitignored and none able to hold an operator's data. The justification is
#: the point of the list: ``.build/`` is the harness's own scratch tree (the Makefile's
#: ``BUILD_DIR``, where the ratchet, coverage and code-health reports land, and the hook
#: ledgers); ``.hypothesis/`` is the example database the property tests write on every run;
#: the three caches are pytest's, ruff's and mypy's bookkeeping. Nothing else in the repository
#: may be opened for writing, ``data/`` and ``config/`` least of all.
ALLOWED_REPO_DIRS = (".build", ".hypothesis", ".pytest_cache", ".ruff_cache", ".mypy_cache")
#: Coverage's data file at the repository root, which parallel mode suffixes with host and pid.
ALLOWED_REPO_PREFIXES = (".coverage",)


def opens_for_writing(mode: object) -> bool:
    return isinstance(mode, str) and bool(WRITE_MODE_CHARS & set(mode))


def write_outside(target: object, allowed: tuple[Path, ...]) -> str | None:
    """``None`` when ``target`` may be opened for writing; the finding to fail with otherwise.

    A pure function so the positive controls can state the rule directly (G19's own controls
    construct the bad state rather than trusting the fixture to have been installed).

    An integer is a file descriptor a caller already holds and is nobody's path. ``__pycache__``
    entries and ``.pyc`` files are the interpreter compiling the tree it was asked to import;
    they arrive through the frozen ``posix`` module rather than through ``os.open``, so this arm
    is belt to that brace. Symlinks are resolved only when the fast comparison says "outside",
    because ``$TMPDIR`` is a symlink on macOS and ``Path.resolve`` is a syscall per open.
    """
    if not isinstance(target, str | bytes | os.PathLike):
        return None
    path = Path(os.fsdecode(target) if isinstance(target, bytes) else os.fspath(target))
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    path = Path(os.path.normpath(path))
    if path == Path(os.devnull) or "__pycache__" in path.parts or path.suffix == ".pyc":
        return None
    if path.parent == REPO_ROOT and path.name.startswith(ALLOWED_REPO_PREFIXES):
        return None
    roots = (*allowed, *(REPO_ROOT / name for name in ALLOWED_REPO_DIRS))
    if any(path.is_relative_to(root) for root in roots):
        return None
    resolved = path.resolve()
    if any(resolved.is_relative_to(root) for root in roots):
        return None
    return (
        f"write outside the data directory: {resolved}\n"
        "Irreversible rule 1: a test writes under its own tmp_path or the resolved "
        "THREADDIGEST_DATA_DIR, and nowhere else. Allowed roots: "
        + ", ".join(str(root) for root in roots)
    )


@pytest.fixture(autouse=True)
def no_write_outside_the_data_dir(
    isolated_data_dir: Path,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[str]]:
    """Fail any test that opens a path for writing outside its own temp tree (G19, C-3(c)).

    Depends on :func:`isolated_data_dir` so it is installed *after* the environment is set and
    the allowed data directory is known.

    Covers the Python-level open paths: ``builtins.open`` (which is ``io.open``, and therefore
    also ``Path.open``, ``Path.write_text``, ``Path.write_bytes`` and ``logging``'s file
    handler), ``Path.open`` again in its own right so a future CPython that stops routing
    through ``io`` is still watched, and ``os.open`` (which is ``tempfile``'s and
    ``shutil``'s). SQLite's file opens happen inside the C library and never pass through any
    of them; those are G19's original half, held by the data-directory seam in ``Settings``.
    Writes a *subprocess* makes are its own process's business and are out of scope, which is
    why the run-level snapshot in ``tests/e2e/test_data_dir_writes.py`` stays.

    The violation is raised through ``pytest.fail``, whose exception derives from
    ``BaseException`` and so cannot be swallowed by an ``except Exception`` in the code under
    test; the list is yielded and re-checked at teardown in case something swallows even that.
    """
    allowed = (tmp_path_factory.getbasetemp().resolve(), isolated_data_dir.resolve())
    violations: list[str] = []
    real_open = builtins.open
    real_os_open = os.open
    real_path_open = Path.open

    def check(target: object, writing: bool) -> None:
        if not writing:
            return
        finding = write_outside(target, allowed)
        if finding is None:
            return
        violations.append(finding)
        pytest.fail(finding, pytrace=False)

    def guarded_open(file: Any, mode: Any = "r", *args: Any, **kwargs: Any) -> Any:
        check(file, opens_for_writing(mode))
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path: Any, flags: Any, *args: Any, **kwargs: Any) -> Any:
        check(path, bool(flags & WRITE_FLAGS))
        return real_os_open(path, flags, *args, **kwargs)

    def guarded_path_open(self: Path, mode: Any = "r", *args: Any, **kwargs: Any) -> Any:
        check(self, opens_for_writing(mode))
        return real_path_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(os, "open", guarded_os_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    yield violations
    assert not violations, "\n".join(violations)


@pytest.fixture
def settings(isolated_data_dir: Path) -> Settings:
    """Settings resolved from the isolated environment and the shipped settings.yaml."""
    resolved = Settings()
    assert resolved.data_dir == isolated_data_dir.resolve()
    return resolved


@pytest.fixture(scope="session")
def demo_fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The demo corpus (every seeded subreddit, ~240 posts, one sticky, one crosspost, one
    unknown ``post_hint``, one deleted post -- section 11.7), **generated** into a session
    temp directory by ``tools/make_demo_fixture.py``.

    It is not a file in the repository. A generated corpus that is also committed is a
    second source of truth that drifts from its generator, and this one was 13,586 lines of
    JSON nobody read. The generator is the definition; ``make fixture`` writes the same
    bytes to the git-ignored ``data/demo.json`` for ``make run``.

    Session-scoped on purpose: every consumer takes it read-only (the CLI loads it, no test
    writes to it), so building it once is ~240 posts of work per session instead of per
    test. Its subreddit names come from the generator's ``SOURCES``, which
    ``tests/tools/test_make_demo_fixture.py`` holds to ``config/seed.yaml``.
    """
    return build_demo_fixture(tmp_path_factory.mktemp("demo-fixture") / "demo.json")


@pytest.fixture
def fake() -> Iterator[FakeRedditGateway]:
    """An empty scenario builder.

    At teardown every planted failure must have fired: a scenario that never reached its
    injected fault is a red, not a silent pass (panel-ingest rule 4).
    """
    gateway = FakeRedditGateway()
    yield gateway
    gateway.assert_no_unconsumed_injections()


@pytest.fixture
def seeded(fake: FakeRedditGateway) -> FakeRedditGateway:
    """r/premiere with 250 live posts (``post 0`` oldest ... ``post 249`` newest)."""
    fake.add_subreddit("premiere", subscribers=120_000)
    for i in range(250):
        fake.add_post(
            "premiere",
            title=f"post {i}",
            selftext=f"body {i}",
            author=f"u{i % 7}",
            created_utc=BASE + i * 60,
        )
    return fake
