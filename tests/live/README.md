# Live suite (opt-in, tranche B)

Tests here talk to Reddit with real credentials and carry the `live` marker. They never run under
`make check` (the marker is deselected and the network is blocked); `make test-live` is the one
way to run them: it loads `.env`, selects the marker, and allows Reddit's hosts only. The
`conftest.py` beside this file keeps the three `INSIGHTMINER_REDDIT_*` variables that the root
fixture otherwise strips, and still isolates the data directory. Written on the probe day
(runbook § 9); empty until then.
