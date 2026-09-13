# launchd deployment (macOS, M0–M3)

Two user agents run Insight Miner on this Mac while it is the production host
(`docs/PLAN.md` § Deployment path, § Resilience to outages). Both go through one wrapper,
`run.sh`, which chooses the interpreter, keeps the Mac awake, logs, and turns exit codes into
notifications.

| Agent (Label) | When | Command | Log |
|---|---|---|---|
| `com.wesmax.insightminer.run` | 06:30, 12:30, 18:30 daily | `.venv/bin/python -m insightminer run` | `data/logs/launchd-run.log` |
| `com.wesmax.insightminer.doctor` | every hour at :15 | `.venv/bin/python -m insightminer doctor --alert-if-stale 36h` | `data/logs/launchd-doctor.log` |

Three run intervals, not one, is the outage design: a run that cannot reach Reddit exits
`network` and the later intervals retry it the same day; a successful run makes the later ones
near no-ops because the sweep is idempotent. The hourly `doctor` is the local dead-man's switch:
it notices a run that never happened at all.

## Files

| File | Purpose |
|---|---|
| `run.sh` | The wrapper launchd runs (`run.sh run` or `run.sh doctor`). Details below. |
| `common.sh` | Helpers shared by the three scripts: repo-root resolution and the TCC check. Sourced, never executed. |
| `com.wesmax.insightminer.run.plist`, `com.wesmax.insightminer.doctor.plist` | Templates. `__ROOT__` stands for the repository's absolute path; `install.sh` substitutes it. launchd never reads these copies. |
| `install.sh` | Renders, lints, writes and bootstraps both agents. `--dry-run` prints every step and changes nothing. |
| `uninstall.sh` | Unloads both agents and removes their rendered plists. Logs and data are untouched. `--dry-run` supported. |

Tests: `tests/deploy/test_launchd.py` (`uv run pytest tests/deploy`). They lint the rendered
plists with `plutil`, parse the scripts with `bash -n`, and run `run.sh` against a fake repo
with `insightminer`, `osascript`, `caffeinate` and `launchctl` replaced by recorders.

## Install

Prerequisites: the repo lives outside the TCC-protected folders (see below), `make setup` has
created `.venv`, and `.env` holds the Reddit credentials.

```sh
deploy/launchd/install.sh --dry-run   # shows the substituted paths and every launchctl step
deploy/launchd/install.sh             # writes ~/Library/LaunchAgents/com.wesmax.insightminer.*.plist and bootstraps them
```

`install.sh` is idempotent: it boots out any loaded copy before bootstrapping the new one, so
run it again after editing a plist template. Nothing runs at install time (`RunAtLoad` is
false); the first run is the next calendar entry.

## Verify

```sh
launchctl print gui/$UID/com.wesmax.insightminer.run      # "state = waiting", program, run interval
launchctl print gui/$UID/com.wesmax.insightminer.doctor
launchctl kickstart gui/$UID/com.wesmax.insightminer.run  # trigger a run now, same environment launchd uses
tail -f data/logs/launchd-run.log
```

After a kickstart, `launchctl print` shows `last exit code = N` and the log ends with a
timestamped `[run] exit N` line followed by the mapped action. `launchctl print` output is
also where a plist mistake surfaces: a job that never gets a `runs` count or shows
`last exit code = 78` before `run.sh` logged anything is refusing to start (see
`data/logs/launchd-run.stderr.log`, where the wrapper's pre-log messages go).

### Missed-interval catch-up after sleep

`StartCalendarInterval` jobs that fall due while the Mac is asleep run once on wake (several
missed entries coalesce into one run; nothing is lost, only delayed, because the collector's
queue and watermark are idempotent). To see it happen:

1. Note the next interval (say 12:30) and put the Mac to sleep (or close the lid) before it.
2. Wake it after 12:30. Within a few seconds `data/logs/launchd-run.log` gains a
   `[run] start:` line stamped with the wake time, not 12:30, and `launchctl print` shows the
   new `last exit code`.
3. `log show --last 1h --predicate 'process == "launchd" AND eventMessage CONTAINS "insightminer"'`
   shows launchd's own record of the spawn, if you want the system's view.

If the Mac was asleep for a whole interval and nothing appears on wake, the job is not
loaded (`launchctl print` says "Could not find service") or the repo is in a TCC-protected
folder (below). A run that is *in progress* when the lid closes is protected differently:
`run.sh` wraps the job in `caffeinate -i`, so idle sleep is held off until the run exits (the
display still sleeps).

## Notifications

`run.sh` maps the CLI's exit codes to actions after every job:

| Exit | Meaning | Wrapper action |
|---|---|---|
| 0 | ok | log only |
| 75 | another Insight Miner process holds the lock | log only |
| 130 | cancelled by the operator (UI or Ctrl-C) | log only |
| 4 | rate limited | log "will retry at the next interval" |
| 5 | network unavailable | log "will retry at the next interval" |
| 1 | failed | macOS notification, subtitle `failed` |
| 3 | partial (warnings recorded) | macOS notification, subtitle `partial` |
| 78 | configuration or credentials refused | macOS notification, subtitle `config error` |
| other | unexpected | macOS notification, subtitle `unexpected exit N` |

A notification appears in Notification Center as a banner titled **Insight Miner** with the
status as subtitle and a body such as `Scheduled run failed (exit 1). Details:
http://127.0.0.1:8765/runs` (the `doctor` job points at `/system`). Set `INSIGHTMINER_UI_URL`
in `.env` if the UI is served elsewhere. Notifications are best-effort: if `osascript` fails
the log says so and the job's exit code is unchanged. The first notification from a new
script may prompt macOS to allow notifications from "Script Editor" or "osascript"; allow it,
or the banners are silently dropped. The UI status pill computed from the `runs` table is the
canonical alert; the notification is the nudge.

The wrapper exits with the job's own code, so `launchctl print` always shows the real status;
launchd itself takes no action on it (there is no `KeepAlive`), the calendar does.

## Interpreter, environment, .env

`run.sh` runs `$ROOT/.venv/bin/python` by absolute path and refuses to start if it is missing
(`make setup` creates it). It never runs `python3`: stock macOS resolves that to 3.9, and
launchd's default `PATH` is `/usr/bin:/bin:/usr/sbin:/sbin`. The plists set `PATH` to the
virtualenv, Homebrew, then the system directories, and `LANG=en_US.UTF-8` because launchd
sets no locale.

`INSIGHTMINER_*` lines in `$ROOT/.env` are exported to the job. The file is parsed (keys
validated as identifiers, one pair of surrounding quotes stripped), never sourced, and the
log records only how many keys were loaded. Nothing in `data/logs/` ever contains a value.

## The TCC note: where the repo may live

launchd agents are denied access to `~/Desktop`, `~/Documents`, `~/Downloads` and every
volume under `/Volumes` by macOS privacy protection (TCC), and the denial is silent: the job
starts, reads nothing, and exits as if the folders were empty. The earlier project lost runs
to this before the cause was found. Both `run.sh` and `install.sh` therefore refuse (exit 78,
with the reason on stderr) when the repository resolves to a path inside one of those
folders. The supported location is `~/repos/insightminer`; anywhere else outside those four
trees also works. `insightminer doctor` performs the same check from inside the application.

## Uninstall

```sh
deploy/launchd/uninstall.sh --dry-run
deploy/launchd/uninstall.sh
```
