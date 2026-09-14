---
paths:
  - "src/insightminer/services/**"
  - "tests/services/**"
  - "tests/e2e/**"
---
# Collector service rules (load when a service file is edited)

Read first: `docs/PLAN.md` § Collector algorithm and § Resilience to outages; the design brief's decisions are recorded in `docs/decisions/DECISIONS.md` (2026-09-13 entries).

- Every mutating command takes the collector lock and writes a run row whose heartbeat carries the stage; a dry run performs zero database writes and writes no run row.
- One database transaction per page; a failure inside a page leaves nothing from that page; the terminal per-source row is written in its own transaction.
- Retries follow the ladder in `core/retry.py`; the second rate-limit response ends the run at once; fatal gateway errors end the run, per-source errors end only that source.
- A run with any warning is `partial`; `ok` means zero warnings; a FAILURE invariant outranks a terminal status.
- Services receive their collaborators (gateway, clock, notifier, engine, settings) explicitly; `praw` is never imported here; the CLI constructs everything.
