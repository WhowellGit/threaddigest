# Review record: the gate and harness fixes of the 2026-09-17 code panel (2026-09-17)

**Scope.** `edc3111..f9644ef`, one commit. Review-required surfaces moved: `tests/gates/`
(`test_routing_rows_resolve.py`, `test_layering.py`, `test_code_health.py`,
`test_no_imported_identifiers.py`, and the new `test_no_write_outside_data_dir.py`) and
`CLAUDE.md` (the irreversible-few list, the banned-API rule row, and PR-protocol step 5).
Also changed, outside the review-required list: `tests/conftest.py`, `pyproject.toml`,
`tools/code_health.py`, `tools/private_terms.py`, `tools/doc_policy.py`,
`tests/services/test_migrate_service.py`, and the documents.

**What was fixed, and by whose finding.** Six findings of the panel recorded in
`2026-09-17-code-panel-since-baseline.md`, dispatched to this round by its disposition:
seat A's A1 and A10, seat C's C-2, C-3(b), C-3(c), C-7 and C-9, plus the tightening that the
private-term list's own record (`2026-09-17-private-term-list.md`) named as available. Each
landed with a known-issues row (KI-045 to KI-049), a widened guards row rather than a new guard
id (G02, G05, G19, G35, G44, G51), and a positive control. The reasoning is in
`docs/decisions/DECISIONS.md` § 2026-09-17 (the gates).

**How each control was proven, which is the whole of what this record adds.** A guard is a
hypothesis until it has been seen failing, so every one of the six was run against the defect it
exists to catch, before and after:

1. *The routing gate* (KI-045). The pre-fix rule — resolving a pointer with `Path.exists` — was
   put back in place and the gate itself plus all four controls went red; restored, all eleven
   tests in the file are green. The gate had already been observed red on the unmodified tree in
   this worktree, which is the birth incident rather than a control.
2. *The dynamic-import ban* (KI-046). `ruff check` under the repository's own configuration on a
   copy of `services/collect.py` with the panel's own planted line appended: one `TID251`
   finding naming `importlib.import_module`, and none on the unmodified copy. The AST scanner's
   control plants the two spellings ruff cannot reach — `__import__`, and an `import_module`
   inside `db/`, where `TID251` is lifted for the engine chokepoint.
3. *The write guard* (KI-047). A child pytest run with only `tests/conftest.py` loaded as a
   plugin, on a planted test writing one directory outside its temp tree: the run fails naming
   the path, and the file was never created — the guard refuses the write rather than reporting
   it afterwards. The same write inside `tmp_path` passes, so the finding is the location. The
   whole suite is green and silent with the fixture on, which is the other half of the claim: a
   guard that is noisy is a guard that gets removed.
4. *The below-head prefix* (KI-048). A head-model read of `runs.warnings_json`, a column
   revision 0005 added and no committed fixture has, was planted inside `_table_counts_json` —
   one of the two statements KI-039's hand-written list did not name. All four parametrised
   cases went red with `no such column: runs.warnings_json`; restored, all four are green. The
   same plant is kept as a monkeypatched control in the file.
5. *The dead-code passes* (KI-049). With the product pass removed, the new control's assertion
   that a source symbol reached only from a test is counted went red, and the two assertions
   about the harness pass stayed green — so the control distinguishes the two passes rather than
   asserting that vulture runs. The measurement moved from 0 to 29.
6. *The private-term tightening.* With the pre-fix `return None` restored, the new control read
   `DID NOT RAISE SystemExit` and printed the CI note for a folder that exists; restored, it is
   green.

**What this round deliberately did not do.**

- No symbol was deleted to make the dead-code ceiling pass. The count is held as a dated birth
  relaxation (`hard_after=2026-10-17`) with its reason in the loosenings ledger, because most of
  the twenty-nine are production API whose consumers land with M1b and M1d, and one group —
  the budget module's — belongs to a different fix round.
- The per-commit stage for the private-term check was not added. `make check` runs that check at
  the pre-push stage twice over, and that stays the gate; the record that named this tightening
  also named its trigger, a term reaching a commit again.
- No new guard id was created. Every fix widened an existing row, which is the check the working
  agreement asks for before a guard is added.

**The weakness of this record, stated rather than left to be found.** It is written by the
session that made the change: in-family, single-pass, no independent seat. What stands in for one
is that every claim above is a command with an output, and that the round's subject is itself a
panel's independent findings — the defects were not self-reported. The write guard's blind spots
(SQLite's own opens, a subprocess's writes) are named in its module docstring and in G19's
mechanism cell rather than in this record alone, so a later reader meets them where the code is.
