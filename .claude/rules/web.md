---
paths:
  - "src/threaddigest/web/**"
  - "tests/web/**"
---
# Web UI rules (load when a web file is edited)

Read first: `docs/PLAN.md` § Web UI and `docs/reference/reviews/2026-09-12-ui-design-review.md`.

- The web layer writes only through the repository limited to the writer map; fetching is always the CLI in a subprocess through the `ProcessRunner` port; `web` never imports `cli`.
- Only ingest-time sanitized html columns render unescaped; search snippets are escaped before markers are inserted.
- State-changing requests need a same-origin check, with an Origin or Referer fallback on plain http, and an allowed Host.
- Destructive actions show the gate state and require a typed confirmation; the CLI mirrors the UI, never the reverse.
