# Review record: the probe command (2026-09-16)

**Scope.** `src/threaddigest/services/probe.py` and the `probe` group in
`src/threaddigest/cli.py`: the five capture modes the probe day needs (`about`, `listing`,
`tree`, `info`, `search`), each calling exactly one `RedditGateway` port method and costing
itself from the gateway's own `requests_made` counter; `save()` behind `--save-fixture`,
which writes only under `<data_dir>/probe/`; and `--blank-bodies`. Landed as 3336e81. The
commit touches `tests/gates/test_mutating_commands.py`, a review-required surface, which is
why this record exists. The probe day the command was built for is specified in
`docs/runbook/RUNBOOK.md` § 9.

**How reviewed.** In-family, the session that built it under a bounded brief, offline
against `FakeRedditGateway` throughout; not an independent seat, and that is this record's
weakness, stated plainly. The evidence is three planted positive controls the builder ran:
each break was made deliberately, the named test was watched go red, and the break was
reverted and the test watched go green again. The three tests were afterwards read against
the claims made for them, and each asserts what its control claims it asserts.

1. Skipping the scrub inside `save()` turned
   `tests/services/test_probe.py::test_save_scrubs_even_a_payload_that_was_never_scrubbed_by_a_capture`
   red. That test hands `save()` a hand-built `Capture` whose payload never passed through a
   `capture_*` at all, so it proves `save()` scrubs on its own account rather than because
   the capture already had — the property that matters, since `save()` is the last gate
   before disk.
2. Pointing `save()` at the repository tree turned
   `tests/e2e/test_data_dir_writes.py::test_a_probe_save_fixture_changes_no_file_outside_the_data_dir`
   red. That test snapshots the repository before and after a real `CliRunner` invocation of
   `probe --gateway fake about r/premiere --save-fixture …` and asserts the two snapshots are
   identical, which is the mechanical enforcer of irreversible rule 1 on this command;
   without it the rule would be review-only here.
3. Dropping `probe search` from the expected command tree turned
   `tests/gates/test_mutating_commands.py::test_the_command_tree_is_exactly_the_documented_one`
   red, which is what stops a command being added to the tree silently (RL-04).

**Outcome.** Accepted as the offline half of the probe work. Promoting a capture from
`<data_dir>/probe/` into `tests/fixtures/json/captures/` is deliberately a second, manual
step rather than a flag, because irreversible rule 1 admits no command-shaped carve-out;
`save()` prints the exact copy line so the probe day does not have to remember the
destination, and refuses to overwrite a name already used, because a silent clobber is the
expensive failure in a one-shot credentialed session. `probe` takes no lock and writes no run
row, so it joins RL-04's excluded commands rather than its mutating ones.

**A design choice worth knowing.** `--gateway` and `--fixture` are declared once, on the
`probe` group's own callback, rather than repeated on all five sub-commands. Click's context
does not survive from a group callback into a Typer sub-command body in the pinned version —
it calls the function directly rather than through `ctx.invoke` — so the resolved gateway is
handed down through a module-level slot set once per invocation. Repeating both flags on the
five sub-commands would also have pushed three of them (`listing`, `tree`, `search`) past the
project's five-argument size ceiling in `.ratchets/code_health.txt`.

**What is not verified, and cannot be until the probe day.** Every wire shape. The command
has only ever run against `FakeRedditGateway`, so what these tests establish is the command's
own behaviour — request cost, scrubbing, paging bookkeeping, where bytes land — and not that
the real API returns the fields the capture modes read. The first credentialed run is the
first evidence of that, and it is the reason the modes exist: to capture the shapes rather
than to assume them. An independent seat should attack the assumption that a mode calling
exactly one port method is enough to characterise a paged endpoint.
