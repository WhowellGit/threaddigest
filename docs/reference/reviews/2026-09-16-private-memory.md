# The working notes leave the public repository (D-35) — record

**Date:** 2026-09-16 · **Scope:** the commit that adds this record (the tool, the gates and
the documents) and the
history rewrite that follows it · **Seat:** the session that made the change, not an independent
one. That is this record's weakness and it is stated plainly: the evidence below is a rehearsal on
a throwaway clone, read and re-run, not a second reader's judgement.

## The ruling

Wes, 2026-09-16: the repository is about to be published; the review records are meant to be read
and the working notes are not. Claude Code's auto-memory is therefore exported to a private folder
outside the repository, and the folder it used to occupy is removed from the tree and from every
commit in history.

## What the change had to answer for

The memory snapshot was not only a directory. Five mechanisms read it, and taking it out would
have quietly narrowed four of them:

1. **The snapshot's own tool.** It resolved the snapshot inside the tree. It now resolves it under
   the `THREADDIGEST_PRIVATE_DIR` environment variable, with a tracked default so a fresh checkout
   knows where the memory is kept. The tool never creates that folder: a misspelt variable would
   otherwise make a new home and call the first export complete. A missing home, with live memory
   present, is red and prints the command that creates it. With no live memory at all (CI, a fresh
   clone) nothing is required, which is the state those machines were already in.
2. **G44, routing pointers.** It read the committed snapshot's topic files. It now reads the
   private snapshot, else live memory. A machine with neither reads no memory file and checks no
   pointer in one: the coverage genuinely narrows to Wes's machine, and that is on G44's row in the
   guards ledger rather than in a commit message.
3. **G40, cited commit hashes,** and **4. G50, the review register's scopes.** Both resolve hashes
   against git, and the rewrite moves the hash of every commit after the first one that ever
   touched the snapshot. Three of the places that cite hashes may not be edited to follow: the
   append-only decisions log, the append-only review register, and the reference records, which are
   added and never edited. Narrowing either gate to stop looking was the obvious fix and is the
   weakening the working agreement forbids, so instead the rewrite records what every commit became
   in a hash-map record under `docs/reference/`, and both gates follow a citation through it before
   applying the same test they always applied: the destination must be an ancestor of `HEAD`. A map
   rescues only the hash it names, and a map entry pointing at a commit this repository does not
   have rescues nothing. Both halves are driven by positive controls.
5. **The packet builder, the document policy and the pre-commit fixers** each named the directory
   and no longer do.

## What is lost, knowingly

A clone of the public repository carries no memory. The private folder is the backup — it is a
local git repository of its own — and `tools/memory_snapshot.py restore --to …` is the way back.
The reference records, the append-only logs and the register keep the hashes they were written
with; a reader who follows one of those hashes needs the map record to find the commit it became.

## Evidence

The whole sequence was rehearsed on a throwaway clone before it was run here: the tool change and
its documents, then `git filter-repo --path memory-snapshot --invert-paths`, then the hash-map
record, with `make check` green at both commits and `git log --all -- memory-snapshot` empty at the
end. The `make check` block is in the pull request body; the rehearsal's notes name every gate that
reacted and how it was satisfied.

## What an independent seat should attack

That the map is a way to make dead citations look alive; that the private home turns a checked
asset into an unchecked one on every machine but Wes's; and that a fourth history rewrite before
the first push is a habit rather than a decision.
