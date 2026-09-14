# External review, round one: three deep-research reports and one partial run on the packet at 616f9b9 (2026-09-14)

## What the reviewers were given

Commit `616f9b9f871c2b4d052f42f6daf6b489d8d938e5`, packet hash `7947b972bd4bec38f59ae5b400f2e640f9d2cc4469f26329ec271ede314fe721`, built 2026-09-14 by
`tools/review_packet.py`: the ten-file upload set (README, brief, claims, seven bundle parts) with
`MANIFEST.json`, and `01-QUERY.md` pasted as the prompt. The same packet went to every reviewer, so
the findings are comparable. The packet predates the SQLite branch (`a0d8e8a`), so KI-009, KI-010,
KI-012 and KI-013 were open in what the reviewers read and fixed by the time the reports came back.

Reviewers are labelled, never named (the register's tier convention):

- **A**: a fifteen-finding report in the brief's own shape, with web citations. Its locations cite
  bundle files the packet does not have (`3-core.md`, `2-db.md`, `4-deploy.md`, `6-tests.md`,
  `1-adapters.md`, `5-harness.md`) and quote lines that are not in the tree, so each finding was
  judged on its substance alone.
- **B**: a facts-only sub-report whose live retrieval failed; it says so and marks every date
  unverified. Nothing on the code.
- **C**: a long analytical report with citations that read the code (the hooks, the backup module,
  the ranking, the schema).
- **D**: a code-executing run that reproduced its claims before reporting and stopped at its plan's
  usage limit. Its early notes were pasted by Wes; the rest follows when the run resumes and is
  triaged the same way.

Triage per `docs/runbook/RUNBOOK.md` § 7: every finding re-run against the tree, never re-read. The
hook claims were run through the two hook scripts with the reviewers' exact command text in a
throwaway repository; the restore and secure-delete claims as driver-level scripts; D's three
collector claims as pytest reproductions against the fake gateway (bodies below, held for the fix
branch). Verdicts: **confirmed** (reproduced), **refuted** (with the evidence), **known** (already
registered), **cannot tell**, **ruling** (a design choice held for Wes).

## Reviewer D (partial notes, code-executing)

1. A crosspost's normalized fields drop the parent text, but the collector stores that text and the
   parent's author in `raw_json`; the existing test checks only the normalized object.
   **Confirmed.** The crosspost row's `raw_json` carried the parent's `selftext`, `selftext_html`,
   `title` and `author` inside `crosspost_parent_list`. `docs/decisions/DECISIONS.md`'s decision
   table and the schema comment both say parent text is never stored. → KI-016.
2. After the only source becomes quarantined, later runs report `ok` while making zero requests.
   **Confirmed.** The second run closed `ok`, exit 0, zero pages, no notification; `doctor`'s
   last-run-age check would stay green indefinitely. → KI-017.
3. A listing shortened by filtered items reports complete coverage while the fake still holds
   uncaptured posts. **Confirmed.** One thousand and fifty posts, one hundred of the newest thousand
   removed: the sweep saw nine hundred items over ten pages, recorded `exhausted`, stamped
   `last_complete_poll_at`, and skipped the gap check on a source whose watermark lay beyond the
   window. → KI-018.
4. The restore primitive deletes the live write-ahead log before preparing the replacement file, so
   a copy failure loses committed data. **Confirmed.** A crash-left log holding a committed table:
   opening a copy recovers it (the control); after `restore()` with a missing backup file, the log
   was gone and the reopened database had no such table. → KI-015.
5. The merge hook allowed a merge whose resulting tree differed from the stamped tree.
   **Confirmed**, and wider than reported: with the stamp naming the branch's tree, the hook allowed
   `git merge feature` on a diverged `main`, `--no-ff`, `-s ours`, `-X theirs` and `--squash`; the
   plain merge on a diverged `main` and the `-s ours` merge each produced a tree the check never saw.
   → KI-019.

## Reviewer C

1. The fake gateway is an executable specification, not a validated model; the sequencing (real
   adapter and captures before comment trees) is right and must not change. **Known**: the probe day
   before M1b (Wes, 2026-09-14) and the brief's own first fact.
2. FTS5's persistent `secure-delete` option is the mechanism for the deletion threat model; `optimize`
   after a scrub is cleanup, not the control. **Confirmed by experiment** (below): with the option
   set, the `delete` command removed the term's bytes from the index blocks immediately, no
   `optimize` needed, and the file held no copy after the checkpoint; without it the delete markers
   added a second copy. Adoption proposed as revision 0004; ruling held for Wes.
3. A backup taken before a deletion is learned keeps the deleted content; a fourteen-day age ceiling
   is not deletion compliance; the backup lifecycle must take part in the scrub protocol.
   **Ruling**, and the check found a mirror conflict inside the plan: § Collector algorithm step 6
   says "keep 7 daily + 4 weekly" while § Adversarial changes says "no backup older than 14 days".
   Recommendation below.
4. Daily scheduling stays blocked until between-run monitoring exists; `launchd` jobs must handle
   `SIGTERM`. **Known**: the M1d blockers (Wes, 2026-09-14).
5. Both enforcement hooks parse command text, and shell indirection defeats them: a protected path
   assigned to a variable in one segment and written through in the next; `git` invoked through a
   variable. **Confirmed**, and wider: seven of seven git forms tried (variable, `bash -c`, `sh -c`,
   `eval`, an interpreter one-liner, a variable push to `main`, a variable switch-and-merge) and four
   of six protected-path forms (a variable, a command substitution, a path built from pieces, the
   settings file through a variable) were allowed. → KI-020. C's framing (a policy hook watching
   shell text is mistake prevention, not a security boundary) is accepted for the ledger wording;
   ruling below.
6. `tests/gates/test_rules_name_their_enforcer.py` checks that a named enforcer exists, not that it
   enforces; the read-before-touch hook is audit, not enforcement, until 2026-09-28. **Known**: both
   are stated where they live (the gate's docstring; the rules table's mode note; the status page).
7. Demote three gate classes (rules name an enforcer, status-page shape, routing pointers) to lint or
   periodic review, because their failure mode is drift, not data loss. **Ruling**: declined,
   recommendation below.
8. `rank_posts()` leaves complete ties in input order, so a query ordering change reorders the visible
   list; add a deterministic final key. **Confirmed by reading**: `_rank_key` has three keys. Cheap;
   on the fix branch (created time, then post id, as the last keys).
9. Distinct authors are not distinct people with the problem (helpers, spectators); the reading week
   is the validation. **Known**: D-09 and the acceptance criterion.
10. `post_themes.rule_pk` is `NOT NULL`, so a manual tag cannot be represented with its own
    provenance. **Known**: the rev-2 design item in the hardening queue.
11. `praw>=7.8` has no upper bound while PRAW 7 and 8 differ in how many comments one
    `replace_more` step discovers. **Partly**: `uv.lock` pins 8.0.3, so an upgrade is deliberate;
    the adapter's budgeting will assume 8's behaviour, so the bound is tightened to `>=8,<9` on the
    fix branch (cheap).
12. KI-010, KI-012 and KI-013 are well founded. **Known**, fixed in `a0d8e8a` before the reports
    arrived.
13. Reddit's guidance requires removing deleted content including titles, bodies and URLs, strongly
    recommends doing so within forty-eight hours, and the Data API Terms were last revised
    2026-07-20. **Cannot tell** from this session: the policy pages refuse the fetch tool. Wes reads
    them and pastes the clause and dates into `docs/decisions/DECISIONS.md` before M1c.
14. The first three live probes: paged `/new` with recorded cursors; a controlled tree with
    `more`, a deletion and a continue-thread node; batched `info()` over live, deleted, removed,
    missing, account-deleted and inaccessible items. **Known** in substance; the three-probe list is
    adopted into the probe-day checklist (`docs/PLAN.md` § M1 probe) on the fix branch, with one more
    from A-7: the 100-child chunking of a large `more` node.
15. Forty-three to seventy engineering hours before the schedule. Noted, not adopted as a plan; the
    queue on the status page is the plan.

## Reviewer A

Each item on its substance; the cited locations are not in the packet.

1. An empty `/api/info` response marks the item `deleted_by_author` and triggers a scrub.
   **Refuted**: `core/deletion.py::decide` rule 2 holds an item missing from `info()` as
   `gone_unconfirmed` and declares it `gone` only after two misses; `deleted_by_author` needs the
   category or the marker.
2. `wal_checkpoint(TRUNCATE)` silently aborts under a reader. **Known**: KI-013, fixed.
3. Rejected raw payloads bypass the scrub. **Ruling** (a design point, not a defect today):
   `raw_rejects` rows hold raw text, have no id to reconcile, and keep a thirty-day retention whose
   pruning is an M1d blocker; the surface is added to the deletion-boundary list in the fix branch's
   canary spec.
4. Zero FTS matches does not mean the bytes are gone. **Known**: KI-009, fixed with a byte-level
   test.
5. Backups by `shutil.copy2` drop the write-ahead log. **Refuted**: `db/backup.py::online_backup`
   uses the driver's online backup API into a staged file, integrity-checked, fsynced and renamed.
6. `INSERT OR REPLACE` bypasses the `AFTER UPDATE` triggers. **Refuted**: the repository emits
   `ON CONFLICT DO UPDATE` / `DO NOTHING` only (`db/repo.py`), and
   `tests/db/test_fts.py::test_a_routine_upsert_with_identical_text_leaves_the_index_untouched` with
   its control exercises exactly the update path.
7. The fake does not model the 100-child limit of `morechildren`. **Cannot tell** at this commit:
   the port's `fetch_tree(post_id, more_limit)` keeps chunking inside the adapter, which does not
   exist yet; added to the probe-day checklist.
8. `author == "[deleted]"` alone scrubs valid content from deleted accounts. **Refuted**: rule 8
   maps a missing author with `author_fullname` absent to `account_deleted` and keeps the content;
   only a link post with no author is held pending `info()`.
9. `StartInterval` skips runs missed during sleep. **Refuted**: the plist uses
   `StartCalendarInterval` at three times a day; C confirms that missed calendar runs coalesce on
   wake.
10. Sleeping for `X-Ratelimit-Reset` balloons a run by hours. **Refuted**: `core/retry.py` bounds a
    429 wait to `min(retry_after, 300)`; there is no adapter yet to sleep otherwise.
11. Batch migrations and `sqlite_sequence`. **Known**: KI-014, open.
12. A LaunchAgent needs a logged-in session. **Ruling** with C-4, below.
13. Client-side hooks are voluntary. **Known**: the ledger's external-controls section; CI is the
    required check once a remote exists; the agent-side hook is the point of the hook.
14. The fake tests itself. **Known**: the probe day.
15. Themes ranked by raw match count. **Refuted**: `core/digest.py::rank_posts` orders by distinct
    authors, then comments, then score (D-09).

A's questions: `optimize` scheduling (answered: KI-009 and the secure-delete proposal); rejects
recovery (design point 3); LaunchDaemon (ruling below); the ten-thousand-comment cap (M1b design).

## Reviewer B

No code findings. Its stable facts agree with what was built the same day: the checkpoint's busy
column, the `delete` command's same-values requirement, `VACUUM INTO` not syncing its output (the
backup module fsyncs), batch mode dropping `sqlite_autoincrement` (KI-014), agents needing a login
session, `SIGTERM` then `SIGKILL` after twenty seconds. Its Reddit-policy items are unverified, the
same gap as C-13.

## Weighing

Independence and evidence, never a tally. D executed the code and every one of its five claims
reproduced. C read the code and found the hook holes; its secure-delete point held up under
experiment. A's fabricated locations mean its correct points cannot be credited to reading this tree;
they coincide with registered issues and general facts. B added nothing on the code. The round's
yield is D's five defects and C's two changes; one evidenced dissent from the code outranked three
agreements in prose, as the runbook requires.

## Confirmed defects, registered open

- KI-015 restore deletes the live log before it copies (`db/backup.py::restore`).
- KI-016 a crosspost stores its parent's text and author in `raw_json` (`core/normalize.py::canonicalize`).
- KI-017 a run with no enabled source closes `ok` (`services/sweep.py::sweep_all`).
- KI-018 a capped listing with removed slots is recorded `exhausted` (`services/sweep.py::_page_loop`).
- KI-019 the merge hook accepts non-fast-forward merges (`tools/hooks/no_bypass_git.sh`).
- KI-020 both hooks are blind to shell indirection (both hook scripts).

Evidence pasted from the reproductions (2026-09-14):

```
restore: wal bytes while the writer is alive: 12392
restore: control: rows after reopening the crashed copy: 1
restore: case: restore failed at the copy step: FileNotFoundError
restore: case: -wal still present after the failed restore: False
restore: case: reopen -> sqlite3.OperationalError: no such table: notes

merge (stamp names feature's tree):
ALLOWED   control: ff-only on linear main    'git merge --ff-only feature'
ALLOWED   diverged main, plain merge         'git merge feature'
ALLOWED   diverged main, --no-ff             'git merge --no-ff feature'
ALLOWED   linear main, -s ours               'git merge -s ours feature'
ALLOWED   linear main, --squash              'git merge --squash feature'
ALLOWED   linear main, -X theirs             'git merge -X theirs feature'
diverged plain merge: stamped tree 19919aaf957c, resulting tree 86a951013444, DIFFERENT
-s ours merge:        stamped tree 19919aaf957c, resulting tree 5e8b042634bf, DIFFERENT

git hook, indirection: BLOCKED direct --no-verify (control); ALLOWED: variable holds git,
bash -c string, eval string, variable push to main, variable switch+merge, sh -c push,
interpreter one-liner.
files hook, indirection: BLOCKED direct redirect (control), bash -c string; ALLOWED: variable
then redirect, command substitution, path built from pieces, settings file via variable.

pytest reproductions (the tests below, all three red on a0d8e8a):
crosspost: 'parent-body-zq7' is contained in the crosspost row's raw_json
no source: second run closed 'ok' with 0 pages fetched
cap:       stop_reason exhausted, items_seen=900, pages=10, last_complete_poll_at stamped
```

The three collector reproductions, to be lifted into `tests/services/` on the fix branch:

```python
def test_a_crosspost_row_keeps_no_copy_of_the_parent_text_or_author(
    fake, add_source, engine, clock, settings, notifier
):
    fake.add_subreddit("premiere")
    fake.add_subreddit("elsewhere")
    parent = fake.add_post("elsewhere", title="parent title",
                           selftext="parent-body-zq7 never to be stored",
                           author="parent-author-zq7", created_utc=BASE)
    cross = fake.add_crosspost("premiere", parent, created_utc=BASE + 60)
    add_source("premiere")
    outcome = collect.collect(engine, settings=settings, clock=clock, gateway=fake, notifier=notifier)
    assert outcome.status is RunStatus.OK
    raw = raw_json_of(engine, cross[3:])
    assert "parent-body-zq7" not in raw and "parent-author-zq7" not in raw


def test_a_run_with_no_enabled_source_is_partial_not_ok(
    fake, add_source, engine, clock, settings, notifier
):
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    add_source("premiere")
    fake.set_status("premiere", "quarantined")  # disabled on first sight (SS-04)
    first = collect.collect(engine, settings=settings, clock=clock, gateway=fake, notifier=notifier)
    second = collect.collect(engine, settings=settings, clock=clock, gateway=fake, notifier=notifier)
    assert first.status is not RunStatus.OK
    assert second.counters.pages == 0 and second.sweep.subreddits == ()
    assert second.status is RunStatus.PARTIAL


def test_a_listing_ending_at_the_cap_with_filtered_slots_is_a_cap_stop_not_exhausted(
    fake, add_source, run_context, notifier, subreddit_row
):
    fake.add_subreddit("premiere")
    total = 1050  # the newest 1,000 are reachable; 100 of those are removed
    for i in range(total):
        extra = {"removed_by_category": "moderator"} if 500 <= i < 600 else {}
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60, **extra)
    source = add_source("premiere", watermark_created_utc=BASE + 10 * 60)  # far behind
    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)
    after = subreddit_row(source.pk)
    assert result.stop_reason is StopReason.CAP
    assert after.last_complete_poll_at is None
    assert after.gap_suspected_at is not None
```

## Adoption proposed: FTS5 `secure-delete` (C-2)

The experiment, SQLite 3.53.1, an external-content index in the project's shape, the scrub done as
the triggers do it (`delete` with the old values, then the row rewritten):

```
secure-delete=off: blocks holding the term before 1, after the delete command 2, term bytes in the file after checkpoint: True
secure-delete=on : blocks holding the term before 1, after the delete command 0, term bytes in the file after checkpoint: False
```

Proposal: revision 0004 sets the persistent option on both indexes
(`INSERT INTO posts_fts(posts_fts, rank) VALUES('secure-delete', 1)`, same for comments) and runs
`optimize` once to merge the markers written before it; the byte-level test in `tests/db/test_fts.py`
gains the case "scrub without `optimize` leaves no term bytes" with the option off as its control;
`optimize` becomes weekly maintenance, not the compliance step, and SC-01 is reworded. Cost of the
option: slower updates and deletes on the index (the sweep's update triggers are now change-gated, so
the cost lands on real edits and scrubs only). Constraint from the documentation: once a row has been
deleted with the option set, the index file format needs SQLite 3.42 or later; `doctor` gains a
version check and the container image (M4) must satisfy it. Confidence high that it is the right
mechanism; medium on the migration's shape until written.

## Rulings held for Wes

1. **Backups and deletions (C-3, plan mirror conflict).** The plan says both "7 daily + 4 weekly"
   and "no backup older than 14 days". Recommendation: seven daily plus one weekly, fourteen days,
   stated in both places; the daily backup is taken after reconcile, so it is a scrubbed snapshot,
   and a deletion learned on day N is out of every retained backup by day N+14 at the latest; the
   retention sweep is written into the reconcile protocol as its last step, and the canary (DB-15's
   successor) asserts the ages. C's stronger reading (retire or regenerate every retained backup as
   soon as a deletion is known) is the alternative if Wes's reading of the terms requires it; it
   costs a regeneration per reconcile. Confidence moderate; the terms' text is Wes's to read (C-13).
2. **Login session (A-12, C-4).** LaunchAgents run only in a logged-in session, so the run and the
   local `doctor` die together at a login screen. Recommendation: no LaunchDaemon; the external
   dead-man ping (already an M1d blocker) is the detector, the runbook's install step says "auto
   login on, or accept that a reboot pauses collection until login", and M4's container path makes
   the question moot. Confidence high.
3. **Hook boundary wording (C-5).** Recommendation: adopt C's framing in the ledger row for G23: the
   hooks are mistake prevention for the agent, sitting in the path of every tool call; a script file
   the agent writes and then runs is outside their sight; the trust boundary against deliberate
   bypass is pre-commit, CI once a remote exists, review, and the remote's branch protection. KI-020's
   fix closes the reported shapes and states this limit. Confidence high.
4. **Demoting drift gates (C-7).** Recommendation: decline. Each of the three was born from an
   incident (a rule naming a nonexistent enforcer, a stale status page, a routing row pointing
   nowhere), they cost nothing at runtime, and Wes's standing rule is that nothing in the gate is
   advisory. Confidence high.

## Cannot tell from this session

Reddit's terms and wiki text and dates (C-13, B's E-series): the pages refuse the fetch tool. Wes
opens them and pastes the deletion clause, the forty-eight-hour language and the revision dates into
the decisions log; the runbook's triage step now says so.

## What changed as a result

- This record and its register row; KI-015 to KI-020 open with their reproductions above; seven
  refuted claims under § Swept in `docs/runbook/KNOWN_ISSUES.md`; the status page's queue and
  waiting list; `docs/runbook/RUNBOOK.md` § 7 (one record per round; unreachable pages are cannot
  tell); the decisions log.
- Held for Wes's go, in cost order: the fix branch (KI-015 restore ordering with a copy-failure
  test; KI-016 the reduction in `canonicalize` with the raw-copy test; KI-017 a `no_enabled_sources`
  warning; KI-018 the tenth-page rule; KI-019 `--ff-only` required, strategy and squash refused;
  KI-020 assignment resolution, `-c`/`eval` recursion, fail-closed on unresolvable expansions;
  revision 0004 secure-delete with its fixture; the rank tie-break; the PRAW bound; the probe-day
  checklist additions), then the four rulings above.
