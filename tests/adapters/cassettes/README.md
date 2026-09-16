# Cassettes

Recorded HTTP exchanges for the adapter tests (pytest-recording), made only against the personal restricted test subreddit on the probe day and after. This directory is excluded from the external review packet by prefix, like `tests/fixtures/`, because a cassette holds recorded Reddit content; the adapter suite is therefore not runnable from a packet (decided 2026-09-16, runbook § 7 and § 9). A `vcr_config` fixture filters the `Authorization` header and the OAuth token before anything is written here.
