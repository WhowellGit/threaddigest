## What

<!-- One paragraph: the change and why. Link the KNOWN_ISSUES row, plan section, or issue. -->

## Tests changed

<!-- Every file under tests/ this PR adds, edits, or deletes: one row each with a one-line reason.
     Write "None" if no test file changed. Weakening or deleting a test to get green is never acceptable. -->

| File | Reason |
|---|---|
| | |

## make check

<!-- Paste the block exactly as `make check` printed it, markers included. Never retype numbers. -->

```
<!-- make-check-summary:begin -->
<!-- make-check-summary:end -->
```

## Ratchets

<!-- Which .ratchets/ keys moved (via `make ratchet-bump` or `make ratchet-loosen KEY=… REASON="…"`)
     and why. Write "None" if none. A loosening also lands a row in docs/runbook/GUARDS.md. -->

## Independent review

<!-- Required only when this PR touches src/insightminer/db/migrations, services/scrub,
     core/deletion, or db/repo. Name the reviewer (a human or an agent other than the author),
     what was reviewed, and the outcome. Otherwise write "n/a". -->
