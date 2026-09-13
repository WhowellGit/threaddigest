<!-- Extracted 2026-09-13 from the panel agent transcript (final assistant message; a one-line conversational lead-in before the heading was dropped, HTML entities unescaped, nothing else touched). -->
<!-- Status: raw, unedited panel report; immutable reference copy (docs/reference/ policy: add, never edit). -->
<!-- Scope: test-strategy panel on enforcement, gates, and CI (ratchets, positive controls, import-linter, hooks, portability job, GUARDS.md structure). -->

# Panel report: enforcement, gates, ratchets, and CI

Scope respected: agent merges when CI is green; no CODEOWNERS; local git first; Python 3.13 required, 3.14 informational; Linux primary; three hard-block hooks; two-day scaffold box; guard count held.

One framing point that drives the whole design: **the agent controls everything inside the repository, so the only enforcement it cannot edit is what lives in GitHub's settings** (branch protection, required-check names, environment reviewers) and the operator's own reading. Every control below is therefore either (a) mechanical and compared against `main` rather than trusted from the PR, (b) a positive control that proves a gate still goes red, or (c) a derived audit surface that makes drift visible to Wes without asking him to review PRs.

---

## A. CI design

Workflow: one file `.github/workflows/ci.yml`, triggers `pull_request: [opened, synchronize, reopened, edited]`, `push: [main]`, `schedule` (weekly Sun 03:00, monthly 1st), `workflow_dispatch`. `concurrency: ci-${{ github.ref }}` with cancel-in-progress on PRs. `permissions: contents: read, pull-requests: write, issues: write`. Every job has `timeout-minutes` (GitHub's default is 360 and a hang burns the month's minutes).

Conditional jobs use `if:` inside the single workflow, never `paths:` filters on the workflow trigger: a required check whose workflow never fires blocks the PR forever, while a job skipped by `if:` satisfies branch protection.

| Job | Trigger | Required? | Steps | Timeout | What failure means |
|---|---|---|---|---|---|
| `check` | PR, push main | **Required** | checkout `fetch-depth: 0`; `astral-sh/setup-uv` (`enable-cache`, glob `uv.lock`); `uv python install` from `.python-version`; `uv sync --frozen`; `gitleaks git --log-opts=origin/main..HEAD`; `actionlint`; `make check`; upload `.build/check-summary.json` + junit + coverage json as artifact; `if: failure()` post failed gate ids to the pinned "Guard firings" issue | 20 | A gate is red. The summary names which (ruff / mypy / import-linter / test / snapshot / ratchet). Never "flaky": no network, injected clock, hypothesis derandomized in the `ci` profile |
| `ratchets` | PR, push main | **Required** | `needs: check`; download summary; `tools/ratchet.py compare --base origin/main --summary .build/check-summary.json`; sets output `loosening` (true/false) and writes the comparison table to the job summary and a sticky PR comment | 5 | Either measured value violates a ratchet file, a file is not what the bump script would render (hand edit), a file lags the measurement (run `make ratchet-bump`), or a value moved the wrong way vs `main` |
| `ratchet-loosen-approval` | PR | **Required, conditional** | `if: needs.ratchets.outputs.loosening == 'true'`; `environment: ratchet-loosen` (required reviewer: Wes); prints the loosening rows and the matching `GUARDS.md` ledger rows | 5 | Pending = a ratchet is being loosened and Wes has not clicked approve. Skipped = no loosening (counts as green) |
| `pr-body` | PR | **Required** | `needs: check`; `tools/pr_body_check.py` on `github.event.pull_request.body`: every changed `tests/**` file listed with a reason; summary block present, `dirty=false`; pasted `collected`, `skipped`, `line_percent` equal CI's artifact (coverage ±0.1) | 5 | PR body omits a changed test file, or the pasted `make check` numbers were not reproduced by CI ("passes locally" that did not) |
| `portability` | weekly; PR `if:` `README.md`, `Makefile`, `pyproject.toml`, `uv.lock`, `.python-version`, `.pre-commit-config.yaml` changed | **Required when it runs**; weekly failure opens an issue | `container: ubuntu:24.04`, no actions cache, no `actions/checkout`; `apt-get install git curl make`; `git clone` at the PR sha; `make setup`; `make check`; then two negative commits: a file containing a fake AWS key and a 2 MB file, each expected to be rejected by the installed pre-commit hooks | 30 | The README quickstart is broken for a fresh machine, or `make setup` no longer installs the hooks |
| `py314` | push main, weekly | Informational (`continue-on-error`) | same as `check` with `uv python install 3.14` | 20 | A dependency or our code is not 3.14-clean yet. Pin moves up when green for 4 consecutive weeks |
| `macos` | weekly; PR `if:` `deploy/launchd/**` or `adapters/notify.py` changed | Informational | `macos-latest`; `uv sync --frozen`; `make check`; `plutil -lint deploy/launchd/*.plist` | 25 | A Linux-first assumption broke the Mac (the reverse of the earlier project's failure). 10x minute multiplier, hence weekly only |
| `stress` | weekly | Informational → issue | `pytest -m slow` (fake-gateway corpus; wall-time budgets; `EXPLAIN QUERY PLAN` index assertions) | 60 | A hot query lost its index or a budget blew. Sized by the DB/ingest panels |
| `mutation` | monthly | Informational → issue | `mutmut run` on `core/deletion.py`, `core/paging.py`, `core/normalize.py`; compare kill % to `.ratchets/mutation.txt` | 180 | Kill rate dropped: tests were weakened or new code is under-tested. Never blocks |
| `audit` | weekly | Informational → issue assigned to Wes | `git log --since=7d origin/main -- <enforcement paths>` with PR links; every `.ratchets/*` diff with direction; informational job outcomes; date each positive control last ran (from junit); open "Guard firings" comments this week | 10 | Nothing "fails"; this is the one thing Wes reads instead of reviewing PRs |
| `settings-drift` | weekly | Informational → issue | `gh api repos/:o/:r/branches/main/protection` and `/environments` with a read-only PAT secret; assert required checks == {`check`,`ratchets`,`ratchet-loosen-approval`,`pr-body`,`portability`}, strict up-to-date, no force-push, linear history, `ratchet-loosen` has ≥1 reviewer | 5 | Someone (or some token) loosened the GitHub-side perimeter |
| `docker` | M4: PR `if:` `deploy/**`; weekly | Required from M4 | build image; run `insightminer doctor --no-network` inside; entrypoint tests | 30 | Image does not build or cannot start on an empty volume |
| `main-red` | push main | Informational → issue | `if: failure()` on `check` for push events: open "main is red" issue | 2 | Should be impossible under branch protection; if it happens, it is noticed within minutes, not by the next PR |

Not in CI at all: `pytest -m live` (credentials never leave the Mac; run locally before a PRAW bump), Playwright (not before M2; deselected marker when it arrives).

Minutes budget (free plan, private repo, 2,000/month): `check`+`ratchets`+`pr-body` ≈ 10 min per push. At M1–M2 pace (≈15 PRs/week × 3 pushes) that is ≈1,800 min/month, which is why `py314` runs on main pushes only and macOS is weekly. See G1 and G8.

---

## B. Gate-by-gate specification

Columns: fails how = blocks commit (pre-commit) / blocks merge (required CI) / refuses to run (runtime exit 78) / tool call blocked (hook) / notification (informational). Cost: S < 1 h, M 1–4 h, L > 4 h. Priority: P1 must ship in M0, P2 by end of M1, P3 optional.

Harness conventions for every row's positive control (PC): lives in `tests/gates/`, marked `@pytest.mark.gate("Gnn")`, runs in the required suite (never `slow`), constructs the bad state in `tmp_path` (never mutates the repo), asserts the tool's own message naming the offending item (never a bare non-zero exit), and has a green twin so the control is not vacuous. Config-borne gates (`addopts`, `filterwarnings`) are proven by running pytest the way CI runs it (`subprocess` with the repo's `pyproject.toml`), not by reading the config.

| ID | Gate / ratchet | Mechanism | Invariant it keys on | Positive control (bad state → exact red) | Fails how | Phase | Cost | Pri |
|---|---|---|---|---|---|---|---|---|
| G01 | Exception-policy lint | ruff `E722 BLE001 S110 S112 B904 TRY2xx TRY3xx RUF100` in `pyproject.toml`; pre-commit + `make check` | The load-bearing rule codes still fire on the tree | Seven canonical snippets in `tmp_path` (`except: pass`, `except Exception:`, `raise X` in handler without `from`, …) run with `ruff check --config <repo pyproject>` → each yields its exact code (`E722`, `BLE001`, `B904`…). Catches someone removing a code from the config | commit + merge | M0 | S | P1 |
| G02 | Banned APIs | ruff `TID251` banned-api: `unittest.mock`, `os.rename`, `time.sleep`, `pathlib.Path.home`, `os.path.expanduser`, `sqlite3.connect`, `sqlalchemy.create_engine`, `sqlalchemy.text`; exemptions only as directory patterns in `per-file-ignores` (`src/insightminer/db/**`, `adapters/clock.py`, `settings.py`, `tests/adapters/**`, `tests/gates/**`) | Each API is called only inside its allowed directory | tmp file per API outside its directory → `TID251` with the configured message; same file under the allowed pattern → clean | commit + merge | M0 | S | P1 |
| G03 | mypy strict | `mypy --strict` on `core`, `ports`, `services`, `adapters`; `enable_error_code = ignore-without-code`; `warn_unused_ignores`; pre-commit runs `uv run dmypy run -- src tests` (full, not changed-files) | Zero errors; every `type: ignore` carries a code and is used | tmp module with untyped `def f(x)` → error; bare `# type: ignore` → `ignore-without-code`; stale ignore → `unused-ignore` | commit + merge | M0 | S | P1 |
| G04 | Layering | import-linter `layers` contract (snippet below); `include_external_packages = True` | No import points inward-to-outward | Copy `src/` to tmp, inject `from insightminer.services import runs` into `core/paging.py`, run `lint-imports` → broken contract names `core.paging -> services.runs` | merge | M0 | M | P1 |
| G05 | External-package chokepoints | import-linter `forbidden` contracts with `ignore_imports` exemptions: `praw`/`prawcore` only from `adapters.reddit_praw`; `sqlalchemy`/`alembic`/`sqlite3` only from `db.*`; `fcntl` only from `services.lock`; `fastapi`/`jinja2` only from `web.*`; `typer` only from `cli`; `allow_indirect_imports = True` | Importer set of each package ⊆ its allowed module | Inject `import praw` into tmp `core/normalize.py` → red names the module and package | merge | M0 | S | P1 |
| G06 | Network block | `addopts = --block-network` (pytest-recording); `--record-mode=none` in CI | No test opens a socket | subprocess pytest on a tmp test calling `socket.create_connection(("example.com", 80), 1)` → the plugin's network-disabled error, not a timeout or DNS error | merge | M0 | S | P1 |
| G07 | Warnings are errors | `filterwarnings = error` | Zero warnings in the required run | subprocess pytest on tmp test `warnings.warn("x", DeprecationWarning)` → 1 failed | merge | M0 | S | P1 |
| G08 | Static skip/xfail ratchet | `tools/ratchet.py measure`: AST over `tests/**` for `mark.skip/skipif/xfail`, `pytest.skip/xfail/importorskip`; each must carry `reason="#<n> …"` as a keyword argument; keys `skips.skip`, `skips.xfail`, ceiling 0 | Static skip constructs ≤ ceiling, justified in syntax; counts markers only, so runtime skips inside an opt-in `-m live` run are not counted | tmp tree with `@pytest.mark.skip(reason="later")` → `skips.skip=1 > ceiling 0` and `missing issue reference tests/x.py:12` | merge (loosening → approval) | M0 | M | P1 |
| G09 | Runtime skipped == 0 | junit `skipped` attribute of the required selection (`-m "not live and not slow and not playwright"`) | Nothing skips at runtime; opt-in suites are deselected, never skipped; `tests/live` *fails* without credentials when explicitly selected | tmp test calling `pytest.skip("x")`, run as CI, summary → `skipped=1 in required run` | merge | M0 | S | P1 |
| G10 | Suppression ratchet | keys: `noqa` = ruff violation count with `--ignore-noqa` minus without; `type_ignore` = `tokenize` comment tokens matching `type:\s*ignore`; `no_cover` = sum of coverage json `excluded_lines`; `filterwarnings_ignore` = `ignore:` entries in pytest config. Ceiling 0 each; every hit printed with file:line on every run | Suppressed findings ≤ ceiling; justification is a rule code / error code / exact warning text | tmp tree with `except: pass  # noqa: E722` → `noqa=1 > 0` printed with location | merge (loosening → approval) | M0 | M | P1 |
| G11 | Coverage ratchet | coverage json `totals.percent_covered` over `core`, `services`, `adapters/reddit_fake.py`; key `coverage.line_percent`; floor; slack 0.5 | measured ≥ floor, and floor ≥ measured − 0.5 (stale floor is red) | fixture json 89.10 vs file 91.40 → `coverage 89.10 < floor 91.40`; fixture 92.50 vs 91.40 → `floor stale: run make ratchet-bump` | merge | M0 | S | P1 |
| G12 | Test-count and assertion floors | junit `tests` attribute → `tests.collected`; AST count of `assert` statements + `pytest.raises` blocks in `tests/**` → `tests.asserts`; floors; slack 2% | The suite and its assertions cannot shrink unnoticed | fixture junit 400 vs floor 412 → red names metric; AST fixture with one fewer assert → red | merge (loosening → approval) | M0 | S | P1 |
| G13 | One-way protocol vs `main` | `tools/ratchet.py compare --base origin/main`: direction table in code; compares PR file vs `main` file, measured vs PR file, and PR file vs `render(measured)` | A ratchet moves only in its direction between `main` and the PR; the file is byte-identical to what the bump script renders | fixture pair (main 91.4, PR 90.0) → `loosening: coverage.line_percent 91.4 -> 90.0`; `91.4  # ok` → `non-canonical .ratchets/coverage.txt`; loosening with no `GUARDS.md` ledger row → `loosening without ledger row` | merge unless approved | M0 | M | P1 |
| G14 | Guard-count ceiling | key `guards.count` = distinct `@pytest.mark.gate` ids; direction down | Hold the count: adding a guard is a loosening (approval); removing one drops `tests.collected` (also approval) | tmp collection with one extra id → `loosening: guards.count 34 -> 35` | approval | M0 | S | P2 |
| G15 | Schema snapshot | `tests/db/test_schema_snapshot.py`: tmp DB, `alembic upgrade head`, normalized `sqlite_master` dump == `src/insightminer/db/schema.sql`; `make schema-snapshot` regenerates | The committed snapshot equals what head produces | `ALTER TABLE … ADD COLUMN zzz` on the tmp DB before dumping → unified diff containing `zzz` | merge | M0 (rev 0, empty) | M | P1 |
| G16 | Models == DDL | pytest-alembic `test_model_definitions_match_ddl`, `test_single_head_revision`, `test_upgrade`, `test_up_down_consistency` | `alembic.autogenerate.compare_metadata` is empty | tmp `MetaData` with an extra column compared to the migrated DB → non-empty diff naming the column | merge | M0 | S | P1 |
| G17 | Per-revision fixture DBs | test parametrized over `alembic history` output: `tests/fixtures/db/<rev>.sqlite` exists, upgrades to head, `integrity_check` ok, FTS count == live count | Every revision has a proven upgrade path on real prior data (derived from the migration tree, not a list) | tmp migration tree with a revision lacking its fixture → red names the revision | merge | M1a | M | P2 (DB panel owns detail) |
| G18 | Runtime schema fingerprint | sha256 of the normalized live `sqlite_master` == sha256 of the same normalization of the packaged `schema.sql`; checked at `doctor`, `run`, `serve` start; exit 78 | The live DB has exactly the shipped schema (catches hand edits with `alembic_version` still at head) | `CliRunner` `doctor` on a migrated tmp DB with a hand-added column → exit 78, `schema fingerprint mismatch` | refuses to run | M1a | S | P1 |
| G19 | DATA_DIR isolation | autouse fixture sets `INSIGHTMINER_DATA_DIR=tmp_path`; `Settings` raises `RefusedDataDir` when `"pytest" in sys.modules` and the dir resolves to the default unless `INSIGHTMINER_ALLOW_REAL_DATA_DIR=1`; G02 bans `Path.home`/`expanduser` outside `settings.py` | Tests can only write under tmp, on the write path too | subprocess pytest tmp test building `Settings()` with env cleared → `RefusedDataDir`; in-test fake `run` → every attribute of `Paths` is under `tmp_path` | test error | M0 | S | P1 |
| G20 | TCC path and interpreter | `doctor`: data dir not under `~/Desktop`, `~/Documents`, `~/Downloads`, `/Volumes`; plist test via `plistlib`: `ProgramArguments[0]` absolute and inside `.venv`, never `python3`; `plutil -lint` in `macos` job | The scheduler can reach the data and runs the right interpreter | `doctor --data-dir $HOME/Desktop/x` with `HOME=tmp` → exit 78 `TCC-protected path`; plist fixture with `python3` → red | refuses / merge | M0, M1d | S | P1 |
| G21 | Size caps | ruff `C901` (max-complexity 10), `PLR0915` (50 statements), `PLR0913` (6 args); `tests/gates/test_file_length.py`: `src/` ≤ 500 lines, `tests/` ≤ 1,000; no exception list (a `noqa` counts in G10) | No god functions or modules form | generated 11-branch function → `C901` under repo config; generated 501-line file → red names it | merge | M0 | S | P1 |
| G22 | Cross-platform | ruff `PLW1514`, `PTH`; G02 bans `os.rename`; G05 confines `fcntl`; hypothesis test: every filename-producing function (`jsonl_sink`, `report`, `backup`, `export`) matches `^[A-Za-z0-9._-]+$` | No Mac-only or shell-hostile assumptions | `open("f")` → `PLW1514`; filename function fed a datetime → checker red on `:` | merge | M0, M1 | S | P1 |
| G23 | Hard-block hooks ×3 | `.claude/settings.json` `PreToolUse` → `tools/hooks/*.sh`; exit 2 blocks (section D) | See D | Synthetic stdin payloads: blocked cases exit 2 with message; allowed twins exit 0; malformed JSON exits 2 | tool call blocked | M0 | M | P1 |
| G24 | Hook wiring currency | test parses `.claude/settings.json`: exactly three `PreToolUse` entries, each `command` uses `$CLAUDE_PROJECT_DIR` (no absolute paths), target exists and is executable; G23 executes the command string *from settings*, not the script path directly | The hooks registered are the hooks tested | settings fixture pointing at a missing script → red; fixture with two entries → red `expected 3 hooks` | merge | M0 | S | P1 |
| G25 | `make check` summary | `tools/summary.py` builds `.build/check-summary.json` (pydantic model) from junit, coverage json, `ruff --output-format json`, mypy and import-linter exit codes, ratchet compare; `ok` requires failed=0, skipped=0, warnings=0, ratchets ok; also renders the paste block | Summary is derived from tool artifacts, never typed | junit with a failure → `ok=false`; missing coverage json → red `artifact missing` (never skip) | merge | M0 | M | P1 |
| G26 | PR-body gate | job `pr-body` (table A) | Claims in the PR body are reproduced by CI | body missing a changed test → `unlisted test change: tests/db/test_x.py`; pasted `collected=500` vs CI 412 → `summary mismatch` | merge | M0 | M | P2 |
| G27 | Changed-tests sticky comment | CI posts per changed `tests/**` file: ± lines, assert count before/after (AST), skip markers before/after, marker changes (`slow`/`live` added) | The test diff is visible as numbers, derived | (informational; counters are G08/G12) | notification | M0 | S | P2 |
| G28 | Portability | job `portability` (table A) | Quickstart works on a fresh machine and `make setup` installs the hooks | The two rejected commits inside the job are the PC for G29 | merge when triggered; weekly issue | M0 | M | P1 |
| G29 | pre-commit hooks | `.pre-commit-config.yaml`: `ruff-format`, `ruff` (via `language: system` + `uv run` so versions come from `uv.lock`), `dmypy`, `gitleaks`, `check-added-large-files --maxkb=1024`, `no-commit-to-branch --branch main`; `pre-push`: `make check` (or fast subset, see E13) | The commit path is enforced with the same tool versions `make check` uses | via G28; locally `pre-commit run --all-files` in `make check` | blocks commit / push | M0 | S | P1 |
| G30 | Guard reachability | `services/invariants.py` exposes `INVARIANTS: tuple[Invariant, ...]`; each scenario test is `@pytest.mark.invariant("<name>")` and drives `CliRunner` `run --gateway fake`, asserting `runs.status == "failed"` and the name in `runs.error`; gate asserts marker-name set == registry-name set | Every post-run invariant is proven through the real run path | registry with a name no test marks → red names it; scenario: fake plants an FTS/live mismatch → status flips | merge / run `failed` | M1a | M | P1 |
| G31 | Connection chokepoint (behavioral) | Fresh pooled connection from `db.engine` reports `journal_mode=wal`, `foreign_keys=1`, `secure_delete=1`, `busy_timeout=30000`; G05 confines `sqlalchemy`/`sqlite3` to `db/` | The pragmas hold on the connection the app actually uses, not on a test-only connection | Raw `sqlite3.connect` to the same file (allowed only under `tests/gates/**`) fed to the checker → red `journal_mode=delete`; chokepoint connection → green | merge | M0 | S | P1 |
| G32 | No-bypass proof | `run --dry-run`, `doctor --no-network`, `config validate` against a recording fake (zero calls) with the DB opened `mode=ro` | Zero HTTP calls, zero DB writes | A command that writes → `OperationalError: readonly` surfaces as red | merge | M1 | S | P2 (ingest panel owns) |
| G33 | Doc currency | One test: `docs/INDEX.md` ↔ `docs/**/*.md` both directions; `KNOWN_ISSUES.md` `Test` column resolves to a collected node id; `DATA_DICTIONARY.md` == generated from `schema.sql`; `GUARDS.md` ids ↔ `gate` marker ids both directions; regex `\b\d+ (tests|guards|suppressions)\b|\d+% coverage` in `docs/**`, `README.md`, `CLAUDE.md` → red | Router and ledger cannot drift from the tree; metric counts are never restated in prose | tmp docs tree with an orphan file → red names it; `GUARDS.md` row `G99` with no marker → red; `README` containing "412 tests" → red | merge | M0 | M | P1 |
| G34 | Guard firings ledger | `if: failure()` step posts failed gate ids + PR link as a comment on the pinned "Guard firings" issue | "Catches since" is derived from CI history, never typed | Poster script with a fixture summary → expected comment body | notification | M0 | S | P2 |
| G35 | Weekly enforcement audit | job `audit` (table A) | Every enforcement-surface change reaches one human-readable place | Fixture repo with a direction-down `.ratchets` commit → issue body lists it | notification | M0–M1 | M | P2 |
| G36 | Settings-drift check | job `settings-drift` (table A) | The GitHub-side perimeter is intact | Fixture protection JSON missing `ratchets` → red names the check | notification | M0 | S | P2 |
| G37 | Weekly stress | `pytest -m slow`: wall-time budgets; `EXPLAIN QUERY PLAN` shows declared index for each hot query | Indexes are real, not declared | Drop an index in the tmp DB → plan shows `SCAN` → red | notification | M1d | M | P3 |
| G38 | Mutation (informational) | monthly `mutmut` on three core modules; kill % in `.ratchets/mutation.txt` (direction up; a drop opens an issue, never blocks) | Tests test something | mutmut is its own PC; a smoke asserts ≥1 mutant killed so a mis-scoped run cannot report 100% | notification | M3 | M | P3 |

**Rows that police a hand-maintained list, and what was done about them.** `GUARDS.md` (G33) is a list, but it is checked bidirectionally against the marker set in `tests/gates/`, so neither can drift; "catches since" was moved from a hand-typed column to the derived pinned issue (G34). The per-revision fixture set (G17) is derived from `alembic history`, not a list. G02's bans are patterns scanned over the whole tree; the *exemptions* are directory patterns, never file lists. The expected required-check set in G36 is a list, but the enforcer (GitHub) is not its curator. Dropped outright: the plan's per-version fingerprint registry (G18 now derives from the shipped `schema.sql`), any per-file exception list for file length (G21), and the hand-typed "catches since".

Snippet for G04/G05 (`.importlinter`):

```
[importlinter:contract:layers]
type = layers
layers = insightminer.web | insightminer.cli
         insightminer.services
         insightminer.db | insightminer.adapters
         insightminer.ports
         insightminer.core

[importlinter:contract:praw-only-in-adapter]
type = forbidden
source_modules = insightminer
forbidden_modules = praw, prawcore
ignore_imports = insightminer.adapters.reddit_praw -> praw
                 insightminer.adapters.reddit_praw -> prawcore
allow_indirect_imports = True
```

Note `web | cli` are siblings on the top layer: web spawns the CLI as a subprocess and must never import it.

---

## C. Ratchet files and the one-way protocol

**Format.** One file per family under `.ratchets/`, `key=value` lines sorted by key, LF, no blank lines, no comments, trailing newline, integers as integers, percentages to one decimal. Direction and slack live in `tools/ratchet.py` as a constant with its own test, not in the files.

```
.ratchets/coverage.txt        line_percent=92.1
.ratchets/skips.txt           skip=0
                              xfail=0
.ratchets/suppressions.txt    filterwarnings_ignore=0
                              no_cover=0
                              noqa=0
                              type_ignore=0
.ratchets/tests.txt           asserts=1893
                              collected=412
.ratchets/guards.txt          count=34
.ratchets/mutation.txt        killed_percent=78.5      (informational)
```

Direction table: `coverage.line_percent` up (slack 0.5); `tests.collected` up (slack 2%); `tests.asserts` up (slack 2%); `mutation.killed_percent` up (informational); `skips.*`, `suppressions.*`, `guards.count` down (slack 0: file must equal measured).

**Three comparisons on every run** (`tools/ratchet.py compare`):

1. measured vs PR file: the gate itself (`coverage 89.1 < floor 91.4` is red).
2. PR file vs `render(measured)`: the file must be byte-identical to what the bump script would write, within slack. A stale floor is red (`run make ratchet-bump`), so the ratchet tracks reality and slack cannot accumulate silently.
3. PR file vs `main` file: any value that moved against its direction is a **loosening**. The job sets `loosening=true`, which makes `ratchet-loosen-approval` run.

Bootstrap: with no `main` yet, comparison 3 is skipped and comparison 2 requires file == render(measured). Locally, `make check` compares against local `main` before the remote exists.

**Legitimate tighten (agent alone).** `make check` reports `floor stale`; agent runs `make ratchet-bump`, which reads `.build/check-summary.json`, writes canonical files, and refuses (exit 1) to write any value in the loosening direction; commit with the feature; CI confirms comparisons 1–3.

**Legitimate loosen (agent + one click).** `make ratchet-loosen KEY=tests.collected REASON="consolidated 14 parametrized cases into 3 (#123)"` writes the new value (never below measured), appends a row to `GUARDS.md` § Loosenings (`date | key | from | to | reason | PR`), and prints that the PR will pause for approval. `ratchets` sets `loosening=true`; `ratchet-loosen-approval` waits in environment `ratchet-loosen`; Wes approves in the GitHub UI after reading the ledger row; the agent merges when green. Expected frequency: a few times a year.

**Illegitimate loosening, and what catches it.**

| Attempt | Caught by |
|---|---|
| Hand-edit `.ratchets/coverage.txt` from 91.4 to 89.0 | H3 blocks the tool call; if it lands anyway, comparison 3 → `loosening` → approval required; comparison 2 catches any value that is not what the script renders |
| Loosen without a ledger row | comparison 3 → `loosening without ledger row` (row must name the key and the new value) |
| Delete `.ratchets/skips.txt` | file missing → red (never skip) |
| Move tests to `-m slow` to shrink the required run | `tests.collected` drops → loosening; G27 shows marker changes per file |
| Neuter `tools/ratchet.py` | it is under `tests/gates/` positive controls (G13) and listed in the weekly audit paths |
| Merge a loosening while approval is somehow skipped | G36 verifies the approval job is still a required check and the environment still has a reviewer; G35 independently lists every direction-down `.ratchets` commit on `main` from `git log`, cross-checked against the ledger |
| `main` moved (another PR tightened) so the PR file is behind | reported as loosening with the hint `rebase onto main and re-run make ratchet-bump`; not an approval case once rebased |

Fallback if the GitHub plan does not support environment reviewers (see G1): the approval job is replaced by a required `ratchet-loosen` label plus an auto-opened issue assigned to Wes; visibility instead of approval.

---

## D. The three hard-block hooks

Registered in the committed `.claude/settings.json` (project scope, travels with the repo). Commands reference `$CLAUDE_PROJECT_DIR/tools/hooks/<name>.sh`, never absolute paths (the earlier project's hooks were stranded by a repo move). Each script is under 40 lines, bash or stdlib Python, no `uv run` startup, `timeout: 5`.

```
"PreToolUse": [
  {"matcher": "Bash",                  "hooks": [{"type":"command","command":"$CLAUDE_PROJECT_DIR/tools/hooks/no_bypass_git.sh"}]},
  {"matcher": "Bash|Edit|Write|MultiEdit", "hooks": [{"type":"command","command":"$CLAUDE_PROJECT_DIR/tools/hooks/no_prod_db_writes.sh"}]},
  {"matcher": "Bash|Edit|Write|MultiEdit", "hooks": [{"type":"command","command":"$CLAUDE_PROJECT_DIR/tools/hooks/enforcement_files_script_only.sh"}]}
]
```

| Hook | Exact triggers (block, exit 2) | Explicitly allowed | Test (`tests/gates/test_g23_hooks.py`, table-driven, executes the command string parsed from settings) |
|---|---|---|---|
| H1 `no_bypass_git` | Bash command matching `git (commit\|merge)\b.*(--no-verify\|\s-n\b)`; `git push .*--no-verify`; `git -c core\.hooksPath`; `SKIP=` or `PRE_COMMIT_ALLOW_NO_CONFIG` in the command; `pre-commit uninstall`; `git push .*(HEAD:)?main\b` (direct push to main) | `git commit -m`, `git push origin feat/x`, `git push --force-with-lease origin feat/x`, `pre-commit run` | 12 rows: each blocked form → exit 2 and stderr contains `use the PR path`; each allowed twin → exit 0 |
| H2 `no_prod_db_writes` | DATA_DIR resolved from `INSIGHTMINER_DATA_DIR`, else `.env`, else `$CLAUDE_PROJECT_DIR/data`. Bash: command references DATA_DIR or `data/(insightminer\.db\|backups\|raw\|locks)` **and** contains a write verb (`sqlite3`, `rm`, `mv`, `cp`, `>`/`>>`, `tee`, `truncate`, `shred`, `dd`, `alembic`, `python -c`, `sed -i`, `chmod`). Edit/Write: `file_path` under DATA_DIR | Commands beginning `uv run insightminer`, `insightminer`, `make` (the CLI's own destructive gate applies); `ls`/`du`/`cat` on the dir; any path under `/tmp` or `pytest-*` | `sqlite3 $D/insightminer.db "DELETE FROM posts"` → 2; `rm -rf $D/raw/2026` → 2; Write `$D/x.json` → 2; `uv run insightminer db backup` → 0; `sqlite3 /tmp/pytest-1/t.db .tables` → 0; `ls $D` → 0 |
| H3 `enforcement_files_script_only` | Edit/Write/MultiEdit with `file_path` matching `\.ratchets/` or `\.claude/settings\.json`. Bash: command references either path **and** contains `>`, `>>`, `tee`, `sed -i`, `cp`, `mv`, `rm`, `python -c`, `printf`, `echo` | `make ratchet-bump`, `make ratchet-loosen`, `tools/ratchet.py`, `cat`, `git diff/log/show/add` | Write `.ratchets/coverage.txt` → 2 with `use make ratchet-bump or make ratchet-loosen`; `echo 90 > .ratchets/coverage.txt` → 2; `make ratchet-bump` → 0; `cat .ratchets/tests.txt` → 0; Edit `.claude/settings.json` → 2 |

H3 covers `.claude/settings.json` as self-protection: a hook that can be edited away by the tool it governs is not a hook. Wes edits that file by hand when needed; changes are rare.

**If the hook itself breaks.** Claude Code treats exit 2 as block, exit 0 as allow, and any other exit or a timeout as a non-blocking error: the tool call proceeds. So a crashing hook **fails open**. Mitigations, all mechanical: `set -euo pipefail; trap 'echo "hook internal error: blocking" >&2; exit 2' ERR` (Python twin: catch-all → exit 2), so internal errors fail closed; malformed stdin is a test row expecting exit 2; G24 verifies wiring on every CI run so a renamed or non-executable script is red before merge; scripts do nothing that can be slow (no network, no interpreter startup beyond `python3`), so the 5 s timeout is never approached. Residual, stated honestly: hooks govern only Claude Code tool calls in this project directory. Wes's terminal, another agent, or a `python - <<EOF` heredoc are governed by the outer rings: `no-commit-to-branch` and gitleaks in pre-commit, branch protection, the ratchet comparator, and the CLI's own destructive-operation gate. The hooks are the innermost of three rings, not the last line.

---

## E. Cut list

| # | Plan item | Verdict | Reason |
|---|---|---|---|
| E1 | Mutation score as a blocking ratchet | Demote to informational, monthly (G38) | Rank 26 already says optional. mutmut on SQLAlchemy/pydantic code is slow and noisy; a blocking kill rate would be met with equivalent-mutant suppressions, which is the grandfathering failure in new clothes |
| E2 | "No counts restated in prose anywhere" | Narrow to a regex on `tests`/`guards`/`suppressions`/`% coverage` (G33) | The general form is unfalsifiable; the narrow form catches the birth incident (hand-typed count off by 57) |
| E3 | Test-count floor "may not fall > 2% without a bump" | Replace with exact floor + 2% slack toward stale, and the loosening protocol for any drop | A free 2% is eight silently deleted tests at 400; the retrospective's lesson is that slack becomes a permanent exemption |
| E4 | Hook #3 "edits to `.ratchets/*` outside a PR that bumps them" | Redesign (D, H3) | A hook has no PR context. "Scripts are the only writers" is enforceable; "outside a PR" is not |
| E5 | "mypy on changed files" in pre-commit | Replace with `dmypy run` on the whole tree | Changed-files mypy misses cross-file breakage and yields false positives; it is a proxy for the invariant "the tree type-checks" |
| E6 | Restore drill as a quarterly manual checklist | Mechanize: scheduled `insightminer db restore --to-temp --verify` writing a `drills` row; `doctor` red when the last drill is > 100 days (DB panel to spec) | A manual checklist is not a gate and has no positive control (lesson D1: mechanism, not discipline) |
| E7 | Docker build as the "second matrix" from day one | Move to M4 | No image exists before M4; a job that builds nothing is a baked green |
| E8 | Live smoke (`-m live`) in CI | Drop from CI; local only | Credentials would have to live in GitHub secrets; the test is a PRAW-bump check Wes runs by hand monthly |
| E9 | Portability triggered by a workflow `paths:` filter on README | Move to an `if:` inside the required workflow, widened to Makefile/pyproject/lock/python-version/pre-commit | A required check whose workflow does not fire blocks the PR forever; README alone is the wrong trigger set |
| E10 | Zero-context second review for deletion/scrub/migrations/upsert PRs | Not a gate; a `CLAUDE.md` practice (spawn a fresh-context reviewer, paste its verdict under `## Independent review`). Optional P3: `pr-body` requires the section when those paths change | A body section is a proxy; it proves a heading exists, not that a review happened. Keep the practice, do not count it as a guard |
| E11 | Runtime fingerprint "recorded for the app version" | Derive from the packaged `schema.sql` (G18) | A per-version registry is a hand-maintained list |
| E12 | `GUARDS.md` "what it has caught since" as a typed column | Derive from CI failures via the pinned issue (G34); the quarterly review cites it | A typed catch count is narration |
| E13 | Pre-push hook running full `make check` | Propose a fast subset (ruff, dmypy, ratchet measure, `tests/gates`, ≈30 s); the full suite stays in required CI | Once CI is required and the ratchets compare against `main`, a 2–5 min pre-push mostly slows the agent's push loop. Decision for Wes (G5) |
| E14 | Stress corpus at 50k posts / 500k comments weekly | Size to what the `EXPLAIN QUERY PLAN` and wall-time assertions need; weekly, informational | Rank 23: the value is real indexes, not scale. DB/ingest panels to size |
| E15 | Coverage counters "amber when any drops more than X points vs trailing 7-run median" | Not a CI gate; runtime control for the ingest panel. Flag: X must be pinned and the positive control must exist before it counts as a guard | As written it has an unpinned threshold and no constructed bad state |
| E16 | Playwright E2E in CI | Not before M2; deselected marker when added | An optional suite that skips when the browser is missing is exactly the inert-gate pattern |
| E17 | "Network block" and "Required CI on main" as separate rows in the gates table | Keep as mechanisms, do not count them as guards | They are containers; counting them inflates the guard count the quarterly review is meant to hold |
| E18 | Dead-man switch, notifier proof, Healthchecks | Keep, out of this panel: runtime, not CI | Listed so the guard count is not double-booked across panels |

---

## F. Compensating controls for "agent merges everywhere"

| Threat | What catches it mechanically | What makes it visible to Wes |
|---|---|---|
| Assertion loosened (`== 5` → `is not None`) | Assert-count floor (G12) catches removals; mutation on core (G38) catches weakened tests where it matters most; `-W error` and the contract suite catch a fake that stopped matching reality | G27 sticky comment shows assert delta per file; G26 requires a reason per changed test file |
| Test deleted or moved to `slow`/`live` | `tests.collected` floor (G12) → loosening → approval (G13); runtime `skipped == 0` (G09); static skip ratchet (G08) | Approval click reads the ledger row; weekly audit lists it |
| Gate neutered (checker made to always pass) | Its positive control (`tests/gates/`) goes red, because the constructed bad state no longer produces red. Neutering both gate and control in one PR is the residual; it shows as changed files under `tests/gates/` | G27 lists them; G35 lists every enforcement-path change that week; G33 ties every gate id to a `GUARDS.md` row so a removed control is a currency failure |
| Ratchet edited by hand | H3 blocks the tool; G13 comparison 2 (non-canonical / not render(measured)); comparison 3 (direction vs `main`) | Approval or audit issue |
| Ratchet job skipped or workflow weakened | Required-check names are pinned in branch protection; a renamed job never reports and the PR cannot merge; G36 verifies the required set weekly; `actionlint` catches malformed YAML | G35 lists `.github/**` changes; G36 opens an issue on drift |
| "Passes locally" claimed on a subset or fabricated | CI is the authority; G26 compares pasted `collected`/`skipped`/`coverage` with CI's artifact and rejects `dirty=true` | Sticky comment shows the comparison |
| Broad `except … pass` | G01 rules; run status `partial` on any recorded warning (ingest panel) | Digest shows amber |
| Schema edited without migration | G15 snapshot, G16 models==DDL, G18 runtime fingerprint | PR diff of `schema.sql`, which is the point of the golden |
| Agent edits branch protection itself | **Token scope**: after M0, the agent's `gh` credential should be a fine-grained PAT with `contents: write` and `pull_requests: write` only, no `administration`, and ideally no `workflows` (GitHub then rejects pushes touching `.github/workflows/*`). Branch protection, required checks, environment reviewers and workflow YAML fall outside the agent's write perimeter | G36 weekly check is the independent verification |

Honest residual: none of this stops an agent that co-edits a gate and its control, or writes tautological tests. The design makes such changes *legible* in one weekly issue and one sticky comment per PR, which is the form of Wes's "review at will" that the retrospectives say mattered (D3: corrections, not approvals). The one human touchpoint kept is the approval click on a loosening, a rare event and not a code review.

**`CLAUDE.md` working agreement** (short, always loaded). Each rule carries its enforcer, so unenforced rules are labeled as such rather than assumed:

| Rule | Enforced by |
|---|---|
| Never weaken, skip, or delete a test to make a change pass | G08, G09, G12, G13 (approval); G38 partial |
| Never commit with `--no-verify`; never push to `main` | H1; `no-commit-to-branch`; branch protection |
| Never catch a broad exception without recording it on the run | G01; run status |
| Every bug fix starts with a failing test and lands a `KNOWN_ISSUES.md` row citing it | G33 (row must resolve to a test); the "failing first" part is agreement only |
| Every schema change ships migration + prior-revision fixture + snapshot | G15, G16, G17 |
| Never edit `.ratchets/*` or `.claude/settings.json` by hand | H3; G13 |
| Never touch the production DB by hand | H2; CLI destructive gate |
| Never store or log credentials | gitleaks (G29) partial; agreement for logs |
| Report results by pasting the `make check` block; every number cites its source | G26 |
| Adding a guard requires a birth-incident issue, a positive control, a `GUARDS.md` row, and a check whether an existing guard can be widened | G14 (approval), G33 |
| No new abstraction without two concrete uses; four layers only | G04; the rest is agreement only |

Plus the routing table ("touching `db/migrations` → read …") and the PR protocol.

**PR template** (`.github/pull_request_template.md`): `## What`; `## Tests changed` as a two-column table (file, reason) that G26 checks against the diff; `## make check` with the paste block between `<!-- make-check-summary:begin/end -->` markers; `## Ratchets` (auto-filled by the sticky comment; if loosened, link the ledger row); `## Independent review` (deletion/scrub/migrations/`repo.py` only, per E10).

**`GUARDS.md` structure:** `## Active` table (`ID | Name | Birth incident | Mechanism | Positive control node | Fails how | Born | Verdict (date) | Firings → pinned issue`); `## Retired` (append-only: id, date, verdict, reason, replaced by); `## Loosenings` (append-only, written by `make ratchet-loosen`). Verdict vocabulary from the earlier project: EARNED, EARNED AT BIRTH ONLY, UNPROVEN, SELF-SERVING. Birth incident is an issue number or a citation into `docs/learnings/`.

**Quarterly guard review** (`RUNBOOK.md`): `make guard-review` prints one row per gate id with the date its positive control last ran (junit), firings this quarter (pinned issue), and runtime cost; Wes assigns verdicts; rules: SELF-SERVING → drop or redesign this quarter; UNPROVEN for four consecutive quarters and > 5 s per run → drop candidate unless the class is data loss or compliance; every loosening approved that quarter is re-read for a pattern; the count is recorded in the review note *with its source line* from the tool output. Adding is by the G14 approval path; widening an existing gate is preferred and needs no approval.

---

## G. Open questions only the owner can answer

1. **GitHub plan.** On a Free personal account, private repositories cannot have branch protection, rulesets, or environment required reviewers. The entire "required CI on `main`" premise depends on this. Is `WhowellGit` on GitHub Pro (about 4 USD/month), or should it be? Without it, the design falls back to convention plus hooks, which is the earlier project's failure mode.
2. **Agent token scope.** Does the agent operate through `gh auth login` as Wes (full admin, `workflow` scope)? Recommendation: full token during the two-day M0, then a fine-grained PAT without `administration` and without `workflows`. Consequence: after M0, Wes applies workflow YAML changes himself (rare). Acceptable?
3. **Loosening approval.** CODEOWNERS review was declined. Is a one-click environment approval on the rare event of a ratchet moving the wrong way acceptable, or should loosening be visibility-only (auto-issue)? The difference is whether a test deletion can merge without a human seeing it first.
4. **Perimeter width.** Should the approval or token perimeter also cover `tests/gates/**`, `tests/conftest.py`, `tools/ratchet.py`, and `.claude/settings.json`, or only `.ratchets/*` and GitHub settings?
5. **Pre-push scope.** Keep the plan's full `make check` on pre-push, or the fast subset (E13)?
6. **Git identity.** The agent commits as `Wes Howell`, so git authorship cannot distinguish agent from human commits in audits. Add a trailer convention (`Agent: claude-code`) or a second identity?
7. **Coverage strictness.** Pure one-way (any drop pauses for approval) versus a hard floor of 90 with drops of ≤ 0.5 allowed above it? Pure one-way pushes an agent toward coverage-padding tests; the mutation job is the counterweight but only monthly.
8. **CI minutes.** Free tier gives 2,000 Linux minutes/month; the M1–M2 estimate is near 1,800. Accept the `py314`-on-main-only and macOS-weekly trade-offs, or upgrade (Pro gives 3,000)?
9. **Notification channel** for scheduled-job failures and the weekly audit: GitHub issues assigned to Wes (recommended; email gets ignored), or email only?
10. **Zero-context second review** (E10): practice in `CLAUDE.md`, body-section check, or drop?
11. **Quarterly thresholds:** four UNPROVEN quarters before a drop candidate, and 5 s runtime, are proposals. Wes sets them.
12. **Live credentials:** confirm they never enter GitHub secrets (E8), which means the PRAW-bump live smoke is a manual step Wes or the agent runs on the Mac.

---

**M0 fit check against the two-day box.** P1 rows total roughly 16–22 hours: pre-commit and CI workflow (≈3 h), ratchet tool with comparator, bump/loosen scripts and controls (≈5 h), import-linter contracts and controls (≈2 h), pytest config controls for `-W error`, `--block-network`, skips (≈2 h), schema snapshot, models==DDL, fingerprint on an empty rev 0 (≈2 h), three hooks with tests (≈2 h), `make check` summary (≈2 h), doc currency and `GUARDS.md` (≈1 h), portability job (≈1 h). If the box overruns, defer G26 (PR-body numeric match), G35, G36 to M1; nothing else is deferrable without leaving a gate unproven at M0.
