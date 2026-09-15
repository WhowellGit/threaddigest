# Reddit policy facts, read from the live pages on 2026-09-14

Read by the session itself (the support site through the browser pane, the two policy pages
through a plain HTTPS fetch), so an outside reviewer no longer has to re-fetch them: the next
review packet carries this file. Obligations are paraphrased closely; only the shortest operative
phrases are quoted. Dates are the pages' own. Re-read the pages before M1c and at each quarterly
review; a changed revision date is a trigger to update this file and the decisions log.

| Page | Revision shown on 2026-09-14 | Where |
|---|---|---|
| Data API Wiki | page timestamp 2026-05-11 | `https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki` |
| Data API Terms | effective 2023-06-19, last revised 2026-07-20 | `https://www.redditinc.com/policies/data-api-terms` |
| Developer Terms | effective 2024-09-24, last revised 2026-03-24 | `https://www.redditinc.com/policies/developer-terms` |
| Responsible Builder Policy | "updated 3 months ago" on the page (no timestamp captured) | `https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy` |

## What binds this collector

1. **Deleted content must be removed.** The wiki's rules section: user content in the
   collector's possession that has been deleted from Reddit must be removed. For a deleted post
   or comment that means everything related to it (the wiki lists title, body and embedded
   URLs). For a deleted account it means the user id (`t2_*`) and every author-identifying
   reference on that account's posts and comments (the wiki lists the author id, name, profile
   URL, avatar URL and user flair).
2. **Forty-eight hours is a strong recommendation, not a stated deadline.** The wiki "strongly
   recommend[s]" routinely deleting stored user data and content "within 48 hours".
3. **Anonymizing does not license retention.** The wiki: retaining deleted content or data
   "even if disassociated, de-identified or anonymized" violates the terms and policies.
4. **Retention is bounded by the approved use case.** Data API Terms § 3: data may not be used or
   retained beyond the approved use case, and data not required for it must be deleted
   immediately; on termination or loss of access, cached or stored User Content is deleted.
5. **Removed, withheld or modified content follows the same rule.** Developer Terms § 3.3
   (Content Removal): User Content that is deleted, gains protected status, or is suspended,
   withheld, modified or removed must be deleted or modified "as soon as possible" after the
   change, or after a written request from Reddit or the user.
6. **Access needs explicit approval.** The Responsible Builder Policy's first restriction:
   access must be requested and explicitly approved before any Reddit data is accessed through
   the API, with agreement to the applicable terms; the wiki links the request form ("To request,
   please contact us here"). Transparency is required: no masking how or why data is accessed,
   no multiple accounts or requests for one use case.
7. **Commercial use needs a separate written agreement** (Data API Terms § 3; Developer Terms
   § 4.1; the Responsible Builder Policy). The policy also forbids using Reddit data to train
   machine-learning or AI models, to target ads, and to derive or infer sensitive characteristics
   about users, and forbids re-identifying users through off-platform matching. The
   commercial-use stance is Wes's own item (`docs/decisions/DECISIONS.md`, 2026-09-13).
8. **Rate limit and identification.** One hundred queries per minute per OAuth client id,
   averaged over a window the wiki says is "currently 10 minutes"; the three `X-Ratelimit-*`
   headers are approximate; unauthenticated traffic is blocked; the User-Agent must follow
   `<platform>:<app ID>:<version string> (by /u/<reddit username>)` and never lie.
9. **Researchers are a separate regime** (the Reddit for Researchers program, with its own
   retention rule of re-running queries against the latest export). Not this project's path.

## What this settles and what it opens

- Settles the round-one "cannot tell" items (`docs/reference/reviews/2026-09-14-external-round-1.md`,
  reviewer C's item 13 and reviewer B's policy section): the clauses and dates those reports
  gave were right.
- The two-day reconcile cadence meets the forty-eight-hour recommendation for the live database.
  For backups the obligation is the one that matters: content "in your possession" includes a
  retained backup that predates a learned deletion. The ruling on backup retention is sharpened
  in the round-one record.
- Opens one prerequisite for tranche B: the API access request and its approval (item 6) before
  the first credentialed call, recorded in the status page's waiting list.
