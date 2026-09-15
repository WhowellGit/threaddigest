# Sweep the documents and memory after a change

Purpose: make a settled or changed fact land in every place that states it, in the right way for
each document, and leave no annotation where a rewrite was due. The steps produce artifacts the
gates check (`tools/doc_policy.py` in `make check`, G55; the retired-claims scan, G34; the memory
audit, G47), so a skipped step shows up red. The reasoning is `docs/runbook/RUNBOOK.md` § 8.

1. **Name the fact and its home.** One sentence; the home is a configuration key, a code constant,
   a plist, a decision entry, or a table row. If the home is a configured value, name its code
   twin too (a default parameter, a constant), because a wrapper is not the only mirror (KI-024).
2. **List the mirrors.** The `mirrors` in the front matter of the document you are changing; every
   living document whose `mirrors` names it (`grep -l` the path); the live-facts row, if one
   exists; the working agreement; the launchd templates and their README when the fact is
   operational; memory.
3. **Choose the move per document, from its `update-policy`.** Append-only: add a dated entry,
   and insert a dated parenthetical into the superseded entry's line (anywhere in it) or append
   to its end; never change the other words. Prune-stale or versioned: rewrite the section that
   states the fact; delete the old sentence; no "update:" paragraph, no dated parenthetical.
   Rewritten (the status page): replace it whole and re-stamp. A generated block: regenerate with
   its tool. Read each mirror's prose yourself: only the live-facts table is checked mechanically.
4. **Register the change in the machine-read tables.** A retired phrase becomes a retired-claims
   row; a fact that will repeat becomes a live-facts row with its home and literal; a fixed bug
   is a `KNOWN_ISSUES.md` row citing its test.
5. **Retire cleanly.** A document that is no longer true and cannot be rewritten moves to
   `docs/reference/` as a record or is deleted; its router line goes and a tombstone names the
   successor; the check reports every pointer left behind.
6. **Memory.** If the fact changes how to work or where to look, update the memory that routes
   there; delete a superseded memory rather than annotate it; keep every topic file under the cap;
   never store state the status page or the decisions log holds. Then `make memory-export`.
7. **Prove it.** `uv run python tools/doc_policy.py --check`, then `make check`; paste the
   output. If the accretion ceiling is red, the fix is a rewrite, not a loosening.
8. **Record.** A decision entry if a choice was made; the PR body names the documents swept.

Rules that bite: never delete a line from an append-only document; never write a count into prose
where a tool prints it; no model names, attribution trailers, or another system's identifiers.
