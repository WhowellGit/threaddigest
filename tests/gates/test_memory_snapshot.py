"""Positive controls for ``tools/memory_snapshot.py``: the memory snapshot's three guarantees.

Birth incidents, all from the earlier project and all about the same asset -- Claude Code's
auto-memory, which lives outside git at a path-keyed location and cannot be regenerated from
the tree:

* **KI-226**: an export mirrored deletions, so deleting a memory file upstream deleted it from
  the backup as well and the only surviving copy went with it ("the memory system ate the
  memory"). ``test_a_deletion_in_live_memory_never_deletes_from_the_snapshot`` is that control.
* **A restore that only counted.** The restore path printed a copy count and never checked the
  result, so an incomplete restore and a complete one printed the same thing. The controls here
  replace :func:`tools.memory_snapshot.copy_file` with a copy that reports success and writes
  the wrong bytes -- the shape of that failure -- and require export and restore to go red.
* **An index nobody could follow.** 28 index links pointed at deleted files and 127 of 166
  files were reachable only through a second-tier index, so most of the memory had been written
  but could not be recalled. ``check`` must report unreachable files, dangling links, an
  over-budget index, and a broken frontmatter contract, each as its own finding.

Every test builds a memory directory under ``tmp_path``, and every invocation passes both
``--memory-dir`` and ``--snapshot-dir``. No test reads, copies or writes the real live memory:
a suite that touched it would be the incident it is guarding against.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tools import memory_snapshot as ms

INDEX = ms.INDEX_NAME


def topic(name: str, kind: str = "feedback", description: str = "why it matters") -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\nmetadata:\n  type: {kind}\n---\n\nbody\n"
    )


def live_memory(root: Path) -> Path:
    """A small, clean memory directory: an index plus the two topic files it links."""
    memory = root / "live" / "memory"
    memory.mkdir(parents=True)
    (memory / "user-wes.md").write_text(topic("user-wes", "user"), encoding="utf-8")
    (memory / "feedback-style.md").write_text(topic("feedback-style"), encoding="utf-8")
    (memory / INDEX).write_text(
        "- [Wes working style](user-wes.md) — enforcement over trust\n"
        "- [Communication style](feedback-style.md) — clarity over brevity\n",
        encoding="utf-8",
    )
    return memory


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    """Drive the CLI the way ``make`` does, and return its exit code with its printed output."""
    code = ms.main(list(argv))
    return code, capsys.readouterr().out


def dirs(memory: Path, snapshot: Path) -> list[str]:
    return ["--memory-dir", str(memory), "--snapshot-dir", str(snapshot)]


def corrupting_copy(source: Path, destination: Path) -> None:
    """A copy that reports success and writes the wrong bytes."""
    destination.write_bytes(source.read_bytes() + b"corrupted")


# --------------------------------------------------------------------------------------
# KI-226: add-or-update only
# --------------------------------------------------------------------------------------
@pytest.mark.gate
def test_a_deletion_in_live_memory_never_deletes_from_the_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"
    flags = dirs(memory, snapshot)

    code, out = run(capsys, *flags, "export")
    assert code == 0, out
    assert "export added 3, updated 0, unchanged 0, live-missing 0" in out
    kept = (snapshot / "feedback-style.md").read_bytes()

    (memory / "feedback-style.md").unlink()
    (memory / INDEX).write_text(
        "- [Wes working style](user-wes.md) — enforcement over trust\n", encoding="utf-8"
    )

    code, out = run(capsys, *flags, "export")
    assert code == 0, out
    assert (snapshot / "feedback-style.md").read_bytes() == kept
    assert "memory: live-missing feedback-style.md (kept in the snapshot, never deleted)" in out
    assert "export added 0, updated 1, unchanged 1, live-missing 1" in out


def test_a_live_missing_file_is_reported_but_is_not_a_change_diff_would_make(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"
    flags = dirs(memory, snapshot)
    assert run(capsys, *flags, "export")[0] == 0
    (memory / "feedback-style.md").unlink()

    code, out = run(capsys, *flags, "diff")

    assert code == 0, out
    assert "memory: live-missing feedback-style.md" in out
    assert "diff add 0, update 0, unchanged 2, live-missing 1" in out


def test_diff_is_red_when_the_snapshot_is_behind_live_memory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"
    flags = dirs(memory, snapshot)
    assert run(capsys, *flags, "diff")[0] == 1, "an empty snapshot must not look clean"
    assert run(capsys, *flags, "export")[0] == 0

    code, out = run(capsys, *flags, "diff")
    assert code == 0
    assert out == f"memory: diff add 0, update 0, unchanged 3, live-missing 0 -> {snapshot}\n"

    (memory / "user-wes.md").write_text(topic("user-wes", "user", "edited"), encoding="utf-8")
    code, out = run(capsys, *flags, "diff")
    assert code == 1
    assert "memory: diff would update user-wes.md" in out


# --------------------------------------------------------------------------------------
# copying is not restoring: both paths verify completeness byte-for-byte
# --------------------------------------------------------------------------------------
@pytest.mark.gate
def test_export_is_red_when_a_destination_byte_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"
    monkeypatch.setattr(ms, "copy_file", corrupting_copy)

    code, out = run(capsys, *dirs(memory, snapshot), "export")

    assert code == 1, out
    assert "memory: verify bytes differ at destination: user-wes.md" in out
    assert "memory: export FAILED verification: 3 of 3 files" in out


@pytest.mark.gate
def test_export_is_red_when_one_file_never_arrives(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"

    def skip_one(source: Path, destination: Path) -> None:
        if source.name != "feedback-style.md":
            shutil.copy2(source, destination)

    monkeypatch.setattr(ms, "copy_file", skip_one)

    code, out = run(capsys, *dirs(memory, snapshot), "export")

    assert code == 1, out
    assert "memory: verify missing at destination: feedback-style.md" in out
    assert "memory: export FAILED verification: 1 of 3 files" in out


def test_restore_copies_the_snapshot_and_verifies_completeness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"
    flags = dirs(memory, snapshot)
    assert run(capsys, *flags, "export")[0] == 0
    target = tmp_path / "restored"

    code, out = run(capsys, *flags, "restore", "--to", str(target))

    assert code == 0, out
    assert f"memory: restore verified 3 files byte-for-byte at {target}" in out
    assert sorted(p.name for p in target.iterdir()) == [INDEX, "feedback-style.md", "user-wes.md"]
    assert (target / INDEX).read_bytes() == (memory / INDEX).read_bytes()


@pytest.mark.gate
def test_restore_is_red_when_a_destination_byte_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"
    flags = dirs(memory, snapshot)
    assert run(capsys, *flags, "export")[0] == 0
    monkeypatch.setattr(ms, "copy_file", corrupting_copy)

    code, out = run(capsys, *flags, "restore", "--to", str(tmp_path / "restored"))

    assert code == 1, out
    assert "memory: restore FAILED verification: 3 of 3 files" in out


@pytest.mark.gate
def test_restore_refuses_the_live_memory_directory_without_yes_live(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"
    flags = dirs(memory, snapshot)
    assert run(capsys, *flags, "export")[0] == 0
    (memory / "feedback-style.md").unlink()

    code, out = run(capsys, *flags, "restore", "--to", str(memory))

    assert code == 2, out
    assert out == (
        f"memory: refusing to restore into the live memory directory {memory} without --yes-live\n"
    )
    assert not (memory / "feedback-style.md").exists(), "a refusal must not copy anything"

    code, out = run(capsys, *flags, "restore", "--to", str(memory), "--yes-live")
    assert code == 0, out
    assert (memory / "feedback-style.md").is_file()


def test_restore_says_so_when_there_is_no_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    snapshot = tmp_path / "memory-snapshot"

    code, out = run(capsys, *dirs(memory, snapshot), "restore", "--to", str(tmp_path / "restored"))

    assert (code, out) == (1, f"memory: no snapshot directory at {snapshot}\n")


# --------------------------------------------------------------------------------------
# the index is the recall mechanism
# --------------------------------------------------------------------------------------
def test_check_is_green_on_a_clean_memory_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The negative control: without it every assertion below could pass vacuously."""
    memory = live_memory(tmp_path)
    size = len((memory / INDEX).read_bytes())

    code, out = run(capsys, *dirs(memory, tmp_path / "memory-snapshot"), "check")

    assert code == 0, out
    assert out == (
        f"memory: check OK; 2 topic files, 2 index links, index 2 lines / {size} bytes "
        f"(budget {ms.INDEX_MAX_LINES} / {ms.INDEX_MAX_BYTES})\n"
    )


@pytest.mark.gate
def test_check_reports_unreachable_dangling_over_budget_and_broken_frontmatter(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    (memory / "project-orphan.md").write_text(topic("project-orphan", "project"), encoding="utf-8")
    (memory / "feedback-style.md").write_text(topic("feedback-style", "bogus"), encoding="utf-8")
    filler = "".join(f"<!-- filler {n} -->\n" for n in range(ms.INDEX_MAX_LINES))
    (memory / INDEX).write_text(
        "- [Wes working style](user-wes.md) — enforcement over trust\n"
        "- [Communication style](feedback-style.md) — clarity over brevity\n"
        "- [Deleted](feedback-gone.md) — this file no longer exists\n" + filler,
        encoding="utf-8",
    )

    code, out = run(capsys, *dirs(memory, tmp_path / "memory-snapshot"), "check")
    findings = out.splitlines()

    assert code == 1
    assert findings[:-1] == [
        f"memory: index over budget: {ms.INDEX_MAX_LINES + 3} lines (max {ms.INDEX_MAX_LINES})",
        f"memory: dangling {INDEX}:3 -> feedback-gone.md (no such file)",
        f"memory: unreachable project-orphan.md (no {INDEX} line links it)",
        'memory: frontmatter feedback-style.md: metadata.type "bogus" not in '
        "{feedback, project, reference, user}",
    ]
    assert findings[-1].startswith("memory: check FAILED - 4 findings; 3 topic files, 3 index")


@pytest.mark.gate
def test_check_reports_an_index_over_the_byte_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    padding = "x" * (ms.INDEX_MAX_BYTES // 20)
    (memory / INDEX).write_text(
        "".join(
            f"- [Wes working style](user-wes.md) — {padding}\n"
            f"- [Communication style](feedback-style.md) — {padding}\n"
            for _ in range(10)
        ),
        encoding="utf-8",
    )

    code, out = run(capsys, *dirs(memory, tmp_path / "memory-snapshot"), "check")

    assert code == 1
    assert f"bytes (max {ms.INDEX_MAX_BYTES})" in out
    assert "lines (max" not in out, "20 lines is inside the line budget"


@pytest.mark.gate
def test_check_reports_every_missing_part_of_the_frontmatter_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    memory = live_memory(tmp_path)
    (memory / "user-wes.md").write_text("no frontmatter at all\n", encoding="utf-8")
    (memory / "feedback-style.md").write_text("---\nname: x\n---\nbody\n", encoding="utf-8")

    code, out = run(capsys, *dirs(memory, tmp_path / "memory-snapshot"), "check")

    assert code == 1
    assert "memory: frontmatter user-wes.md: no closed --- frontmatter block" in out
    assert (
        "memory: frontmatter feedback-style.md: missing description; missing metadata.type" in out
    )


@pytest.mark.gate
def test_check_reports_a_memory_directory_with_no_index(tmp_path: Path) -> None:
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "user-wes.md").write_text(topic("user-wes", "user"), encoding="utf-8")

    findings, summary = ms.check_memory(memory)

    assert findings == [
        f"memory: index missing: no {INDEX} in {memory}",
        f"memory: unreachable user-wes.md (no {INDEX} line links it)",
    ]
    assert summary.startswith("memory: check FAILED - 2 findings; 1 topic files, 0 index links")


# --------------------------------------------------------------------------------------
# no live memory directory is a state, not a skip
# --------------------------------------------------------------------------------------
def test_no_live_memory_directory_prints_the_exact_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "gone" / "memory"
    flags = dirs(missing, tmp_path / "memory-snapshot")
    expected = f"memory: no live memory directory at {missing}\n"

    assert run(capsys, *flags, "check") == (0, expected)
    assert run(capsys, *flags, "diff") == (0, expected)
    assert run(capsys, *flags, "export") == (
        1,
        expected + "memory: export FAILED: nothing to snapshot\n",
    ), "export was asked to snapshot something and did not: silence there is the old bug"


# --------------------------------------------------------------------------------------
# the path key: the whole asset is addressed by it
# --------------------------------------------------------------------------------------
def test_the_memory_directory_follows_the_path_slug_convention() -> None:
    """``[user]`` is the repo's home-path placeholder; a literal home here is an identifier."""
    repo = Path("/Users/[user]/repos/insightminer")
    slug = "-Users-[user]-repos-insightminer"

    assert ms.slug_for(repo) == slug
    assert ms.memory_dir_for(repo) == Path.home() / ".claude" / "projects" / slug / "memory"


def worktree_of(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "repo"
    gitdir = main / ".git" / "worktrees" / "w"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    return main, worktree


def test_a_worktree_is_keyed_to_the_main_checkout_not_to_the_worktree(tmp_path: Path) -> None:
    """Agents work in worktrees; keying their memory to one would report "none" every time."""
    main, worktree = worktree_of(tmp_path)

    assert ms.main_checkout(worktree) == main.resolve()
    assert ms.main_checkout(main) == main.resolve()


@pytest.mark.gate
def test_the_snapshot_defaults_into_this_tree_not_into_the_main_checkout(tmp_path: Path) -> None:
    """Caught live: the first export from a worktree wrote its snapshot into the main checkout.

    The memory is shared with the main checkout; the snapshot is a committed file and must land
    in the tree being worked on, or a worktree's export lands outside its own branch.
    """
    main, worktree = worktree_of(tmp_path)

    memory, snapshot = ms.default_paths(worktree)

    assert memory == ms.memory_dir_for(main.resolve())
    assert snapshot == worktree / ms.SNAPSHOT_DIRNAME
    assert ms.default_paths(main) == (ms.memory_dir_for(main.resolve()), main / "memory-snapshot")
