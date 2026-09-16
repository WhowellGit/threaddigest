# Review record: the project rename (2026-09-16)

**Scope.** The package (`insightminer` → `threaddigest`), the CLI command and the module
entry point, the `INSIGHTMINER_*` environment prefix, the launchd labels and the two plist
file names, the database file name, the harness page's file name, the import-linter and
rule-file globs, the memory snapshot, and the documents' prose (*harvester* → *reader*).
Landed as 662b59b on top of 9bf4a2b, which added the one front-matter line exempting the
live-facts table from the append-only diff. Decision: D-33 in `docs/decisions/DECISIONS.md`,
superseding D-18.

**How reviewed.** Refute-framed against the tree. The rename was performed by a
parametrized script, not by hand: the script was exercised on a throwaway clone of the
repository until `make check` there was green, then run once here in `--dry-run` mode whose
full output was read line by line — every move, every rewritten file, all twenty-two prose
substitutions, the two live-facts rows, the twenty-two protected lines it refused to touch,
and the twenty-five reference records it left alone — and only then in `--apply` mode. The
gates that react are named in the PR body with their test ids; the one that stays red until
its own commit is the review register, which is what this record covers.

**Outcome.** No behaviour change intended and none found: the suite is unchanged except for
the names it imports, and the coverage, assert and collected-test floors all held at their
pre-rename values. One rendered string changed deliberately, because the mechanical
substitution made it redundant: the digest heading now reads "Thread Digest for `<date>`"
rather than "… digest for `<date>`", and its golden moved with it. Four prose lines were
re-written by hand where the substitution was grammatical but clumsy
(`docs/PLAN.md` twice, `docs/OVERVIEW.md`, `CLAUDE.md`).

**What deliberately did not move.** The repository folder, because the agent runtime keys
its hooks and its memory on that absolute path; the reference records under
`docs/reference/`, which are added and never edited; and the existing lines of every
append-only document, which are history. The two live-facts rows that name the package and
the harness page did move, under the exemption landed the same day, because those rows state
the present and are resolved against the tree.

**Known narrowing.** The register gate's `SURFACES` are paths, so `git log` over the renamed
`db/repo.py` no longer reaches the pre-rename commits and they stop counting as required.
Nothing goes red and every existing row stays valid, but the gate now sees less history.
A follow-up, not a blocker.
