"""Render docs/PLAN.md to docs/PLAN.html for review in a browser (no third-party dependencies).

Usage: uv run python tools/render_plan.py  (or: make plan-html)
Handles the markdown subset the plan uses: headings, paragraphs, tables, fenced code, lists, hr,
bold, inline code, links. The HTML is derived output and is git-ignored; regenerate after edits.
"""

from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "PLAN.md"
OUT = ROOT / "docs" / "PLAN.html"


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    codes: list[str] = []

    def _code(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", _code, s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)


def slug(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"[`*]", "", t).lower()).strip("-")


def cells(r: str) -> list[str]:
    r = r.strip()
    r = r[1:] if r.startswith("|") else r
    r = r[:-1] if r.endswith("|") else r
    return [c.strip() for c in r.split("|")]


def render(src: str) -> tuple[str, list[tuple[int, str, str]]]:
    lines = src.splitlines()
    i = 0
    body: list[str] = []
    toc: list[tuple[int, str, str]] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            body.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            flush()
            j = i + 1
            buf: list[str] = []
            while j < len(lines) and not lines[j].startswith("```"):
                buf.append(lines[j])
                j += 1
            body.append("<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            flush()
            level, text = len(m.group(1)), m.group(2).strip()
            sid = slug(text)
            body.append(f'<h{level} id="{sid}">{inline(text)}</h{level}>')
            if level in (2, 3):
                toc.append((level, sid, re.sub(r"[`*]", "", text)))
            i += 1
            continue
        if re.match(r"^-{3,}\s*$", ln):
            flush()
            body.append("<hr>")
            i += 1
            continue
        if ln.startswith("|"):
            flush()
            rows: list[str] = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            header, data = cells(rows[0]), [cells(r) for r in rows[1:]]
            t = [
                '<div class="tw"><table><thead><tr>'
                + "".join(f"<th>{inline(c)}</th>" for c in header)
                + "</tr></thead><tbody>"
            ]
            for r in data:
                if all(re.match(r"^:?-{2,}:?$", c) for c in r if c):
                    continue
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            body.append("".join(t))
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", ln)
        if m:
            flush()
            start, items = m.group(1), []
            while i < len(lines):
                m2 = re.match(r"^(\d+)\.\s+(.*)$", lines[i])
                if m2:
                    items.append(m2.group(2))
                    i += 1
                elif lines[i].startswith("   ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            body.append(f'<ol start="{start}">' + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue
        if ln.startswith("- "):
            flush()
            items = []
            while i < len(lines):
                if lines[i].startswith("- "):
                    items.append(lines[i][2:])
                    i += 1
                elif lines[i].startswith("  ") and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            body.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        if not ln.strip():
            flush()
            i += 1
            continue
        para.append(ln.strip())
        i += 1
    flush()
    return "".join(body), toc


CSS = """:root{--fg:#1b1f23;--muted:#57606a;--border:#d0d7de;--bg:#fff;--alt:#f6f8fa;--link:#0969da}*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg)}
.banner{background:#fff8c5;border-bottom:1px solid #d4a72c;padding:8px 24px;font-size:13px;color:#5a4a00}
.layout{display:grid;grid-template-columns:270px minmax(0,1fr);gap:36px;max-width:1500px;margin:0 auto;padding:24px}
nav.toc{position:sticky;top:12px;align-self:start;max-height:calc(100vh - 24px);overflow:auto;font-size:13px;border-right:1px solid var(--border);padding-right:12px}
nav.toc ul{list-style:none;padding:0;margin:0} nav.toc li.l3{padding-left:14px} nav.toc a{color:var(--muted);text-decoration:none;display:block;padding:2px 0;line-height:1.35} nav.toc a:hover{color:var(--link)}
main{min-width:0} h1{font-size:26px;margin:.2em 0 .6em} h2{font-size:21px;margin:1.9em 0 .6em;padding-bottom:.25em;border-bottom:1px solid var(--border)} h3{font-size:17px;margin:1.5em 0 .5em}
.tw{overflow-x:auto;margin:12px 0 18px} table{border-collapse:collapse;width:100%;font-size:13.5px} th,td{border:1px solid var(--border);padding:6px 9px;vertical-align:top;text-align:left} th{background:var(--alt);font-weight:600} tbody tr:nth-child(even){background:#fbfcfd}
code{font:12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--alt);padding:1px 4px;border-radius:4px}
pre{background:#0d1117;color:#e6edf3;padding:12px 14px;border-radius:6px;overflow-x:auto;font-size:12.5px;line-height:1.35} pre code{background:none;color:inherit;padding:0}
hr{border:0;border-top:1px solid var(--border);margin:28px 0} ul,ol{padding-left:24px} li{margin:.25em 0} p{margin:.6em 0} a{color:var(--link)}
@media (max-width:900px){.layout{grid-template-columns:1fr} nav.toc{position:static;border:0;max-height:none}}
@media print{nav.toc,.banner{display:none} .layout{display:block;padding:0} pre{white-space:pre-wrap} h2{page-break-after:avoid}}"""


def main() -> None:
    body, toc = render(SRC.read_text(encoding="utf-8"))
    try:
        rev = subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%h %ad", "--date=short"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
    except OSError:
        rev = "unknown"
    toc_html = "<ul>" + "".join(
        f'<li class="l{lvl}"><a href="#{sid}">{html.escape(txt)}</a></li>' for lvl, sid, txt in toc
    ) + "</ul>"
    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Insight Miner Plan</title><style>{CSS}</style></head><body>"
        f'<div class="banner">Insight Miner plan · rendered from docs/PLAN.md at commit {html.escape(rev)} · '
        "regenerate with <code>make plan-html</code></div>"
        f'<div class="layout"><nav class="toc">{toc_html}</nav><main>{body}</main></div></body></html>'
    )
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes; {len(toc)} headings)")


if __name__ == "__main__":
    main()
