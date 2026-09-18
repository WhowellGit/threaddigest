---
purpose: The record of the code panel's seat B fix round — the deployment and data-safety findings, each hardened, with what was watched red first and what is deliberately left open.
update-policy: append-only
mirrors: []
verified-at: M1b
---
# Panel fix round B: deployment and data safety (2026-09-17)

Scope `4f03faf..9328e85` on branch `panel-fix-b`. Seven commits, one per finding plus the cut
list. Source: `docs/reference/reviews/2026-09-17-code-panel-seat-B.md` findings B1–B4, B6, B7
and § 4; the round's summary record is `2026-09-17-code-panel-since-baseline.md`. B5 (the
permalink join in `db/repo.py`) is not in this round: another agent holds that file, and it
lands with the digest fixes.

Reviewed surface: `tests/gates/test_data_dir_isolation.py` (commit `c225750`), which is why
this record exists. In-family review by the session that made the change under a bounded
brief, tests before the code, each behaviour watched red before the fix existed; not an
independent seat, which is this round's weakness.

## What each fix turned on, and what was watched red

**B1, the entry point (KI-045, P0).** `python -m threaddigest` did not exist, so both launchd
jobs exited 1 before doing anything and the hourly `doctor` — the control that would have
noticed a collector which had stopped — died on the same line. The red line was the new test
against the unfixed tree: `No module named threaddigest.__main__; 'threaddigest' is a package
and cannot be directly executed`. The finding's real lesson is the fixture: the deployment
gate writes a stub `threaddigest/__main__.py` onto `PYTHONPATH`, so thirty passing tests
proved the wrapper's plumbing and *manufactured the entry point production lacked*. The new
module runs the real interpreter against the real package, outside that fixture; the macOS
module's docstring now says what it cannot prove. A fixture that supplies the thing under test
is the pattern to look for elsewhere.

**B2, credential material on every run row (KI-046).** `non_secret_settings` is sound for what
it claims — it excludes every field annotated `SecretStr`, structurally — but the claim is
narrower than the rule it was read as keeping. Two of the four credential fields were `str`.
The positive control was the digest page rendering
`reddit_client_id: "SENTINEL-CLIENT-ID-Qx41" → "ROTATED-SENTINEL-CLIENT-ID-Qx41"`, which is the
panel's own reproduction reached through the page. Both fields became `SecretStr` rather than
gaining a second, hand-kept list of credential names, so the mechanism that was already right
now covers them. The page test rotates *every* credential between the two runs deliberately:
the digest prints only the keys that changed, so a test whose credentials never change would
have passed before the fix — it did, on the first attempt, which is why the test asserts first
that the diff was reached at all.

**B3, a saved capture outside the data directory (KI-047).** `probe --save-fixture` joined the
operator's name onto the probe directory, and a `pathlib` join lets a traversing or absolute
right operand win. Watched red on the unfixed code, in a temp tree: a traversing name wrote
`…/escape/pwned.json` and an absolute name wrote `…/outside/absolute.json`, both with
`inside data_dir: False`. Under the real default directory the traversal reaches
`tests/fixtures/json/captures/`, the committed fixture set, which is the one step
`promotion_command` exists to keep deliberate. Two checks, not one: the name must be a single
safe segment, and the resolved file's parent must be the literal `<resolved data_dir>/probe`.
The second is not decoration — it is what catches a probe directory symlinked out of the data
tree, a shape no check of the name can see, and it has its own test. G19 was **widened** rather
than joined by a new guard, so the guard count did not move.

**B4, a fabricated corpus in the real data directory (KI-048).** `make fixture` wrote
`data/demo.json` beside the operator's database and `make run` depends on `fixture`. The
control was the pre-fix generator, taken verbatim from `HEAD` and pointed at a temp tree shaped
like the repository: a 545,695-byte corpus written next to a `threaddigest.db`. The refusal is
keyed on the path, not on pytest, so it holds in a plain shell. **The tests assert it against a
stand-in data directory, never the real one**: if this guard regresses, the test that notices
must not be the one that writes a fabricated corpus into the operator's data tree. The real
path is covered by a pure predicate, which cannot write anything. The two D-10 guards held
throughout and always would have: they refuse the fake gateway against the default data
directory, and a JSON corpus is not a database — a guard being green is not evidence about a
rule it does not cover.

**B6, the log directory (KI-049).** `LOG_DIR` was set forty lines before `.env` was parsed.
The ordering was the whole bug, and it was not an accident: the wrapper logs how many `.env`
keys it exported, so the log file had to exist before the parse, while the parse decides where
the log file lives. `load_env` moved into `common.sh` and stopped logging — it records a count
the caller reports once the file is open — and the directory comes from one function,
`data_dir_of`, read by the wrapper and by the installer. launchd's own
`StandardOutPath`/`StandardErrorPath` are a different case, argued rather than assumed: launchd
opens those two files before the wrapper starts, so they cannot be resolved at run time. They
are rendered at install time from the same function, through a second placeholder, and the
consequence is stated where an operator will meet it — **after moving the data directory, run
`install.sh` again**. The wrapper also logs the directory it resolved, on the log's own first
lines, so a stale rendering is visible rather than inferred.

**B7, the content-security policy (KI-050).** `default-src` is the fallback for *fetch*
directives only; `frame-ancestors`, `base-uri`, `form-action` and `object-src` do not fall back
to it, so every page was frameable by any origin. The header test could not have caught it: it
compared each response's header against the constant the code sends, which is a tautology about
a directive the constant does not have. The new test states the five directives by name and
value. It also refuses a duplicate: in CSP the first occurrence of a directive wins and a later
one is ignored, so a repeat is a quiet way to believe a policy that is not in force. Cost today
is near zero — seat B proved by hand-made ASGI scopes that no state-changing route exists — and
the reason to do it now is that M2's "Run now" and "Cancel" land inside this same header. The
middleware docstring stops calling itself the whole perimeter and names what is still missing.

**The cut list (§ 4).** One of the three was load-bearing: `cli`, `services.migrate` and
`services.doctor` each built the collector lock's path, and a `doctor` probing a different path
than the collector takes would report the lock free during a run. One definition now, in the
module that owns the lock, with an AST scan as the enforcer — a string literal naming the lock
file in *code* outside that module is red, while prose may still describe the path — plus a
positive control that plants a second spelling and checks that a docstring mention is not one.
`_FROM_ENVIRONMENT` was declared twice with the same paragraph of explanation and is now one
read-only constant in `settings.py`. `adapters/notify.py` justified its delivery bookkeeping by
a notify sub-command that was never built: the bookkeeping stays, since the tests read it, and
the sentence now says what actually reads it.

## Claims this round makes, and what verifies each

| Claim | Verified by |
|---|---|
| The scheduled command line starts | `tests/deploy/test_entry_point.py::test_python_m_threaddigest_starts_and_prints_the_version`, and `uv run python -m threaddigest --version` from a plain shell |
| No credential reaches a run row, the fingerprint's input, or the digest | `tests/unit/test_settings.py::test_no_credential_reaches_the_stored_settings_or_the_fingerprint_input`, `tests/web/test_report_page_settings.py::test_no_credential_appears_anywhere_on_the_digest` |
| A supplied name cannot steer a capture out of the probe directory | `tests/gates/test_data_dir_isolation.py::test_probe_save_refuses_a_name_that_is_not_one_safe_segment` and the three cases beside it |
| The generated corpus never lands in the real data directory | `tests/tools/test_make_demo_fixture.py::test_the_generator_refuses_to_write_into_the_default_data_directory`, `::test_the_real_data_directory_is_refused_by_the_predicate_itself` |
| The scheduled logs follow a relocated data directory | `tests/deploy/test_launchd.py::test_the_job_log_follows_a_relocated_data_directory_from_the_env_file`, `::test_install_renders_the_log_paths_from_the_env_files_data_directory` |
| The policy carries every directive `default-src` does not cover | `tests/web/test_app.py::test_the_policy_carries_every_directive_default_src_does_not_cover` |
| The lock has one spelling | `tests/services/test_lock.py::test_only_services_lock_names_the_lock_file_in_code` and its control |

## Deviations from the brief, named rather than papered over

1. **The error class for B3 is `UnsafeFixtureTargetError`, not the brief's `ConfigError`.**
   `ConfigError` lives in `cli`, and `services/` may not import `cli` (the layers contract). The
   service raises its own error and `cli` translates it into `ConfigError`, which is the seam
   `FixtureExistsError` already took, so the operator still sees a configuration error and
   exits 78.
2. **B3's second guard is confinement to the probe directory, tested through a symlink.** A
   check written as "the resolved target is under the resolved probe directory" is vacuous when
   the probe directory is itself the symlink, because both sides resolve to the same place. The
   comparison is against the literal `<resolved data_dir>/probe`, which is what makes the second
   check bite, and the test plants the symlink.
3. **B6 took the plists' half rather than the README's.** The brief allowed either. Rendering
   `__LOG_DIR__` at install time needed `load_env` moved into `common.sh` so the wrapper and the
   installer read `.env` the same way; the README states the one limitation that remains (a
   rendering is stale after a later move).
4. **`tests/conftest.py` still says `make fixture` writes `data/demo.json`.** Another round of
   this panel holds that file, so the stale sentence is left for it; the statement is wrong in
   one docstring only, and the target, the generator, the runbook and the tool's own docstring
   all say `.build/`.
5. **The status page is not updated.** The main session lands this branch and owns
   `docs/recent/STATUS.md`'s milestone stamp.
