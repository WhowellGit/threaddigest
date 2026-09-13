"""Render docs/PLAN.md to docs/PLAN.html for review in a browser (stdlib only).

Usage: ``uv run python tools/render_plan.py`` or ``make plan-html``.

Handles the markdown subset the plan uses: headings, paragraphs, pipe tables, fenced code,
ordered and unordered lists, horizontal rules, bold, inline code, and links. The HTML is a
derived artifact and is git-ignored; regenerate it after editing the plan.
"""

from __future__ import annotations

import html
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "PLAN.md"
OUT = ROOT / "docs" / "PLAN.html"
CSS = Path(__file__).resolve().parent / "plan.css"

HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
ORDERED = re.compile(r"^(\d+)\.\s+(.*)$")
RULE = re.compile(r"^-{3,}\s*$")
SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")


def inline(s: str) -> str:
    """Escape, then apply inline code, bold, and links; code spans are protected first."""
    s = html.escape(s, quote=False)
    codes: list[str] = []

    def _code(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", _code, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"[`*]", "", text).lower()).strip("-")


def cells(row: str) -> list[str]:
    row = row.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") else row
    return [c.strip() for c in row.split("|")]


@dataclass
class Doc:
    """Accumulates rendered blocks and the table of contents."""

    body: list[str] = field(default_factory=list)
    toc: list[tuple[int, str, str]] = field(default_factory=list)
    para: list[str] = field(default_factory=list)

    def flush(self) -> None:
        if self.para:
            self.body.append("<p>" + inline(" ".join(self.para)) + "</p>")
            self.para.clear()


def take_code(lines: list[str], i: int, doc: Doc) -> int:
    j = i + 1
    buf: list[str] = []
    while j < len(lines) and not lines[j].startswith("```"):
        buf.append(lines[j])
        j += 1
    doc.body.append("<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>")
    return j + 1


def take_table(lines: list[str], i: int, doc: Doc) -> int:
    rows: list[str] = []
    while i < len(lines) and lines[i].startswith("|"):
        rows.append(lines[i])
        i += 1
    header = "".join(f"<th>{inline(c)}</th>" for c in cells(rows[0]))
    parts = [f'<div class="tw"><table><thead><tr>{header}</tr></thead><tbody>']
    for row in rows[1:]:
        values = cells(row)
        if all(SEPARATOR_CELL.match(c) for c in values if c):
            continue
        parts.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in values) + "</tr>")
    parts.append("</tbody></table></div>")
    doc.body.append("".join(parts))
    return i


def take_list(lines: list[str], i: int, doc: Doc, ordered: bool) -> int:
    items: list[str] = []
    start = "1"
    while i < len(lines):
        line = lines[i]
        m = ORDERED.match(line)
        if ordered and m:
            start = start if items else m.group(1)
            items.append(m.group(2))
        elif not ordered and line.startswith("- "):
            items.append(line[2:])
        elif line.startswith("  ") and line.strip() and items:
            items[-1] += " " + line.strip()
        else:
            break
        i += 1
    tag = f'<ol start="{start}">' if ordered else "<ul>"
    close = "</ol>" if ordered else "</ul>"
    doc.body.append(tag + "".join(f"<li>{inline(x)}</li>" for x in items) + close)
    return i


def take_heading(m: re.Match[str], doc: Doc) -> None:
    level, text = len(m.group(1)), m.group(2).strip()
    sid = slug(text)
    doc.body.append(f'<h{level} id="{sid}">{inline(text)}</h{level}>')
    if level in (2, 3):
        doc.toc.append((level, sid, re.sub(r"[`*]", "", text)))


def render(src: str) -> Doc:
    """Walk the markdown once, dispatching each block type to a small handler."""
    lines = src.splitlines()
    doc = Doc()
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = HEADING.match(line)
        if line.startswith("```"):
            doc.flush()
            i = take_code(lines, i, doc)
        elif heading:
            doc.flush()
            take_heading(heading, doc)
            i += 1
        elif RULE.match(line):
            doc.flush()
            doc.body.append("<hr>")
            i += 1
        elif line.startswith("|"):
            doc.flush()
            i = take_table(lines, i, doc)
        elif ORDERED.match(line):
            doc.flush()
            i = take_list(lines, i, doc, ordered=True)
        elif line.startswith("- "):
            doc.flush()
            i = take_list(lines, i, doc, ordered=False)
        elif not line.strip():
            doc.flush()
            i += 1
        else:
            doc.para.append(line.strip())
            i += 1
    doc.flush()
    return doc


def git_revision() -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%h %ad", "--date=short"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "unknown"
    return proc.stdout.strip() or "unknown"


def page(doc: Doc, rev: str) -> str:
    toc = "<ul>" + "".join(
        f'<li class="l{lvl}"><a href="#{sid}">{html.escape(txt)}</a></li>'
        for lvl, sid, txt in doc.toc
    )
    toc += "</ul>"
    banner = (
        f"Insight Miner plan · rendered from docs/PLAN.md at commit {html.escape(rev)} · "
        "regenerate with <code>make plan-html</code>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Insight Miner Plan</title><style>{CSS.read_text(encoding='utf-8')}</style>"
        f'</head><body><div class="banner">{banner}</div><div class="layout">'
        f'<nav class="toc">{toc}</nav><main>{"".join(doc.body)}</main></div></body></html>'
    )


def main() -> None:
    doc = render(SRC.read_text(encoding="utf-8"))
    OUT.write_text(page(doc, git_revision()), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes; {len(doc.toc)} headings)")


if __name__ == "__main__":
    main()
