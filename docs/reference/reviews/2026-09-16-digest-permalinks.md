# Review record: the digest's post links (2026-09-16)

**Scope.** `src/threaddigest/db/repo.py`, the `ranked_posts` read: the permalink it hands
`core.digest.PostItem` is now rooted at the module constant `REDDIT_WEB_HOST` instead of
being passed through as the site-relative path the column stores. Landed as `0ba61c9` with
its `docs/runbook/KNOWN_ISSUES.md` row, KI-036, and the two tests that hold it. `db/repo.py`
is a review-required surface, which is why this record exists.

**The defect.** `posts.permalink` holds what Reddit's API returns,
`/r/premiere/comments/1abc1/x/`. Rendered into an `href` unchanged, that resolves against
whichever host served the page, so every post link in the digest pointed at
`127.0.0.1:8765`. The ranked list exists to put the reader in the thread; it was the one
thing the list could not do. The gap was not discovered after the fact: the register row for
`69d369b..24fc717` recorded it on the day the first web slice landed, as one of three things
that slice returned to the main session rather than papered over.

**How reviewed.** In-family, the session that made the change under a bounded brief; not an
independent seat, which is this record's weakness. Three things were checked rather than
assumed:

1. *Which reads hand a permalink to the digest.* `ranked_posts` is the only one. The
   repository's other mention of the column is the ingest value builder, which writes it;
   `core/digest.py` declares `PostItem.permalink` and three renderings consume it — the page
   template, the Markdown digest and the HTML digest — all from the one model, which is why
   the host is joined on at the read rather than in each rendering.
2. *Whether the fix could be bought by rewriting rows.* The repository test asserts, in the
   same breath, that every stored `permalink` still begins `/r/`. Storing the relative path
   is right: it is what the column's comment describes, what a scrub clears, and what a
   re-upsert compares. Only the value travelling out of the read changed.
3. *Whether the golden moved.* It did not. `tests/unit/golden/digest_example.md` was built
   from a hand-written model whose permalinks were absolute all along — which is part of why
   the defect survived the slice: the digest's own golden showed the links it should have had
   while the database path produced links it did not.

**Refutations attempted.** That a helper function belongs around the join: refused, there is
one call site and N-20 asks for two concrete uses. That the host belongs in settings today:
deferred to M2 with the reason in the constant's own comment, because the UI gains its
configuration there and a setting with no reader is the same abstraction under another name.
That the constant belongs in `settings.py` rather than `db/repo.py`: it sits with its one
consumer for now; moving it is the M2 change, not this one.

**Both tests were watched red before the fix.** The repository's failed on
`'/r/premiere/comments/x/'.startswith('https://www.reddit.com/r/')`; the page's named the
three relative hrefs it found. Neither would have passed against the unfixed read.
