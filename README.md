# Thread Digest

A personal, read-only reader for a handful of subreddits. It reads Reddit through the
official API, keeps what it reads in one SQLite database on the machine it runs on, and
writes its owner a private digest of what people in those communities are struggling with.
One user, one Reddit account, one registered app. It is not a service and has no other
users; nothing it reads is published, shared, or sent anywhere.

## What it never does

It never posts, comments, votes, or sends a message: every call it makes is a read. It never
redistributes or sells the content it reads and never uses it to train a model. It keeps one
record per author — a name, an id, when they were first and last seen, and a running count of
their posts and comments, added up across every subreddit it monitors rather than kept apart
per subreddit. That record exists only to label whose post or comment is whose; nothing else is
built from it, and it is dropped outright the moment the account itself is deleted. It reads
only the subreddits its owner has listed, under a per-run request budget with a hard cap, so a
run cannot quietly grow.

## Deleted and removed content

Content a person removes on Reddit is removed here. Stored items are re-checked on a
schedule; an item that comes back deleted by its author or removed by a moderator is
scrubbed — its text and its author identifier are overwritten, and the row survives only as
a tombstone, so the item is never fetched again and the counts stay honest. If a Reddit
account is deleted, the author identifier is dropped from everything that account wrote.
Backups follow the same rule rather than preserving what was scrubbed. This work lands
before the first real fetch; today there is nothing to scrub, because nothing has been read.

## Status

The design and the offline build are complete and green. The collector, the database and
the digest are built and tested against an in-process fake of Reddit. The code that talks to
the real API is written too, and is tested against mocked HTTP for its failure paths, its
request counting, and its error translation, but **it has never been run against Reddit, and
no Reddit data has been read.** The project is waiting on Reddit Data API access approval;
the recorded fixtures and the first real fetch both come after that.

## Building and checking it

    make setup      # installs uv if missing, creates the virtualenv, copies .env.example
    make check      # format, lint, types, import layering, the whole test suite, the gates

`make check` is the gate. It is green before anything lands, and its output is pasted into
the pull request rather than described.

## Where to read more

- `docs/OVERVIEW.md` — the system in ten minutes.
- `docs/PLAN.md` — the design; canonical for every design question.
- `docs/runbook/RUNBOOK.md` — setting it up, operating it, migrating and restoring it.
- `CLAUDE.md` — the working agreement every change follows, and what enforces each rule.
