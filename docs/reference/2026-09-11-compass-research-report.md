# Building a Personal, Rules-Compliant Reddit Insight Miner (2026)

## TL;DR
- **Build it on the official Reddit Data API via PRAW with an authenticated "script" app, store into SQLite, browse with Datasette, and schedule a daily job on your QNAP** — this is fully within Reddit's rules, free for personal/non-commercial use (100 queries/minute per OAuth client), and the single biggest 2026 change is that the old "add .json to a URL" trick is dead (Reddit shut down unauthenticated JSON access on May 28, 2026), so authenticated API access is now the *only* compliant path.
- **Do not automate replies, do not use proxies, and do not use a roving mobile hotspot** — automated commenting is the fastest route to an account ban, and a constantly-changing IP looks *more* suspicious, not less. Surface deep links and reply by hand. A normal home IP running one small daily job is exactly what Reddit's free tier is designed for.
- **Start minimal**: a ~150-line Python/PRAW script that pulls `/new` from 3–6 Premiere/editing subreddits into SQLite with fullname-keyed dedup, plus a separate on-demand comment-tree harvester. Graduate to search-term monitoring, LLM summarization, and richer UI only once the daily fetch is boringly reliable.

## Key Findings

1. **The rules got stricter in 2026.** Reddit's Data API Wiki (updated May 11, 2026) confirms: authenticated OAuth clients get **100 queries per minute (QPM) per client ID, averaged over a 10-minute window**; non-OAuth traffic is *blocked*, not throttled. Unauthenticated `.json` endpoints were deprecated May 28, 2026, and old.reddit.com began requiring login on June 30, 2026. The compliant path is now narrow: authenticated API only.
2. **Storage obligation you cannot ignore:** Reddit requires you to delete any content that users delete or mods remove, and explicitly says retaining deleted content "even if disassociated, de-identified or anonymized" violates their terms, recommending you purge within 48 hours. This shapes the whole data model — you need a sync-and-purge loop, not a write-once archive.
3. **Commercial use is a real, expensive line.** Free tier covers personal/hobby/research use. The moment you monetize insights, you need a separate commercial agreement. The often-quoted **$0.24 per 1,000 API calls** originates in Reddit's own June 2023 announcement, where CEO Steve Huffman said "Reddit needs to be a self-sustaining business, and to do that, we can no longer subsidize commercial entities that require large-scale data use," with apps above 100 QPM "subject to the new charge of $0.24 per 1,000 API calls." In practice there is nothing between the free tier and a large commercial commitment — 2026 breakdowns (Prowlo, Redditapis) report the commercial tier carries roughly a **$12,000/year minimum** including tens of millions of calls, i.e. "nothing between the free tier's 100 queries per minute and a $12,000/mo commitment." Training any ML/AI model on Reddit content needs a *separate* license even on paid tiers.
4. **PRAW is the right tool and is actively maintained** (4,222 GitHub stars, last updated Aug 10, 2026; BSD-2 license; Python 3.10+). It handles rate limiting automatically by reading Reddit's response headers, so you don't write sleep loops.
5. **The 1,000-item listing cap is real and permanent**, but irrelevant for your use case if you poll often enough — none of your target subreddits produce anywhere near 1,000 posts/day.
6. **Good, simple reference code exists** — `reddit-to-sqlite`, `reddit-user-to-sqlite`, and the Datasette ecosystem — that match your "simple script + polish" preference far better than heavyweight archivers like BDFR.

### Your target subreddits (2026, approximate)

Third-party analytics sites (GummySearch, RedPulse, PainOnSocial) are the practical source for these; they sync periodically and differ by ±10k depending on date. Reddit's own `about.json` figures could not be independently pulled for this report.

| Subreddit | ~Members (2026) | Notes / source |
|---|---|---|
| **r/VideoEditing** | ~527k (GummySearch, Sept 11 2026; earlier snapshot 516k) | Hobby/amateur focus; "sister sub /r/editors." Active daily flow of advice/tech-support posts (tens/day). |
| **r/premiere** | ~187k (GummySearch, Sept 11 2026); ~180k (PainOnSocial, Oct 2025) | The **primary Adobe Premiere Pro** community. |
| **r/editors** | ~182,317 (RedPulse, Aug 31 2026); ~196k (GummySearch) | Professional post-production focus; "ASK a PRO" threads. |
| **r/PremierePro** | count unconfirmed | Confirmed to exist (Glyph Tech "Top 10" list) but a **secondary/smaller** alternate to r/premiere. |
| **r/AdobePremierePro** | **could not confirm exists** | Did not surface in any analytics source; the canonical sub is **r/premiere**. Likely nonexistent or a redirect. |
| **r/videoediting** (lowercase) | count unconfirmed | Distinct low-traffic variant of r/VideoEditing; exists but small. |

**Recommended starting set:** r/premiere, r/VideoEditing, r/editors — and optionally r/AfterEffects and r/DavinciResolve if you want adjacent editing topics. Combined, these produce well under 1,000 posts/day, so daily polling gives you complete coverage with enormous headroom.

## Details

### 1. Reddit API rules and limits (highest priority)

**Rate limits (current, 2026).** Per Reddit's official Data API Wiki (support.reddithelp.com, "Reddit Data API Wiki," updated May 11, 2026):
- **100 QPM per OAuth client ID**, averaged over a (currently) 10-minute window to allow bursting — a budget of ~1,000 requests per 10 minutes.
- **"Traffic not using OAuth or login credentials will be blocked, and the default rate limit will not apply."** Unauthenticated access is no longer a fallback.
- Chat limits (if ever relevant): 2,000 messages/day per recipient, 3,000/day total; bots can join up to 300 chat rooms/day.
- **The commonly-cited "60 requests/minute" figure is outdated.** It survives verbatim in Reddit's archived GitHub wiki (github.com/reddit/reddit/wiki/api: "Clients connecting via OAuth2 may make up to 60 requests per minute") — but that repo was archived Nov 9, 2017 and predates the July 2023 change to 100 QPM. Ignore it. The "10 QPM unauthenticated" figure is also historical; unauthenticated is now simply blocked.

**Auth types and their treatment:**
- **Script app** (what you want): tied to your own account, one client ID + secret, simplest OAuth flow. Registered at reddit.com/prefs/apps.
- **Installed app / userless ("application-only") auth**: for distributed client apps; can do read-only userless OAuth. Since July 2023 the rate limit is per client ID (not per client-ID/user pair), so there's no throughput advantage to userless for a single-user tool.
- **Unauthenticated/anonymous**: blocked. Do not build on it.

**The rate-limit headers.** Every response includes:
- `X-Ratelimit-Used` — approximate requests used this period
- `X-Ratelimit-Remaining` — approximate requests left
- `X-Ratelimit-Reset` — approximate seconds until the window resets

Best practice: read these programmatically and back off when `Remaining` gets low, rather than hardcoding "100" (Reddit can and does vary limits by client). PRAW does this for you.

**User-Agent — get this exactly right.** Reddit's required format (verbatim from the Data API Wiki):
```
<platform>:<app ID>:<version string> (by /u/<reddit username>)
```
Example: `User-Agent: android:com.example.myredditapp:v1.2.3 (by /u/kemitche)`. Yours might be: `python:com.yourname.insightminer:v0.1.0 (by /u/yourusername)`.

Reddit says: *"Many default User-Agents (like 'Python/urllib' or 'Java') are drastically limited"* and *"NEVER lie about your User-Agent. This includes spoofing popular browsers and spoofing other bots. We will ban liars with extreme prejudice."* A generic or spoofed UA is one of the most common causes of throttling/blocking. Including a version string lets Reddit block only broken versions rather than your whole app.

**Account age / karma.** Reddit-wide API access doesn't require karma, but individual subreddits use AutoModerator to filter new/low-karma accounts (thresholds commonly ~50–500 comment karma and account age of a few weeks; e.g., AutoModerator rules like `author: comment_karma: "< 100" action: remove`). This matters only if you *post*; for read-only harvesting it's irrelevant. A brand-new account doing high request volume plus writes is a suspicion signal, so if you ever reply, use an aged, established account.

**Storage / retention / deletions.** From the Data API Wiki and Data API Terms (Last Revised July 20, 2026):
- You must remove any content a user deletes or a mod removes — title, body, embedded URLs, everything.
- When a user account is deleted, you must delete all their user-ID info (t2_*) and author-identifying info (name, profile URL, avatar, flair) from their posts/comments.
- Retention of deleted content, even anonymized, is a violation. Reddit "strongly recommends routinely deleting any stored user data and content within 48 hours."
- Content must be attributed and linked back to Reddit.

*Practical implication:* You should re-fetch stored items periodically and reconcile deletions/removals. For a personal tool, a pragmatic reading is to re-poll each stored item on a schedule and mark/purge anything returning `[deleted]`/`[removed]` or 404. Store point-in-time snapshots but honor deletions promptly.

**Commercial vs non-commercial.** Free tier = personal, hobby, research, moderation. The Responsible Builder Policy states: *"If you'd like to use Reddit data for commercial purposes, you'll need to get explicit written approval."* The trigger is when you store/aggregate/sell Reddit data as a service to others, or use insights to drive a revenue-generating business. A gray area: using insights to inform *your own* business decisions. Reading Reddit to decide what product to build is different from productizing Reddit data. If you monetize the *data or insights themselves*, or train models, you cross the line and need a separate agreement (the ~$12,000/year commercial commitment applies, and AI training needs its own license). A cautionary datapoint: GummySearch itself, a 140,000-user Reddit research product, shut down to new signups on Nov 30, 2025 after failing to secure a Reddit commercial API license — evidence Reddit enforces this line against products.

**old.reddit.com .json endpoints.** As of May 28, 2026, unauthenticated `.json` returns 403 (Reddit's r/modnews post "Protecting communities from scrapers and platform abuse": *"We'll also be shutting down unauthenticated .json endpoints. These endpoints can be used to scrape Reddit without accountability. Logged-in and authenticated access won't be impacted."*). Using it is both non-functional and against Reddit's stated intent. The authenticated API returns the same JSON legitimately — use that. Reddit has also flagged RSS as a possible next surface to close.

**Anti-scraping enforcement 2024–2026.** Reddit uses TLS fingerprinting and IP-reputation checks; generic HTTP clients and datacenter/cloud IPs can get 403 even with a valid UA. Triggers for blocks: unauthenticated requests, generic/spoofed UAs, ignoring 429/Retry-After, hammering endpoints, and running from flagged IP ranges. **429 = rate-limited (temporary); 403 = forbidden/blocked; repeated violations can escalate to account suspension.** The consistent developer lesson: authenticate properly, set a real UA, respect headers, and keep volume modest.

### 2. The 1,000-item listing cap and historical data

**The cap.** Listing endpoints (`/new`, `/hot`, `/top`) return at most ~1,000 items via `after`/`before` fullname cursor pagination (25 default, up to 100 per page). You cannot page past ~1,000. This is a hard Reddit limit; BDFR's own docs note "we cannot bypass" it.

**Why it doesn't hurt you.** Your busiest target, r/VideoEditing, produces on the order of tens of posts per day — nowhere near 1,000. To never miss items, poll frequently enough that fewer than ~1,000 new posts accumulate between runs. For these subs, **once daily is safe with a large margin**; even weekly would rarely miss anything. Rule of thumb: required minimum poll interval (days) = 1,000 ÷ (posts per day). At ~40 posts/day that's ~25 days of headroom.

**Catching up after downtime.** Track a "last seen" fullname watermark per subreddit. On restart, page `/new` backward until you hit a known ID or the 1,000 cap. If you were down long enough that >1,000 posts accrued (won't happen at daily cadence here), you'd have a gap that only historical dumps can backfill.

**Historical / bulk data in 2026:**
- **Pushshift**: restricted to verified moderators since May 2, 2023. Per Reddit Help ("Pushshift Access Request"): access is "reinstated for verified Reddit moderators … limited to moderation use cases only," and "each moderator will also need explicit approval from Reddit." Over 1,700 scholarly articles once relied on it. Not available to the public — don't build on it.
- **Arctic Shift** (github.com/ArthurHeitmann/arctic_shift, ~1.5k stars, actively maintained): the de-facto successor. Monthly bulk dumps (2005→present), a limited free query API, and a web UI/downloader for individual subs/users. Best free backfill option. Note: its collection rescans/overwrites ~36 hours after posting, so like Pushshift it can capture-then-lose some later-deleted content.
- **Academic Torrents dumps**: Reddit posts/comments split by subreddit, 2005-06 through 2023-12 (NDJSON/zst). Good for deep history; large.
- **PullPush.io**: free Pushshift-schema drop-in with partial post-2023 coverage and tight limits.
- Caveats: these archives often contain content users later deleted — which conflicts with Reddit's deletion-honoring terms. Treat backfill data carefully; spot-check coverage; redistribution is restricted.

**Monitoring strategy — polling vs streaming.** PRAW offers `subreddit.stream.submissions(skip_existing=True)`, which yields new posts as they appear. Per PRAW docs, without `skip_existing` the stream first replays "up to 100 historical submissions"; with `skip_existing=True`, "To only retrieve new submissions starting when the stream is created." It internally polls `/new`, dedupes (via a bounded set), and backs off. Tradeoffs (per docs and issues #1025/#16): streams are best-effort and "may drop some submissions" on high-volume feeds, and the generator can break on unhandled exceptions (wrap in `while True: try/except`, use `pause_after=None, skip_existing=True`). You can stream a combined feed: `reddit.subreddit("premiere+VideoEditing+editors").stream.submissions(skip_existing=True)`. For a **daily batch** job, plain `/new` polling with a persisted watermark is simpler, more robust, and easier to reason about. **Recommendation: poll `/new` on a schedule** for the core miner; consider a stream only if you later want near-real-time alerts.

### 3. Libraries and tooling

- **PRAW** (github.com/praw-dev/praw, **4,222 stars**, last updated **Aug 10, 2026**, BSD-2, Python 3.10+): actively maintained (v8.x line; changelog "Bumped prawcore to 3.0.2," dropped Python 3.9 after its 2025-10-31 EOL; prawcore's own current release is v4.0.0, June 13, 2026). Handles rate limiting dynamically from response headers — "no need to introduce sleep calls." `ratelimit_seconds` (default 5) controls how long it silently waits on write rate-limit warnings; `window_size` (default 600) matches Reddit's window. Strengths: mature, well-documented, correct-by-default rules compliance. Limits: synchronous; the 100 QPM cap is shared across all instances/threads sharing one client ID, so adding workers doesn't add throughput.
- **Async PRAW** (github.com/praw-dev/asyncpraw, **154 stars**, last updated **Aug 10, 2026**, BSD-2): official async version, same features, for asyncio environments. Overkill for a daily batch job.
- **prawcore / asyncprawcore**: the low-level HTTP layers; you won't touch these directly.
- **prawtools**: archived (last update Dec 2022) — don't rely on it. **prawdditions**: archived (2020), no longer maintained.
- **aPRAW** (Dan6erbond/aPRAW): a separate async wrapper, effectively abandoned. Avoid.
- **JavaScript — snoowrap / snoostorm**: long-popular but effectively unmaintained for years; risky in 2026. If you must use JS, verify recent commits first.
- **RedditWarp** (Python): a well-designed alternative wrapper, less widely used than PRAW; viable but smaller community.
- **Go/Rust**: `graw` (Go) and various Rust crates exist but are niche and less maintained; not worth it given your Python bias.

All the maintained wrappers refresh OAuth tokens automatically (tokens expire after 1 hour) and respect rate limits. **Bias strongly toward PRAW.**

### 4. Existing open-source projects — fork or learn from

| Project | Stars | Status | License | Verdict |
|---|---|---|---|---|
| **catherinedevlin/reddit-to-sqlite** | small | Dogsheep-based | — | **Best reference/fork candidate.** Pulls posts+comments for a subreddit or user into SQLite; creates `posts`, `comments` tables + unified `items` view; idempotent (safe to re-run, "will refresh already-saved results"). Pairs with Datasette. Uses PRAW. Simple. |
| **xavdid/reddit-user-to-sqlite** | small | maintained-ish | — | Good reference. User-centric (comments+posts), deliberately slimmed schema because "Reddit's API has a lot of junk in it," idempotent user refresh. Good patterns for schema design. |
| **simonw/datasette + sqlite-utils** | 9k+ | very active | Apache-2 | **Adopt for storage-to-UI.** Not a scraper — the browse/search/JSON-API layer on top of your SQLite. `sqlite-utils` builds/reshapes the DB; Datasette serves it as a filterable website with full-text search. |
| **Serene-Arc/bulk-downloader-for-reddit (BDFR)** | ~2.6k | maintained | GPL-3 | **Learn from, don't fork.** Powerful media/submission archiver with an SQLite hash-dedup mode (via BDFRx fork by OMEGARAZER), Docker wrappers, cron-friendly. But media-download-centric and more complex than you want for text/comment insight mining. |
| **ArthurHeitmann/arctic_shift** | ~1.5k | active | — | For historical backfill only (see §2), not live monitoring. |

**Recommendation:** treat `reddit-to-sqlite` as your architectural template (or literal starting point), layer Datasette for the UI, and borrow BDFR's ideas (hash/ID dedup DB, `--no-dupes`, config-driven runs) without inheriting its complexity.

### 5. Storage and data model

**Format choice — opinionated ladder:**
- **SQLite (start here).** Perfect for daily append + dedup + later querying on a single machine. Zero server, one file, ACID, excellent Python support, full-text search (FTS5), and instant browsability via Datasette. For years and millions of rows of text, SQLite is more than enough.
- **JSONL flat files (use *alongside* SQLite, not instead).** Keep the raw API JSON per fetch as append-only `.jsonl` for provenance and easy LLM batching. It's the ideal shape to feed Claude later.
- **DuckDB (graduate here for analytics).** If/when you do heavy analytical queries (aggregations, trend detection across millions of rows), DuckDB is dramatically faster than SQLite for OLAP and reads Parquet/JSONL directly. Add it as an analysis layer over the same data; don't replace SQLite as the system of record.
- **Postgres (only if multi-user/concurrent-writer).** Overkill for single-user. Graduate only if you outgrow a single machine or need concurrent writers/network access.

**Recommendation:** SQLite as system of record + raw JSONL for provenance; add DuckDB for analytics later; skip Postgres unless you go multi-user.

**Data model best practices:**
- **Primary keys = Reddit fullnames/IDs.** Use the base-36 ID (or full `t3_`/`t1_` fullname) as the PK for submissions and comments. This makes dedup trivial (`INSERT OR IGNORE` / upsert).
- **Capture, for submissions:** id/fullname, subreddit, author (+ author fullname), title, selftext, url, created_utc, score, upvote_ratio, num_comments, flair, over_18, permalink, is_self, link_flair_text, plus your provenance fields.
- **For comments:** id/fullname, link_id (parent submission), parent_id, author, body, created_utc, score, depth, permalink.
- **Mutable fields (score, edits, deletions, removals):** these change over time. Two-table pattern: a stable "current state" row (upserted) plus an optional "snapshots" table capturing `(id, fetched_at, score, num_comments, body_hash)` when you want point-in-time history. For a first version, upsert current state and record `first_seen_at` / `last_fetched_at`.
- **Store the raw JSON blob** in a `raw_json` column (or the JSONL sidecar) alongside normalized columns. Disk is cheap; reprocessing is priceless when your schema evolves.
- **Provenance columns on every row:** `fetched_at` (UTC), `source_query` (e.g., "r/premiere/new" or a search term), `schema_version`, and optionally the client/UA version. This lets you sort, differentiate, and re-run migrations confidently.

**Comment-tree expansion cost — budget carefully.** In PRAW, `submission.comments.replace_more(limit=N)` resolves "load more comments" placeholders. Per PRAW docs, verbatim: *"Each replacement requires 1 API request"* and *"each replacement will discover at most 100 new Comment instances."* So a fully-loaded deep thread with T comments costs roughly ⌈T/100⌉+ requests.
- `limit=0` → remove all "more" links with **zero** extra requests (keep only already-loaded top comments) — cheapest.
- `limit=32` (default) → up to 32 expansions.
- `limit=None` → expand everything (expensive/slow on big threads); follow with `submission.comments.list()` to flatten.
- Use `threshold` to skip low-value expansions (note: "continue this thread" links appear to have 0 children, so a threshold >0 skips them). Loop with try/except on `prawcore.TooManyRequests` (raised when used concurrently).

*Budgeting:* At 100 QPM you have generous room for daily post capture, but don't blindly `replace_more(limit=None)` on every thread. **Tier your harvesting:** capture all new *posts* cheaply daily; only drill into full comment trees for threads you flag as interesting. A single 500-comment thread can cost 5+ requests; a hundred such threads is 500+ requests — fine occasionally, wasteful daily. Also note the docs' caveat: `submission.num_comments` may not exactly match the number extracted.

**Idempotency & watermarks:** Make every run safe to re-run (upsert by ID). Track a per-subreddit `last_seen_fullname` and/or `last_run_utc`. Incremental sync = fetch `/new` until you hit the watermark, upsert, advance the watermark.

### 6. Scheduling and hosting

**Scheduler options:**
- **OS cron** — simplest; fine on Linux/NAS. One line, well-understood.
- **systemd timers** — more robust than cron (logging via journald, dependency handling, `Persistent=true` catches missed runs after downtime). Best on a Linux box you control.
- **APScheduler (in-process Python)** — good if you want one long-lived Python process managing schedules; adds a dependency and a process to keep alive.
- **Docker + scheduler** — clean, reproducible; pair a Python image with cron/supercronic (supercronic is designed for containers — doesn't need root, logs to stdout). Matches QNAP Container Station well.
- **GitHub Actions on a schedule** — free, zero home infrastructure, but: cron triggers are best-effort (can be delayed/dropped under load), you'd commit the SQLite DB back to the repo or use external storage, and secrets live in GitHub. Fine for a lightweight public-data pull; awkward as your DB grows.

**QNAP specifics (you own one):**
- **Container Station** runs Docker/LXC. Best practice: package the miner as a small Python container with an internal scheduler (cron/supercronic) or run it one-shot and schedule externally.
- **QNAP cron gotcha (well-documented):** QNAP's persistent crontab is `/etc/config/crontab`, but editing via `crontab -e` gets **overwritten on reboot/firmware update**. You must edit `/etc/config/crontab` directly and reload with `crontab /etc/config/crontab && /etc/init.d/crond.sh restart`. Running the schedule *inside* a container (supercronic) sidesteps this and survives reboots if the container is set to auto-start.
- Persist the SQLite DB and JSONL on a mounted NAS volume (not inside the container's ephemeral layer).

**Reliability for a single-user system:**
- **Missed runs:** use `Persistent=true` (systemd) or a catch-up query on start (watermark makes this automatic).
- **Overlapping runs:** guard with a lockfile (`flock`) or a PID/lock table so a slow run doesn't collide with the next.
- **Retries/backoff:** let PRAW handle API backoff; wrap the run in try/except with a bounded retry and log failures.
- **Alerting:** on failure, send yourself a notification (e-mail, ntfy, or a Healthchecks.io ping — a dead-man's switch that alerts if the job *doesn't* check in is ideal for cron).
- **Logging/observability:** structured logs with timestamps, counts (new/updated/purged), and request counts per run.

**Home IP vs VPS vs roving hotspot — candid assessment.** For compliant, authenticated, low-volume polling (one daily job, well under 100 QPM), a **home residential IP is completely fine and is exactly the expected pattern**. A VPS/datacenter IP is actually *worse* — datacenter ranges have poorer reputation and are more likely to hit Cloudflare challenges (Reddit uses IP-reputation checks). The **mobile Wi-Fi hotspot with roving IPs is a bad idea**: your requests are authenticated with your OAuth token and account, so Reddit identifies you by token, not IP. Constantly changing IPs (especially shared carrier-grade NAT mobile ranges) makes your traffic look *more* like evasion/abuse, not less — it's a classic ban-evasion signal. It adds risk and cost for zero benefit. **Use your normal home connection.** The thing that keeps you safe is authenticating properly, a correct UA, and modest volume — not IP gymnastics.

### 7. Frontend / UI layer

**For viewing/searching harvested data:**
- **Datasette (recommended).** Point it at your SQLite file and you instantly get a browsable, sortable, filterable website with full-text search (FTS5 + `datasette-search-all`), a JSON API for every table/query, and per-row permalinks. Zero UI code. Run it locally or on the NAS; `datasette-lite` even runs in-browser via WebAssembly for quick looks. This is the highest value-for-effort option and matches "simple script + polish" perfectly.
- **Streamlit** — good if you want custom dashboards/charts with minimal code; more work than Datasette for basic browse/search, better for bespoke visualizations later.
- **FastAPI + HTMX** — most control, most effort; only if you want a tailored app.
- **Static site generator / Markdown-CSV exports** — trivial, good for sharing digests; not interactive.
- **Terminal / query via Claude** — for ad-hoc analysis, feeding JSONL batches to Claude is powerful and needs no UI at all.

**Managing monitored subreddits/search terms — config file, not a UI.** For a single user, a hand-edited (or Claude-edited) **YAML/TOML config** is the right call. It's version-controllable, diff-able, requires no UI build, and Claude can edit it for you. Building a UI to add search terms is over-engineering for one user. Add a UI only if you find yourself editing config many times a day.

**Deep links for manual reply.** Store `permalink` for every item and render `https://www.reddit.com{permalink}` as a clickable link in Datasette. That gives you one-click "open this thread to reply manually" — the right pattern.

**Should the system help you *reply*? Clear recommendation: NO automated replies.** Research is unambiguous:
- Reddit's rules and subreddit-level AutoModerator heavily police automated/bot commenting. Signals that get accounts flagged/shadowbanned/banned: rapid or repetitive comments, generic/templated text, off-topic replies, promotional language, unnatural timing, and new/low-karma accounts commenting promotionally.
- "Accounts caught using bots are often banned permanently." Reddit detects bot-like behavior via high-volume/low-quality comments, lack of context, unnatural timing, and user reports.
- Many subreddits require bot accounts to be pre-approved and clearly labeled; unapproved automated posting violates both site-wide and community rules.

The sane design is **human-in-the-loop**: the system surfaces relevant threads with deep links; *you* write and post replies manually from your normal browser session. This keeps your account safe and your contributions authentic (which is also what actually works on Reddit). If you ever want assistance, have Claude *draft* a reply you review and post by hand — never auto-post.

### 8. Common mistakes and failure modes

Real-world causes of rate-limiting, blocks, and suspensions:
- **Generic/spoofed User-Agent** — heavily throttled; spoofing gets you banned "with extreme prejudice."
- **Unauthenticated requests** — now simply blocked (403).
- **Ignoring 429 / Retry-After** — retrying immediately compounds the problem and escalates toward suspension.
- **Retrying too aggressively / tight loops** — bursts trip the rolling window even if your average looks fine ("most API bans come from burst traffic, not total volume").
- **Running multiple instances on one client ID** — they *share* the 100 QPM budget; you don't get more throughput, you just throttle yourself.
- **Not persisting the `after` cursor / watermark** — leads to re-fetching or gaps.
- **`replace_more(limit=None)` on everything** — burns your request budget fast.
- **Hammering `/new` every minute** when daily suffices — unnecessary load, more block risk, no benefit for slow subs.
- **Automated commenting** — the top account-suspension risk.

**Best-practices checklist:**
1. Authenticate with OAuth (script app), one client ID.
2. Correct, honest, versioned User-Agent.
3. Let PRAW manage rate limits; honor `Retry-After`.
4. Poll at the lowest cadence that meets your needs (daily is plenty here).
5. Persist watermarks; make runs idempotent.
6. Tier comment-tree expansion; never blanket-expand.
7. Honor deletions/removals (sync-and-purge).
8. Read-only for harvesting; manual, human replies only.
9. Home IP, no proxies, no roving hotspot.
10. Log request counts and alert on failures.

### 9. Forward path / next stage

Sensible evolution, in order of increasing cost/complexity:
1. **Daily fetch + dedup (MVP).** `/new` for 3–6 subs → SQLite. Datasette for browse.
2. **Comment harvesting on demand.** Flag interesting threads; harvest trees with budgeted `replace_more`.
3. **Search-term monitoring.** Add Reddit search across subs for keywords (e.g., "proxy workflow," "crash on export"); store with `source_query` provenance. (Note Reddit search is limited/less complete than listing endpoints.)
4. **Keyword/entity extraction + classification.** Start with simple keyword tallies, then LLM classification (pain point? feature request? bug?).
5. **LLM summarization (Claude in the loop).** Batch new items as **JSONL** (one post/comment per line), chunk to a token budget, and have Claude summarize/theme/rank. JSONL is the ideal shape — cheap to slice, easy to stream, maps cleanly to token budgeting. Store LLM outputs back in SQLite with model/version provenance.
6. **Trend detection + alerting.** Track topic frequency over time (DuckDB shines here); alert when a theme spikes.

Costs/complexity grow at steps 4–6 (LLM API spend, prompt engineering, evaluation). Keep the ingestion layer stable and boring; iterate on the analysis layer.

## Recommendations

**Architecture options, minimal → built-out:**

**Option A — "The 150-line script" (start here).**
PRAW script app → poll `/new` for your subs → SQLite (fullname PK, upsert, watermark, raw JSON sidecar) → cron/supercronic in a QNAP container → Datasette for browse/search. Config in YAML. Manual replies via deep links.
- *Tradeoffs:* Minimal effort, fully compliant, easy to reason about. Forecloses nothing. Doesn't yet do search terms or LLM analysis — but adding them is incremental.

**Option B — Option A + on-demand comment harvester + search terms.**
Add a second script that expands comment trees for flagged threads (budgeted `replace_more`) and a search-term poller writing to the same DB with provenance.
- *Tradeoffs:* Moderately more code and request budget. Enables real thread-level insight. Still simple.

**Option C — Option B + LLM analysis pipeline.**
Batch new items to JSONL → Claude for summarization/classification/ranking → results back into SQLite → Datasette dashboards (or Streamlit for charts).
- *Tradeoffs:* Introduces LLM cost and prompt/eval work. Delivers the "insight miner" payoff. Build only after A/B are reliable.

**Option D — Container-native, observable service.**
Everything in Docker on the QNAP with supercronic, Healthchecks.io dead-man's-switch, structured logging, and a scheduled sync-and-purge job for deletion compliance.
- *Tradeoffs:* Most robust and "productionized"; more upfront DevOps. Worth it once you depend on the data.

**Start with Option A.** It's the smallest thing that is complete, correct, and compliant, and it forecloses nothing — B, C, and D are strictly additive on top of the same SQLite core. It matches your "simple script + thoughtful polish" preference, leans on your QNAP, and uses the well-regarded `reddit-to-sqlite` + Datasette patterns so you're learning from good code rather than forking a monolith.

## Caveats
- **Third-party subscriber counts** (GummySearch, RedPulse, PainOnSocial) are marketing/analytics estimates that vary ±10k by sync date; treat them as ballpark. r/premiere (~180–187k), r/VideoEditing (~516–527k), and r/editors (~182–196k) are the reliable core; **r/AdobePremierePro likely does not exist as a distinct sub** (the canonical one is r/premiere), and r/PremierePro / lowercase r/videoediting are smaller unverified variants — confirm each by visiting its page before wiring it in.
- The **$0.24/1,000-calls** figure and the **~$12,000/year** commercial-tier minimum come from Reddit's 2023 announcement and 2026 third-party breakdowns respectively; Reddit does not publish a live self-serve commercial price, so exact current commercial pricing is uncertain and negotiated case-by-case.
- The **48-hour deletion recommendation** is Reddit's stated guidance, not a hard technical enforcement; how strictly you implement sync-and-purge is a compliance judgment call. For a private, single-user, non-redistributed research store the practical risk is low, but the terms are the terms — build the purge loop.
- Many of the "2026 rules" details (the May 28 .json shutdown, the June 30 old.reddit login wall) are corroborated across multiple secondary sources and Reddit's own r/modnews post, but secondary blogs (many of them vendors selling scraping alternatives) have an incentive to emphasize the crackdown — the load-bearing facts (100 QPM, OAuth required, UA format, deletion rule) are confirmed directly from Reddit's official Data API Wiki.
- **Star counts and dates** for smaller repos (`reddit-to-sqlite`, `reddit-user-to-sqlite`) were not precisely captured; verify current maintenance status on GitHub before adopting. PRAW (4,222 stars, Aug 2026), Async PRAW (154 stars), and arctic_shift (~1.5k) are confirmed current.