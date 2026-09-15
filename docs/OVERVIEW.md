# Insight Miner in ten minutes

> **Who this is for.** A reader who wants to understand what the system is, what it answers, how, and
> what it deliberately does not do, without reading the plan. Every design fact here is stated in full
> in `docs/PLAN.md`, which is canonical; this page points at its sections and restates no numbers.
> **Update policy:** prune-stale, rewritten in place. What is built right now is on
> `docs/recent/STATUS.md`.

## What it is

A personal, rules-compliant harvester of Reddit discussion, stored locally in one SQLite file, read
through a local web UI and a periodic digest. It runs on a schedule from one Mac, later from a
container on a NAS. It reads Reddit through the official API in read-only mode with an honest
user-agent, never posts or replies, and honours deletions: content a person removes on Reddit is
scrubbed here on the next scheduled run, and the search index clears the bytes as it goes.

## The one question it answers

*What are people struggling with, how many distinct people, and for how long.* Everything about how
the data is stored and queried follows from that sentence. The first workspace is Premiere Pro and its
adjacent editing communities; the design carries other domains as further workspaces (below).

## How the data becomes insight

**Our own ranking, not Reddit's.** Reddit's hot and popular listings answer Reddit's question: what is
engaging right now. This system never uses them. Every ranked list, in the digest, on a theme page, in
an export, uses one deterministic function: distinct authors first, then comment count, then score,
then a stable identifier so ties never wobble. Never raw post count, never recency. One prolific
poster cannot manufacture a trend and a fresh post is not an important one. Authors are counted by
their stable Reddit identifier, never by display name; scrubbed and deleted accounts are excluded from
the count rather than lumped into one bucket, and every ranked list prints the share of its rows that
had a countable identity.

**Themes are rules you write, not a model.** A theme is a named group of keyword or regular-expression
rules (match, exclude, only-in), scoped to title, body, or comments. Tagging records which rule
matched, never a text snippet. The rule set is hashed, so changing a theme re-tags everything.
Determinism is what makes digests weeks apart comparable. There is no learned ranker and no
conversational agent inside the app before the analysis milestone; exploring what to track happens
beside the app and arrives as a rule file.

**Two signals for what you are not looking for.** The digest's untagged section surfaces posts no
theme matched but several distinct people are discussing. Its rising-phrases section compares title
phrases in the current window against a trailing baseline. The first says a problem exists that the
rules miss; the second says it is growing.

**"For how long" comes from revisiting.** A post is re-fetched on a ladder of days after it was
created, so comment counts reflect a thread's maturity rather than its first hour, and every fetch
stores a numeric-only snapshot of score and comment count: the raw material for velocity. Nothing
textual is snapshotted, so a deleted post leaves no derived copy.

**Every count carries its denominator.** No bare numbers: a theme shows its matches *of* the new posts
in the window; the digest's backlog and compliance sections say what was not harvested and how old the
last full re-check is, so a coverage gap is visible rather than absorbed into a smaller number.

**Search is over live content only.** Full-text search is built over views that exclude deleted and
scrubbed rows, so a removed post is not merely hidden from search but never indexed.

## Workspaces: the same system on another domain

A second purpose does not get different tables. A **workspace** is a lens over shared data: its own
sources (subreddits, saved searches), its own themes, its own digest settings, and its own ranking
rule; posts and comments are stored once and are visible in every workspace whose sources reach them.
The compliance obligations attach to the data, not the focus area, so deletion and scrubbing are
workspace-agnostic, and the request budget is one pool reported per workspace. The schema carries
workspaces from the first revision; version one runs a single workspace, Premiere Pro, and the loop
over several lands when a second one is actually wanted (plan § Workspaces). A second domain may
equally run as a separate instance on another machine or in another container, and leaving a domain
is short either way: archive or delete the workspace, or export and start a fresh data directory.
Every focus area is personal interest with no business application (Wes, 2026-09-15), which keeps
all of it inside Reddit's non-commercial terms; and the system tells you what people *say*, never who
they are. A very large community will not sweep completely at any cadence, and the design says so
rather than pretending: the levers for that case (a daily cadence, an ingest filter) are deferred with
their triggers in the decisions log.

## What keeps it honest

The rules of the harness are in `docs/INSIGHTMINER_HARNESS.md`. In one sentence: every rule names the mechanism
that enforces it, the mechanisms sit in the path of every change and fail closed, `main` receives
only a tree the full check has stamped green, and every count the human reads is derived by a tool
rather than typed.

## What it deliberately is not

Not a search engine over Reddit. Not a bridge to any other system. Not a learned ranker. Not a
profiler of people. Not a daemon: it runs on a schedule, has until the next run to succeed, and pauses
and resumes on its own. Not a commercial service. The analysis layer (summaries, trends) is a later
milestone, and the decisions that closed each of these doors, with the trigger that would reopen it,
are in `docs/decisions/DECISIONS.md`.

## Where to go next

- The plan: `docs/PLAN.md` (design, canonical).
- What is built and what is next: `docs/recent/STATUS.md`.
- Why a thing was decided: `docs/decisions/DECISIONS.md`, then `docs/insights/INSIGHTS_2026-09-12.md`.
- Operating it: `docs/runbook/RUNBOOK.md`.
