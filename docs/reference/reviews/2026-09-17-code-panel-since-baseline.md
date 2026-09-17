# The new-module panel over the code built since 2026-09-15 (2026-09-17)

**Why this panel.** `docs/PLAN.md` § Review harness prescribes, for a new module, a new service or
a migration, two focused seats (correctness and tests; operator and data safety) plus one
adversarial seat, fresh-context and read-only. The code landed since the round-one fix panel of
2026-09-15 — the collector services, the real adapter and the fake, the `probe` and `doctor`
commands, the web slice, revision 0005 — carried single-pass landing records only, each saying
"not an independent seat" is its weakness. Wes asked on 2026-09-17 when the adversarial code
reviews happen; this is the answer, run before M1b adds six modules on top.

**What the seats were given.** The brief `brief_CP_code_panel.md` (kept with the session's
working files, not in the tree), a detached worktree at `main` commit `7528af9`, permission to
run the code against a temporary data directory with the fake gateway only, and no permission to
edit. Seat C was also permitted to stage violating changes to see whether the guards caught them,
reverting everything before it finished. The three seat memos are filed beside this record as
`2026-09-17-code-panel-seat-A.md`, `-seat-B.md` and `-seat-C.md`; every finding below cites the
seat's own reproduction.

**Verdict.** The load-bearing paths held under independent re-running: the migration round trip,
the content-state machine clause for clause, the escaping of hostile author-controlled strings,
the Host check failing closed, the backup before a destructive migrate, the two-call cost of the
network diagnostic, the lock, the run status precedence. The failures concentrate in claims
(docstrings describing a mechanism that does not exist, a guarantee tested where it cannot fail,
a template header the template itself breaks), in the seams between the tree and the machine (a
gate that flips on a clean tree), and in two entry points nothing had ever run for real. Two P0,
ten P1, fourteen P2, weighed by evidence rather than tallied; every one reproduced by the seat
that raised it, and the two P0 re-checked by the main session before this record was written.

## Findings, ranked, with their disposition

| id | sev | where | what | fix round |
|---|---|---|---|---|
| B1 | P0 | `deploy/launchd/run.sh` | both scheduled jobs invoke the package as a module and the package has no module entry point, so every scheduled run and hourly doctor would exit at once; the deployment test writes the missing entry point itself onto the test path | H-B |
| C-1 | P0 | `adapters/reddit_praw.py` | a 429 whose `Retry-After` is the HTTP-date form fails inside the library's own constructor, classifies fatal, stamps the source errored, and the run keeps requesting while rate-limited; tranche B had accepted this path knowingly, a call this record reverses | H-A |
| A1, C-2 | P1 | `tests/gates/test_routing_rows_resolve.py` | the routing gate is red on the committed tree wherever the gitignored build directory is absent, and green after another test creates it; three identical suite runs gave green, red, red | H-C |
| A2 | P1 | `core/budget.py` | the hard cap bounds the configured limit, never the spend; with `reserve: 0`, a legal configuration, a run was driven past the cap | H-D |
| A3 | P1 | `core/budget.py`, `services/runs.py` | two docstrings describe a session hook that records every response; no such call site exists, the count is synced at four named points | H-D |
| A4 | P1 | `tests/services/test_runs_lifecycle.py` | DB-64's equality is asserted on the in-memory context where it cannot fail; on the row, a crash after a heartbeat leaves warnings recorded and the counter absent | H-D |
| B2 | P1 | `settings.py` | "non-secret" means "not typed as a secret", so the OAuth client id and the account name land on every run row and print on the digest page when they change | H-B |
| B3 | P1 | `services/probe.py` | a traversing or absolute save name writes outside the data directory, against the module's own docstring | H-B |
| B4 | P1 | `Makefile`, `tools/make_demo_fixture.py` | the demo corpus is written into the default data directory beside the real database | H-B |
| C-3 | P1 | the gates | three planted violations passed every gate: a regression test weakened in place (review-only by design), a dynamic import of the Reddit library from `services/`, a live write outside the data directory that the suite exercised thirty-seven times | H-C |
| C-4 | P1 | `core/digest.py`, `web/templates/report.html` | the ranked list prints three bare numbers, one of them Reddit's own comment count, under a header claiming every number carries its population | H-E |
| C-5 | P1 | `adapters/reddit_praw.py` | the tree builder re-emits a comment an expansion returns again; the fake cannot produce the shape, so the contract suite would never see it | H-A |
| A5 | P2 | `core/deletion.py` | a stale docstring clause says the hold counts a miss; the code and the plan say it does not | H-E |
| A6 | P2 | `services/report.py` | the "trailing four weeks" baseline contains the seven-day window it is compared against; settled as a disjoint baseline | H-E |
| A7 | P2 | `cli.py` | the dry-run notice names two counters that are structurally zero while a third, equally zero, prints unmarked | H-E |
| A8 | P2 | `tests/unit/test_normalize.py` | fixture coverage is a hand-typed list, so a sixth fixture would be silently untested | H-E |
| A9 | P2 | `services/sweep.py` | the "never folded inside a transaction" docstring is contradicted by the page counter | H-D |
| A10 | P2 | `tools/code_health.py` | dead-code analysis scans `src` and `tests` together, so a symbol reached only from a test counts as used; the budget module's unused API is the example | H-C |
| B5 | P2 | `db/repo.py` | a stored permalink that is not a rooted path renders a link whose real host is elsewhere | H-B |
| B6 | P2 | `deploy/launchd/run.sh` | the log directory is fixed before the environment file is read, so a relocated data directory is ignored | H-B |
| B7 | P2 | `web/middleware.py` | the security header lacks the directives the default source does not cover, so the pages are frameable | H-B |
| C-6 | P2 | `adapters/reddit_praw.py`, the fake | a split stub relabels Reddit's hidden-comment count as the chunk size; the fake reports the true count, so the two disagree by construction | H-A |
| C-7 | P2 | `services/migrate.py` | KI-039's guard is a hand-maintained list of two functions while the upgrade issues four head-model statements below head | H-C |
| C-8 | P2 | `db/repo.py`, `services/doctor.py` | staleness is keyed on a run with zero warnings, so a routine warning makes the hourly alarm permanently red on a healthy collector | H-D |
| C-9 | P2 | `.ratchets/` | the floors carry slack on a clean tree; the landing routine now bumps them so headroom is spent, not banked | H-C |

Cut list, adopted: the `new_head` port method with its adapter, fake and anchor code, which the
freshness anchor's retirement (N-08) left with no caller; the budget module's unused public API and
the tests that exist only for it; the lock path spelled three times; the notifier docstring
promising a command that does not exist; the duplicated environment helper; the duplicated
checkpoint-and-re-finish block in the collector; a shape check on the seed file's theme block.

Settled by the main session rather than asked: the rising-phrases baseline is the three weeks
before the seven-day window, not the four weeks containing it; the account name and the client id
are typed as secrets and never stored; the hard cap bounds the spend in `can_afford` and a
failure-severity invariant holds it at the end of every run; staleness is keyed on the newest run
that swept a source successfully; the tree builder de-duplicates on the item's name.

## What the demo hides

Seat C measured it: the generated corpus has no comments and constant ranking keys, so the
digest's headline list is ordered by id and the function the product is built around is
exercised by no demo run; no title holds a character HTML must escape, a non-Latin script, an
emoji, or more than about forty-five characters; no source approaches the page cap; no
tombstone is ever ingested. M1b's demo brief extends the corpus with trees, and the title set
gains the hostile and long cases.

## Disposition

Five fix briefs, serial, each landing failing tests first with a known-issues row per reproduced
defect and a register row where a review-required surface moves: H-A the adapter and the port,
H-B deployment and data safety, H-C the gates and the harness, H-D the budget, the run
lifecycle and the doctor, H-E the digest and the smaller correctness items. The previous
rounds' conclusion that the harness is ready stands with two amendments recorded here: a gate
may ask nothing of the machine it runs on, and an entry point is proven by running it.
