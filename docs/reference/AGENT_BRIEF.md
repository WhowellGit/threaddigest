# Sub-agent brief template

> The brief is the routing surface that actually fires: the earlier project's transcripts show its reference corpus was consumed mainly inside sub-agent runs, and its memories reached agents only when pasted into briefs. Every brief written for this project carries these parts. Prune-stale; revise in place.

```
PURPOSE   one sentence: what the agent produces and for whom.
TIER      the model tier and why (judgement → Opus; well-specified mechanical → Sonnet).
READ FIRST  the routing rows this task touches, from CLAUDE.md § Routing and docs/INDEX.md § Start here,
          plus the decision entries that bind the task.
RULES THAT BITE  the three to six working-agreement rules most likely to be violated by this task,
          quoted, with their enforcer named.
SCOPE     the files the agent may edit; everything else is read-only. Worktree isolation when in parallel.
CONTRACT  what the agent must return (structured fields, short), and where it writes findings
          (outside the repo unless the task says otherwise).
VERIFY    the exact commands to run before returning (the capped make check; the positive controls).
DON'TS    no attribution trailers; no model names in documents; no identifiers from other systems;
          never weaken a test; never touch .ratchets/ or the hooks; never run make ratchet-bump
          unless told; cap every long command (perl -e 'alarm N; exec @ARGV' -- ...).
RETURN    a summary under N words; details go in the commit body or the findings file.
```
