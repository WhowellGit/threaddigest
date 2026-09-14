# Collector, data model, and testing design review — 2026-09-12

> Raw, unedited report from an independent reviewer agent (Plan agent) asked to critique the collector design sketch, verify PRAW/prawcore behavior against upstream, and propose a failure-mode test matrix, migration practices, and milestones. Paths in its layout section assumed the then-current working directory and the name `reddit_harvest`/`rharvest`; the project name is `insightminer` and the location decision is pending. Confidence tags are the reviewer's: **[V]** verified in source/docs on 2026-09-12; **[C]** confident from experience; **[?]** must be verified with a live probe.

---

# Reddit Harvester — Design Review and Implementation Plan

## 0. What this is based on

- Read the research document in full.
- Verified the load-bearing PRAW/prawcore behaviors against the upstream `main` branches on 2026-09-12 (PRAW 8.0.3, 2026-08-12; prawcore 4.0.0, 2026-06-13): `prawcore/{sessions,rate_limit,exceptions,requestor,auth,const}.py`, `praw/{reddit,models/auth,models/comment_forest,models/reddit/more,models/reddit/base,models/reddit/redditor,models/reddit/submission,models/reddit/comment,models/reddit/subreddit/subreddit,models/reddit/mixins/fullname,models/listing/generator,models/listing/listing,models/listing/mixins/base}.py`, both CHANGES files, and the PRAW docs pages for authentication, configuration options, `Auth.limits`, and the comments tutorial. Also pytest-alembic and pytest-recording docs.
- Environment facts observed: the working directory is empty; `uv` is not installed; Homebrew Python is 3.14.6 (so `uv python install 3.12` is a setup step); PRAW is not installed anywhere locally. Reddit itself cannot be probed anonymously anymore, so Reddit-side semantics are marked for a live probe.

Confidence legend used throughout: **[V]** verified in source/docs today; **[C]** confident from experience, cheap to confirm; **[?]** must be verified with a live probe during implementation.

---

## 1. Critique: data model, fetch algorithm, and PRAW facts

### 1.1 PRAW / prawcore facts a careful implementer must know

| Topic | What is actually true | Conf. | Implication for the design |
|---|---|---|---|
| Read-only auth | `Reddit(client_id=..., client_secret=..., user_agent=...)` with no username/password uses `ReadOnlyAuthorizer` → `grant_type=client_credentials` with HTTP Basic `client_id:client_secret` to `/api/v1/access_token`. `reddit.read_only` is True; scopes are `{"*"}`. Works for script apps. Token endpoint errors: non-200 → `prawcore.ResponseException` (401 for bad id/secret); JSON `error` → `prawcore.OAuthException`. Token validity is checked with `time.monotonic_ns()`; refresh is automatic. | [V] | Never supply username/password. Make one deliberate cheap request (about.json) at run start so auth failures surface before paging. Wall-clock skew cannot break token expiry logic. |
| User-Agent | prawcore appends ` prawcore/<version>` to your UA and rejects UAs shorter than 7 chars. | [V] | Reddit will see `python:com.you.harvest:v0.3.0 (by /u/you) prawcore/4.0.0`. That is normal and acceptable. Build the string from a single `__version__`. |
| Automatic retries | `FiniteRetryStrategy` with `DEFAULT_RETRIES = 2` → at most 3 attempts. Retried statuses: `{500, 502, 503, 504, 408, 520, 522}`; retried exceptions: `ChunkedEncodingError, ConnectionError, ReadTimeout`. Sleep: `0–2 s` before the first retry, `2–4 s` before the last. POSTs are retried too. After exhaustion: `ServerError` (5xx) or `RequestException` (wraps the `requests` exception). | [V] | prawcore's retry is short (seconds). Add your own outer retry per unit of work (a page, a tree, an `info` batch) with longer backoff (e.g., 30 s → 2 min → 5 min) and a per-run failure budget. |
| HTTP 429 | Not retried. Raises `prawcore.TooManyRequests` immediately, with `.retry_after` (string from header, may be None) and `.message`. | [V] | Catch it; sleep `min(float(retry_after or 60), 300)`; retry once; abort the run if it recurs. It should be rare single-process because the limiter paces requests. |
| Rate limiter | Reads `x-ratelimit-remaining/used/reset` on every response. If `remaining <= 0` it sleeps until reset (min 1 s). Otherwise it spreads remaining requests evenly over the remaining window, with the inter-request delay capped at 10 s. If headers are absent it decrements a local counter. `window_size` = 600. Timestamps are nanoseconds (`next_request_timestamp_ns`). | [V] | A 1,500-request run will take at least ~15 minutes at steady state; design per-run request budgets and expect pacing, not bursts. |
| `reddit.auth.limits` | Returns a dict with keys `remaining` and `used`; values are `None` until the first response. Sourced from `Session.rate_limiter` (a public property since prawcore 3.2.0). PRAW 8 docs do not list a `reset_timestamp` key (PRAW 7 had one). | [V] keys; [C] on `reset_timestamp` removal | Use for logging only. For budgeting, count requests yourself with a `requests` response hook on a Session you inject via `requestor_kwargs={"session": s}`; read `X-Ratelimit-Reset` there if you want it. |
| 401/403/404/3xx mapping | 401 and 403 go through `authorization_error_class`, which chooses `InvalidToken` / `InsufficientScope` / `Forbidden` from the `WWW-Authenticate` header; on `InvalidToken` prawcore clears the token, refreshes, and retries. 404 → `NotFound`. 301/302 → `Redirect` (with `.path`). | [V] mapping; [C] 401 refresh flow | Private sub → `Forbidden`; banned sub → `NotFound`; nonexistent sub → `Redirect` to `/subreddits/search?q=...` [C]; quarantined → `Forbidden` unless opted in [?]. Handle all four distinctly. |
| Timeout | Default 16 s (`timeout` option; env `PRAWCORE_TIMEOUT`). Every exception raised by `requests` is wrapped in `RequestException`. | [V] | Pass `timeout=30`. Catch `RequestException` and inspect `.original_exception` for logging. |
| `check_for_updates` | Default true; PRAW checks PyPI for a newer version at construction. | [C] | Set `check_for_updates=False` (no surprise network call, no noise in containers). |
| `ratelimit_seconds` | Applies only to JSON `RATELIMIT` errors returned by write endpoints, not to HTTP 429. | [V] | Irrelevant for a read-only client. |
| Lazy-fetch footgun | `RedditBase.__getattr__`: any missing attribute not starting with `_` on an object with `_fetched=False` calls `_fetch()` = one HTTP request. A `Redditor` built from a name (which is what `comment.author` is) fetches `/user/{name}/about` when you touch `.id` or `.fullname`. A `Submission` from a listing is `_fetched=False`, so `getattr(sub, "some_missing_key", None)` silently fetches `/comments/{id}`. | [V] | Serialize PRAW objects with `vars(obj)` (drop keys starting with `_`); never `getattr(..., default)` on PRAW objects; read `author_fullname` from the dict, not `author.fullname`. Assert exact request counts in adapter tests. |
| Objectified fields | `Submission.__setattr__` converts `author` → `Redditor` or `None` (JSON `"[deleted]"` → `None`), `subreddit` → `Subreddit`, `poll_data` → `PollData`. `Comment` converts `author`, `subreddit`, and `replies` → `_replies`. | [V] | Your `to_raw()` must map these back (`author.name`, `subreddit.display_name`, drop `_replies`), or bypass objectification with `reddit.request()` (see §2). |
| `reddit.request()` | Returns parsed wire JSON, not objectified. PRAW itself relies on this: `Submission._fetch_data` calls it and indexes `["data"]["children"][0]["data"]`. | [V] | Cleanest path to exact raw JSON for provenance. |
| Listing pagination | `ListingGenerator` sets `params["limit"] = request_limit or limit or 1024` (Reddit clamps to 100/page), advances `after` from the listing JSON, and stops only when `after` is `None` or unchanged. `subreddit.new()` makes no request until iterated and never fetches about.json. | [V] | Do not add a "page shorter than 100 → stop" heuristic; Reddit drops removed items after pagination so short pages with more remaining are normal [C]. |
| Tree fetch cost | First access to `submission.comments` → `GET /comments/{id}?limit=2048&sort=confidence` (1 request; response is `[submission_listing, comment_listing]`, so the post row is refreshed for free). | [V] | Reddit clamps `limit` to some maximum [?]; everything beyond arrives as `more` nodes. |
| `replace_more` | Default `limit=32`; each replacement is 1 request and discovers at most 100 comments; nodes with `count == 0` are "continue this thread" links and cost 1 request each (they fetch `/comments/{post}/_/{parent_id}`); `threshold > 0` skips them; largest `count` is expanded first (max-heap); returns the list of `MoreComments` it did **not** replace; raises `TooManyRequests` under concurrency. | [V] | `skipped = forest.replace_more(limit=N)`; `comments_complete = not skipped`; persist `more_skipped = len(skipped)` and `more_skipped_count = sum(m.count for m in skipped)`. |
| `num_comments` | Includes deleted/removed/spam comments; will not match the harvested count. | [V] | Never use it as a completeness check. |
| `reddit.info(fullnames=...)` | Accepts `t1_`, `t3_`, `t5_`; issues one request per 100 fullnames; yields found items "in their relative order"; unmatched items are silently omitted. | [V] | Match results by fullname, not position. Absence ≠ deletion (could be transient) → confirm before scrubbing. Comments returned by `/api/info` carry no `replies`/`depth` [C], so keep stored `depth`. |
| Case-insensitive names | Subreddit names are case-insensitive; `r/videoediting` and `r/VideoEditing` are the same community. The research doc's "distinct low-traffic variant" claim is wrong. | [C] | Normalize to lowercase for identity; store canonical `display_name` and `t5_` id from about.json. |

### 1.2 Data model critique

| Sketch item | Problem | Recommendation |
|---|---|---|
| `posts.id` (base36) as PK, TEXT | Two real issues: (1) FTS5 external-content tables map to `rowid`, and SQLite may renumber implicit rowids on `VACUUM` unless the table has an `INTEGER PRIMARY KEY`; (2) TEXT PKs make every index and FK larger. | Use a surrogate `pk INTEGER PRIMARY KEY` on `posts`/`comments`, with `reddit_id TEXT NOT NULL UNIQUE` (base36) and a generated/stored `fullname`. Join and FK on `pk`; dedupe on `reddit_id`. |
| `comments.parent_id` | Reddit's `parent_id` is a fullname (`t1_…` or `t3_…`). Mixing that with base36 `post_id` makes tree joins awkward. | Store `parent_fullname TEXT` (raw), `parent_comment_pk INTEGER NULL` (resolved when the parent exists), `post_pk INTEGER NOT NULL`. Do not enforce an FK on parent (parents may be skipped `more` nodes). |
| `edited` | Reddit returns `false` or a float epoch. | `edited_utc INTEGER NULL`. |
| Missing columns | No `subreddit_id` (t5_), `crosspost_parent`, `is_video`, `is_gallery`, `post_hint`, `spoiler`, `archived`, `author_flair_text`, `num_crossposts`; no provenance `source` ("r/premiere/new", "comments", "info"); no `normalizer_version`. | Add them. `source` and `normalizer_version` on every row make "reprocess rows where normalizer_version < N from raw_json" possible. |
| `deleted_at` | Conflates four different states, and cannot represent "author deleted their account but content remains" (which the terms treat differently: scrub author info only). | `content_state TEXT CHECK IN ('live','deleted_by_author','removed_by_moderator','removed_by_reddit','gone_unconfirmed','gone')`, `removed_by_category TEXT` (raw), `author_state TEXT CHECK IN ('known','account_deleted')`, `scrubbed_at`, `misses INTEGER` (consecutive `info()` misses). |
| `comments_complete` | Underspecified. | True only if the tree fetch succeeded **and** `replace_more` returned an empty list. Also store `more_skipped`, `more_skipped_count`, `comments_harvested`. |
| Revisit milestones computed on the fly | Hard to resume after crashes and hard to test. | Add `next_check_at INTEGER`, `check_stage INTEGER` on posts (stage 0..N = 1d/3d/7d/30d/90d). A run selects `WHERE next_check_at <= now ORDER BY next_check_at LIMIT budget`. Idempotent and trivially testable. |
| `subreddits.name PK` | Case-insensitivity; no stable id; watermark in the wrong time domain; no status. | `name_lower TEXT PK`, `display_name`, `subreddit_id TEXT UNIQUE` (t5_), `subreddit_type`, `subscribers`, `over18`, `quarantine`; `watermark_created_utc INTEGER` (max `created_utc` seen in the last **complete** pass), `last_complete_poll_at`, `last_seen_fullname` (informational only), `status` ('ok','forbidden','not_found','redirect','error'), `last_error`, `consecutive_failures`, `gap_suspected_at`. |
| `raw_json` on rows | Fine, but it must be scrubbed too (it contains the content). Size: ~5–10 KB/post, 2–3 KB/comment; 100k comments ≈ 300 MB. | Keep it; on scrub replace with a tombstone object. Consider zlib-compressed BLOB later if size matters. |
| `snapshots` with `body_hash` | A hash of deleted content is derived content; you also do not need it: on refresh you have both old and new body to detect edits. | Keep snapshots numeric-only: `(item_pk, kind, fetched_at, score, num_comments, upvote_ratio)`. Cheap, written on every revisit, enables velocity/trend later. |
| `runs` | Missing per-subreddit outcome detail. | Add `run_kind`, `started_at`, `finished_at`, `status` ('running','ok','partial','failed','rate_limited','skipped_locked'), `app_version`, `praw_version`, `schema_rev`, `api_requests`, `error`; plus `run_subreddits(run_id, name_lower, pages, items_seen, new, updated, stop_reason, error)`. |
| `themes` / `theme_rules` / `post_themes` | No rule versioning; regex authored in a UI is a ReDoS risk; no scope. | `theme_rules(theme_id, kind 'keyword'|'regex', pattern, scope 'title'|'selftext'|'comments'|'any', case_sensitive, enabled)`; `post_themes(post_pk, theme_id, rule_id, matched_field, tagged_at, rules_hash)`. Retag when `rules_hash` changes. Use the `regex` package with `timeout=` (stdlib `re` has none), cap pattern length, compile-check on save. Store no matched-text snippets (they are content). |
| FTS5 | Sync triggers must also handle scrub (an UPDATE trigger that re-indexes `"[deleted]"` is wrong) and Alembic autogenerate will try to drop the FTS shadow tables. | External-content FTS5 on `pk`; triggers `WHEN new.content_state = 'live'` for insert/update, delete-old on update/delete. Create via `op.execute` in migrations; add an `include_object` filter ignoring `%_fts%`. |
| Timestamps | SQLAlchemy `DateTime(timezone=True)` on SQLite silently drops tz. | Store `created_utc`/`edited_utc` as INTEGER epoch (Reddit's domain) and all `*_at` as INTEGER epoch too (or a `TZDateTime` TypeDecorator). Pick one and enforce with a test. |
| Append-only JSONL sidecar | Conflicts with the deletion terms: an append-only file retains deleted content forever, "even if disassociated". | JSONL becomes **rewrite-on-scrub** plus **bounded retention**: files are per run (`raw/<YYYY>/<MM>/run-<id>.jsonl`, compressed after the run); a `raw_files(run_id, path)` table plus `first_seen_run_id`/`last_run_id` on rows lets the scrubber rewrite only files that can contain the item (atomic temp-and-rename). Default retention 30 days (raw_json in the DB is the long-term reprocessing store). |
| Authors | "Track usernames" implies aggregation. | `authors(author_fullname PK, name, first_seen_at, last_seen_at, post_count, comment_count, state)`. On `author_state='account_deleted'` delete the row and null `author*` columns everywhere. Never fetch `/user/{name}/about` (costs a request per author and is not needed). |
| Config split | Fine. | Secrets only in `.env`/env vars; YAML export must never include them. |

### 1.3 Fetch algorithm critique and edge cases

**Biggest structural change I recommend:** a full page-through of `/new` costs at most 10 requests per subreddit (1,000-item cap at 100/page). For three subreddits that is 30 requests/day out of ~144,000 available. So page the **entire** listing every run by default and let the PK upsert dedupe. This (a) removes the watermark from the correctness path (it becomes a reporting/gap-detection aid), (b) refreshes score/num_comments/edits for the newest ~1,000 posts per sub daily for free, (c) catches posts released late from the spam/mod queue no matter how late (within the cap window), and (d) yields a cheap removal signal: a post previously seen in the window that no longer appears in `/new` is likely removed/deleted → confirm with `info()`. Keep the early-stop rule as an opt-in optimization for high-volume subs.

| Edge case | What happens | Correct handling |
|---|---|---|
| Late-released posts (AutoMod/spam filter, approved hours or days later) | `/new` is ordered by `created_utc`; an approved post appears at its **original** position, i.e., "in the past" relative to a fullname/time watermark. A 12 h overlap misses anything approved later. | Full page-through (above). If you keep early-stop, the overlap must be days, not hours, and the stop rule must be: "stop after a page in which zero non-stickied items have `created_utc >= boundary`", not "first old item seen". |
| Watermark time domain | `created_utc` is Reddit's clock; `last_polled_at` is yours. Mixing them makes the stop rule sensitive to local clock skew. | Watermark = `max(created_utc)` seen in the last complete pass. Never compare Reddit timestamps to local time for correctness decisions. |
| `before=<fullname>` paging | Breaks if the anchor item is deleted/removed (empty listing). | Never use `before`. Page forward with `after` (PRAW default) and stop by rule. |
| Short pages | Reddit removes deleted/removed items after pagination; a page of 37 with a non-null `after` is normal. | Rely on `ListingGenerator`'s `after` semantics only [V]. |
| The 1,000-item cap without reaching the boundary | Only possible after a long outage (>~25 days at 40 posts/day). | Record `gap_suspected_at` on the subreddit and `stop_reason='cap'` in `run_subreddits`; surface in the digest. Backfill is out of scope. |
| Stickies | Appear in chronological position in `/new` [C]; if they ever appear pinned, a naive stop rule terminates early. | Exclude `stickied=True` from the stop computation. |
| Crossposts | A crosspost is a separate submission with `crosspost_parent` and `crosspost_parent_list` (parent's full data). `selftext` is empty. | Store `crosspost_parent`; do not FK it (parent may be in an unmonitored sub). Theme tagging should also look at `raw_json.crosspost_parent_list[0].title/selftext`. |
| Edits | `edited` flips to a float; edits within ~3 minutes of posting do not flip it [C]. | Refresh via the daily `/new` sweep and tree refetches; compare bodies directly, no hash needed. |
| Deleted/removed before first sight | Never appears in `/new`. | Nothing to do; this is fine. |
| Removed-then-approved | Post vanishes from `/new` and returns `removed_by_category='moderator'`, later reappears with content. | Allow `removed_by_moderator → live` transitions; `deleted_by_author` is terminal. |
| Ordering of run steps | Sketch starts with lock → runs row. | Validate config → open DB and refuse if migrations pending → acquire lock → create `runs` row → auth ping (about.json for the first sub) → work. Config/auth failures must never leave a `running` row. |
| Transaction boundaries | Unspecified. | One DB transaction per listing page (posts + `run_subreddits` progress); one transaction per comment tree; JSONL line(s) written and flushed **before** the DB commit. A crash leaves at most an orphan JSONL line, never a half-written page or tree. |
| Comment harvest of posts with `num_comments == 0` | Wastes a request. | Skip the tree fetch, set `comments_complete=1`, `check_stage=0`, `next_check_at = created_utc + 1d`; the milestone revisit picks it up. |
| Initial backfill cost | ~1,000 posts × 3 subs; trees at ~2 requests avg ≈ 6,000 requests ≈ 60+ minutes with pacing. | Per-run comment budget (default 1,500 requests) with priority = newest first; the queue drains over a few days. Report backlog size in the digest. |
| Huge threads | An AMA with 2,000 comments costs 20+ replacements. | Per-post cap on replacements (e.g., 40); mark incomplete and schedule a follow-up; a later refetch starts fresh (skipped `MoreComments` are not resumable across runs). |
| Leaf deleted comments vanish | Reddit drops `[deleted]` comments with no visible children from trees [C]. | After a **complete** refetch, previously-known comments absent from the tree → batch `info()` them; if returned scrubbed → scrub; if not returned at all → `gone_unconfirmed`, `misses += 1`; scrub at 2 misses. |
| Reconcile comments via `info()` vs refetching trees | `info()` is 100 comments/request but lacks tree context; a tree refetch refreshes hundreds of comments for 1 + N requests. | Tiered: ≤ 30 d: milestone tree refetches (1d/3d/7d/30d); 30 d–1 y: `info()` on posts every 7 d and trees every 30 d; > 1 y: `info()` every 30 d. Keep the tiers configurable. |
| Digest/report files | A markdown digest written on day 1 quotes content deleted on day 2. | Generate reports from the DB on demand; if persisted, keep ≤ 14 days and include titles/links/counts only. Judgment call, but be deliberate. |
| Lock | `flock` is fine on macOS and in a single container on a local volume; unreliable on a network share. | `fcntl.flock` on a file **beside the DB** plus `runs.status='running'` with a heartbeat column; on startup mark stale `running` rows (heartbeat > 2 h) as `crashed`. Exit code 75 when locked. |
| Datasette/Web UI reading concurrently | Readers block writers without WAL. | WAL mode (see §4). |

### 1.4 Deletion vs removal: how it manifests

| Situation | Post (`t3`) | Comment (`t1`) | Conf. |
|---|---|---|---|
| User deleted the item | `author` → `None` (JSON `"[deleted]"`, `author_fullname` key **absent**), `selftext` `"[deleted]"`, title still present, `removed_by_category` `"deleted"`; gone from `/new` | `author` `None`, `body` `"[deleted]"`, `collapsed_reason_code` `"DELETED"`; leaf deleted comments disappear from the tree entirely | [C]/[?] |
| Moderator removed | Title and author remain visible publicly; `selftext` `"[removed]"`; `removed_by_category` `"moderator"`; gone from `/new` | `body` `"[removed]"`, author shown as `None` to non-mods; stays in tree as a placeholder | [C]/[?] |
| Removed by Reddit/filters | `removed_by_category` ∈ {`"reddit"`, `"automod_filtered"`, `"anti_evil_ops"`, `"content_takedown"`, `"copyright_takedown"`, `"community_ops"`, `"legal_operations"`, `"author"`} (observed values, not officially documented) | no `removed_by_category`; body `"[removed]"` | [?] |
| Account deleted, content kept | `author` `None`, `author_fullname` absent, `selftext` intact | `author` `None`, `body` intact | [C] |
| Account suspended | author name visible, content intact | same | [C] |
| Subreddit banned/private | listing 404/403; `info()` on individual items may still return them | | [?] |

Rule for the state machine (pure function, unit-tested): `body/selftext == "[deleted]"` → `deleted_by_author`; `== "[removed]"` → `removed_by_moderator` unless `removed_by_category` says Reddit → `removed_by_reddit`; `author is None` with intact body → `author_state = account_deleted`; not returned by `info()` → `gone_unconfirmed` then `gone`. Scrub = null all content/author/URL columns, replace `raw_json` with a tombstone, delete FTS row, delete `post_themes`, delete snapshot rows' non-numeric fields (they have none), rewrite JSONL. A milestone-1 `probe` command that dumps raw JSON for a known deleted post, a removed post, a deleted comment, and a removed comment turns every [?] above into a fixture.

---

## 2. Ports-and-adapters structure and the cassette layer

### 2.1 Ports (Protocols in `ports.py`)

All ports speak **plain dicts/dataclasses**, never PRAW objects, so `core/` and `services/` never import `praw`.

| Port | Methods | Notes |
|---|---|---|
| `RedditGateway` | `about(name) -> dict`; `iter_new_pages(name, *, max_pages) -> Iterator[Page(items: list[dict], after: str|None)]`; `fetch_tree(post_id, *, more_limit, sort) -> TreeResult(post: dict, comments: list[dict], more_skipped: int, more_skipped_count: int, requests_used: int)`; `info(fullnames) -> list[dict]`; `limits() -> Limits(remaining, used)`; `requests_made -> int` | Raises domain exceptions: `RateLimited(retry_after)`, `AuthFailed`, `SubredditForbidden`, `SubredditNotFound`, `SubredditRedirected(path)`, `TransientError`, `GatewayError`. |
| `RawSink` | `open_run(run_id)`, `write(kind, source, fullname, data)`, `close()`, `rewrite_without(fullnames, run_ids)` | JSONL adapter; in-memory fake for tests. |
| `Clock` | `now() -> int`, `sleep(seconds)` | Injected so tests control time and never sleep. |
| `Notifier` | `notify(level, message)` | stdout/log now; ntfy/Healthchecks later. |

### 2.2 Adapters

| Adapter | Approach | Tradeoff |
|---|---|---|
| `adapters/reddit_praw.py` (recommended v1) | PRAW for auth, pacing, retries, UA. Listings and `info()` via `reddit.request()` (exact wire JSON). Trees via `Submission.comments` + `replace_more` (hard to reimplement well), serialized with a strict `to_raw()` (`vars()` minus `_`-keys; `author`→`name`; `subreddit`→`display_name`; drop `_replies`). Inject a counting `requests.Session` via `requestor_kwargs={"session": ...}` and set `check_for_updates=False`, `timeout=30`. | Trees are "PRAW-attribute JSON" rather than wire JSON; document that in the JSONL line (`"shape": "praw"` vs `"wire"`). |
| Alternative (later) | Everything through `reddit.request()` including `/api/morechildren` and `/comments/{id}/_/{cid}`; mirror PRAW's max-heap algorithm (~100 lines). | Perfect provenance, zero dependence on PRAW object internals; more code to test. |
| `adapters/reddit_fake.py` | In-memory scenario builder: `add_post()`, `add_comment()`, `add_more(children, count)`, `delete()`, `remove()`, `delete_account()`, `fail_next(exc)`, `fail_page(sub, n, exc)`, `rate_limit_next(retry_after)`, `set_status(sub, forbidden|not_found|redirect)`; records every call. Ships in `src/` so `run --gateway fake` works for demos. | Keeps the core 100% offline. |

### 2.3 Recording and fixtures

| Layer | Library | Why | Tradeoffs |
|---|---|---|---|
| Adapter happy paths | **pytest-recording (vcrpy)** | prawcore's own test suite moved from Betamax to VCR.py in 3.1.0 [V]; `--record-mode=none` in CI; `--block-network` enforces no HTTP anywhere in unit tests; cassette path convention `cassettes/<module>/<test>.yaml`. Config: `filter_headers=["Authorization","Cookie","Set-Cookie"]`, `before_record_response` to blank `access_token` in the token response, `decode_compressed_response=True`, match on `["method","scheme","host","path","query"]`. | Cannot simulate timeouts; cassettes contain real Reddit content (see risk in §6). |
| Adapter failure paths | **`responses`** | Deterministic status sequences (429 with `Retry-After`, 503→503→200), exceptions as bodies (`ReadTimeout`), assert exact call counts. Works with prawcore's `requests` Session. | Hand-built payloads; keep them minimal. |
| Normalizer/state machine | **hand-scrubbed JSON fixtures** in `tests/fixtures/json/` | Small, reviewable, PII-free (usernames replaced), stable across PRAW versions; also drive the fake gateway. | Manual upkeep; mitigated by a `probe --save-fixture` helper. |
| Betamax | not recommended | requests-only, less maintained, upstream abandoned it. | — |
| Contract tests | Same parametrized test module runs against `FakeRedditGateway` and `PrawRedditGateway` (cassette) | Keeps the fake honest. | Needs cassettes for each contract case. |

Strong recommendation: create a **personal restricted test subreddit** (readable by anyone, only you can post) and populate it by hand in the browser with the fixture cases you need: a normal post, a post you delete, a post you remove as mod, a deleted comment with children, a leaf deleted comment, a "continue this thread" chain, a crosspost. That gives deterministic cassettes with no third-party content and no compliance concern in git.

Other test libs: `time-machine` (clock), `hypothesis` (random key deletion in JSON), `pytest-alembic` (migrations), `pyfakefs` or a read-only tmpdir (disk failures).

---

## 3. Failure-mode test matrix

| Failure | Expected system behavior | How to simulate |
|---|---|---|
| 429 with `Retry-After: 3` | Adapter catches `TooManyRequests`, logs, `clock.sleep(min(3, 300))`, retries once; on a second 429 raises `RateLimited`; run status `rate_limited`; watermark untouched; exactly 2 requests to that URL. | `responses`: 429 twice then assert call count; core: `fake.rate_limit_next(3)` with fake clock asserting `sleep(3)` called. |
| 401 at token endpoint (bad secret) | `AuthFailed` before any listing request; no `runs` row left `running`; exit code 78 (EX_CONFIG); notifier fires. | `responses` on `/api/v1/access_token` → 401. |
| 401 `invalid_token` mid-run (token expiry) | prawcore refreshes and retries transparently; run continues; `api_requests` includes the retry. | `responses` sequence: 200 token, 401 with `WWW-Authenticate: Bearer realm="reddit", error="invalid_token"`, 200 token, 200 listing. |
| 403 private subreddit | `SubredditForbidden`; subreddit `status='forbidden'`, `consecutive_failures += 1`; other subs proceed; run `partial`; data retained. | `responses` 403 on `/r/x/about`; fake: `set_status("x","forbidden")`. |
| 404 banned subreddit | `SubredditNotFound`; `status='not_found'`; alert; existing content flagged for the "banned sub" policy decision (§6). | `responses` 404; fake `set_status`. |
| Nonexistent subreddit | prawcore `Redirect` (`.path` = `/subreddits/search?...`) → `SubredditRedirected`; `status='redirect'`; disabled automatically after N runs with alert. | `responses` 302 with `Location: /subreddits/search?q=x`. |
| Subreddit "renamed"/case mismatch/redirected | Reddit does not rename subs; realistic cases: configured `VideoEditing` vs about.json `display_name` casing → normalized, no duplicate row; `subreddit_id` (t5_) differs from stored → abort that sub with a loud alert (identity changed). | Fixture about.json with different casing; second fixture with a different `name`. |
| 5xx mid-page | prawcore retries 3× (seconds); then `ServerError` → outer retry (30 s, 2 m, 5 m via fake clock); success → page committed; persistent failure → that sub fails, others continue, watermark not advanced, `stop_reason='error'`. | `responses` 503,503,200 and 503×7; fake `fail_page("x", 2, TransientError)`. |
| Network timeout mid-page | Same path via `RequestException(ReadTimeout)`. | `responses` body=`ReadTimeout()`; adapter test asserts `timeout=30` passed. |
| Crash between pages | Pages 1–2 committed atomically; rerun yields no duplicate rows; `first_seen_at` unchanged; watermark/gap flags unchanged after crash and correct after rerun; JSONL has duplicate lines with distinct `run_id` and dedupes by fullname. | Fake raises `CrashInjected` after page 2; run twice; assert `COUNT(*)`, `first_seen_at`, watermark. |
| Crash mid comment-tree | Nothing committed for that post (tree is one transaction); `comments_fetched_at` unchanged; post still due; rerun completes it. | Fake raises after N comments serialized; assert no comment rows for the post; rerun. |
| Overlapping run | Second process exits 75 with "lock held", writes no `runs` row (or `skipped_locked`), makes zero API calls. | Test holds `flock` on the lock file, invokes CLI via `CliRunner` with fake gateway; assert `fake.calls == []`. |
| DB locked by another writer | Page write retries with `busy_timeout=30 s`, then fails the run cleanly (`failed`), watermark untouched. | Second `sqlite3` connection does `BEGIN IMMEDIATE` and holds; use small `busy_timeout` in test settings. |
| Stale `running` row from a crashed process | Marked `crashed` at next startup; new run proceeds. | Insert a `runs` row with old heartbeat; run; assert status. |
| Malformed/missing fields | Optional fields → NULL with typed coercion; required (`id`, `created_utc`, `subreddit`) missing → row goes to `raw_rejects(run_id, raw_json, error)`, run continues; raw JSON always preserved. | Fixtures: `author_fullname` absent, `edited` as `false` and as float, `selftext` null, `distinguished` null, unknown keys; `hypothesis` strategy deleting random keys. |
| Deleted/removed scrubbing | State transitions as in §1.4; all content columns null; `raw_json` tombstone; FTS returns 0 hits for a canary token; `post_themes` gone; JSONL rewritten; `grep -r canary data/` finds nothing (the compliance canary test). | Fake: fetch live at t0 with a unique canary phrase, `delete()`/`remove()`, advance clock, run `reconcile`. |
| Account deletion | `author*` nulled everywhere, `authors` row deleted, content kept. | Fake `delete_account(name)`. |
| Item missing from `info()` | `gone_unconfirmed`, `misses=1`, content kept; second miss → scrub. | Fake `info()` omits the id on two runs. |
| Config validation errors | Missing client id, subreddit name failing `^[A-Za-z0-9_]{3,21}$`, invalid regex rule, negative budgets, unwritable data dir → exit 78 before any API call. | `CliRunner` with bad config + fake gateway; assert zero calls. |
| DB file missing at run time | `fetch` refuses ("DB not found; run `db init`") — protects against an unmounted Docker volume. | Point settings at a nonexistent path. |
| DB behind Alembic head | Refuse to run; exit 78 with the pending revision list. | Downgrade a temp DB one step, run `fetch`. |
| Disk/JSONL write failure | JSONL write precedes commit; `OSError` aborts the page, no partial commit, run `failed`, notifier fires. | Read-only raw dir (`chmod 0500`) or `RawSink` fake raising `OSError(ENOSPC)`. |
| Clock skew (local clock ±1 day) | Stop rule and milestones use `created_utc` and monotonic deltas; results identical. | `time_machine.travel()` ±86400 s; run against the same fixtures; assert identical rows/watermark. |
| Empty subreddit | Zero pages of items, `stop_reason='exhausted'`, watermark unchanged, run `ok`. | Fake with no posts. |
| Cloudflare/HTML 403 body | `BadJSON`/`Forbidden` → abort run (not per-sub), alert, no tight retry. | `responses` 403 with `text/html` body. |
| Listing shifts between pages (same post on two pages) | Upsert dedupes; counts correct. | Fake returns overlapping pages. |
| Quarantined/NSFW subreddit | `Forbidden` with `reason: quarantined` → `status='quarantined'`, disabled with alert (opt-in requires a logged-in user; out of scope). | Fixture 403 JSON. |

---

## 4. Migration, upgrade, and backup practices (SQLite + Alembic, later Docker)

| Practice | Recommendation |
|---|---|
| Alembic on SQLite | `render_as_batch=True` in `env.py` (SQLite lacks most `ALTER`); a `MetaData(naming_convention=...)` so batch ops can drop constraints by name; FTS virtual tables and triggers created with `op.execute()` using `IF NOT EXISTS`; `include_object` excluding `%_fts%` shadow tables from autogenerate; `PRAGMA foreign_keys=OFF` during batch migrations (SQLAlchemy event enables it per connection otherwise). |
| Pre-migration backup | `db upgrade` always does `sqlite3.Connection.backup()` (online, WAL-safe) to `backups/pre-migrate-<from_rev>-<to_rev>-<utc>.sqlite`, runs `PRAGMA quick_check` on the copy, then migrates, then `PRAGMA integrity_check` and `foreign_key_check`; on failure it restores the copy and exits non-zero. Keep the last 3 pre-migration backups. |
| Migration tests | `pytest-alembic` built-ins: `test_single_head_revision`, `test_upgrade`, `test_model_definitions_match_ddl`, `test_up_down_consistency` (enable with `--test-alembic`). Plus your own: upgrade-from-seeded-fixture per prior revision (`tests/fixtures/db/<rev>.sqlite` generated by a script that runs migrations to `<rev>` and seeds data), asserting row counts, FTS query works, and `PRAGMA integrity_check == ok`; a downgrade-one-step-and-back test with data. |
| `schema_version` on rows | Rename to `normalizer_version`: the version of the JSON→columns code that produced the row. `reprocess --below N` re-normalizes from `raw_json` without touching Reddit. The DB schema version lives in `alembic_version` and is stamped into `runs.schema_rev`. |
| Raw JSON for reprocessing | `raw_json` column (scrubbable) is the reprocessing source; JSONL is short-retention provenance. Write a test that a full reprocess from `raw_json` reproduces identical normalized rows. |
| Pinned deps | `uv lock` committed; `uv sync --frozen` in Docker; `requires-python` pinned to one minor; Dependabot/Renovate for `praw`/`prawcore` bumps with cassette tests as the gate. |
| Versioning | Single source in `pyproject.toml`; `__version__` via `importlib.metadata`; UA built from it; `runs.app_version` recorded; SemVer: bump minor for new commands/schema migrations, patch for fixes. Reddit can then block a bad version without blocking you entirely. |
| Health check | `doctor` (exit 0/1): config valid, DB reachable and at head, `integrity_check` (quick), free disk > threshold, last successful run age < 36 h, lock not stale, optional auth ping (1 request). Docker `HEALTHCHECK CMD doctor --no-network`. Healthchecks.io/ntfy ping at end of each successful run (dead-man's switch). |
| Migrations in the container entrypoint | `set -euo pipefail`; verify the volume mount contains the DB (or `INIT=1` to create); `db upgrade --backup`; then `exec supercronic /etc/crontab`. Migration and runs share the same flock, so a cron-triggered run cannot start during a migration. Never auto-downgrade. |
| WAL and pragmas | On every connection (SQLAlchemy `connect` event): `PRAGMA journal_mode=WAL` (persistent), `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=30000`, `temp_store=MEMORY`; optionally `secure_delete=ON` so scrubbed bytes are overwritten. At end of run: `PRAGMA wal_checkpoint(TRUNCATE)`. The DB must live on a **local** filesystem (QNAP local volume, not a network share). |
| VACUUM/backup | Daily `VACUUM INTO 'backups/daily-<date>.sqlite'` after the run (compact, consistent copy; needs ~1× DB size free); retention 7 daily + 4 weekly; monthly `VACUUM` only if free pages > 20%. Restore = `db restore <file>` (stops on lock, swaps files atomically). |
| Expand/contract | Add nullable column → deploy code writing both → backfill from `raw_json` in batches → switch reads → later drop old column in a separate release. Never rename in place on SQLite. |

---

## 5. Repo layout, CLI, milestones

### 5.1 Layout (src layout)

```
<repo>/
  pyproject.toml  uv.lock  .python-version  alembic.ini  README.md
  config.example.yaml  .env.example
  src/<package>/
    __init__.py            # __version__
    cli.py                 # typer app
    settings.py            # pydantic-settings: env + config.yaml
    ua.py                  # user_agent() from __version__
    ports.py               # Protocols + domain exceptions
    core/                  # pure, no I/O
      models.py normalize.py paging.py deletion.py milestones.py themes.py budget.py digest.py
    adapters/
      reddit_praw.py reddit_fake.py jsonl_sink.py clock.py notify.py
    db/
      engine.py (pragmas) schema.py (SQLAlchemy models) repo.py (upserts) fts.py backup.py
      migrations/env.py  migrations/versions/
    services/              # use cases wiring ports + repo
      lock.py runs.py fetch_new.py harvest_comments.py revisit.py reconcile.py scrub.py tag_themes.py report.py export.py config_io.py doctor.py
  tests/
    unit/ core/…  db/ (migrations, repo, fts)  adapters/ (cassettes/, responses)  e2e/ (CLI + fake gateway + tmp DB)
    fixtures/json/  fixtures/db/
  deploy/
    launchd/<label>.plist  docker/Dockerfile  docker/entrypoint.sh  docker/crontab  compose.yaml
```

### 5.2 CLI (typer)

| Command | Purpose |
|---|---|
| `run [--budget N] [--no-comments] [--dry-run]` | Daily composite: fetch → comments → revisit → reconcile → tag → report → backup → checkpoint → ping. |
| `fetch [--subreddit X] [--pages N]` | `/new` sweep only. |
| `comments [--post ID] [--budget N]` | Drain the tree-harvest queue. |
| `revisit [--budget N]` / `reconcile [--older-than 30d]` | Milestone refetches / `info()` sweeps + scrub. |
| `tag [--all]` | Theme tagging (retag on rules change). |
| `report [--date] [--out]` | Digest markdown from the DB. |
| `export posts|comments --format jsonl|csv [--since]` | Exports (live content only). |
| `subs add|remove|list|enable|disable` · `themes list|add-rule|test` | DB-backed config. |
| `config validate|show|export|import` | YAML round-trip (no secrets). |
| `db init|upgrade|downgrade|current|backup|restore|vacuum|check` | Schema and files. |
| `doctor [--no-network]` · `auth-check` · `probe <fullname> [--save-fixture]` | Health, auth ping printing `auth.limits`, raw JSON dump for verifying [?] items. |

### 5.3 Milestones

| # | Milestone | Definition of done | Tests |
|---|---|---|---|
| M0 | Bootstrap | `uv` installed; Python installed via uv; `run --version`; ruff clean; `config validate` rejects bad configs; `--block-network` on in pytest. | Settings unit tests; UA format test (`python:<id>:v<ver> (by /u/<user>)`). |
| M1 | First authenticated fetch | `auth-check` fetches `about.json` for r/premiere and prints `limits`; `probe` dumps raw JSON for a deleted post, removed post, deleted/removed comment (fills the [?] gaps into fixtures). One cassette recorded and passing with `--record-mode=none`. | Adapter cassette test; request-count assertion (exactly 2 HTTP calls: token + about). |
| M2 | Posts ingestion | Schema rev 1; `db init/upgrade`; `fetch` writes posts + JSONL, idempotent rerun, watermark/gap logic, `run_subreddits` rows. | Fake-gateway e2e; crash-between-pages; short pages; duplicate pages; pytest-alembic suite; timestamp-type test. |
| M3 | Comment trees + budget | `comments` drains queue newest-first within budget; `comments_complete` semantics; `more` accounting; one transaction per tree. | Fixtures with `more`/continue-thread nodes; crash mid-tree; budget exhaustion leaves items queued. |
| M4 | Revisit, reconcile, scrub | Milestones via `next_check_at`; state machine; `info()` misses; JSONL rewrite; FTS sync; author scrub. | All §1.4 scenarios; the canary compliance test; `info()` ordering/absence tests. |
| M5 | Themes + digest | Rules with `regex` timeout; retag on rules hash; digest with new posts, hot threads, backlog, gaps, subreddit statuses. | Rule engine unit tests (incl. ReDoS timeout); digest golden-file test. |
| M6 | Reliable daily run (Mac, launchd) | `run` composite with lock, stale-run cleanup, backups, checkpoint, `doctor`, Healthchecks ping; 7 consecutive successful launchd runs; digest read each morning. | Failure matrix rows implemented; launchd plist lints (`plutil -lint`). |
| M7 | Docker (Mac → QNAP) | Image with `uv sync --frozen --no-dev`, entrypoint migration, supercronic, volume layout, `HEALTHCHECK`; runs a week on Mac Docker, then on QNAP local volume. | Entrypoint test with empty volume (refuses), with DB behind head (upgrades with backup). |

---

## 6. Open questions and risks to decide

1. **JSONL policy**: rewrite-on-scrub with 30-day retention (recommended) vs. keep-forever (non-compliant) vs. no sidecar (raw_json in DB only).
2. **Reconcile cadence beyond 30 days**: Reddit's 48-hour guidance vs. the tiered schedule proposed; full `info()` sweeps are cheap for years (10k posts = 100 requests) but comment sweeps grow (~1,000 requests per 100k comments). Pick the tiers.
3. **Banned/private subreddit content**: scrub everything (strict reading) or retain (private research store)? Needs an explicit policy flag.
4. **Cassettes with third-party content in git**: mitigate via the personal restricted test subreddit; decide whether the repo will ever be public.
5. **PRAW-attribute JSON vs. wire JSON for trees**: accept the hybrid (recommended) or reimplement `morechildren` for perfect provenance.
6. **Initial backfill depth**: full 1,000/sub with trees (≈1 hour of paced requests spread over days) or posts-only first.
7. **Score snapshots**: include numeric snapshots in v1 (recommended, cheap) or defer.
8. **Regex rules authored in the UI**: `regex` with timeouts and pattern caps, or keyword-only rules in v1.
9. **Digest persistence**: on-demand only vs. 14-day retention of markdown files.
10. **Timezone** for "daily" and digest boundaries (local vs UTC); milestone math should stay in UTC epoch.
11. **Secrets in Docker**: env file vs Docker secrets on QNAP; `.env` must never be exported with config.
12. **Interim browsing**: run Datasette read-only against the WAL DB until the FastAPI UI lands (zero code, good for validating the schema early).
13. **Live-verification items marked [?]**: `removed_by_category` values, comment `collapsed_reason_code`, leaf-deleted-comment disappearance, `info()` behavior for deleted items and banned subs, `/comments` `limit` clamp, quarantined-sub response shape, sticky ordering in `/new`. The `probe` command exists to close these.
14. **Platform note**: `uv` is not installed and system Python is 3.14; the project must pin one minor via `.python-version` and `requires-python`.

(Disposition of these questions is recorded in the plan's decisions table and in `insights/INSIGHTS_2026-09-12.md`.)
