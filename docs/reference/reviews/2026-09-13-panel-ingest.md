<!-- Extracted 2026-09-13 from the panel agent transcript (final assistant message; a one-line conversational lead-in before the heading was dropped, HTML entities unescaped, nothing else touched). -->
<!-- Status: raw, unedited panel report; immutable reference copy (docs/reference/ policy: add, never edit). -->
<!-- Scope: test-strategy panel on ingest and collector failure modes (fake-gateway scenario catalogue, parity across ingest paths, state machine, freshness, budget and ladder, reconcile). -->

# Panel report — ingest and collector failure modes

Sources read in order: plan (collector algorithm, data model, testing strategy, robustness/gates), collector design review (PRAW facts, edge cases, deletion semantics, ports, failure matrix), ranked DB learnings, `WHY_THE_GUARDS_EXIST.md`. Everything below is scoped to the collector path; UI, migrations, and CI mechanics are left to the other panels except where a collector spec needs them.

---

## A. `FakeRedditGateway` scenario-builder API

**Design rules the fake must obey** (so the matrix is expressible without `mock.patch`):

1. The fake implements the same `RedditGateway` Protocol as `PrawGateway` and raises only domain exceptions from `ports.py` (`RateLimited(retry_after)`, `AuthFailed`, `SubredditForbidden`, `SubredditNotFound`, `SubredditRedirected(path)`, `SubredditQuarantined`, `HtmlBlocked`, `TransientError`, `GatewayError`), plus one test-only `CrashInjected(Exception)` that is *not* in the domain hierarchy, so a broad `except` swallowing it is itself a detectable defect.
2. Listing, tree, `info()`, anchor, and search are all **derived from one in-memory world** (subs → posts → comments/more stubs) unless explicitly frozen, so a mutation (`delete`, `remove`, `restore`) is visible on every path at once. This is what makes parity and the removal signal testable.
3. Request cost mirrors the real Session hook exactly: `about`=1, page=1, `fetch_tree`=1+expansions, `info`=ceil(n/100), `new_head`=1, search page=1; a request that raises still costs 1. The contract suite (AD-04) pins these against `responses.calls`.
4. Every failure injection is a queue consumed in order; **an injection still unconsumed at teardown fails the test** ("the scenario never reached its planted failure" is a red, not a silent pass — positive control for the scenario itself).
5. Ids are deterministic (`t3_` base36 from a counter); `created_utc` defaults to the injected `Clock.now()` at add time; the fake owns no clock.
6. `from_fixture()`/`to_fixture()` use the **same JSON schema as `probe --save-fixture`** — one producer of fixture shape.

**Port additions this panel needs** (beyond the review's `about / iter_new_pages / fetch_tree / info / limits / requests_made`): `new_head(name) -> dict|None` (the freshness anchor, one item, must be a code path separate from paging) and `iter_search_pages(query, sort, time_filter, *, max_pages)` (M3).

### Method list

| Group | Method | One-line semantics |
|---|---|---|
| World | `add_subreddit(name, *, display_name=None, t5=None, subreddit_type="public", quarantine=False, subscribers=0, over18=False) -> name_lower` | Creates the about.json payload; controls casing and identity (`t5_`). |
| | `add_post(sub, *, created_utc=None, author="u1", title=..., selftext="", num_comments=None, stickied=False, hidden=False, **raw) -> fullname` | Adds a post; `raw` overrides any wire key (e.g. `edited=False`, `post_hint="new_thing"`); `hidden` keeps it out of `/new` until `unhide`. |
| | `add_comment(post, *, parent=None, body=..., author="u1", created_utc=None, **raw) -> fullname` | Adds a comment under post or parent comment; depth derived. |
| | `add_more(post, parent, *, count, children=())` | Adds a `MoreComments` stub; `count==0` is a continue-thread node; expansion yields `children` and costs 1 request. |
| | `add_crosspost(sub, parent_fullname, **raw) -> fullname` | Post with empty `selftext` and `crosspost_parent_list=[parent payload]`. |
| | `set_about(sub, **fields)` / `set_field(fullname, key, value)` / `remove_field(fullname, key)` | Arbitrary raw mutation: `t5_` change, score bump, nested/missing keys (`author_fullname` absent), unknown enum values. |
| | `set_raw_shape(kind, transform)` | Applies a shape transform to every emitted payload of a kind (e.g. nest `author_fullname` under `author_info`) — drives NM-03. |
| | `edit(fullname, body)` | Sets new body and `edited=<float>`. |
| | `unhide(fullname)` | Late-approval: post appears in `/new` at its original `created_utc` position. |
| Content state | `delete(fullname)` | Author deletion: `author=None`, `author_fullname` key absent, body/selftext `"[deleted]"`, posts get `removed_by_category="deleted"`; gone from listing; leaf comments vanish from the tree; `info()` still returns the scrubbed shape unless `vanish`ed. |
| | `remove(fullname, by="moderator")` | `"[removed]"` body; posts get `removed_by_category=by` (any string, incl. unknown); gone from listing; comments stay in tree as placeholders. |
| | `restore(fullname)` | Re-approval: content and author back on every path (used to prove `deleted_by_author` is terminal and `removed_by_moderator` is not). |
| | `delete_account(author)` | Every item by that author: `author=None`, `author_fullname` absent, content intact. |
| | `vanish(fullname, *, times=None)` | Omitted from `info()`, listing, and tree; `times=1` makes it transient (returns on the next call). |
| | `drop_from_tree(comment_fullname)` | Leaf-deleted-comment behavior: absent from `fetch_tree` only; `info()` still governed by `delete`/`vanish`. |
| | `ban_subreddit(sub, *, info_returns=True)` | Listing/about → `SubredditNotFound`; `info()` on its items per flag. |
| Listing behavior | `set_page_size(sub, sizes: list[int])` | Page lengths per page (short pages with non-null `after`). |
| | `set_overlap(sub, n)` | Page k+1 repeats the last n items of page k (listing shift). |
| | `set_listing_order(sub, *, sticky_first=True)` | Emits stickies pinned at the head instead of chronological position. |
| | `freeze_listing(sub=None)` | Listing snapshot stops tracking the world (uniform staleness). |
| | `set_live_anchor(sub, *, created_utc | fullname)` | What `new_head()` returns, independent of the (possibly frozen) listing. |
| | `set_info_order(shuffle=True, seed=0)` | `info()` returns matches in shuffled order (order not guaranteed). |
| | `set_tree_clamp(n)` | Comments beyond n per fetch arrive as `more` stubs (the `/comments?limit` clamp). |
| | `set_limits(remaining, used)` | What `limits()` reports (logging only; budget tests use `requests_made`). |
| Failure injection | `fail_page(sub, page_no, exc, *, times=1)` | Raise `exc` when that page is requested, `times` times, then succeed. |
| | `fail_tree(post, exc, *, after_comments=0, times=1)` | Raise mid-serialization after N comments (crash mid-tree) or before any. |
| | `fail_info(batch_index, exc, *, times=1)` | Raise on the k-th `info()` batch. |
| | `fail_next(exc)` | Next call of any kind raises. |
| | `rate_limit_next(retry_after, *, times=1)` | Next request raises `RateLimited(retry_after)` `times` times. |
| | `set_status(sub, "ok"|"forbidden"|"not_found"|"redirect"|"quarantined", *, path=None)` | `about`/listing raise the mapped exception. |
| | `set_html_403()` | Next request raises `HtmlBlocked` (Cloudflare). |
| | `set_auth_failed()` | Every request raises `AuthFailed` (surfaces at the about ping). |
| | `block_on(kind, n, event)` | Blocks the n-th call of `kind` on a threading event (SIGTERM test). |
| Recording | `calls: list[Call(method, args, cost, seq)]`, `requests_made`, `count(method)`, `fullnames_requested(method)` | Every call recorded with its request cost. |
| | `assert_no_unconsumed_injections()` | Called by the fixture at teardown (rule 4). |
| Fixtures | `FakeRedditGateway.from_fixture(path) / .to_fixture(path)` | Same schema as `probe --save-fixture`; contract cases load one fixture into both gateways. |

**Companion fakes** (ports, not mocks): `FakeClock(now, advance(s), sleep(s)→records and advances, advance_on_call(method, n, seconds))`; `FakeRawSink(lines, fail_on(page|post, exc), truncate_last_line(), unlink_after_write(path), call_log)`; `FakeNotifier(sent, fail_next())`.

---

## B. Test specifications (60)

Layer key: unit / service / e2e / adapter-cassette / adapter-responses / contract / gate. Phase per plan milestones. Cost S/M/L, Priority H/M/L. "Positive control" = the concrete defect or planted state that turns the spec red.

### B.1 `/new` sweep

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| SW-01 | sweep_full_window_forward_after_only | unit(core.paging)+service | Sub A 250 posts; page sizes [100,100,37,13] with non-null `after`; one post created 5 d ago hidden until run 2 | `fetch` twice | Run 1: 4 page calls chained by `after`, never `before`; 250 rows; short page does not stop; `stop_reason=exhausted`. Run 2: late post captured with its original `created_utc`, `first_seen_at`=run 2, ladder stage computed from `created_utc` | add_subreddit; add_post×250; add_post(created_utc=now-5d, hidden=True); set_page_size(A,[100,100,37,13]); run; unhide(P); run | M1a | Stop on `len(page)<100`; any `before` param; watermark early-stop (late post missing) | S | H |
| SW-02 | sweep_cap_sets_gap_stickies_excluded | unit+service | 1,100 unknown posts; 60-day-old sticky pinned at head of page 1. Variant: 200 already known | `fetch` | Exactly 10 page calls; 1,000 rows; `stop_reason=cap`; `gap_suspected_at` set; sticky upserted `stickied=1` but excluded from known-territory and watermark. Variant: cap hit but known territory reached → `gap_suspected_at` NULL | add_post×1100; add_post(stickied=True, created_utc=now-60d); set_listing_order(A, sticky_first=True) | M1a | Page 11 requested; gap set despite known territory; watermark = sticky's `created_utc` | S | H |
| SW-03 | sweep_overlapping_pages_dedupe | service | Listing shifts by 5 between pages | `fetch` | `COUNT(*)` = distinct ids; `items_seen` counts raw, `new` counts distinct; PK-stable | set_overlap(A,5) | M1a | `new == items_seen`; IntegrityError aborts page | S | H |
| SW-04 | sweep_crash_between_pages_one_txn_per_page | e2e | 300 posts; page 3 raises `CrashInjected` | run; run again | After crash: exactly 200 rows, run `crashed` with traceback, watermark and gap flag untouched, 200 JSONL lines. Rerun: 300 rows, `pk`/`first_seen_at` of the 200 unchanged, watermark advanced | fail_page(A,3,CrashInjected) | M1a | Per-item commit (≠200); per-run commit (0); broad `except` turning the crash into `partial` | S | H |
| SW-05 | field_ownership_per_ingest_path | unit(structural)+service | Ownership table: sweep→{score,num_comments,upvote_ratio,edited_utc,…}, tree→{+comments_*,check_stage,next_check_at}, info→{content_state,…}; a known post at `check_stage=2` | Fake bumps score and edits; sweep; then tree; then info | Structural: each repo upsert's `SET` column set (introspected) equals the declared set for its path. Behavioral: sweep changed score/`edited_utc` only; `first_seen_at`, `check_stage`, `next_check_at`, `comments_fetched_at` untouched | add_post; run; set_field(P,"score",99); edit(P,"x"); run | M1a | Sweep `SET` includes `check_stage`; table edited without repo change | M | H |
| SW-06 | sweep_removal_signal_confirmed_via_info | service | 50 known posts; P mod-removed (gone from listing); Q merely aged past the window | Sweep, then the confirm step of the same run | P is a candidate → one `info([P])` → `removed_by_moderator`, scrubbed. Q not a candidate (no `info` for it). Candidate set bounded to `created_utc >= oldest item seen in this complete sweep` | add_post×50; run; remove(P); run | M1a/M1c | State flips without `info()`; aged-out posts flood `info()` | M | H |
| SW-07 | sweep_empty_or_zero_new_ok | service | Sub B with no posts; sub A identical listing to previous run | `fetch` | Run `ok`; `stop_reason=exhausted`; watermark unchanged (NULL stays NULL); `new=0`, `updated=N`; zero-yield counter incremented (feeds FR-02) | add_subreddit(B); freeze_listing(A) before run 2 | M1a | Watermark set to 0/now; `partial` on empty | S | M |

### B.2 Subreddit status

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| SS-01 | sub_forbidden_others_continue | service | 3 subs; B private | run | B `status=forbidden`, `consecutive_failures=1`, rows retained, nothing scrubbed; A and C swept; run `partial` | set_status(B,"forbidden") | M1a | Exception aborts run (A/C empty); B rows scrubbed | S | H |
| SS-02 | sub_not_found_banned_policy | service | B has 20 stored posts; banned; `info()` still returns 12 | run (sweep+reconcile) ×2 | `status=not_found`; one notification; policy `scrub_confirmed_gone`: 8 absent → `gone_unconfirmed` → scrubbed at second miss; 12 retained | ban_subreddit(B); vanish(8 posts) | M1c | All 20 scrubbed on run 1; or none ever | M | M |
| SS-03 | sub_redirect_auto_disabled_after_n | service | `nosuchsub`; N=3 | run ×3 | Runs 1–2 `status=redirect`, enabled; run 3 `enabled=0`, one alert, `last_error` holds path | set_status(X,"redirect",path="/subreddits/search?q=x") | M1a | Disabled on run 1; never; alert every run | S | M |
| SS-04 | sub_quarantined_disabled_with_alert | service+adapter-responses | Quarantined sub (fixture P-07) | run | `status=quarantined`, `enabled=0`, alert; adapter maps 403 JSON `reason=quarantined` → `SubredditQuarantined`, not `SubredditForbidden` | set_status(X,"quarantined"); responses 403 body=P-07 | M1a | Mapped to forbidden (stays enabled, retried daily) | S | M |
| SS-05 | sub_identity_casing_merges_t5_change_aborts | service+CLI | Stored `videoediting` t5_abc; `subs add VideoEditing`; later about.json returns t5_zzz | subs add; run | Add refused as duplicate (one row, `display_name` from about); run: sub `stop_reason=error`, `status=error`, `last_error` names identity, zero rows written for it, others continue, alert | add_subreddit("VideoEditing",t5="t5_abc"); …; set_about("videoediting",t5="t5_zzz") | M1a | Two rows; posts written under old `subreddit_pk` after t5 change | S | H |
| SS-06 | sub_recovery_clears_error_state_after_complete_sweep | service | B forbidden 2 runs, then ok; variant run 3 hits cap | run ×3 | Run 3 `exhausted` → `status=ok`, `consecutive_failures=0`, `last_error` NULL, `gap_suspected_at` NULL. Variant: status ok but gap flag stays | set_status(B,"forbidden"); run×2; set_status(B,"ok"); run | M1a | Flags cleared on `cap`; counters not reset | S | M |

### B.3 Transient errors and rate limit

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| TE-01 | transient_page_error_outer_retry_backoff | service | Page 2 fails `TransientError` ×2 then succeeds; variant ×4 | `fetch` | `clock.sleeps==[30,120]`; page 2 committed on 3rd attempt; failed attempts counted in `api_requests`. Variant: sleeps `[30,120,300]`, sub `stop_reason=error`, page 1 stays, watermark untouched, others continue, run `partial` | fail_page(A,2,TransientError,times=2) / times=4 | M1a | Real `time.sleep` (wall-time guard trips); page 1 rolled back; watermark advanced on error | S | H |
| TE-02 | rate_limited_and_fatal_gateway_errors | service | (a) 429 `retry_after=3`; (b) 429 `retry_after=400`; (c) 429 ×2; (d) HTML 403 | run | (a) `clock.sleep(3)`, one retry, run `ok`; during the wait `runs.stage=="rate_wait:3s"` and `heartbeat_at` fresh; (b) sleep 300; (c) run `rate_limited`, page not written, lock released; (d) `HtmlBlocked` → run `failed` at once, alert, zero retries, remaining subs not attempted | rate_limit_next(3) / (400) / (3,times=2); set_html_403() | M1a | Second 429 swallowed as `partial`; stage not written (stale detector would kill a legitimate wait); HTML 403 retried in a loop | S | H |

### B.4 Comment trees

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| TR-01 | tree_skip_when_num_comments_zero | service | Due post `num_comments=0` | harvest | No `fetch_tree` call; `comments_complete=1`; `check_stage=0`; `next_check_at=created_utc+1d` | add_post(num_comments=0) | M1b | `fetch_tree` called; `next_check_at` NULL | S | H |
| TR-02 | tree_more_accounting_and_per_post_cap | service | 150 comments + stubs (count 20, 5, and a `count==0` continue node); `more_limit=2`, cap 40; variant: 60 stubs of 100 | harvest | `requests_used==1+2` (largest first: 20 then 5); `comment_more` row for the skipped stub with parent and count; `more_skipped=1`, `more_skipped_count=0`, `comments_complete=0`, `comments_harvested==COUNT(*)`; with `more_limit=3` → complete and `comment_more` rows cleared; huge: stops at cap, `more_skipped_reason='cap'` | add_post; add_comment×150; add_more(P,c,count=20,children=…); add_more(…,5,…); add_more(…,0) | M1b | Completeness derived from `num_comments`; stale `comment_more` rows after a complete refetch; cap ignored | M | H |
| TR-03 | tree_crash_mid_tree_nothing_committed | e2e | `CrashInjected` after 40 comments serialized | run; run again | Zero comment rows for P; `comments_fetched_at` unchanged; P still due; rerun completes; orphan JSONL lines tolerated | fail_tree(P,CrashInjected,after_comments=40) | M1b | 40 rows present; P no longer due | S | H |
| TR-04 | tree_budget_reserve_newest_first | service | budget 20, reserve 5; 3 subs need 6 sweep requests; 30 due posts ≈2 requests each | run | Sweep completes; `fetch_tree` calls in `created_utc` desc; harvest stops when `requests_made` reaches 15; untouched posts keep `next_check_at`; run `ok` with `backlog` counter; digest "N of M due posts harvested" | add_post×30 (num_comments>0); settings budget=20 | M1b | `requests_made>budget`; oldest first; due posts advanced without a fetch | S | H |
| TR-05 | tree_missing_known_comments_checked_via_info | service | Complete refetch omits 3 stored comments; `info()` returns 1 as `[deleted]`, omits 2 | revisit | One `info()` with exactly the 3 fullnames; returned one → `deleted_by_author` + scrub; omitted → `gone_unconfirmed`, `misses=1`, content intact; their children still hang (`parent_comment_pk` intact); an *incomplete* refetch does not trigger the check | drop_from_tree(c1,c2,c3); delete(c1); vanish(c2,c3) | M1c | Rows deleted; no `info()`; check runs after incomplete refetch | M | H |

### B.5 Revisit ladder

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| RV-01 | ladder_pure_never_null | unit+hypothesis | Any `created_utc`, stage 0..N, tier config | `next_check(created_utc, stage)` | Stage k → `created_utc+[1d,3d,7d,30d][k]`; beyond last → tier value, never None; monotonic in stage; independent of `now` | — | M1a | None after last stage; uses `now` | S | H |
| RV-02 | ladder_advances_on_complete_refetch_skew_safe | service (time-machine ±86,400 s) | Post discovered 10 d after creation; a due post whose tree fetch fails persistently | harvest under 3 clock offsets | Late post fetched once at discovery, then `next_check_at=created_utc+30d` (1d/3d/7d skipped); failed tree: stage unchanged, still due, run `partial`; across offsets: identical `content_state`, watermark, stop/gap decisions, `next_check_at` values (only local `*_at` columns and the due-set may differ) | add_post(created_utc=now-10d); fail_tree(Q,TransientError,times=99) | M1c | `next_check_at=now+delta`; stage bumped on failure; NULL after ladder | S | H |

### B.6 Reconcile and state machine

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| RC-01 | deletion_state_table_fail_closed | unit (exhaustive table) | body ∈ {text,"[deleted]","[removed]",None,missing} × author ∈ {name,None} × `author_fullname` {present,absent} × `removed_by_category` ∈ {None,"deleted","moderator","reddit","automod_filtered",…,"UNKNOWN"} × prior state × `info_returned` | `decide()` | Expected (`content_state`,`author_state`,scrub?,misses) per row, seeded from probe fixtures; unknown category + "[removed]" → a removed state, never `live`, counted; None/missing body → never `live`; `deleted_by_author` terminal; removed + intact payload → `live` | fixtures P-01..P-05 | M1a | mutmut: default branch → `live`; unknown category coerced to "moderator" | S | H |
| RC-02 | reconcile_batches_100_match_by_fullname | service | 250 stored items; `info()` order shuffled; 3 omitted | reconcile | 3 `info()` calls ≤100 each; results matched by fullname (shuffle assigns nothing wrong); 3 omitted → `gone_unconfirmed`, `misses=1` | add_post×250; set_info_order(shuffle=True); vanish(a,b,c) | M1c | Positional zip; 4 calls; misses on wrong rows | S | H |
| RC-03 | reconcile_misses_scrub_second_transient_resets | service | P vanishes permanently; Q for one call only | reconcile; +2 d reconcile | P: miss 1 content intact → miss 2 `gone`, scrubbed. Q: miss 1, then returned → `live`, `misses=0` | vanish(P); vanish(Q,times=1) | M1c | Scrub at first miss; `misses` never reset | S | H |
| RC-04 | author_deletion_terminal_mod_removal_returns | service | P deleted by author; R removed by moderator; both later restored in the fake | reconcile; restore; run | P: `deleted_by_author`, scrubbed, still scrubbed after restore, `new` counter 0. R: `removed_by_moderator`, scrubbed, then `live` with content repopulated, FTS row back, re-tagged | delete(P); remove(R,"moderator"); run; restore(P); restore(R); run | M1c | P returns to live; R stays removed; FTS count ≠ live count | M | H |
| RC-05 | account_deletion_scrubs_author_only | service | u1 has 3 posts, 5 comments | delete_account; reconcile | All 8: author cols NULL, `author_state=account_deleted`, bodies intact, FTS still hits; `authors` row gone; author-count invariant holds | delete_account("u1") | M1c | Content nulled; `authors` row remains; other authors' counts change | S | H |
| RC-06 | reconcile_cadence_invariant_and_tier_fallback | service+digest | (a) last complete reconcile 61 h ago, budget exhausted before reconcile; (b) 5,000 items, budget 30 | run | (a) run `partial`, reason `reconcile_overdue`; (b) ≤30 d items fully checked, older tiered; digest "reconcile: N of M items checked; fell back to tiers" | clock.advance(61h); add_post×5000 (cheap in-memory) | M1c/M3 | 61 h and `ok`; digest silent | M | M |

### B.7 Scrub and canary

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| SC-01 | scrub_is_one_function_all_surfaces | service (connection chokepoint) | Live post with canary phrase, tagged, JSONL in retention (plain and .gz) | reconcile after `delete(P)` | One call: content/author/URL cols NULL; `raw_json` tombstone `{tombstone,reddit_id,scrubbed_at}`; `post_themes` gone; FTS MATCH canary = 0; JSONL line rewritten via temp+`os.replace`, all other lines byte-identical; `item_snapshots` kept; row and `parent_comment_pk` links intact; after `wal_checkpoint(TRUNCATE)` the DB file bytes contain no canary (`secure_delete`) | add_post(selftext=CANARY); run; delete(P); run | M1c | Any one surface skipped; `secure_delete` off (bytes found in free pages) | M | H |
| SC-02 | compliance_canary_end_to_end | e2e | Canary in a title, selftext, comment body, crosspost parent; export taken; digest and daily backup produced | delete()/remove() all carriers; clock +2 d; run; fresh export | grep every TEXT column of every table, FTS, every file under `data/**` (JSONL, .gz, reports, logs, backups), and the new export → 0 hits | add_post/add_comment/add_crosspost(CANARY); run; export; delete…; run; export | M1c | Scrub skips FTS or JSONL; **day-1 digest or daily backup still holds the phrase — red under the current plan (see D-4)** | M | H |

### B.8 Freshness

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-01 | per_source_freshness_degraded | e2e | B fails quietly every page for 2 runs; A, C fine | run ×2 | Run 2 `degraded`; digest names B, "last fetched 2 runs ago"; `run_subreddits` shows B `error` both runs | fail_page(B,1,TransientError,times=99) | M1a | Both runs `ok` | S | H |
| FR-02 | freshness_anchor_uniform_staleness | e2e (run+doctor) | All listings frozen K=3 runs; live anchor for A newer; control: anchor == watermark (quiet weekend) | run ×3; doctor | Run 3 `degraded`; digest "no new items for 3 runs while Reddit shows newer"; anchor costs exactly 1 request/sub through `new_head()` (not the paging code); control stays `ok` | freeze_listing(); set_live_anchor(A,created_utc=now-1h); run×3 | M1a | K runs `ok`; anchor fetched via the same frozen paging path | M | H |

### B.9 Parity and normalizer

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| PA-01 | shape_parity_listing_tree_info_search | unit(fixtures)+contract | Same post captured four ways (P-10) | canonicalize → normalize each | Identical `PostRow` on all shared fields; `author` `"[deleted]"`/None handled identically; un-owned fields per path untouched | from_fixture("parity/post_X.{listing,tree,info,search}") | M1a | Tree path keeps `author` as object → mismatch | S | H |
| PA-02 | reprocess_golden_byte_identical | db/unit | 200 rows with `raw_json`, `normalizer_version=N` | `db reprocess --below N+1` | Rows byte-identical to golden; version stamped; refactor keeps golden; semantic change needs bump + new golden | fixtures | M1a | Coercion change without version bump → diff (that red is the point) | S | H |
| NM-01 | normalize_missing_fields_and_rejects | unit+hypothesis | `edited` false/float, `author_fullname` absent, `selftext` null, `distinguished` null, unknown keys; random key deletion | normalize page | Optional → typed NULL; required (`id`,`created_utc`,`subreddit`) missing → `raw_rejects(run_pk,raw_json,error)`, run continues `partial`, raw preserved in JSONL; property: never raises, always Row or Reject, required-key deletion ⇒ Reject | remove_field(P,"author_fullname"); set_field(P,"edited",False) | M1a | Exception aborts page; reject silently dropped | S | H |
| NM-02 | unknown_enum_stored_raw_and_counted | service | `post_hint="new_thing"`, `removed_by_category="future_ops"`, `subreddit_type="weird"` | run | Stored verbatim; `unknown_enum_values=3` on run row; digest lists them | set_field(...) ×3 | M1a | Coerced to NULL/known; counter 0 | S | H |
| NM-03 | population_floor_and_coverage_median_via_run | gate (through `run`) | (a) `author_fullname` nested under `author_info` on every payload; (b) 8 runs, run 8 drops `% selftext_html` > X vs trailing-7 median | run | (a) run `failed`, error names `posts.author_fullname` (95% floor over live rows with `author_state=known`, scoped by `normalizer_version`), notification; (b) run 8 `partial`, digest shows the drop with denominators | set_raw_shape("post", nest_author_fullname); set_field(...,"selftext_html",None) on 40% | M1a | Invariant reads a config flag; floor counts account-deleted rows (false alarm); run stays `ok` | M | H |

### B.10 Run lifecycle

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| RL-01 | preconditions_exit_78_no_running_row | e2e (CliRunner), parametrized | Bad client id (AuthFailed at ping); invalid sub name; invalid regex; negative budget; unwritable data dir; migrations pending (downgraded temp DB); DB file missing | run | Exit 78; message names cause / pending revisions; `fake.calls` empty except the single `about` ping in the auth case; no `runs` row left `running`; notifier fired | set_auth_failed(); settings variants | M0/M1a | `runs` row inserted before validation/ping; a listing request made | S | H |
| RL-02 | flock_held_exit_75_zero_calls | e2e | Test holds `flock` on `data/locks/collector.lock` | run (and each mutating command) | Exit 75; `fake.calls==[]`; no `running` row | — | M1a | Run proceeds; row left `running` | S | H |
| RL-03 | stale_running_row_marked_crashed_at_45m | e2e | `running` row, heartbeat 50 min old; control 30 min old | run | 50-min → `crashed`, new run proceeds; 30-min row untouched | insert via repo | M1a | 30-min row killed; 50-min not | S | H |
| RL-04 | every_mutating_command_takes_lock_writes_run_row | gate (structural+behavioral) | Typer registry; commands flagged `mutating=True` | For each: invoke with lock held; without | With lock: 75; without: `runs` row with `kind`, `stage`, heartbeat. Structural: the flagged set derived from the registry equals {run, fetch, comments, revisit, reconcile, tag, scrub, reprocess, import, db upgrade, db restore}; no unflagged command writes (temp DB opened ro for them) | — | M1a | New mutating command without the flag → set mismatch | M | H |
| RL-05 | wall_clock_ceiling_partial_after_batch | service | Ceiling 3 h; clock jumps 3 h + 1 s during tree 5 of 10 | run | Tree 5 committed whole; 6–10 untouched and still due; run `partial`, reason `ceiling` | clock.advance_on_call("fetch_tree",5,3h+1s) | M1d | Ceiling checked only at end; tree 5 half-written | S | M |
| RL-06 | sigterm_finishes_batch_cancelled | e2e (subprocess) | Child process; fake blocks on page 2 | SIGTERM during page 2 | Page 2 committed whole or fully rolled back; run `cancelled`; lock released; documented exit code; second SIGTERM → immediate exit | block_on("page",2,event) | M1d | Row left `running`; lock held; partial page | M | M |
| RL-07 | write_side_failures_abort_page_cleanly | e2e | (a) second connection holds `BEGIN IMMEDIATE` (test `busy_timeout=1 s`); (b) `RawSink` raises `OSError(ENOSPC)` on page 2; (c) raw dir `chmod 0500` | run | (a) run `failed` cleanly, no partial page, watermark untouched; (b)/(c) page 2 not committed, page 1 intact, run `failed`, notifier fired; sink call log proves JSONL flush precedes commit | FakeRawSink.fail_on(page=2,OSError(ENOSPC)) | M1a | Commit before flush; retry past `busy_timeout`; `partial` | M | H |

### B.11 JSONL sink

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| JS-01 | jsonl_per_run_file_compress_verify_before_delete | unit(tmp_path)+service | Run writes N lines; variant: a truncated .gz planted | End-of-run compression | `raw/YYYY/MM/run-<id>.jsonl.gz` re-read line count == `raw_files.item_count` before the plain file is unlinked; lines carry `shape`, `run_id`, `fullname`; truncated gz → raises, plain retained, run `partial`; `raw_files.compressed` accurate | write truncated gz directly in tmp_path | M1c | Unlink before verify; truncated archive reads as empty and 0==0 passes | S | H |
| JS-02 | jsonl_retention_gate_and_partial_trailing_line | service | Files aged 29/30/31 d; no recorded backup; a file with a truncated last line | Retention sweep; read | Without backup → sweep refuses; with backup → 31 d removed, 29/30 kept; reader yields complete lines and warns once; `raw_files` invariant counts complete lines (no false alarm) | clock.advance; FakeRawSink.truncate_last_line() | M1c | 29-d file deleted; sweep without backup; truncated line raises | S | M |

### B.12 Themes and digest

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| TH-01 | theme_regex_timeout_and_caps | unit | `(a+)+$` vs 30k `a`s; pattern over length cap; invalid regex | compile/match | Match returns `timeout` within the `regex` budget (wall < 1 s); rule flagged, run `partial`, other rules still applied; over-cap/invalid rejected at save/import (422 / exit 78) | — | M1d | stdlib `re` (pytest-timeout red); over-cap accepted | S | H |
| TH-02 | theme_inputs_bot_exclusion_retag | service | AutoModerator post; mod-distinguished bot sticky; humans; crosspost whose parent title matches; rule edited later | tag; edit rule; tag | Bot items `author_is_bot=1`, no `post_themes`, excluded from digest counts with the denominator saying so; crosspost tagged `matched_field=crosspost_parent`; changed `rules_hash` → retag all; unchanged → none; surviving matches keep `tagged_at` | add_post(author="AutoModerator"); add_crosspost(...) | M1d | AutoMod tagged; retag every run; `tagged_at` reset | M | H |
| DG-01 | digest_golden_denominators_from_state | unit(golden)+service | Seeded: 2 subs ok, 1 forbidden, backlog 12, gap on one, 3 unknown enums, budget changed since last run, tier fallback | `report` | md/html equal golden; structural pass: every count line matches `N of M` and names its population; names the forbidden sub and the changed setting (`settings_fingerprint`); regenerated after scrub has no scrubbed text | seeded via fake + run | M1d | A bare count; a fake failure absent from the digest (template, not state) | S | H |
| DG-02 | notifier_proof_recorded | service | FakeNotifier ok; then failing | `notify --test`; doctor | Delivery timestamp recorded; `doctor` reports last delivery age; failing notifier → `doctor` red; a failed run → exactly one notification | FakeNotifier.fail_next() | M1d | `doctor` green with no delivery ever recorded | S | M |

### B.13 Config, dry-run, isolation

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| CF-01 | dry_run_no_network_zero_http_zero_db_writes | gate (adapter-responses + db ro) | Real adapter, `responses` active with **no routes**; DB opened `mode=ro` | `run --dry-run`; `doctor --no-network`; `config validate` | No `ConnectionError` (zero HTTP); zero DB writes (ro raises); dry-run JSONL only under the scratch dir | — | M1a | A `runs` row inserted; token request attempted | S | H |
| CF-02 | no_bypass_flags_budget_hard_cap | gate (structural+behavioral) | CLI option registry; a deleted item and a due reconcile | `--budget 9000`; all run flags combined | Budget clamped/refused at 5,000; no option name matches `skip|no-reconcile|no-scrub`; with every flag set, reconcile and scrub still execute | add_post; delete(P); run --no-comments … | M1a | Adding `--no-reconcile` → structural red; 9,000 accepted | S | H |
| CF-03 | settings_extra_forbid_and_fingerprint | unit | Misspelled key `budgt`; two settings differing only in `client_secret`; two differing in budget | load; fingerprint | Misspelled → exit 78 naming the key; fingerprint equal when only secrets differ; differs when budget differs; stamped on `runs` | — | M0 | Unknown key ignored; secret in fingerprint | S | M |
| CF-04 | data_dir_isolation_refusal | gate | pytest loaded, opt-in var unset, default `DATA_DIR` | Construct settings | Raises; autouse fixture points every test at tmp; positive: subprocess pytest without the fixture → write to default dir refused | — | M0 | Settings resolve to the real dir under pytest | S | H |

### B.14 Adapter and contract

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| AD-01 | cassette_auth_ping_two_requests_ua_limits | adapter-cassette | Recorded token + `/r/premiere/about` (C-01) | `about()` | Exactly 2 HTTP requests (hook count == cassette interactions); UA `python:com.wesmax.insightminer:v<ver> (by /u/<user>)` + prawcore suffix; `limits()` `remaining/used` populated; `x-ratelimit-*` present; `--record-mode=none` | — | M0 | `check_for_updates` default → 3rd request; UA from a literal | S | H |
| AD-02 | responses_failure_paths_exact_counts | adapter-responses, parametrized | 429×2 (`Retry-After: 3`); 401 at token; token→401 `invalid_token`→token→200; 503,503,200; 503×3; `ReadTimeout` body; 403 `text/html`; 302 `/subreddits/search`; 404; 403 quarantine JSON (P-07) | Port method | Domain exception per case (`RateLimited(3)`, `AuthFailed`, ok, ok, `TransientError`, `TransientError`, `HtmlBlocked`, `SubredditRedirected(path)`, `SubredditNotFound`, `SubredditQuarantined`); `len(responses.calls)` exact per case (2,1,4,3,3,3,1,1,1,1); `timeout=30` on every request; prawcore's `time.sleep` patched (the one permitted patch site, `tests/adapters/`) | — | M1a | Wrong class; hidden extra request; real sleep | M | H |
| AD-03 | cassette_tree_serialization_no_lazy_fetch | adapter-cassette | Recorded tree with `more` nodes incl. `count==0` (C-03) | `fetch_tree(more_limit=2)` | Request count == 1+2 exactly (no `/user/*/about`, no extra `/comments/{id}`); `author_fullname` from dict; `_replies` dropped; `author`→name/None; `TreeResult.requests_used` == hook count | — | M1b | `comment.author.fullname` → unmatched-request error | S | H |
| AD-04 | contract_suite_fake_vs_praw | contract | Cases: about; first `/new` page; tree with more; `info()` with omitted id + shuffled order; deleted post; mod-removed post; deleted comment with children; account-deleted author; 429 once; 503 once | Same module against `FakeRedditGateway.from_fixture` and `PrawGateway` (cassette/responses) | Identical canonical dict keys and value types; identical `requests_made`; identical exception classes | from_fixture(P-*) | M1a–M1c | Fake emits `author:"[deleted]"` where canonical says None; fake under-counts requests | M | H |

### B.15 Gates

| ID | Test name | Layer | Given | When | Then | Scenario | Phase | Positive control | Cost | Pri |
|---|---|---|---|---|---|---|---|---|---|---|
| GT-01 | guard_reachability_meta_and_planted_invariants | gate | Invariant registry (functions decorated `@invariant("name")`); gate tests marked `@pytest.mark.gate("name")`, each planting a violation then invoking `run` via CliRunner | Meta: compare the two sets; each gate test: run | Meta red if any invariant lacks a gate test or vice versa (structural scan, no hand list), or if a gate test never invokes the CLI. Planted states → `runs.status='failed'` naming the invariant: extra `running` row not stale; FTS trigger dropped in the temp DB (FTS≠live); `raw_files` entry whose file was unlinked (`FakeRawSink.unlink_after_write`); JSONL tombstone missing for a scrubbed item; `alembic_version` stamped wrong; fresh row with old `normalizer_version`; reconcile overdue; counters≠deltas (row inserted by SQL mid-run through a test-only hook). Plus AST scan: no `time.sleep` outside `adapters/clock.py` and `tests/adapters/` | — | M0 scaffold, grows per invariant | Register an invariant with no gate test; a gate test that calls the guard directly | L | H |
| GT-02 | pk_stability_three_reruns | gate (through run) | 300 posts, 1,000 comments, overlaps | run ×3 | `pk`, `first_seen_at`, `max(pk)==count(*)` identical for posts and comments; invariant flips run `failed` when a test build swaps the repo to `INSERT OR REPLACE` | add_post×300; add_comment×1000; set_overlap | M1a | Rowid churn | S | H |

### Coverage maps

**Plan failure-matrix rows → specs** (all 35 mapped): 429→TE-02, AD-02 · 401 token→RL-01, AD-02 · 401 invalid_token→AD-02 · 403→SS-01, AD-02 · 404→SS-02, AD-02 · Redirect→SS-03, AD-02 · casing/identity→SS-05 · 5xx/timeout→TE-01, AD-02 · crash between pages→SW-04 · crash mid-tree→TR-03 · overlapping run→RL-02 · DB locked→RL-07 · stale row→RL-03 · malformed→NM-01 · deleted/removed→RC-04, SC-01, SC-02 · account deletion→RC-05 · missing from info→RC-03 · config errors→RL-01 · DB missing/behind→RL-01 · disk/JSONL→RL-07 · clock skew→RV-02 (scoped, see D-2) · empty/zero new→SW-07 · Cloudflare→TE-02, AD-02 · overlapping pages→SW-03 · quarantined→SS-04 · budget exhausted→TR-04 · 100% NULL column→NM-03 · inert gate→GT-01 · source freshness→FR-01 · uniform staleness→FR-02 · real data dir→CF-04 · PK churn→GT-02 · two-path parity→PA-01 · recovers→SS-06 · dry-run/no-network→CF-01. **Unmapped: none.** One row is mapped only in scoped form (clock skew, D-2).

**DB learnings ranks → specs**: 4→RC-01, NM-02, RV-01 · 5→NM-03 · 6→FR-01, FR-02, SW-07 · 9→GT-01 (and every gate row runs through `run`) · 11→CF-01, CF-02 · 13→RL-03, RL-04, RL-05, TE-02 (stage during wait), SS-06 · 14→PA-01, SW-05, AD-04 · 15→PA-02, CF-03, DG-01 · 21→DG-01, DG-02 · 25→JS-01, JS-02, TR-03 (orphan lines).

---

## C. Probe plan

The plan's `probe <fullname>` needs sub-modes to produce these (see D-14): `probe about r/<sub>`, `probe listing r/<sub>/new --limit N`, `probe tree <id> --more-limit N`, `probe info <fullname,...>`, `probe search "<q>"`, each with `--save-fixture <name>`. Fixtures land in `tests/fixtures/json/` in the exact schema `FakeRedditGateway.from_fixture` loads; usernames are replaced on save. "Test sub" = the personal restricted subreddit; where it cannot produce the case, the fallback is noted.

| # | Reddit behavior (review conf.) | Probe capture | Fixture | Consumed by |
|---|---|---|---|---|
| P-01 | Author-deleted post: `author` `"[deleted]"`, `author_fullname` absent, `selftext` `"[deleted]"`, `removed_by_category="deleted"` ([C]/[?]) | Post then delete in test sub; `probe info t3_x` and `probe tree x` | `post_deleted_author.{info,tree}.json` | RC-01, RC-04, AD-04, PA-01 |
| P-02 | Mod-removed post: title/author visible, `selftext` `"[removed]"`, `removed_by_category="moderator"` ([C]/[?]) | Remove as mod in test sub; `probe info`, `probe tree` | `post_removed_moderator.*.json` | RC-01, RC-04, SW-06, AD-04 |
| P-03 | Reddit-removed categories (`reddit`, `automod_filtered`, `anti_evil_ops`, `content_takedown`, …) ([?]) | Cannot be produced in the test sub; `probe info` on public examples whose payload is already `[removed]` (no third-party content survives) | `post_removed_reddit_<cat>.json` | RC-01, NM-02 |
| P-04 | Deleted comment with children: `body` `"[deleted]"`, `collapsed_reason_code="DELETED"`, stays in tree ([C]/[?]) | Delete a parent comment in test sub; `probe tree` | `comment_deleted_with_children.json` | RC-01, TR-05, AD-04 |
| P-05 | Leaf-deleted comment disappears from the tree; `info()` returns it or omits it ([C]/[?]) | `probe tree` before and after deleting a leaf; `probe info t1_leaf` after | `tree_before_leaf_delete.json`, `tree_after_leaf_delete.json`, `info_deleted_leaf.json` | TR-05, RC-03, RC-01 |
| P-06 | Mod-removed comment: `"[removed]"`, author None to non-mods, stays in tree ([C]/[?]) | Remove a comment as mod; `probe tree`, `probe info` | `comment_removed_moderator.json` | RC-01, AD-04 |
| P-07 | Quarantined sub response shape with read-only token ([?]) | `probe about r/<known quarantined sub>` (captures the 403 body only) | `about_quarantined_403.json` | SS-04, AD-02 |
| P-08 | `/comments` `limit` clamp: how many comments arrive before `more` stubs ([?]) | `probe tree <id of a >2,000-comment thread> --more-limit 0`; count nodes | `tree_large_clamp.json` (structure only, bodies blanked) | TR-02 (`set_tree_clamp`), AD-03 |
| P-09 | Sticky ordering in `/new`: chronological or pinned first ([C]) | Pin an old post in test sub; `probe listing r/<test>/new --limit 5` | `listing_new_with_sticky.json` | SW-02, FR-02 (anchor must skip stickies) |
| P-10 | Same post via listing (wire), tree (PRAW-attr), `info()` (wire), search (wire) — shape parity | Four probes of one test-sub post | `parity/post_X.{listing,tree,info,search}.json` | PA-01, AD-04 |
| P-11 | `count==0` continue-thread `more` node shape and cost ([V] cost, shape [?]) | Deep chain (>10 replies) in test sub; `probe tree --more-limit 0` | `tree_continue_thread.json` | TR-02, AD-03 |
| P-12 | Crosspost: `crosspost_parent`, `crosspost_parent_list[0]` shape ([C]) | Crosspost a test-sub post into the test sub; `probe info` | `post_crosspost.json` | TH-02, PA-01 |
| P-13 | Account-deleted author with content intact ([C]) | Cannot be produced deliberately; `probe info` on a public example with the body replaced by a placeholder on save | `post_author_account_deleted.json` | RC-05, RC-01 |
| P-14 | Nonexistent sub → `Redirect` with `.path=/subreddits/search?q=` ([C]) | `probe about r/thissubdoesnotexist_xyz` | `redirect_nonexistent.json` | SS-03, AD-02 |
| P-15 | Read-only token: `x-ratelimit-*` headers present; `auth.limits` keys (`reset_timestamp` gone?) ([V]/[C]) | `doctor` with header printing; cassette C-01 | `cassettes/auth_about.yaml` | AD-01 |
| P-16 | `info()` on items in a banned/private sub ([?]) | Only if a banned sub with a known post id is available; otherwise **unresolvable** → SS-02 policy stays fixture-less and is marked as such in `GUARDS.md` | `info_banned_sub.json` (maybe) | SS-02 |
| P-17 | Edits within ~3 min don't flip `edited` ([C]) | Edit a test post at t+1 min and t+10 min; `probe info` both | `post_edited_early.json`, `post_edited_late.json` | SW-05 (`edited_utc` ownership) — low priority |

Cassettes for the adapter happy paths (C-01 auth+about, C-02 first `/new` page, C-03 tree with more, C-04 `info()` batch) are recorded against the test sub only.

---

## D. Judgements on the collector design

| # | Item | Verdict | Reason (one sentence) | Recommendation |
|---|---|---|---|---|
| D-1 | `--dry-run` semantics | **Contradictory** | Collector says dry-run "writes only JSONL to a scratch dir" (implies fetching), the gates table says dry-run makes zero HTTP calls. | Define two modes:`--dry-run` = real fetch, HTTP counted, zero DB writes, JSONL to scratch; `--no-network` = zero HTTP and zero DB writes. CF-01 tests each against its own definition. **Add.** |
| D-2 | Clock-skew row: "identical rows and decisions" | **Over-claimed** | `next_check_at <= now` is inherently a local-clock comparison, so ±1 day must change the due-set; only stop/gap/state decisions and the stored `next_check_at` values can be identical. | Scope the claim to what is true (RV-02 does); add "never NULL, never double-advanced" as the skew invariant. **Simplify.** |
| D-3 | Per-post expansion cap 40 vs per-pass 16 | **Under-specified** | Skipped `MoreComments` are not resumable across runs, so a cumulative cap across revisits has nothing to count against. | Define the cap as the per-fetch maximum for posts above a `num_comments` threshold; drop any cumulative reading. **Simplify.** |
| D-4 | Canary scope vs retained copies | **Compliance gap** | Daily `VACUUM INTO` backups (7 daily + 4 weekly ≈ a month), 14-day digest files (titles are content), and structured logs can all hold deleted text after scrub, yet the canary scans only DB, FTS, JSONL, export. | Extend SC-02 to `data/**`; decide the backup policy (retention ≤ reconcile cadence, or scrub-on-restore, or a documented exclusion); digests carry titles only after re-check or link-only. **Add.** |
| D-5 | Removal signal from `/new` absence | **Under-specified** | A post leaves `/new` by aging past the 1,000 cap or by listing jitter, not only by removal, so the candidate set needs a bound. | Candidates = known posts with `created_utc >=` the oldest item seen in a *complete* sweep, and never a state change without `info()` confirmation (SW-06). **Add.** |
| D-6 | Exit codes | **Under-specified** | Only 0/75/78 exist; `failed`, `partial`, `cancelled`, `rate_limited` have no code, yet the launchd wrapper "notifies on non-zero". | Define the full table (proposal: 0 ok, 1 failed/crashed, 3 partial, 4 rate_limited, 130 cancelled) and test it in RL-01/RL-06. **Add.** |
| D-7 | Heartbeat during long waits | **Under-specified** | A 300 s rate wait and prawcore's internal sleeps run with no heartbeat writes unless the design says when they happen. | Write the heartbeat before every request and before every sleep with a `wake_at` column; the stale detector uses `max(heartbeat_at, wake_at)`. **Add.** |
| D-8 | Unknown `removed_by_category` with `[removed]` body | **Under-specified** | Fail-closed says "not live", but which removed state decides whether the item may return to live later. | Allow every `removed_*` state to return to `live` on an intact payload (only `deleted_by_author` terminal); unknown → `removed_by_reddit`, stored raw and counted. **Simplify.** |
| D-9 | Scrub latency for pure `info()` absence | **Contradictory with 48 h guidance** | Reconcile every 2 days plus scrub at the second miss means up to ~4 days before an absent item is scrubbed. | Re-check first-miss items at the end of the same run (transient absence resolves in minutes); second miss in the same run → scrub. **Add**; owner decides (E-3). |
| D-10 | `--gateway fake` in the shipped package | **Risk** | A demo run with the fake against the default `DATA_DIR` writes fake posts into the production DB. | Refuse `--gateway fake` unless `DATA_DIR` is explicit and non-default; gate test in CF-02. **Add.** |
| D-11 | Budget accounting | **Under-specified** | Whether token refreshes, the anchor, and failed requests count, and whether the check runs before each variable-cost tree, is unstated. | Count every HTTP response (the hook cannot tell them apart anyway); check `requests_made + 1 + more_limit <= budget - reserve` before each tree. **Add.** |
| D-12 | Freshness anchor code path | **Fragile as written** | If the anchor reuses the sweep's paging code, a paging bug freezes both and the anchor cannot detect it; a pinned sticky as `limit=1` result makes Reddit look permanently older. | Separate `new_head()` port method; skip stickies (fetch `limit=3`, take the first non-sticky). **Add.** |
| D-13 | `author_fullname` 95% floor | **False-alarm risk** | Account-deleted and deleted items legitimately lack `author_fullname`, so a floor over all live rows trips on normal deletion volume and trains the operator to ignore it. | Compute floors over live rows with `author_state=known` and `content_state=live`, scoped by `normalizer_version` (NM-03). **Simplify.** |
| D-14 | `probe <fullname>` only | **Under-specified** | Parity, anchor, clamp, quarantine, and redirect fixtures need listing/tree/about/search captures, and the fixture format must be the one the fake loads. | Add the sub-modes in C; `probe --save-fixture` and `FakeRedditGateway.from_fixture` share one schema module. **Add.** |
| D-15 | Hypothesis "random key deletion" | **Vague** | Without a stated property it degenerates to "does not crash". | Property: never raises; output is Row or Reject; deleting any required key ⇒ Reject; deleting any optional key ⇒ Row with that field NULL (NM-01). **Add.** |
| D-16 | SIGTERM "finishes its batch" | **Under-specified** | A batch may be a 40-expansion tree paced at up to 10 s per request, so cancel latency can reach minutes. | Cancel at the request boundary; roll back the in-flight tree (still due); commit an in-flight page only if fully fetched (RL-06). **Simplify.** |
| D-17 | `comments_harvested == actual count` invariant | **Ambiguous** | Tombstoned comments keep their rows, so "actual count" must say whether it includes them. | Define as `COUNT(*)` of all comment rows for the post regardless of state; state it in the data dictionary. **Add.** |
| D-18 | Stress scenario at 50k/500k weekly | **Over-engineered for this panel's scope** | The learnings rank it "adopt lightly"; its value is index reality, not scale. | Keep, M3, `EXPLAIN QUERY PLAN` assertions on the four hot queries only. **Keep (light).** |

---

## E. Open questions for the owner

1. **Exit codes**: what should `failed`, `partial`, `cancelled`, and `rate_limited` return, and should `partial` trigger a macOS notification or only a digest line? (D-6)
2. **Dry-run**: may `--dry-run` fetch from Reddit (HTTP counted, JSONL to scratch), or must it be zero-HTTP? (D-1)
3. **Scrub latency**: accept up to ~4 days for items confirmed only by `info()` absence, or re-check misses at the end of the same run? (D-9)
4. **Unknown `removed_by_category`**: which removed state, and may `removed_by_reddit` return to live on an intact payload? (D-8)
5. **Retained copies**: is a month of daily/weekly backups holding deleted text acceptable, or do backups need scrub-aware retention? Same question for 14-day digest files containing titles. (D-4)
6. **Banned-sub policy default**: scrub only items confirmed gone via `info()`, or everything from a banned sub?
7. **Test subreddit**: will you create the personal restricted subreddit (account-age rules permitting)? P-01, P-02, P-04, P-05, P-06, P-09, P-10, P-11, P-12 and all cassettes depend on it.
8. **Public probes**: is it acceptable to probe public examples for Reddit-removed posts (P-03) and account-deleted authors (P-13), given the saved payload is already `[removed]` or has the body replaced?
9. **Per-post expansion cap**: per fetch for huge threads, or cumulative across revisits? (D-3)
10. **Zero-new threshold**: K=3 consecutive runs per subreddit, and is r/editors exempt on weekends?
11. **Budget scope**: do token refreshes and the freshness anchor count against the per-run budget? (D-11)
12. **`--gateway fake` guard**: refuse against the default `DATA_DIR`, or require an explicit `--data-dir`? (D-10)
13. **Cancel latency**: is "stop at the next request boundary, roll back the tree" acceptable for the UI Cancel button? (D-16)
14. **Fixture scrubbing**: automatic username replacement on `probe --save-fixture`, or manual review before commit?
