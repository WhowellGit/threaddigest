# Local web UI design review — 2026-09-12

> Raw, lightly de-entitized report from an independent reviewer agent (Plan agent) asked to design the Reddit-style local UI on FastAPI + Jinja2 + HTMX. It used the working name `harvest`; the project name is `insightminer`. Later decisions that override parts of this report: the UI is the operator surface for every routine action (not only browsing), LAN access is open without a password by Wes's decision, and comment mode defaults to `full`.

---

# Local Web UI for the Reddit Harvester — Design Report

## 0. Stack assumptions and conventions (applies to everything below)

| Item | Decision |
|---|---|
| Process model | One process: `harvest web` runs uvicorn (**single worker**, required because retag/export job state lives in-process). Fetching is always the CLI in a subprocess. |
| Shared code | One package used by both CLI and web (`models.py`, `db.py`, `tagging.py`, `export.py`, `lock.py`). The web never re-implements matcher/export logic. |
| Templates | Jinja2, `StrictUndefined`, autoescape on. Every list page has a page template that `{% include %}`s a `_rows.html` fragment. |
| HTMX partial convention | Same URL serves full page or fragment: `render(request, "feed/list.html", ctx, partial="feed/_rows.html")` picks the fragment when the `HX-Request` header is present. Dedicated partial routes exist only for things that are not page-shaped (validate, preview, run panel, subtree, more comments). |
| URL scheme | Mirrors Reddit so muscle memory works: `/r/{sub}`, `/r/{sub}/comments/{id}/{slug}`, `/u/{name}`; themes at `/t/{slug}`. |
| Deep links | Jinja filter `reddit_url(obj)`: posts → `https://www.reddit.com{permalink}`; comments → `https://www.reddit.com/r/{sub}/comments/{post_id}/_/{comment_id}/?context=3`; tombstones (no permalink stored) → `https://www.reddit.com/comments/{post_id}` (works with IDs only). All `target="_blank" rel="noopener"`. User-settable host `www` vs `old`. |
| Mutations | POST/PUT/DELETE only via HTMX or plain forms. Validation failures return **422 with the re-rendered form**; HTMX configured via `<meta name="htmx-config">` `responseHandling` to swap 422. Flash messages via out-of-band swap `<div id="flash" hx-swap-oob="true">` (zero JS). |
| JS budget | Vendored `htmx.min.js` + one ~25-line `app.js` (comment collapse delegate, `/` focuses search). No build step. |
| Content rendering | Markdown → HTML at **ingest** (CLI) with `markdown-it-py` + `nh3` sanitizer, cached in `body_html`/`selftext_html_safe`. Web renders `|safe` only from that column. Tombstone scrub clears it. Never trust Reddit's `selftext_html`. |
| SQLite | WAL mode, `busy_timeout=5000`, one engine per process. FTS5 external-content tables with sync triggers (so tombstoning also purges the index). |
| Time | Store UTC; display relative ("3 hours ago") with absolute `title=`; display TZ from config (Docker defaults to UTC). |

### If you chose Python API + React/Next.js instead

| Area | What changes |
|---|---|
| Routes | Every page below becomes a JSON endpoint (`/api/...`) with Pydantic response models; the page/partial split disappears. Comment tree returned as nested JSON or flat + client builds tree. |
| Interactivity | Collapse, sort, filters, live preview, polling become React state/`useEffect`/SWR. Easier for keyboard-driven triage later, more code now (~2x). |
| Build/deploy | Node toolchain, `npm build`; Docker becomes a multi-stage build. Next.js adds a Node runtime process — prefer Vite+React SPA served as static files by FastAPI if you go this route. |
| Security | Need CORS config in dev, still need CSRF/Host checks. |
| Testing | Vitest + React Testing Library for components, plus API tests; Playwright unchanged. |
| What stays | Data model, CLI, lockfile, subprocess runner, export builder, FTS sanitizer, deep-link rules, tombstone rules — all backend, all unchanged. |

---

## 1. Page / route inventory

### 1a. Pages

| Route | Purpose | Data needed | Main interactions | HTMX partials used |
|---|---|---|---|---|
| `GET /` | Home feed: all monitored subs merged | posts (active subs) + theme badges + `is_new` flag; last completed run; per-sub/theme "new" counts for sidebar | sort (`new` default / `comments` / `score`), filters (sub, flair, author, from/to), paging (25/page), "new since last run/visit" toggle | rows fragment (same URL + `HX-Request`, `hx-push-url`), status pill |
| `GET /r/{sub}` | Subreddit view | same as feed filtered; sub meta (subscribers, description, last fetched, post count, monitored state, comment mode) | same as feed; flair filter populated from that sub's distinct flairs; "Pause/Remove/Re-add" shortcut to settings | rows fragment |
| `GET /t/{slug}` | Theme view | posts joined `post_themes` for theme; rules summary; per-rule hit counts; matched rule per post | same as feed + "edit theme", "re-tag now" | rows fragment, retag status |
| `GET /r/{sub}/comments/{post_id}/{slug?}` (`GET /p/{post_id}` redirects) | Post + full nested comment tree | post row (+ rendered HTML), all comments for post (flat, ordered), `more` stubs (uncaptured counts), themes matched | comment sort (`top` / `new` / `old`), collapse/expand, "continue this thread", "load more comments", deep links "open on reddit", "reply on reddit" per item | `/comments/{post_id}/subtree/{cid}`, `/comments/{post_id}/more` |
| `GET /r/{sub}/comments/{post_id}/{slug}/{cid}` | Comment permalink: subtree rooted at `cid` with "show parent / full thread" links | post header + subtree | same as post page | same |
| `GET /search` | FTS results, tabs Posts (n) / Comments (n) | FTS match + joined base rows, snippets, counts | query, `in=posts|comments`, sort relevance/new, filters sub/theme/date/author/flair, paging, syntax help | results fragment |
| `GET /u/{name}` | Author page: everything captured from a username | posts + comments by author (tabs Overview/Posts/Comments), counts, first/last seen | sort new/score, paging, "open profile on reddit". 404 with explanation for `[deleted]` | rows fragment |
| `GET /settings/subreddits` | Monitored subreddit CRUD | subreddits (active + paused + removed-but-retained), captured counts per sub, cached meta | add (validate first), pause/resume, remove (keep data / purge), set comment-harvest mode, open reddit | validate, add, confirm-remove, remove, toggle |
| `GET /settings/themes`, `/settings/themes/new`, `/settings/themes/{id}` | Theme list + editor | themes, rules, match counts, `last_tagged_at`, rules hash vs tagged hash (stale flag) | add/remove rule rows, live preview, save, delete, retag | rule-row, preview, save (422 or `HX-Redirect`), retag |
| `GET /runs` | Runs history + Run now + live progress panel | last 50 runs (status, trigger, duration, counts, errors), current run, lock state, next scheduled (display only) | Run now (disabled while running), cancel, open run detail, filter by status | `/runs/current`, `POST /runs` |
| `GET /runs/{id}` | Run detail | run row + per-subreddit counts + log tail + error traceback + link to raw JSONL path | view log, retry (= Run now) | `/runs/{id}/log` |
| `GET /export` | Export collection | DB size, JSONL total size, config size, previous exports, disk free | "Build export" (zip), download, delete old exports, options: include raw JSONL | `POST /export`, `/export/status` |
| `GET /healthz` | Health/status JSON (Docker `HEALTHCHECK`, header pill) | see 1c | none | `GET /partials/status` (HTML pill, polled every 60 s) |
| `GET /settings/appearance` | Theme light/dark/auto, reddit host www/old, timezone, page size | `ui_state` | plain form POST, sets cookie/`ui_state` | none |

### 1b. Partial endpoints (all return HTML fragments)

| Endpoint | Triggered by | Returns | Swap |
|---|---|---|---|
| Any list route + `HX-Request` | sort/filter controls (`hx-get`, `hx-push-url="true"`), prev/next | `_rows.html` (`<ol id="post-list">` contents + pager) | `#post-list` outerHTML |
| `GET /comments/{post_id}/subtree/{cid}?sort=` | "continue this thread →" (also a real `href` for middle-click) | nested comments rooted at `cid`, depth re-based to 0 | `closest .continue` outerHTML |
| `GET /comments/{post_id}/more?sort=&offset=` | "load more comments (N remaining)" | next batch of top-level comments with subtrees + new button (or nothing) | button outerHTML |
| `POST /settings/subreddits/validate` | name input, `hx-trigger="keyup[key=='Enter'], change, input changed delay:600ms"` | preview card (icon, display name, subscribers, description, type, NSFW) + Add button, or error line | `#sub-preview` |
| `POST /settings/subreddits` | Add button | new `_sub_row.html` + OOB cleared form + flash | `#sub-list` beforeend |
| `GET /settings/subreddits/{name}/confirm-remove` | remove link | confirm block with counts and two buttons | row outerHTML |
| `DELETE /settings/subreddits/{name}?purge=0|1` | confirm button (`hx-confirm` for purge) | empty body + OOB flash | row outerHTML |
| `POST /settings/subreddits/{name}/toggle` | pause/resume | updated row | row outerHTML |
| `PATCH /settings/subreddits/{name}` | comment-mode select `hx-trigger="change"` | updated row | row outerHTML |
| `GET /settings/themes/rule-row?kind=keyword` | "+ add rule" | one blank `_rule_row.html` | `#rules` beforeend |
| `POST /settings/themes/preview` | `hx-trigger="change, input delay:600ms from:closest form"`, `hx-include="closest form"` | counts, per-rule hits, 10 sample titles with highlights, compile errors | `#theme-preview` |
| `POST /settings/themes`, `PUT /settings/themes/{id}` | Save | 422 + form with errors, or `HX-Redirect: /t/{slug}` | form outerHTML |
| `DELETE /settings/themes/{id}` | Delete (`hx-confirm`) | empty + flash | row outerHTML |
| `POST /settings/themes/{id}/retag`, `GET /settings/themes/{id}/retag-status` | Re-tag button; poll every 1 s while running | progress line / done summary | `#retag-status` outerHTML |
| `POST /runs` | Run now (`hx-disabled-elt="this"`) | `_panel.html` (running) or **409** panel "already running (pid, started)" | `#run-panel` outerHTML |
| `GET /runs/current` | `hx-trigger="every 2s"` on the panel while running | panel; when finished, panel **without** `hx-trigger` (polling stops) or HTTP 286 | `#run-panel` outerHTML |
| `GET /runs/{id}/log?tail=80` | inside run panel/detail | `<pre>` of last N lines | `#run-log` |
| `POST /runs/{id}/cancel` | Cancel | panel | `#run-panel` |
| `POST /export`, `GET /export/status` | Build export; poll every 1 s | progress (stage, bytes) then download link + manifest summary | `#export-panel` outerHTML |
| `GET /partials/status` | header pill `hx-trigger="every 60s"` | pill: ok/error/running + last run time | outerHTML |

### 1c. `GET /healthz` JSON

```json
{"status":"ok|degraded|error","version":"0.3.0","db":{"ok":true,"path":"...","size_bytes":123,"schema_rev":"a1b2"},
 "last_run":{"id":42,"status":"ok","finished_at":"...","posts_new":43,"comments_new":312},
 "run_in_progress":false,"lock_held":false,"stale_run_detected":false,
 "disk_free_bytes":0, "reddit_credentials_present":true,"uptime_s":1234}
```
`status` is `error` if last run failed or DB unreadable, `degraded` if last successful run older than 2× schedule interval.

---

## 2. Wireframes (old-reddit density)

### Feed (`/`, `/r/{sub}`, `/t/{slug}` share this layout)

```
+---------------------------------------------------------------------------------------------------+
| r/premiere - r/VideoEditing - r/editors - r/AfterEffects        |  t/crashes - t/proxy - t/audio  |
+---------------------------------------------------------------------------------------------------+
| [harvest]  ALL    new | comments | score          search [__________________________] [go]        |
|                                                  Settings   Runs   Export   (o) last run ok 06:02 |
+----------------------------------------------------------------------------------+----------------+
| filter: sub [all v] flair [any v] author [________] from [______] to [______] [x] | LAST RUN       |
|----------------------------------------------------------------------------------| 06:00 today ok |
| 1  ^128  Premiere crashes on export with H.264 (self.premiere)             [NEW] | +43 posts      |
|          submitted 3 hours ago by u/editorguy to r/premiere [Help] . crashes     | +312 comments  |
|          58 comments (52 captured) . open on reddit ^                            | [ Run now ]    |
|                                                                                  |----------------|
| 2  ^12   Proxy workflow for 6K R3D - best practice?                              | MONITORED      |
|          submitted 5 hours ago by u/colorist to r/editors [Workflow] . proxy     | r/premiere     |
|          7 comments . open on reddit ^                                           |  187k  12 new  |
|                                                                                  | r/VideoEditing |
| 3  ^3    [deleted]                                                               |  527k  27 new  |
|          submitted 7 hours ago by [deleted] to r/VideoEditing                    | r/editors      |
|          2 comments . open on reddit ^                                           |  182k   4 new  |
|                                                                                  |----------------|
| ...                                                                              | THEMES         |
|                                                                                  | crashes 12 new |
| 25 ^41   Audio drift after import from OBS                                       | proxy    3 new |
|          submitted 1 day ago by u/streamer to r/VideoEditing [Audio] . audio     | audio    0 new |
|          19 comments . open on reddit ^                                          | + new theme    |
|----------------------------------------------------------------------------------|                |
|                              < prev   next >                                     |                |
+----------------------------------------------------------------------------------+----------------+
```

Notes: rank number, score, title, domain hint, tagline line, action line — exactly old reddit's three-line entry. `[NEW]` badge = first seen in latest run. Theme badges link to `/t/crashes`. Tombstoned post: muted row, `[deleted]` title/author, still links to reddit by ID.

### Post + comments

```
+---------------------------------------------------------------------------------------------------+
| [harvest]  r/premiere   new | comments | score        search [____________________] [go]  Settings |
+---------------------------------------------------------------------------------------------------+
| ^128  Premiere crashes on export with H.264 (self.premiere)                      open on reddit ^  |
|       submitted 3 hours ago by u/editorguy to r/premiere [Help]  . themes: crashes                |
|       score/comments as of 06:00 today                                                            |
|       +-----------------------------------------------------------------------------------------+ |
|       | Every time I export H.264 with hardware encoding on, Premiere 2026.1 crashes at 43%...  | |
|       | Specs: M2 Max, 64GB, macOS 15.6. Media is 4K H.265 from a Sony FX3.                     | |
|       +-----------------------------------------------------------------------------------------+ |
|       58 comments on reddit (52 captured)     sorted by: top | new | old        reply on reddit ^  |
|---------------------------------------------------------------------------------------------------|
| [-] u/helper  45 points  2 hours ago                                         permalink ^  reply ^  |
|  |  Try turning off hardware-accelerated encoding in the export settings, or transcode the        |
|  |  H.265 to ProRes proxies first.                                                                |
|  |                                                                                                |
|  |  [-] u/editorguy [OP]  12 points  1 hour ago                              permalink ^  reply ^  |
|  |   |  That fixed it, thanks!                                                                    |
|  |   |                                                                                            |
|  |   |  [+] u/other  3 points  55 minutes ago  (2 children)                                       |
|  |                                                                                                |
|  |  [-] [deleted]  5 points  2 hours ago                                              permalink ^  |
|  |   |  [removed]                                                                                 |
|  |   |                                                                                            |
|  |   |  [-] u/someone  2 points  1 hour ago                                  permalink ^  reply ^  |
|  |   |   |  Same here on Windows 11 with an RTX 4080...                                           |
|  |   |   |  continue this thread ->                                                               |
|                                                                                                   |
| [-] u/another  9 points  3 hours ago                                         permalink ^  reply ^  |
|  |  Check Media Encoder logs ...                                                                  |
|                                                                                                   |
| [ load more comments (14 remaining) ]                                                             |
+---------------------------------------------------------------------------------------------------+
```

Notes: `[-]`/`[+]` is a `<button aria-expanded>`; collapsed rows show header + "(N children)". `permalink` = our own URL (`#c-{id}` anchor also works), `reply ^` = deep link to reddit with `?context=3`. "(52 captured)" makes the harvest budget visible; the gap links to reddit.

---

## 3. Nested comment rendering

| Concern | Recommendation |
|---|---|
| Query | One query: `SELECT ... FROM comments WHERE post_id=? ORDER BY depth, sort_key` (flat rows). Index `(post_id, parent_comment_id)`. Top-level rows have `parent_comment_id IS NULL`. |
| Tree build | In Python, O(n): `children = defaultdict(list)`; append each row to `children[row.parent_comment_id]`; sort each list by chosen sort (`top`: score desc, created asc; `new`; `old`). Attach `subtree_size` via a reverse pass. ~500 comments: single-digit ms. |
| Template | **Recursive `{% for c in roots recursive %}` … `{{ loop(children[c.id]) }}`** (or a self-calling macro). Produces genuinely nested DOM, which is what makes collapse trivial and lets CSS draw thread lines with `border-left`. Depth is bounded so Python recursion limits are irrelevant. |
| Why not precomputed flat DFS + `margin-left: depth*20px` | Simpler template, but collapse then needs JS to walk following siblings by depth, and thread lines are ugly. Flat is only better for 10k+ node pages, which we cap anyway. |
| Depth cap / continue thread | Render to `max_depth = 10` (Reddit's own visible cap). At a node whose children exceed the cap, emit `<a class="continue" href="/r/{sub}/comments/{pid}/_/{cid}" hx-get="/comments/{pid}/subtree/{cid}" hx-swap="outerHTML">continue this thread →</a>`. HTMX swaps the subtree in place (re-based depth, its own cap); `href` works without JS and as a permalink page. |
| Pagination for long threads | Page by **top-level comments with their whole subtrees**, budgeted: include top-level comments in sort order until `sum(subtree_size) >= 300` (min 1). Remaining count shown on the "load more comments (N remaining)" button. Offset paging is safe here: the comment set only changes at fetch time. |
| Uncaptured comments | Store `more` stubs from PRAW (`comment_more(post_id, parent_comment_id, count)`). Render "N more replies not captured - view on reddit →" at that position, so the user knows the gap is a harvest budget, not a bug. |
| Collapse/expand | ~10 lines vanilla JS, event-delegated (survives HTMX swaps): click `.toggle` → `closest('.comment').classList.toggle('collapsed')`, flip `aria-expanded`, swap text `[-]`/`[+]`. CSS: `.comment.collapsed > .c-body, .comment.collapsed > .c-children { display:none }`. `<details>` is not recommended because the header links must live in `<summary>`, where clicks also toggle. |
| Tombstones | Row still renders (children remain visible, as on Reddit). Author `[deleted]` unlinked; body `[deleted]` (user) or `[removed]` (mod) from `tombstone_kind`; score shown if retained, no theme badges; `permalink` still works via IDs; no `reply` link. CSS class `.tombstone` for muted styling. Author pages must never list tombstoned items. |
| Anchors | Every comment `id="c-{id}"`; `:target` highlight so `/...#c-{id}` from search results lands correctly. |
| OP marking | Compare `comment.author == post.author` at render (both non-tombstoned). |

---

## 4. Settings UX

### 4a. Subreddits

| Step | Behavior |
|---|---|
| Input | Single text box "Add subreddit". Accepts `premiere`, `r/premiere`, `/r/premiere/`, or a full URL; normalized server-side. |
| Validate | Debounced `hx-post /settings/subreddits/validate` (600 ms, or Enter). Server uses read-only PRAW: `sub = reddit.subreddit(name); sub.id` (forces fetch). Map exceptions: `Redirect`/`NotFound` → "r/x does not exist" (this catches the doc's r/AdobePremierePro case); `Forbidden` → "private or quarantined - cannot be fetched"; banned → "banned"; `ResponseException 401` → "credentials invalid - check .env". Cache result 24 h. One API call per validation. |
| Preview card | `display_name` (canonical casing from API), subscribers (`fmt_num`, e.g. 187k), `public_description` (truncated), created year, `subreddit_type`, `over18` flag, "already monitored" notice if applicable, "open on reddit" link, **Add** button. Optional on Add: comment-harvest mode (`none` / `top-level` / `themed posts only` / `full`). |
| List row | name, subscribers, last fetched, posts/comments captured, state (active / paused), comment mode select, actions: pause/resume, remove, open on reddit, view `/r/name`. |
| Remove | Row swaps to a confirm block: "Stop monitoring r/x? Captured: 1,240 posts, 9,871 comments. [Stop, keep data] [Stop and delete captured data]". Keep = `active=0, removed_at=now`; `/r/x` remains browsable with a "not monitored - re-add" banner; sub hidden from nav. Purge = `hx-confirm` + deletes posts/comments/post_themes/FTS rows for that sub in one transaction. State honestly that raw JSONL files (per run, mixed subs) are not rewritten by purge; offer "also scrub raw JSONL" as a slower option later. |
| Re-add | Adding a previously removed sub reactivates the row and keeps its history. |

### 4b. Themes

| Element | Design |
|---|---|
| Header fields | name, slug (auto from name, editable), color (badge), description, enabled. |
| Rule model | `theme_rules(id, theme_id, kind, value, field, negate, case_sensitive, position)`; `kind in (keyword, regex, flair, subreddit)`; `field in (title, body, title_body)` for keyword/regex. |
| Semantics (shown in UI as three groups) | **Match any of**: keyword/regex/flair rules OR'd. **Exclude if any of**: same kinds with `negate=1`. **Only in**: subreddit rules (empty = all monitored). `match = any(matchers) and not any(excludes) and (no scopes or sub in scopes)`. |
| Keyword matching | Case-insensitive, whole-word by default (`\bword\b` compiled internally), checkbox "substring". Multi-word = phrase. |
| Regex | Python `re`, flags `i` unless case-sensitive; server validates with `re.compile` and returns the error inline on the rule row (422). Guardrails: max 300 chars, preview reports elapsed time and warns above 1 s (catastrophic backtracking). |
| Flair | Case-insensitive exact match on `link_flair_text`; datalist of known flairs across monitored subs. |
| Rule rows | `+ keyword`, `+ regex`, `+ flair`, `+ subreddit` buttons `hx-get /settings/themes/rule-row?kind=...` append rows; each row has a remove `x`. Rows are plain form inputs named `rules[i][kind]` etc., so the form posts without JS. |
| Live preview | Whole form debounced to `POST /settings/themes/preview`. Returns: "Would tag **143** posts (12 in last 7 days, 3 new since last run)", per-rule hit counts, 10 sample titles with matched text `<mark>`ed, compile errors. Uses the **same** `tagging.match(post, compiled_theme)` as the CLI, run over `posts` (30k rows in-process is ~50-200 ms; use an FTS pre-filter for keywords if it grows). |
| Save | `PUT` → validate all rules → store → compute `rules_hash` → if tag work is small (< ~2 s measured) retag inline; else start in-process retag job and redirect with panel polling. `HX-Redirect: /t/{slug}`. |
| Re-tag semantics | `post_themes` upsert: insert new matches with `matched_rule_id, matched_at`; delete rows no longer matching; **keep** existing rows (preserves "new in theme" timestamps). `themes.tagged_hash` vs `rules_hash` mismatch shows a "rules changed - re-tag" stale badge. CLI runs the same retag for new posts on every fetch. "Re-tag all themes" button on the list page. |
| Delete | `hx-confirm`; deletes theme + rules + post_themes; posts untouched. |
| Config export/import | `config export` writes subreddits + themes as YAML (diff-able, and included in the export zip); `config import` upserts. DB stays source of truth. |

---

## 5. "Run now"

| Question | Recommendation |
|---|---|
| Mechanism | **`subprocess.Popen([sys.executable, "-m", "<package>", "fetch", "--trigger", "manual", "--run-id", str(run.id)], stdout=logfile, stderr=STDOUT, start_new_session=True, cwd=DATA_DIR)`** — the exact same CLI launchd/supercronic runs. Isolation (a PRAW crash cannot take down the web), no event-loop blocking, one code path, and the lockfile is shared by construction. Rejected: FastAPI `BackgroundTasks`/threads (second code path, GIL contention, dies with the web process, harder to see in `ps`); Celery/RQ/Huey (broker + worker for one user). Log to a **file**, never `PIPE` (unread pipes deadlock). |
| Run record | Web inserts `runs(status='queued', trigger='manual', started_at, pid=NULL)` first so the panel has something to poll, then spawns, then sets `pid`. If spawn raises, mark `error`. The CLI updates the same row: `status='running'`, `stage`, counters, `heartbeat_at` every ~5 s, then `status ok|error|cancelled`, `finished_at`, `error_summary`, `traceback`, `per_subreddit_json`, `raw_path`, `log_path`. |
| Live progress | `<section id="run-panel" hx-get="/runs/current" hx-trigger="every 2s" hx-swap="outerHTML" aria-live="polite">`. Server renders stage, counters, elapsed, last 40 log lines, Cancel. When no run is active the panel is rendered without `hx-trigger` (or HTTP **286**), so polling stops by itself. Header pill polls every 60 s regardless. |
| Overlap prevention | The **CLI** owns the lock: `fcntl.flock(open(DATA/locks/fetch.lock), LOCK_EX | LOCK_NB)` for the whole run, writes its PID + start time into the file. Second starter exits with code 75 and the web shows 409. The web never takes the lock itself; it probes state via `runs`. Works across launchd + web on macOS and across containers sharing a bind-mounted **local** volume (do not put the data dir on a network share — SQLite forbids that anyway). |
| Stale runs | On web startup and in `/runs/current`: a `running` row with `heartbeat_at` older than the threshold and (same host) `os.kill(pid, 0)` failing → mark `crashed` with note. Heartbeat is primary (PID checks do not cross container PID namespaces). |
| Cancel | `POST /runs/{id}/cancel` → `os.kill(pid, SIGTERM)`; CLI traps SIGTERM, finishes the current upsert batch, marks `cancelled`. |
| Errors | Red panel with `error_summary` mapped to friendly text: 401 → "Reddit rejected credentials"; 403 → "forbidden/blocked - check User-Agent"; 429 → "rate limited; backed off, run retried N times"; network → "no connectivity"; `database is locked` → "DB busy - is another process writing?". "View full log" → `/runs/{id}` with traceback. Partial success is still `ok` with `warnings_json` shown as amber. |
| Button state | `hx-disabled-elt="this"` on click; server-side 409 protects against double posts; button hidden while a run is active. Optional dropdown: "Run for r/x only", "Re-tag only", "Tombstone sync only" → extra CLI flags. |

---

## 6. Export collection

| Aspect | Design |
|---|---|
| Trigger | `POST /export` starts an in-process job (single `ThreadPoolExecutor(max_workers=1)`; I/O-bound, 10-90 s). Panel polls `/export/status` every 1 s. Done → download link + size + sha256. Also available as a CLI command (same function). |
| DB snapshot | `sqlite3` `backup()` API (progress callback feeds the panel). Correct under WAL and concurrent CLI writes (raw file copy would miss the `-wal` contents / tear pages). Alternative: `VACUUM INTO 'tmp'` — also safe, produces a compacted file. Then `PRAGMA integrity_check` on the copy before zipping. |
| Archive | Write to `DATA/exports/<name>-YYYYMMDD-HHMMSS.zip` with `zipfile` (`ZIP_DEFLATED`, level 6), then serve with `FileResponse` (resumable, re-downloadable, survives a browser refresh). |
| Contents | DB snapshot, `raw/<run_id>/*.jsonl` of **finished** runs only, `config/config.yaml` (subreddits + themes exported from DB), `config/settings.yaml` (**secrets redacted**), `MANIFEST.json` (app version, alembic rev, created_at, counts, per-file sha256 + sizes, excluded runs), `README.txt` (how to restore). |
| Retention | Keep last 3 exports (configurable), list them on the page with delete buttons; temp snapshot files cleaned on startup. |
| Size expectations | ~60 posts/day × ~4 KB + ~600 comments/day × ~2 KB ≈ 1.5 MB/day raw JSON → ~550 MB/yr uncompressed (~60-80 MB deflated). DB ~150-300 MB/yr (+ ~500 MB if `raw_json` is also stored in the DB). Typical yearly export zip: 100-250 MB. |
| Guardrail | Refuse to start if free disk < 2× (DB size + JSONL size). |

---

## 7. Search (FTS5)

| Aspect | Design |
|---|---|
| Index | `posts_fts(title, selftext, author, flair, subreddit UNINDEXED, content='posts', content_rowid='id')` and `comments_fts(body, author, content='comments', content_rowid='id')`, tokenizer `porter unicode61 remove_diacritics 2`. Requires a stable **INTEGER PRIMARY KEY** on posts/comments. Insert/update/delete triggers keep them in sync, so tombstoning scrubs the index too. |
| UX | Header box on every page; on `/r/x` a "limit to r/x" checkbox, on `/t/x` "limit to theme". Results page: tabs Posts (n) / Comments (n); sort **relevance (bm25)** or new; filters: subreddit (multi), theme, date range, author, flair; 25/page. Result item = title/comment snippet with `<mark>`, tagline, "view in thread" (`#c-{id}`), "open on reddit". Empty state with syntax hints. Enter submits; no search-as-you-type. |
| Query building (never pass raw input to MATCH) | Mini-grammar: `"quoted phrase"`, `-word` (NOT), `word*` (prefix), `OR`. Everything else is a literal term. Each term is emitted as a double-quoted string with internal `"` doubled; `*` re-appended outside the quotes for prefix; terms joined by space (implicit AND); `NOT` terms appended after positives; if only negatives → return "add a positive term". Column scope from the UI becomes `{title}: (...)`. An "advanced FTS5 syntax" checkbox passes raw text and catches `sqlite3.OperationalError` → friendly "syntax error near ..." (422). Unit-test the sanitizer with adversarial inputs. |
| Snippets safely | `snippet(posts_fts, 1, char(2), char(3), '...', 24)` with control-char markers, then in Python: `html.escape(text).replace('\x02','<mark>').replace('\x03','</mark>')` → `Markup`. Never `|safe` the raw snippet. |
| Query shape | `SELECT p.*, snippet(...) FROM posts_fts f JOIN posts p ON p.id=f.rowid WHERE posts_fts MATCH :q AND p.subreddit IN (...) AND p.created_utc BETWEEN :a AND :b AND p.tombstone_kind IS NULL ORDER BY bm25(posts_fts) LIMIT 26`. Theme filter adds `EXISTS (SELECT 1 FROM post_themes ...)`. |
| Comments results | Show parent post title (link to our post page anchored at the comment), author, score, snippet, deep link. |

---

## 8. Testing strategy

| Layer | Approach |
|---|---|
| Fixtures | `pytest`; `tmp_path` SQLite created via `alembic upgrade head`; `factories.py` with `make_subreddit`, `make_post`, `make_comment(parent=..., depth=...)`, `make_tombstone(kind=deleted|removed)`, `make_theme(rules=...)`, `make_run(status=...)`. `app.dependency_overrides` for the DB session, the Reddit client (fake), and the run launcher (records the argv instead of spawning). `TestClient(app)` module fixture. |
| Per-route tests | 200 for every page with seeded and with empty DB; 404s; sort/filter params change order; paging boundaries. Parse HTML with `selectolax` — assert structure, not whole-page snapshots. |
| Template assertions | Comment tree: `comment[data-id=c2]` is a DOM descendant of `comment[data-id=c1]`; `data-depth` equals seeded depth; depth-11 node renders as `.continue` link; subtree endpoint re-bases depth to 0. Tombstones: `.author` text `[deleted]`, `.c-body` text `[removed]`/`[deleted]`, no `reply` link, children still rendered, `body_html` absent. Deep links: exact `href` equality for post, comment, tombstoned post, all with `rel="noopener"`. Markdown safety: seeded `<script>` in body renders escaped. `[NEW]` badge appears only for `first_seen_at >= last_run.started_at`. |
| HTMX partials | Request with `HX-Request: true` → body has no `<html>`/`<nav>`, starts with the fragment root; without the header → full page. `POST /settings/themes` invalid regex → 422 + error text inside the rule row. Successful save → `HX-Redirect` header. OOB flash present in add-subreddit response. `/runs/current` while running contains `hx-trigger`; when idle does not (or 286). |
| Behavior tests | Run now: creates `queued` row, launcher called with `--run-id`; second click with a `running` row → 409. Stale run detection marks `crashed`. Subreddit validate: nonexistent → error text; private → warning; duplicate → notice. Remove keep vs purge: counts before/after; purge also empties FTS rows. Retag upsert preserves existing `matched_at`. Export: run on seeded DB, open zip, assert members, `PRAGMA integrity_check == ok` on extracted DB, row counts match, in-progress run's JSONL excluded, manifest hashes verify. FTS sanitizer property tests (optional `hypothesis`). |
| Playwright smoke (optional) | Start uvicorn on a random port against a seeded temp DB in a session fixture. Flows: (1) home → click post → collapse a comment → assert children hidden → "continue this thread" swaps subtree; (2) settings → type sub name → preview card (fake client) → Add → row appears → Remove keep data → row gone, `/r/name` still 200; (3) Runs → Run now with a stub CLI script that sleeps 2 s while writing heartbeats → panel shows running then ok. Optionally `axe-core` via Playwright for a11y violations on the 3 pages. |
| Accessibility/keyboard basics | Landmarks, skip link, one `<h1>` per page, all controls are real `<button>`/`<a>`/`<label>`ed inputs, visible focus ring, `aria-expanded` on collapse toggles, `aria-live="polite"` on run/export/preview panels, `aria-current` on active sort, contrast ≥ 4.5:1 in both themes, `prefers-reduced-motion` respected, `/` focuses search, Esc blurs, Enter submits forms without HTMX. |
| CI | `ruff`, `mypy` (light), `pytest -q`; Playwright as a separate optional job. |

---

## 9. Styling

| Decision | Rationale |
|---|---|
| **Hand-written CSS, one file (~350 lines), design tokens via custom properties.** Not Pico/Water/MVP. | Classless frameworks are tuned for airy documents (large type, generous spacing); old-reddit density fights every default and you end up overriding most of it. A feed row + comment tree is ~40 selectors. |
| Tokens | `--bg --bg-alt --fg --muted --link --visited --accent --border --thread --mark --ok --warn --err --new`; light: reddit-ish (`#369` links, `#551a8b` visited, `#888` meta, `#f6f7f8` alt); dark: `#1a1a1b` bg, `#d7dadc` fg, `#4fbcff` links. Font: system stack at 13px, titles 14px; line-height 1.35. |
| Light/dark | `@media (prefers-color-scheme: dark)` default plus `<html data-theme="light|dark">` override set by a cookie from `/settings/appearance` (no JS, no flash of wrong theme). |
| Components | `.entry`, `.comment` (with `border-left: 1px solid var(--thread)` on `.c-children`), `.badge`, `.pill`, `.card`, `.panel`, `<mark>`, `.htmx-indicator`, `.tombstone`. Print styles optional. |
| Responsive | Sidebar collapses below 900px; desktop-first personal tool. |

---

## 10. Risks and decisions

| # | Decision / risk | Recommendation |
|---|---|---|
| 1 | **Custom UI vs Datasette.** | Build the custom UI, but also run Datasette read-only against the same DB as a "power query" link for ad-hoc SQL. |
| 2 | **Source of truth for subreddits/themes: DB or YAML.** | DB, with `config export/import` YAML for diffs, backup, and the export zip. |
| 3 | **Integer PK vs Reddit ID as PK.** FTS5 external-content tables need a stable integer rowid. | `id INTEGER PRIMARY KEY` + `reddit_id TEXT UNIQUE`. Alembic autogenerate does not manage FTS virtual tables/triggers — write those in raw-SQL migrations. |
| 4 | **Raw JSON in DB and JSONL = double storage, and deletion compliance.** | Store raw JSON in one place and have the tombstone-sync job rewrite affected JSONL lines. (Later decided: `raw_json` column long-term + 30-day JSONL with rewrite-on-scrub.) |
| 5 | **Unauthenticated localhost app = CSRF target.** | Bind `127.0.0.1`; middleware rejects state-changing requests unless `Sec-Fetch-Site` is `same-origin`/`none` and `Host` is an allowed value (also blocks DNS rebinding). On the QNAP/LAN add optional basic-auth or Tailscale-only exposure. |
| 6 | **Rendering Reddit markdown.** XSS via comments/selftext if you trust `selftext_html`. | `markdown-it-py` + `nh3` at ingest; store sanitized HTML; a `rerender` command when libraries change. |
| 7 | **Comment coverage vs API budget.** UI must not pretend the tree is complete. | Show "(N captured)" and "N more replies not captured" stubs; a per-post "harvest full tree" button. |
| 8 | **Staleness of score/num_comments.** | Show "as of <time>" on the post page. |
| 9 | **Single uvicorn worker** is required (in-process retag/export state). | Enforce; if you ever need more, move job state to a `jobs` table. |
| 10 | **Old reddit login wall (June 30 2026).** | Default to `www.reddit.com`; setting to switch to `old`. |
| 11 | **Regex rules can be slow/catastrophic.** | Length cap, preview timing warning. |
| 12 | **QNAP volumes.** flock + SQLite need a local filesystem. | Data dir on a local NAS volume bind-mounted into the container(s); never a network share. |
| 13 | **Scope creep.** | Build order: (1) DB + feed + post/comment tree + deep links, (2) settings subs/themes with preview, (3) runs + Run now, (4) search, (5) export, (6) author pages + filters + new-since indicators, (7) Playwright + dark mode polish. Each step is shippable. |
