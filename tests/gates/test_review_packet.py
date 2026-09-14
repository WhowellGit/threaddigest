"""G52: an external review packet is the committed tree and nothing else.

``tools/review_packet.py`` is run the way the runbook runs it (a subprocess with the same
interpreter) against a throwaway git repository that plants what must never leave the machine:
a tracked secret, a data file, the earlier project's folder, a dated review report, and a
binary. The last control builds a packet from this repository's own HEAD and runs the imported
identifier scan over it, so the packet is proven clean by the same gate that keeps the tree
clean.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.gates.test_no_imported_identifiers import violations

pytestmark = pytest.mark.gate("G52")

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "review_packet.py"
TEMPLATE = "docs/reference/reviews/templates/external-deep-research.md"
CLAIMS = "docs/reference/reviews/templates/claims.md"

PLANTED: dict[str, str | bytes] = {
    "CLAUDE.md": "# agreement\n",
    "docs/PLAN.md": "# plan\n\n## Intent (read this first)\n\nThe intent paragraph.\n\n## Next\n",
    TEMPLATE: "# brief for {project} at {commit} on {date}, packet {packet_hash}\n",
    CLAIMS: "# claims\n",
    "src/insightminer/thing.py": "def thing() -> int:\n    return 1\n",
    "tests/gates/test_gate.py": "def test_gate() -> None:\n    assert True\n",
    "tests/unit/test_thing.py": "def test_thing() -> None:\n    assert True\n",
    "tools/ratchet.py": "print('ratchet')\n",
    ".ratchets/tests.txt": "collected=2\n",
    ".claude/settings.json": '{"hooks": {}}\n',
    ".env": "REDDIT_CLIENT_SECRET=never-in-a-packet\n",
    "data/insightminer.db": "not really a database but must never be packed\n",
    "docs/reference/earlier-project-retrospectives/notes.md": "# from another system: keep out\n",
    "docs/reference/reviews/2026-01-01-prior-verdict.md": "# a prior verdict: keep out\n",
    "tests/fixtures/db/rev1.db": b"\x00\x01\x02binary",
    "src/insightminer/blob.bin": b"\xff\xfe\x00binary-in-src",
}


def git(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root),
        "GIT_AUTHOR_NAME": "packet-test",
        "GIT_AUTHOR_EMAIL": "packet-test@example.invalid",
        "GIT_COMMITTER_NAME": "packet-test",
        "GIT_COMMITTER_EMAIL": "packet-test@example.invalid",
    }
    proc = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env=env, text=True, timeout=60
    )
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for rel, content in PLANTED.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    git(root, "add", "-A", "-f")
    git(root, "commit", "-q", "-m", "baseline")
    return root


def run_tool(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        timeout=300,
    )


def test_a_packet_holds_only_the_allowlist_from_head(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "packet"
    proc = run_tool(repo, "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    packed = {entry["path"] for entry in manifest["files"]}
    assert "src/insightminer/thing.py" in packed
    assert "tests/gates/test_gate.py" in packed and "tests/unit/test_thing.py" in packed
    assert ".claude/settings.json" in packed and ".ratchets/tests.txt" in packed
    for never in (
        ".env",
        "data/insightminer.db",
        "docs/reference/earlier-project-retrospectives/notes.md",
        "docs/reference/reviews/2026-01-01-prior-verdict.md",
        "tests/fixtures/db/rev1.db",
    ):
        assert never not in packed, never
    assert manifest["skipped_binary"] == ["src/insightminer/blob.bin"]
    everything = "".join(
        (out / name).read_text(encoding="utf-8")
        for name in (
            "00-README.md",
            "01-QUERY.md",
            "1-documents.md",
            "2-harness.md",
            "3-source.md",
            "4-tests.md",
        )
    )
    for leak in ("never-in-a-packet", "must never be packed", "keep out"):
        assert leak not in everything, leak
    source_part = (out / "3-source.md").read_text(encoding="utf-8")
    assert "    1  def thing() -> int:" in source_part  # line numbers in the margin
    # hashes are real: every manifest entry matches the bytes written under tree/
    import hashlib

    for entry in manifest["files"]:
        digest = hashlib.sha256((out / "tree" / entry["path"]).read_bytes()).hexdigest()
        assert digest == entry["sha256"], entry["path"]
    commit = git(repo, "rev-parse", "HEAD").strip()
    assert manifest["commit"] == commit and manifest["working_tree"] == "clean"
    query = (out / "01-QUERY.md").read_text(encoding="utf-8")
    assert commit in query and manifest["packet_sha256"] in query and "{" not in query
    readme = (out / "00-README.md").read_text(encoding="utf-8")
    assert "The intent paragraph." in readme and commit[:12] in readme


def test_a_dirty_tree_is_refused(repo: Path, tmp_path: Path) -> None:
    (repo / "CLAUDE.md").write_text("# edited, not committed\n", encoding="utf-8")
    proc = run_tool(repo, "--out", str(tmp_path / "packet"))
    assert proc.returncode != 0
    assert "not clean" in proc.stderr
    assert not (tmp_path / "packet").exists()
    proc = run_tool(repo, "--out", str(tmp_path / "packet2"), "--allow-dirty")
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((tmp_path / "packet2" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["working_tree"] == "dirty"
    assert "dirty working tree" in (tmp_path / "packet2" / "00-README.md").read_text(
        encoding="utf-8"
    )
    # the content is still HEAD, not the uncommitted edit
    assert "# agreement" in (tmp_path / "packet2" / "1-documents.md").read_text(encoding="utf-8")
    assert "edited, not committed" not in (tmp_path / "packet2" / "1-documents.md").read_text(
        encoding="utf-8"
    )


def test_copy_to_places_the_upload_set_only(repo: Path, tmp_path: Path) -> None:
    dest = tmp_path / "desk"
    proc = run_tool(repo, "--out", str(tmp_path / "packet"), "--copy-to", str(dest))
    assert proc.returncode == 0, proc.stderr
    assert sorted(p.name for p in dest.iterdir()) == [
        "00-README.md",
        "01-QUERY.md",
        "02-CLAIMS.md",
        "1-documents.md",
        "2-harness.md",
        "3-source.md",
        "4-tests.md",
        "MANIFEST.json",
    ]


def test_this_repositorys_packet_carries_no_imported_identifier(tmp_path: Path) -> None:
    """The packet from HEAD is scanned by the same rules that keep the tree clean, so what
    leaves the machine is proven clean, not assumed clean."""
    out = tmp_path / "packet"
    proc = run_tool(REPO_ROOT, "--out", str(out), "--allow-dirty")
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    for must in (
        "CLAUDE.md",
        "docs/PLAN.md",
        "docs/decisions/DECISIONS.md",
        "tools/review_packet.py",
    ):
        assert must in {entry["path"] for entry in manifest["files"]}, must
    for rendered in ("00-README.md", "01-QUERY.md", "02-CLAIMS.md"):
        assert (out / rendered).is_file(), rendered
    assert "Load-bearing claims" in (out / "02-CLAIMS.md").read_text(encoding="utf-8")
    packed = [entry["path"] for entry in manifest["files"]]
    assert not any(p.startswith("docs/reference/earlier-project") for p in packed)
    # the identifier gate's own test spells out what it bans; it never ships
    assert "tests/gates/test_no_imported_identifiers.py" not in packed
    assert "test_no_imported_identifiers.py" in (out / "00-README.md").read_text(encoding="utf-8")
    assert violations(out / "tree", packed) == []


def test_the_index_maps_every_file_to_its_part_and_large_bundles_split(
    repo: Path, tmp_path: Path
) -> None:
    """A retrieval tool reads the index, not the parts in order; and a bundle over the part
    budget is written in numbered parts so no single upload is oversized."""
    out = tmp_path / "packet"
    proc = run_tool(repo, "--out", str(out), "--part-bytes", "40")
    assert proc.returncode == 0, proc.stderr
    index = (out / "00-README.md").read_text(encoding="utf-8")
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    parts = {bundle["name"]: bundle["files"] for bundle in manifest["bundles"]}
    assert "2-harness-1.md" in parts and "2-harness-2.md" in parts, sorted(parts)
    for part_name, files in parts.items():
        assert (out / part_name).is_file()
        for rel in files:
            assert f"| `{rel}` | `{part_name}` |" in index, rel
    assert sum(len(files) for files in parts.values()) == len(manifest["files"])
    readme = (out / "00-README.md").read_text(encoding="utf-8")
    assert "2-harness-1.md" in readme and "## File index" in readme
