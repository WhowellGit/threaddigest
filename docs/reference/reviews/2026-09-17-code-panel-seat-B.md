# Panel CP, seat B: operator and data safety

## 1. What I was given

Brief `scratchpad/brief_CP_code_panel.md`, seat B only. Tree: detached worktree
`/Users/wesmax/repos/threaddigest-review-7528af9` at `main` commit **7528af9**, read-only —
nothing in it was created, edited or deleted. Read: `CLAUDE.md`, `docs/OVERVIEW.md`,
`docs/PLAN.md` (Collector algorithm, Data model, Silent-failure controls, Web UI, Robustness),
`docs/TEST_STRATEGY.md`, `docs/runbook/KNOWN_ISSUES.md`, and the source of `settings.py`,
`cli.py`, `web/*` (all four templates), `services/{probe,lock,migrate,doctor}.py`,
`db/{engine,repo}.py`, `adapters/notify.py`, `tools/make_demo_fixture.py`, `Makefile`,
`deploy/launchd/*`.

Commands run (all with `THREADDIGEST_DATA_DIR` pointing at
`scratchpad/seatB/data`; `--gateway fake` only; no network):

```
uv sync
uv run python tools/make_demo_fixture.py <scratch>/demo.json --base 2026-09-01
uv run threaddigest db init                      # schema: None -> 0005, exit 0
uv run threaddigest run --gateway fake --fixture <scratch>/hostile.json   # exit 3
uv run threaddigest config validate              # with a deliberately bad static key
uv run threaddigest doctor                       # exit 0
uv run pytest tests/gates/test_data_dir_isolation.py \
  tests/adapters/test_praw_gateway.py::test_the_auth_ping_costs_exactly_two_http_calls \
  tests/services/test_migrate_service.py tests/web tests/deploy/test_launchd.py \
  -k/-q as noted below
```

plus three scratch scripts (`hostile_fixture.py`, `render.py`, `raw_asgi.py`) that build a
corpus whose author-controlled strings are hostile, drive the app in-process, and hand the
ASGI app hand-made scopes.

**One caveat for the synthesis.** The worktree is shared with the other seats, and at 06:53
seat C staged a deliberate violation in `services/collect.py` (`_audit_trail`, a write to
`/private/tmp/claude-501/seatC-outside-the-data-dir.log`) as its brief instructs. Every
collector run of mine finished at 06:49, before that edit, and none of my findings touches
`collect.py`; but `git status` in that tree is not clean and the next seat should not read
those two modified files as commit 7528af9.

## 2. Findings

### B1 — P0 — the scheduled collector cannot start at all

`deploy/launchd/run.sh:122,126` — `set -- "$PY" -m threaddigest run` (and `… doctor
--alert-if-stale 5d`). The package has **no `__main__.py`**:

```
$ ls src/threaddigest/__main__.py
ls: src/threaddigest/__main__.py: No such file or directory
$ .venv/bin/python -m threaddigest run
.../python: No module named threaddigest.__main__; 'threaddigest' is a package and cannot be
directly executed
exit=1
$ uv run threaddigest --version        # the console script works
threaddigest 0.1.0
```

So both launchd jobs exit 1 the instant they start. `run.sh:148` maps exit 1 to a
Notification Center alert ("Scheduled run failed (exit 1)") with no diagnosis, and the hourly
`doctor` — the silent-failure control that would notice a collector that has stopped
collecting — is dead by the same line, so nothing catches it.

The deployment gate is green over this. `tests/deploy/test_launchd.py:207` writes the missing
file itself: `(stub_pkg / "threaddigest" / "__main__.py").write_text(STUB_MAIN)`, put on
`PYTHONPATH` to shadow the real package. The stub *manufactures the entry point production
lacks*, so the test can only ever prove the wrapper's plumbing:

```
$ uv run pytest tests/deploy/test_launchd.py -q
..............................                                           [100%]   (30 passed)
```

**Cost if left:** the first real deployment silently never collects; the operator's only
signal is a failure banner twice a week. **Smallest fix:** add
`src/threaddigest/__main__.py` (`from threaddigest.cli import app; app()`), or point the
wrapper at `$ROOT/.venv/bin/threaddigest`. **Enforcer:** one test that runs the *real*
interpreter for the wrapper's own command line
(`[ROOT/".venv/bin/python", "-m", "threaddigest", "--version"]`, exit 0), outside the stub
fixture; positive control = the test is red today, before the fix. Confidence: **high**
(reproduced directly). `deploy/` is outside the brief's literal file list but is the `run`
and `doctor` entry point seat B was asked to check.

### B2 — P1 — `settings_json` carries the OAuth client id and the Reddit account name

`settings.py:382` `non_secret_settings` defines "secret" structurally as "annotated
`SecretStr`". `reddit_client_id` and `reddit_username` (`settings.py:264,266`) are plain
`str`, so they are inside the mapping that `settings_json` stores on every run row
(revision 0005) and that the digest diffs:

```
$ sqlite3 …/threaddigest.db "select pk, settings_json from runs order by pk desc limit 1;"
3|{"data_dir":"…","reddit_client_id":"CLIENTID-xyz","reddit_username":"wes_real_account", …}
```

and the values are printed verbatim on the digest page when they change (a rotated client id,
rendered through `report.html:90`):

```html
<li><code>reddit_client_id</code>: <code>&#34;CLIENTID-xyz&#34;</code> →
  <code>&#34;ROTATED-CLIENTID-999&#34;</code></li>
```

The brief asked to verify `non_secret_settings`; it is sound for what it claims, but the
claim is narrower than "no credential, no account id". **Cost:** the OAuth client id and the
operator's Reddit username in every run row, every backup, every DB copy, and on a page that
is screenshotted. **Fix:** annotate `reddit_client_id` as `SecretStr` and drop or hash
`reddit_username`; belt and braces, have `report.py` list changed key *names* without values.
**Enforcer:** a test that sets all three credentials to sentinels and asserts none appears in
`settings_json(settings)`; positive control = unwrap one and it goes red. Confidence:
**high**. (Sits at the P0/P1 boundary: it is a write of credential material on every real run,
but not of the secret itself.)

### B3 — P1 — `probe --save-fixture` writes outside the resolved data directory

`services/probe.py:199` joins the operator's name straight on:
`target = probe_dir / f"{name}.json"`. `pathlib` lets a traversing or absolute right operand
win, and `save` mkdirs the parent first:

```
data_dir       : …/scratchpad/seatB/data
name '../../escape/pwned'  -> …/scratchpad/seatB/escape/pwned.json   inside data_dir: False
name '<abs path>/absolute' -> …/scratchpad/seatB/escape/absolute.json inside data_dir: False
```

The module docstring (`probe.py:8-11`) asserts the opposite and cites irreversible rule 1:
"`save` writes under `<data_dir>/probe/` and nowhere else". With the default data dir
(`<repo>/data`), `--save-fixture ../tests/fixtures/json/captures/x` lands a raw capture
directly in the committed fixture tree — precisely what `promotion_command` exists to keep a
separate, deliberate step. **Cost:** on the one-shot credentialed probe day, an unscrubbed
capture in git history, or a file written anywhere the process can reach. **Fix:** refuse a
name that is not a single safe segment (`Path(name).parts != (name,)` or resolve and require
`is_relative_to(probe_dir)`), raised as the existing `ConfigError`. **Enforcer:** a case in
`tests/gates/test_data_dir_isolation.py` with a positive control. Confidence: **high**.

### B4 — P1 — `make fixture` writes the demo corpus into the *default* data directory

`Makefile` `RUN_FIXTURE ?= data/demo.json`, and `make run: fixture`. `default_data_dir()` is
`<repo>/data` (`settings.py:113`), and `build_demo_fixture` (`tools/make_demo_fixture.py:313`)
creates the parent if it is missing. So a fabricated corpus is written into the live data
directory, beside `threaddigest.db`, while `make serve`'s own comment three lines below says
"neither target can touch the real `data/`". The resolved data dir for the run itself is
`.build/run-data`, so the write is also outside the *resolved* directory — rule 1's literal
wording. The database is safe (the two D-10 guards hold, see §3), but the file is not.
**Cost:** a fabricated 316-post corpus inside the operator's real data tree, which future
tooling (backups, exports, retention) has no reason to treat as foreign. **Fix:**
`RUN_FIXTURE ?= $(BUILD_DIR)/demo.json`. **Enforcer:** make `build_demo_fixture` refuse a path
under `default_data_dir()` unless `THREADDIGEST_ALLOW_REAL_DATA_DIR` is set, with a positive
control. Confidence: **high**.

### B5 — P2 — a stored permalink can point the digest's link off Reddit

`db/repo.py:1579` builds the link as `f"{REDDIT_WEB_HOST}{row['permalink']}"` with no check
that the stored value is a rooted path. A post whose wire `permalink` is `@evil.example/x`
renders (confirmed in the page built from my hostile corpus):

```html
<a href="https://www.reddit.com@evil.example/phished">authority confusion</a>
```

whose real host is `evil.example` — `www.reddit.com` is parsed as userinfo. The field is
Reddit-generated, so the likelihood is low, but the comment at `repo.py:111-116` already
claims this join is what makes a permalink safe to render. **Fix:** require
`permalink.startswith("/")` and not `//`, and no `@` or `\` before the first `/`; anything
else is treated as no link (NULL permalinks are already excluded from both halves of the
window). **Enforcer:** one test with a hostile permalink fixture. Confidence: **high** that
the string renders as shown; **low** that Reddit would ever emit it.

### B6 — P2 — the launchd log directory ignores a relocated data directory

`deploy/launchd/run.sh:51` sets `LOG_DIR="$ROOT/data/logs"` — line **51**, forty lines before
`load_env "$ROOT/.env"` at line 94, so `THREADDIGEST_DATA_DIR` from `.env` cannot be honoured
even in principle. Both `.plist` files hardcode `__ROOT__/data/logs/…` for
`StandardOutPath`/`StandardErrorPath`. An operator who relocates the data directory — which
doctor's `data_dir_outside_tcc` check (`doctor.py:245`) actively pushes them to do — gets the
scheduled run's entire stdout/stderr written outside the resolved data directory, and
`runs.log_path` is written `NULL` (`cli.py:424`) so no page points at it. **Fix:** compute
`LOG_DIR` after `load_env`, defaulting to `${THREADDIGEST_DATA_DIR:-$ROOT/data}/logs`.
**Enforcer:** extend `tests/deploy/test_launchd.py` to set `THREADDIGEST_DATA_DIR` in the fake
`.env` and assert where the log lands. Confidence: **high**.

### B7 — P2 — the CSP omits the directives `default-src` does not cover

`web/middleware.py:74` sends `default-src 'self'` only. `frame-ancestors`, `form-action`,
`base-uri` and `object-src` do **not** fall back to `default-src`, so the pages are frameable
by any origin. Cost today is near zero (no state-changing route — proven in §3), but M2's
"Run now" and "Cancel" land inside this same header, and the docstring presents the current
header as the whole perimeter. **Fix:** append
`frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'`.
**Enforcer:** the existing header test, extended. Confidence: **high** on the gap, **medium**
on it mattering before M2.

## 3. Checks I re-ran that held

1. **Escaping of every Reddit-controlled string.** A corpus with `</a><script>alert(…)`
   as a title, `<img src=x onerror=…>` as the author, `"><svg onload=…>` as the flair, and a
   script tag in the body, collected and rendered: 0 hits for `script>alert`, `onerror=`,
   `onload=`; the title appears as `&lt;/a&gt;&lt;script&gt;…`. `StrictUndefined` +
   `select_autoescape(default=True)` in `build_templates` does its job, and no template uses
   `|safe`.
2. **Host check fails closed.** Raw ASGI scopes: no Host header → **421**, empty Host → 421,
   `evil.example` → 421, two Host headers → 421; `127.0.0.1:8765` and `localhost` → 200; an
   `X-Forwarded-Host` is ignored. Static files carry the CSP too.
3. **No state-changing route.** `POST /runs` 405, `DELETE /runs/1` 405, `/docs` `/redoc`
   `/openapi.json` 404, a 26-digit run id 422, `/reports/notadate` 422, `/static/../app.py`
   404.
4. **No secret in a settings failure.** `config validate` with both secrets set and a bad
   static key printed the field path and the value error only — no input echoed — and exited
   78. `hide_input_in_errors=True` holds.
5. **`doctor`.** Default path makes zero requests structurally (`run_checks` never touches
   `gateway` unless `no_network=False` *and* a gateway is supplied);
   `tests/adapters/test_praw_gateway.py::test_the_auth_ping_costs_exactly_two_http_calls`
   passes; a live `doctor` run listed 15 checks, left no residue, exited 0 on a warning.
6. **Data-directory isolation gate.** `tests/gates/test_data_dir_isolation.py` — 7 passed,
   including the subprocess seam.
7. **The two D-10 guards** (fake against the default dir; fake against a database holding real
   runs) — 37 selected tests passed.
8. **Backups before a destructive migrate.** `db upgrade` takes the copy, `quick_check`s it,
   aborts *before* migrating if the copy is bad and deletes it, records the row in the live
   database, and restores on any of three named failure classes;
   `tests/services/test_migrate_service.py` + `tests/web` — 87 passed.
9. **The lock.** `flock` across descriptions, `is_held` a read-only shared probe that creates
   nothing, `acquire` creating the parent first, nesting refused rather than silently
   idempotent.
10. **`MacNotifier`** passes message, title and level as `argv` to an `on run argv` handler —
    no AppleScript splicing, no injection from run-error text.

## 4. Cut list

- **One lock path, three spellings**: `cli.py:89`, `services/migrate.py:145`,
  `services/doctor.py:917` each build `data_dir/"locks"/"collector.lock"`. Load-bearing —
  a doctor probing a different path than the collector takes would report "lock free" during
  a run. One constant in `services/lock.py`, imported by all three.
- **`adapters/notify.py:5`** promises `threaddigest notify --test`; no such command exists
  (`cli.py` has run, doctor, serve, db, config, probe). Either the sentence or the
  `MacNotifier.sent` / `last_ok` bookkeeping it justifies should go.
- **`_FROM_ENVIRONMENT`** is declared twice (`cli.py:199`, and again in `doctor.py` per its own
  comment) for one mypy workaround; one shared helper would do.
- `probe.py`'s `promotion_command` becomes unnecessary polish if B3 is fixed by refusing
  unsafe names — but keep it; it is the documented deliberate step.

## 5. Confidence

B1 high · B2 high · B3 high · B4 high · B5 high on the rendering, low on the likelihood ·
B6 high · B7 high on the gap, medium on urgency.
