# The one-session-per-checkout guard: build and refute pass (2026-09-16)

## Claim under test

"The fifth hook makes the one-live-session-per-checkout practice mechanical instead of written.
Its controls drive the script the way the agent runtime does, and each one plants a bad state the
guard must see: a second live session, a session that died without releasing the lock, a repeated
intrusion, an internal error. The remedy the block message names actually works, because a git
worktree is its own checkout with its own lock. The registration gate was widened for a hook
registered under two events without any existing assertion losing strength. No false positive is
possible for a sub-agent, for a directory outside a git repository, or for a session that ends
normally."

Branch `one-session-guard`, one commit, built in a git worktree of the repository and rebased onto
`main` after the project rename. The branch stays unmerged on purpose: the settings gate is red
until a human registers the new script, which is the gate working as designed. The register row
naming this build commit is not on the branch: the registration script appends it after its own
final rebase, because every rebase renames the commit such a row would pin, and a stale hash turns
the register gate red.

## Method

Read first, in the order the routing rows give: `CLAUDE.md` whole; `docs/recent/STATUS.md`;
`docs/THREADDIGEST_HARNESS.md`; `docs/runbook/GUARDS.md` (the column layout and the G23, G49 and
G56 rows); `docs/PLAN.md` § Robustness → "Guard design rules"; `.claude/skills/harden/SKILL.md`;
both existing log-first hook scripts; `tests/gates/test_hooks.py` whole; the decisions log's
2026-09-14 incident row and its 2026-09-16 rulings; `docs/reference/reviews/REGISTER.md`.

The script was then driven by hand outside the repository (a throwaway checkout, JSON payloads on
stdin) before a single test was written, so that the first evidence about its behaviour came from
running it rather than from reading it.

## What was built

- `tools/hooks/one_session_per_checkout.sh` and its committed `.mode` file, holding `log`.
  PreToolUse on `Edit|Write|MultiEdit|Bash` and SessionEnd, one script branching on
  `hook_event_name`. The lock is `.build/hooks/session.lock` inside the checkout that
  `git rev-parse --show-toplevel` names from the payload's `cwd`.
- Ten controls in `tests/gates/test_hooks.py`, four of them carrying `@pytest.mark.gate("G57")`.
- The widened registration gate, a `docs/runbook/GUARDS.md` row, a working-agreement rule row,
  the swept mirrors, and a Terminal script for the human who registers the hook.

## How the controls drive the script

Every control runs the real script through the existing `run_hook` helper: the executable, a JSON
payload on stdin, `CLAUDE_PROJECT_DIR` and the payload's `cwd` pointing at a throwaway git
checkout built by `make_repo_on_branch` and committed by the helper the G56 controls use. Nothing
is stubbed, and the exit code is the decision, exactly as the runtime reads it.

The bad state is planted in the population the guard scans, not beside it:

| Control | The bad state it plants |
|---|---|
| `test_one_session_per_checkout_logs_a_second_session_and_blocks_it_in_block_mode` | a second session id arriving while the first holds a live lock; asserted logged-and-allowed in `log` mode, refused in `block` mode with the holder and the remedy in the message |
| `test_one_session_per_checkout_lets_a_worktree_hold_its_own_lock` | the remedy itself, run in `block` mode: a real `git worktree add`, then the second session working there. A false positive would be red |
| `test_one_session_per_checkout_takes_over_a_stale_lock` | a lock last seen past the liveness window (a dead session), then one inside it |
| `test_one_session_per_checkout_releases_the_lock_at_session_end` | another session's SessionEnd against a held lock, then the holder's own |
| `test_one_session_per_checkout_logs_a_repeated_intrusion_once` | the same intrusion three times, then a different holder |
| `test_one_session_per_checkout_internal_errors_follow_the_mode` | malformed JSON and a payload with no session id, in both modes |
| `test_one_session_per_checkout_is_quiet_outside_a_git_repository` | a `cwd` outside any repository, in `block` mode |
| `test_one_session_per_checkout_takes_the_lock_and_refreshes_it` | the holder's own later calls, including a Bash call such as a sub-agent makes |

## What was refuted, and how

1. **"A new matcher entry is the way to register it."** Refuted by running the registration edit
   against a copy of the settings: the tools this hook needs are the same four the
   enforcement-files hook already matches, so a second entry would have two `PreToolUse` entries
   with the same matcher — which the gate refuses, and rightly. The registration script therefore
   adds the hook to the existing entry, and the gate was widened to compare a matcher as a set of
   tool names and to allow an entry to hold several hooks.
2. **"Widening the gate weakens it."** Refuted by listing the old assertions and checking each
   against the new test: per-event timeouts, `$CLAUDE_PROJECT_DIR` in every command, the file on
   disk, the registered set equal to the on-disk set, no two entries of an event sharing a
   matcher. All are kept; three are stronger (the no-shared-matcher rule now applies to every
   event, not only `PreToolUse`; an entry registering nothing is refused; the executable check
   covers every event). Proven both ways: the gate is red on the tree as it stands, naming
   `one_session_per_checkout.sh` as a script nothing registers, and green when the two functions
   are run against a copy of the settings patched by the registration script's own block.
3. **"The lock will fire on sub-agents."** Refuted by the payload: a sub-agent carries the
   parent's session id, so it takes the refresh path. Asserted, with a Bash call, in the first
   control.
4. **"A crashed session locks the checkout for ever."** Refuted by the liveness window, with a
   control that plants a lock older than it. The window is stated once in the script and quoted in
   the ledger row, and the control reads the same number from the script's text, so the two cannot
   drift apart.
5. **"The hook is too slow for a hook on every Bash call."** Refuted by measurement: ten calls
   end to end in about a third of a second on this machine, against a five-second timeout.
6. **"It is a guard that can never go red."** Not refuted by argument but by construction: four
   controls carry the `G57` marker and each asserts an exit code of 2 or a ledger line for a
   planted bad state. The honest limit is the same one G23 carries: a hook runs only in a session
   started in the repository root, and it is mistake prevention for the agent, not a boundary
   against a deliberate bypass.

## The honest limits

- The guard cannot see a session that never makes a tool call, nor a human typing `git commit` in
  a terminal beside the agent; the practice on the status page still carries those.
- `log` mode means the guard currently records and allows. It is a hypothesis until its ledger is
  read on 2026-09-28 with G49's and G56's, and the flip to `block` is a reviewed commit.
- Registration is a human edit. Until it happens the script has never run, which is exactly what
  the red settings test says.
