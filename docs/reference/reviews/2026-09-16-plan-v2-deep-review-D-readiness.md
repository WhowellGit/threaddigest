# Readiness to start tranche B and M1b (2026-09-16)

## Claim under test

"Nothing in the working agreement, the harness page, the test strategy, the guards ledger, the
hooks, the pytest configuration, or the plan's tranche B and M1b sections contradicts the next
work, and every precondition of that work is named somewhere a builder would read."

Refuted in part. Thirteen findings below; three of them would stop or damage the probe day itself.
The harness (hooks, gates, ratchets, document contracts) is in good order and blocks nothing the
next work needs. The gaps are all in the *content* of the tranche B specification: the probe
command's shape, what the probe day must capture, and what happens to the bytes it brings back.

---

## Method

Read, in this order: `docs/reference/AGENT_BRIEF.md`; `CLAUDE.md` whole; `docs/INSIGHTMINER_HARNESS.md`
§ 8; `docs/TEST_STRATEGY.md`; `docs/runbook/GUARDS.md`; `docs/runbook/RUNBOOK.md`; `docs/PLAN.md`
§ Module map, § TDD policy by layer, § Testing strategy, § Milestones, § Review harness;
`docs/recent/STATUS.md`; `docs/reference/reddit-policy-facts-2026-09-14.md`;
`docs/reference/reviews/2026-09-13-panel-ingest.md` § C and § D; `docs/reference/reviews/2026-09-12-collector-design-review.md`
§ 2; `docs/decisions/DECISIONS.md` (retired claims, live facts, D-14, D-16, D-30);
`docs/runbook/KNOWN_ISSUES.md` KI-018 and KI-023; `tools/hooks/*.sh`; `.claude/settings.json`;
`pyproject.toml`; `tests/conftest.py`; `tests/gates/test_pytest_config.py`,
`test_data_dir_isolation.py`, `test_superseded_claims.py`, `test_no_imported_identifiers.py`,
`test_no_bypass.py`; `src/insightminer/cli.py`, `ports.py`, `settings.py`, `services/doctor.py`,
`adapters/reddit_fake/__init__.py`; `.env.example`; `.gitleaks.toml`; `.pre-commit-config.yaml`;
`.importlinter`; `.github/workflows/ci.yml`; the `Makefile`; `tools/review_packet.py`;
`.venv/.../pytest_recording/plugin.py` (to settle what `--block-network` actually does).

Nothing in the repository was edited. Commands and their output:

```
$ uv run pytest --collect-only -q -p no:cacheprovider 2>&1 | tail -5
tests/unit/test_paging.py: 30
tests/unit/test_retry.py: 90
tests/unit/test_settings.py: 20
tests/unit/test_themes.py: 49
```

(There is no trailing total line under `-q` in this pytest; summing the 75 per-file counts gives
**1591 collected items**. The `collected=1059` floor in `.ratchets/tests.txt` counts test
*functions* by AST, not parametrized items — `tools/ratchet.py:426 count_tests(tree)` — so the two
numbers are not comparable and the floor is not stale. No `tests/live` directory exists.)

```
$ uv run pytest --markers 2>&1 | head -40
@pytest.mark.live: needs real Reddit credentials; never runs in CI

@pytest.mark.slow: weekly jobs

@pytest.mark.gate: positive control proving a guard can go red

@pytest.mark.macos: needs macOS tooling (plutil, launchd); deselected on the Linux CI matrix, run on the Mac

@pytest.mark.hypothesis: Tests which use hypothesis.

@pytest.mark.anyio: mark the (coroutine function) test to be run asynchronously via anyio.

@pytest.mark.time_machine(...): set the time with time-machine

@pytest.mark.no_cover: disable coverage for this test.

@pytest.mark.alembic: Tests which use pytest-alembic.

@pytest.mark.vcr: Mark the test as using VCR.py.

@pytest.mark.block_network: Block network access except for VCR recording.

@pytest.mark.default_cassette: Override the default cassette name.

@pytest.mark.allowed_hosts: List of regexes to match hosts to where connection must be allowed.
[...]
```

```
$ grep -n "live" pyproject.toml tests/conftest.py
tests/conftest.py:8:of touching live data.
tests/conftest.py:10:``fake`` / ``seeded`` / ``BASE`` live here (design-round5.md §2.2) rather than under
tests/conftest.py:86:    """r/premiere with 250 live posts (``post 0`` oldest ... ``post 249`` newest)."""
pyproject.toml:64:#   -m 'not live'    live tests are deselected here, so the skip ratchet stays at zero
pyproject.toml:72:addopts = "-q -m 'not live' --block-network --strict-markers -W error"
pyproject.toml:81:  "live: needs real Reddit credentials; never runs in CI",
pyproject.toml:133:"sqlalchemy.text".msg = "Raw SQL lives inside insightminer.db only; ..."
```

So: the `live` marker **is** registered (`pyproject.toml:81`), `--strict-markers` is on, and
`-m 'not live'` in `addopts` deselects a marker that exists. `tests/conftest.py` says nothing
about live tests at all.

```
$ git check-ignore -v data/x tests/fixtures/x
.gitignore:3:data/*	data/x
```

`data/` is ignored; `tests/fixtures/` is **not** — fixtures are tracked and permanent in history.

```
$ uv run python tools/hooks_status.py
git hooks: installed (/Users/wesmax/repos/insightminer/.git/hooks/pre-commit and pre-push run pre-commit)
claude hooks: 3 of 3 scripts registered in .claude/settings.json
```

```
$ grep -n "probe" src/insightminer/cli.py
(no output; exit 1)
```

The decisive piece of library behaviour, read from the installed plugin
(`.venv/lib/python3.13/site-packages/pytest_recording/plugin.py:133`):

```python
# If network blocking is enabled there is one exception - if VCR is in recording mode (any mode except "none")
if (block_network or request.config.getoption("--block-network")) and (not vcr_markers or record_mode == "none"):
    allowed_hosts = request.getfixturevalue("allowed_hosts")
    with network.blocking_context(allowed_hosts=allowed_hosts):
```

Read this carefully: the block is lifted **only** for a test that carries a `vcr` marker *and* is
recording. A test with no `vcr` marker — which is exactly what a `tests/live` credentialed smoke
test is — is blocked unconditionally by the `--block-network` in `addopts`, whatever `-m` selects
it. That is Finding 1.

---

## Preconditions

| Precondition | Where named | Consistent? | Enforced by | Gap |
|---|---|---|---|---|
| Where live tests live, how selected | `docs/runbook/GUARDS.md:50` (G08/G09, "`tests/live` (M1b, opt-in)"); `pyproject.toml:72,81` | Marker yes; directory does not exist yet (M1b, so fine) | `tests/gates/test_pytest_config.py::test_addopts_deselect_live_tests`; `--strict-markers` | **A selected live test cannot pass**: `--block-network` blocks it and the autouse fixture strips its credentials (F1) |
| How probe payloads are scrubbed before becoming fixtures | Three places that disagree: `docs/reference/reviews/2026-09-13-panel-ingest.md:218` ("usernames are replaced on save"); `docs/TEST_STRATEGY.md:345` (open question, awaiting Wes); `src/insightminer/adapters/reddit_fake/__init__.py` fixture schema ("the `data` objects exactly as Reddit returned them") | **No** | Nothing | F2 — no gate reads `tests/fixtures/` for Reddit identifiers |
| Which gate catches an unscrubbed fixture | — | — | None. `tests/gates/test_no_imported_identifiers.py` scans for e-mails, IPv4, `/Users/<name>`, model names, attribution trailers and the earlier project's codenames — not Reddit usernames or `t2_` ids | F2 |
| Which cassette library, is it a dependency | `pyproject.toml:36` `pytest-recording>=0.13`; `docs/PLAN.md:88,279`; `docs/TEST_STRATEGY.md:21` | Yes | Installed; its markers are live (see `--markers` output) | None. This precondition holds cleanly |
| `--record-mode=none` in CI | `docs/runbook/GUARDS.md:19` (G06 mechanism), `docs/PLAN.md:279`, `docs/TEST_STRATEGY.md:21` | Claimed as a mechanism | **Nowhere in the tree** — `grep -rn "record-mode" .github Makefile pyproject.toml tests` is empty. True only as pytest-recording's default (`plugin.py:44 default=None` → `"none"`) | F6 |
| Cassette auth/token filtering | `docs/PLAN.md:279` ("auth headers and tokens filtered"); `docs/reference/reviews/2026-09-12-collector-design-review.md:134` (the exact `filter_headers` / `before_record_response` recipe) | Named, not built | Nothing. No `vcr_config` fixture exists anywhere | F7 |
| How credentials reach the probe | `.env.example`; `src/insightminer/settings.py:37-38,262-264`; `docs/runbook/RUNBOOK.md` § 1 steps 2 and 5; `docs/PLAN.md` § Things only Wes can do 1 | Yes | `.gitignore:2`; gitleaks in `.pre-commit-config.yaml:33` (installed); `SecretStr`; `hide_input_in_errors=True` (`settings.py:259`); `settings_fingerprint` excludes secrets structurally (`settings.py:386`); `tests/conftest.py:36-38` strips every `INSIGHTMINER_*` so a developer's `.env` never reaches a test | Holds, and is the strongest-built precondition of the set. The one side effect is F1 |
| The doctor auth ping | `docs/PLAN.md:180` ("one cheap auth ping"), § Verification 2 "(tranche B)"; `docs/runbook/RUNBOOK.md` § 1 step 6 | Runbook step 6 asserts behaviour that does not exist and carries **no** milestone marker, while steps 7 and 8 carry `(M1a+)` / `(M1d+)` | `services/doctor.py:477 check_credentials_present` is presence only, "never validated" | F10 |
| What the probe must capture (deletion predicates, KI-023) | Scattered over six documents; the real list is `2026-09-13-panel-ingest.md` § C P-01…P-17, an immutable reference record | Partly — P-18 exists only as a phrase in a gaps paragraph (`docs/TEST_STRATEGY.md:289`) | Nothing; no single checklist, no runbook section | F5 |
| What the review runner / second external round need | `docs/recent/STATUS.md:23`; `docs/PLAN.md` § Review harness; `docs/runbook/RUNBOOK.md` § 7 | The packet mechanism exists and is gated (G52) | `tools/review_packet.py`; `tests/gates/test_review_packet.py` | F3 — the exclusion list names `tests/fixtures/` only, so cassettes land inside or outside the packet by accident |
| What `make check` does when tests first need network | `Makefile:5,66`; `pyproject.toml:72` | Yes | `MARKEXPR` is `not live` on Darwin, `not live and not macos` elsewhere; cassette replay is offline | None. Nothing about `make check` needs to change |
| Would the hooks block a probe-day step | `.claude/settings.json`; `tools/hooks/*.sh` | Yes | Three hooks, all registered and installed (`hooks_status.py` output above) | None for the probe itself (F12 is a minor read-only false positive) |
| A cassette over 1 MB | — | Not named anywhere | `.pre-commit-config.yaml:13-14` `check-added-large-files --maxkb=1024` would refuse it | F9 — the constraint is real but unwritten, and a real `/new` page may exceed it |
| Import-linter names `adapters/reddit_praw.py` | `.importlinter:20-34` | Yes | `lint-imports` in `make check`; `tests/gates/test_layering.py` | F8 — `unmatched_ignore_imports_alerting = warn` must flip to `error` the day the module lands, and nothing says so |
| Reddit policy facts still bound the design | `docs/reference/reddit-policy-facts-2026-09-14.md` | The obligations do; **one derived conclusion does not** (line 57) | `docs/decisions/DECISIONS.md` live-facts table F-01/F-02 and the retired-claims table pin the cadence facts; G34 excludes `reference/` | F11 |
| The probe command's shape | `docs/PLAN.md:222` (one command, a fullname) vs `2026-09-13-panel-ingest.md:218,261` (five sub-modes, verdict **Add**) | **No** | Nothing | F4 |
| The fixture schema the probe writes | `src/insightminer/adapters/reddit_fake/__init__.py` § "Fixture schema (`from_fixture` / `load_fixture` / `to_fixture`; written by `probe --save-fixture`)" | Yes, fully specified | `FakeRedditGateway.from_fixture` is built and tested (`tests/adapters/test_fake_gateway.py`, 109 items) | None. This is the best-prepared piece of tranche B |

---

## Findings

### F1 — HIGH — A `tests/live` test cannot pass even with credentials; two independent blockers

**Evidence.** `pyproject.toml:72` puts `--block-network` in `addopts` unconditionally.
`pytest_recording/plugin.py:133` lifts the block only for a test that has a `vcr` marker *and* a
record mode other than `none`; a credentialed live test has neither, so it is blocked whatever
`-m live` selects. Independently, `tests/conftest.py:33-42`:

```python
@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name)
```

`ENV_PREFIX` is `"INSIGHTMINER_"` (`conftest.py:29`), so the fixture deletes
`INSIGHTMINER_REDDIT_CLIENT_ID/_SECRET/_USERNAME` from every test in the suite, live ones included.
`docs/runbook/GUARDS.md:50` states the intended behaviour: "`tests/live` (M1b, opt-in) *fails*
without credentials when explicitly selected." That is satisfied — but vacuously, because it also
fails *with* credentials, for two reasons that have nothing to do with credentials. The guard as
written cannot distinguish the two outcomes, so it would read green on a broken live suite.

**Fix.** Decide the live-suite escape now and write it into `docs/TEST_STRATEGY.md` § 1 and
`pyproject.toml`'s addopts comment: a `tests/live/conftest.py` that overrides `isolated_data_dir`
to keep the three `INSIGHTMINER_REDDIT_*` variables, plus either an `allowed_hosts` marker on each
live test or a documented `--allowed-hosts='.*\.reddit\.com'` on the live invocation; add a
`make test-live` target so the invocation has one home.

---

### F2 — CRITICAL — Fixture scrubbing is an open question, three documents disagree, and no gate would catch an unscrubbed fixture

**Evidence.** Three statements about the same act, in three places a builder would read:

- `docs/reference/reviews/2026-09-13-panel-ingest.md:218`: "Fixtures land in `tests/fixtures/json/`
  in the exact schema `FakeRedditGateway.from_fixture` loads; **usernames are replaced on save**."
- `docs/TEST_STRATEGY.md:345`, in the list of things awaiting Wes: "Fixture scrubbing on
  `probe --save-fixture`: automatic username replacement (recommended) or manual review before
  commit?" — still open.
- `src/insightminer/adapters/reddit_fake/__init__.py`, the fixture-schema section that the probe is
  named as the writer of: "``posts`` and ``comments`` are the ``data`` objects **exactly as Reddit
  returned them**."

The third contradicts the first outright. A builder implementing `--save-fixture` from the fake's
docstring writes the wire payload verbatim.

No gate closes this. `tests/gates/test_no_imported_identifiers.py` scans tracked text for e-mails,
IPv4 literals, `/Users/<name>`, model names, attribution trailers and the earlier project's
codenames; a Reddit username, a `t2_*` author id, a flair string or a body of third-party text
passes every one of them. `git check-ignore -v tests/fixtures/x` returns nothing: fixtures are
tracked, so `CLAUDE.md` § The irreversible few rule 2 applies in full — "history keeps them" —
and the repository has already had its history rewritten three times for exactly this class of
mistake (`docs/recent/STATUS.md:29`).

The compliance dimension makes this the top finding rather than a tidiness one.
`docs/reference/reddit-policy-facts-2026-09-14.md` item 1 requires the author id and every
author-identifying reference to be removable when an account is deleted, and item 3 says
anonymising does not license retention. A committed fixture is content that cannot be scrubbed
later without another history rewrite.

**Fix.** Settle the open question in `docs/TEST_STRATEGY.md` § Fixtures and probes before the probe
day (recommendation: automatic replacement on save, a pure function in `core/` with its own unit
tests, so the scrub is testable without credentials); correct the fake's fixture-schema docstring in
the same change; then add a gate under `tests/gates/` that scans every tracked file under
`tests/fixtures/` for a `t2_`/`t5_` id or an `author` value outside an allow-list of invented names,
with a positive control that plants one.

---

### F3 — HIGH — Where cassettes live decides whether recorded Reddit content ships to external reviewers, and nothing decides it

**Evidence.** `tools/review_packet.py:100-113`:

```python
EXCLUDED_PREFIXES = (
    ".env",
    "data/",
    "docs/reference/earlier-project",
    "docs/reference/reviews/2026-",
    "memory-snapshot/",
    "tests/fixtures/",
    ...
)
```

and `"4-tests": ("tests",)` at line 96 — the whole `tests/` tree is in the packet, minus those
prefixes. `tests/fixtures/` is excluded; nothing else under `tests/` is. The two documents that
name a cassette path both put cassettes **outside** `tests/fixtures/`:
`docs/reference/reviews/2026-09-12-collector-design-review.md:134` gives the convention
`cassettes/<module>/<test>.yaml`, and `2026-09-13-panel-ingest.md:236` (P-15) names
`cassettes/auth_about.yaml`. `docs/runbook/GUARDS.md:42` (G52) nonetheless states that "secrets,
data, **fixtures**, the earlier project's folders, the memory snapshot, and dated review reports are
excluded by prefix" — true of `tests/fixtures/`, false of a cassette directory placed anywhere else.
`docs/recent/STATUS.md:23` schedules "the second external round at tranche B's design freeze", so
this fires precisely at the moment the first cassettes exist.

The same rule cuts the other way: if cassettes *are* excluded, a code-executing seat — which
`docs/PLAN.md` § Review harness now requires in every round, "because the two rounds so far found
their defects only by running the code" — cannot run the adapter suite at all.

**Fix.** Decide the cassette directory in `docs/PLAN.md` § Testing strategy (recommendation:
`tests/adapters/cassettes/`), add that prefix to `EXCLUDED_PREFIXES` in `tools/review_packet.py`,
add an assertion to `tests/gates/test_review_packet.py` that no packet file matches the cassette
prefix, and state in `docs/runbook/RUNBOOK.md` § 7 that the adapter suite is not runnable from a
packet and why.

---

### F4 — HIGH — The plan and the probe plan disagree about what `probe` is, and the recommendation that would have settled it was never adopted

**Evidence.** `docs/PLAN.md:222` — the CLI table, which is the builder's specification:

```
| `insightminer probe <fullname> [--save-fixture]` | Dump raw JSON for an item; the probe day turns unverified Reddit behaviours into fixtures before M1b | tranche B |
```

`docs/reference/reviews/2026-09-13-panel-ingest.md:218` — the probe plan that the probe day
executes: "The plan's `probe <fullname>` needs sub-modes to produce these (see D-14):
`probe about r/<sub>`, `probe listing r/<sub>/new --limit N`, `probe tree <id> --more-limit N`,
`probe info <fullname,...>`, `probe search "<q>"`, each with `--save-fixture <name>`." The panel's
own D-14 row (line 261) gives the verdict: under-specified, "Parity, anchor, clamp, quarantine, and
redirect fixtures need listing/tree/about/search captures", recommendation **Add**.

That adoption was never carried anywhere. `grep -rni "sub-mode" docs/` returns only those two lines
in the reference record; `docs/decisions/DECISIONS.md` has no entry; the plan's CLI row is
unchanged. `grep -n "probe" src/insightminer/cli.py` returns nothing, which is correct for tranche
B — but a builder who implements the plan's row builds a single command that takes a fullname and
then cannot capture P-07 (quarantined `about`), P-09 (listing with a sticky), P-10 (four-way parity),
P-11 (continue-thread), or P-14 (redirect). Five of seventeen probes, each needing a credentialed
session to redo.

Note that the panel's `(see D-14)` is an internal cross-reference to its own § D table, not to
`DECISIONS.md` D-14, which is about QNAP scope. A reader chasing the citation lands on the wrong
document; worth fixing in the plan's wording rather than in the immutable record.

**Fix.** Rewrite the `probe` row in `docs/PLAN.md` § CLI to the five sub-modes with
`--save-fixture <name>`, add a `DECISIONS.md` entry recording the adoption of the ingest panel's
D-14 and the `(see D-14)` ambiguity, and sweep `docs/TEST_STRATEGY.md:13` and § 3.2 in the same
change.

---

### F5 — HIGH — There is no probe-day checklist; the captures are scattered over six documents, two of them immutable

**Evidence.** What the one credentialed session must bring back is stated in:

- `docs/recent/STATUS.md:20` — the headline ("capturing the shapes the deletion predicates and the
  fake's summary assume (KI-023's fidelity limit included)")
- `docs/PLAN.md:172` — the content-state predicates to re-confirm; `:362` — the TDD row
- `docs/TEST_STRATEGY.md:112` (FK-01), `:128` (RC-01), `:160-162` (AD-01, AD-03), `:343-345`
  (the two open questions)
- `docs/runbook/KNOWN_ISSUES.md:35` (KI-018: "the probe day records what a real capped listing
  returns") and `:43` (KI-023: "with the probe day confirming the real shape")
- `docs/reference/reviews/2026-09-13-panel-ingest.md` § C — the actual seventeen-row table, in a
  reference record that `tools/doc_policy.py` holds byte-identical and that therefore cannot grow

P-18 is the sharpest illustration. `docs/TEST_STRATEGY.md:289` says the deleted-link-post probe
should be "add[ed] to the probe plan as P-18" — but the probe plan is immutable, so P-18 exists
only as a clause in a paragraph headed "Gaps the adversarial review named that have no spec ID yet".
Nothing collects it into the list the probe day works from. `docs/runbook/RUNBOOK.md` has eight
sections and none of them is the probe day, though it is the single highest-stakes, one-shot,
credentialed session in the project: a missed capture costs another approved-access session.

**Fix.** Add `docs/runbook/RUNBOOK.md` § 9 "The credentialed probe day" as a prune-stale checklist
that restates P-01…P-17 as rows with a tick column, adds P-18, and folds in KI-018's capped-listing
capture and KI-023's large-`more` capture, each citing its source; cite that section from
`docs/recent/STATUS.md` § Next 1 and from `docs/PLAN.md` § TDD policy by layer.

---

### F6 — MEDIUM — `--record-mode=none` is a mechanism named in three documents and present in none

**Evidence.** `docs/runbook/GUARDS.md:19` lists it in G06's *mechanism* column: "`addopts =
--block-network` (pytest-recording), `--record-mode=none` in CI". `docs/PLAN.md:279` and
`docs/TEST_STRATEGY.md:21` repeat it. But
`grep -rn "record-mode" .github Makefile pyproject.toml tests` returns nothing. It is true only
because pytest-recording defaults to it (`plugin.py:44-47`, `default=None` documented as
'Default to "none"'). Against `CLAUDE.md` § Enforcement over trust — "every rule ... names what
enforces it ... if nothing can, it is labelled review-only with the reason" — a mechanism column
naming a flag that is not in the tree overstates the guard. G06's positive control
(`test_socket_connect_raises_under_block_network`) proves the socket block and says nothing about
record mode.

The hole is real, not notional: a stray `--record-mode=rewrite` on a developer or agent invocation
re-records every cassette against the live API, because `plugin.py:133` lifts the network block for
exactly that case, and nothing would fail.

**Fix.** Either add `--record-mode=none` to `addopts` in `pyproject.toml` and assert it in
`tests/gates/test_pytest_config.py` beside the three existing addopts assertions, or strike the
claim from G06, the plan and the test strategy and record it as the library default.
Recommendation: add it — it costs one line and converts a review-only claim into a checked one.

---

### F7 — MEDIUM — No `vcr_config`: the first recorded cassette will carry the Authorization header and the OAuth token

**Evidence.** `docs/PLAN.md:279` requires "auth headers and tokens filtered" and
`docs/reference/reviews/2026-09-12-collector-design-review.md:134` gives the exact recipe
(`filter_headers=["Authorization","Cookie","Set-Cookie"]`, `before_record_response` to blank
`access_token`, `decode_compressed_response=True`, match on
`["method","scheme","host","path","query"]`). No `vcr_config` fixture exists in the tree
(`grep -rni "vcr" tests/` returns only `test_pytest_config.py`'s docstring). pytest-recording's
`vcr_config` fixture defaults to `{}` (`plugin.py:86`), so without one, recording writes the token
exchange verbatim. gitleaks runs in pre-commit and is installed, and its generic-api-key rule may
well match `access_token:` in a YAML cassette — but "may well" is not the standard this repository
sets, and the `.gitleaks.toml` allowlist is a single narrow regex for ratchet addresses, so nothing
has been tuned for this shape.

**Fix.** Land `tests/adapters/conftest.py` with the `vcr_config` fixture from the design review
*before* the first recording, and add a gate that reads the fixture's `filter_headers` and asserts
`Authorization` is in it, with a positive control that removes it.

---

### F8 — MEDIUM — The import-linter praw contract must be tightened the day `reddit_praw.py` lands, and nothing says so

**Evidence.** `.importlinter:28-34`:

```
ignore_imports =
    insightminer.adapters.reddit_praw -> praw
    insightminer.adapters.reddit_praw -> prawcore
# The adapter module does not exist yet, so its allow-list entries match nothing today.
# "warn" keeps the contract passing on the current tree; the contract still fails the
# moment any other module imports praw.
unmatched_ignore_imports_alerting = warn
```

The contract already names `adapters/reddit_praw.py`, which is the good half of the answer. But
`warn` was a temporary accommodation for a module that does not exist, and once the module lands it
silently tolerates a stale allow-list entry — for example a later rename of the module leaving both
the old and the new path ignored. No gate, no `KNOWN_ISSUES` row and no plan line records that it
must flip to `error`; only this comment does, and a comment is not an enforcer.

**Fix.** Add the flip to `error` to the tranche B checklist in `docs/runbook/RUNBOOK.md` § 9 (see
F5) and assert the value in `tests/gates/test_layering.py`.

---

### F9 — MEDIUM — A real listing cassette may exceed the 1 MB pre-commit cap, and nothing warns

**Evidence.** `.pre-commit-config.yaml:13-14` sets `check-added-large-files --maxkb=1024`.
`docs/reference/reviews/2026-09-13-panel-ingest.md:240` schedules C-02, "first `/new` page", as a
cassette against the test subreddit. A `/r/<sub>/new` page is 100 posts, each carrying `selftext`
and `selftext_html`; on a busy subreddit that is plausibly over a megabyte of YAML. The constraint
is enforced (the commit is refused) but is named in no document a builder reads, so it surfaces as
a mysterious pre-commit failure at the end of the probe day.

**Fix.** Note the 1 MB cap and the mitigation (record C-02 against the test subreddit, or cap the
recorded page) in the probe-day section of `docs/runbook/RUNBOOK.md` (F5).

---

### F10 — MEDIUM — The runbook asserts a `doctor` auth ping that does not exist, with no milestone marker

**Evidence.** `docs/runbook/RUNBOOK.md` § 1 step 6: "`uv run insightminer doctor` — expects auth OK
with rate-limit headers and exactly two HTTP calls (token + about), DB at head, data dir writable
and outside TCC folders." `src/insightminer/services/doctor.py:477-493` is
`check_credentials_present`, whose own docstring says "The three Reddit credentials are non-empty.
**Presence only, never validated**". Steps 7 and 8 of the same list carry `(M1a+)` and `(M1d+)`
markers; step 6 carries none, and `docs/PLAN.md` § Verification item 2 does mark the same claim
"(tranche B)". `tools/doc_policy.py` cannot catch this: the identifiers on the line
(`insightminer doctor`) all resolve, and G55's own ledger row records that "a behavioural claim
without an identifier" stays review.

**Fix.** Mark step 6 `(tranche B+)` in `docs/runbook/RUNBOOK.md` § 1 and split it: what `doctor`
checks today (credential presence, DB at head, data dir) and what it adds in tranche B.

---

### F11 — MEDIUM — The policy facts file states a compliance conclusion that the cadence decision made false, and the plain restatement D-30 called for was never written

**Evidence.** `docs/reference/reddit-policy-facts-2026-09-14.md:57`: "The two-day reconcile cadence
meets the forty-eight-hour recommendation for the live database." Under D-30 the collector runs
Monday and Thursday, so the longest gap is 96 hours, and `config/settings.yaml:16` now sets
`tier_max_age_hours.under_30d: 120` (KI-026, and F-07 in the live-facts table). The obligation
itself is unaffected — `docs/decisions/DECISIONS.md:215` records that removal has no stated deadline
and 48 hours is a recommendation — but the derived sentence is now wrong.

`docs/decisions/DECISIONS.md:218` listed the correction as a D-30 consequence to sweep: "the
reconcile wording (the removal obligation is met at the next run; the forty-eight-hour
recommendation is not met between runs, **said plainly instead of claimed**)". That plain statement
does not appear in the plan — `grep -n "forty-eight\|48 h\|48-hour" docs/PLAN.md` is empty. The
§ 2 purge-latency row (`DECISIONS.md:49`) carries a dated re-derivation and
`docs/recent/STATUS.md:41` lists the compliance bounds as awaiting Wes, so the item is tracked, but
the one document a tranche B builder is pointed at for policy still states the superseded
conclusion with no marker.

Two mechanisms that would normally catch this both miss by design:
`tests/gates/test_superseded_claims.py` excludes `reference/` ("Historical material ... [is] outside
the scan: they are allowed to describe the past"), and the retired phrase registered on 2026-09-15
is `every 2 days`, not "two-day reconcile cadence". `tools/doc_policy.py` holds reference records
byte-identical, so the file cannot be edited — which is right, and means the fix belongs elsewhere.

**Fix.** Add one plain sentence to `docs/PLAN.md` § Collector algorithm step 4 stating that the
48-hour recommendation is not met between scheduled runs and the obligation is met at the next run,
and add `two-day reconcile cadence` to the retired-claims table so the phrase cannot reappear in a
live document.

---

### F12 — LOW — The enforcement hook refuses a read-only loop over `.ratchets/`

**Evidence.** During this review:

```
$ for f in .ratchets/*.txt; do echo "-- $f"; cat "$f"; done
PreToolUse:Bash hook error: enforcement_files_script_only: BLOCKED: for may write .ratchets;
use make ratchet-bump / make ratchet-loosen (tools/ratchet.py), or, for .claude/settings.json,
generate a Terminal script for the human to run (docs/runbook/RUNBOOK.md section 1)
```

The command only reads. The hook treats `for` as an unrecognised command word in a pipeline that
names a protected path and fails closed, which is the documented and correct posture
(`tools/hooks/enforcement_files_script_only.sh:6-8`). Plain `cat .ratchets/tests.txt ...` works. Not
a defect; recorded because loops over files are natural on a probe day and a builder should know the
refusal is about the shell construct, not about intent.

**Fix.** None required. Optionally note in `docs/INSIGHTMINER_HARNESS.md` § Enforcement that
read-only access to protected paths is by direct command, not by loop.

---

### F13 — LOW — `-W error` versus PRAW's own warnings is an unbudgeted risk for the first cassette test

**Evidence.** `pyproject.toml:72` sets `-W error`, and the comment at line 67 states the intent:
"PRAW deprecations and SQLAlchemy warnings surface now". PRAW and prawcore are currently imported
nowhere (`docs/reference/reviews/2026-09-14-testing-and-workflow-panel.md:22`: "`pytest-recording`,
`responses`, and `time-machine` are declared and imported nowhere"), so no PRAW warning has ever
been seen in this suite. `praw>=8,<9` is pinned deliberately. The first adapter test may therefore
fail on a library warning rather than on its own assertion, and the only sanctioned escape is a
`filterwarnings` ignore, which `.ratchets/suppressions.txt` counts as a ratcheted suppression
needing a loosening.

**Fix.** Expect it; budget one `make ratchet-loosen KEY=suppressions.filterwarnings_ignore` with a
reason, or pin the warning to a specific module. No document change needed beyond a line in the
probe-day section.

---

## Where the claim held

These are not filler: each was checked and each is genuinely in good order.

1. **The `live` marker is registered and correctly deselected.** `pyproject.toml:81` declares it,
   `:72` deselects it, `--strict-markers` means a typo is an error, and
   `tests/gates/test_pytest_config.py:32` asserts the exact addopts string. The `--markers` output
   above confirms it resolves at runtime. `-m "not live"` therefore deselects a marker that exists,
   and the skip ratchet stays at zero honestly (`.ratchets/skips.txt`: `count=0`).
2. **The cassette library is chosen, declared and live.** `pytest-recording>=0.13` at
   `pyproject.toml:36`; its four markers appear in `--markers`. Nothing to decide.
3. **The import-linter contract already names the adapter.** `.importlinter:20-34` forbids `praw`
   and `prawcore` everywhere except `insightminer.adapters.reddit_praw`, and the layers contract
   places `adapters` below `services` and beside `db`. Only the `warn` setting needs attention (F8).
4. **The fixture schema the probe must write is fully specified and already implemented on the
   reading side.** The "Fixture schema" block in `src/insightminer/adapters/reddit_fake/__init__.py`
   gives the exact JSON, names `probe --save-fixture` as its writer, and `FakeRedditGateway.from_fixture`
   is built and covered by 109 collected items in `tests/adapters/test_fake_gateway.py`. The panel's
   "one producer of fixture shape" requirement is met.
5. **Credential handling is the best-built precondition in the set.** `.env` is gitignored, never
   read implicitly (`settings.py:37-38` — only `uv run --env-file .env` exports it), secrets are
   `SecretStr`, `hide_input_in_errors=True` keeps them out of validation messages,
   `settings_fingerprint` excludes every secret field *structurally* so a new secret cannot leak by
   omission, gitleaks runs in pre-commit and the hooks are installed, and `tests/conftest.py`
   strips every `INSIGHTMINER_*` variable so a developer's real `.env` can never reach a test.
6. **No hook blocks any step of the probe day or the adapter build.** The three registered hooks
   govern git bypass (`no_bypass_git.sh`), the enforcement files
   (`enforcement_files_script_only.sh`) and read-before-touch (log mode). A probe writing under
   `data/` (gitignored), a fixture under `tests/fixtures/` (tracked, unblocked) and a new module
   under `src/insightminer/adapters/` are all unaffected. `tools/hooks_status.py` confirms 3 of 3
   registered and both git hooks installed.
7. **`make check` needs no change when tests first need the network.** `Makefile:5` sets
   `MARKEXPR` to `not live` on Darwin and `not live and not macos` elsewhere; cassette replay is
   offline under `--block-network` (`plugin.py:133` — a `vcr` marker with record mode `none` still
   blocks real sockets, and VCR intercepts before the socket); live tests are deselected on both
   platforms; `.github/workflows/ci.yml:36` runs exactly `make check` with no secrets.
8. **A cassette over 1 MB is already refused** by `check-added-large-files --maxkb=1024`. The
   enforcement exists; only its documentation is missing (F9).
9. **The Reddit policy facts that bound the design still bind.** The rate limit (100 queries per
   minute per OAuth client id, averaged over ~10 minutes), the User-Agent format
   `<platform>:<app ID>:<version> (by /u/<username>)` — implemented at `settings.py:391-395` and
   asserted as AD-01 — the deletion obligations, and the explicit-approval requirement are all
   cadence-independent and are correctly reflected in `docs/runbook/RUNBOOK.md` § 1 step 2 and
   `docs/PLAN.md` § Things only Wes can do item 1. Only the derived 48-hour sentence is stale (F11).
10. **The cadence sweep of 2026-09-15 was thorough.** The live-facts table pins the schedule
    (F-01 `Monday and Thursday`), the staleness default (F-02 `5d`) and the reconcile bound
    (F-07 `120`) to homes a tool reads, and the retired-claims table blocks five superseded
    cadence phrases. `docs/PLAN.md:184`'s statement that `full_sweep_every_hours` (48) is shorter
    than the gap between runs is true under Monday/Thursday. The one residue is F11, and it sits in
    a file the sweep was structurally unable to reach.

---

## What I could not check

- **Whether gitleaks would actually catch a Reddit OAuth token in a YAML cassette.** Testing it
  means planting a fixture in the repository, which this review is read-only for. F7's fix does not
  depend on the answer.
- **Whether a real `/r/<sub>/new` page cassette exceeds 1024 kB.** No network and no real payload;
  F9 is stated as a risk with its mitigation, not as a measurement.
- **Whether PRAW 8 or prawcore emit warnings that `-W error` turns into failures.** Neither is
  imported anywhere yet, so there is nothing to run (F13).
- **`make check` was not run.** It writes `.build/` and a green stamp, which is a repository
  mutation. The stamp on disk is `.build/check-green.json`: tree a tree hash, commit `4238992`,
  2026-09-16T14:12:30Z — one commit behind `HEAD` (`7e8412c`), so the merge hook would currently
  refuse a fast-forward into `main` until the check is re-run. That is the gate working, not a
  finding.
- **Whether `docs/reference/reviews/2026-09-13-panel-ingest.md` § C is still the right list.** It is
  a 2026-09-13 record written before the cadence decision and before KI-018 and KI-023; I checked
  that it is *not* contradicted by them, but not that it is complete against everything decided
  since. F5's fix (a derived checklist) is also the place to resolve that.

---

## Verdict

**Ready after the listed fixes.** Confidence: **high**.

The harness is not the problem. Hooks, gates, ratchets, the document contracts and the pytest
configuration are consistent with the next work and block none of it; the one hook refusal I
triggered was a read-only false positive behaving exactly as designed. `make check` needs no change,
the `live` marker is properly registered and deselected, the cassette library is chosen and
installed, the import-linter contract already names the adapter, and the fixture schema the probe
must write is fully specified with its reader already built and tested.

What is not ready is the tranche B *specification*, in three specific places, and all three bite on
the probe day itself — a one-shot credentialed session whose cost of being redone is another
approved-access request:

1. **F2 (CRITICAL)** — nobody has decided whether probe fixtures are scrubbed, three documents give
   three answers, and nothing mechanical would catch an unscrubbed one entering permanent history.
2. **F4 (HIGH)** — the plan specifies a one-argument `probe` command that cannot produce five of the
   seventeen planned captures; the review that caught this recommended "Add" fifteen months of
   project-days ago and the recommendation was never carried into the plan.
3. **F5 (HIGH)** — there is no single list of what the probe day must bring back; it is spread
   across six documents, two of which are immutable records that cannot absorb the additions
   (P-18, KI-018, KI-023) already known to belong in it.

F1 and F3 are close behind: the live suite cannot pass even with credentials, and where cassettes
land decides whether recorded Reddit content travels to external reviewers at exactly the milestone
where the second external round is scheduled.

Recommended sequence before the first credentialed call: settle F2 and F4 as decisions with
`DECISIONS.md` entries; write the probe-day runbook section (F5) that absorbs F3, F8, F9 and F13 as
checklist rows; land the `vcr_config` fixture and the fixture-scrub gate (F2, F7) while there is
still nothing to scrub; then F1 and F6 as one small pytest-configuration change. F10, F11 and F12
are documentation corrections that can ride along with the next `docs-sweep`.
