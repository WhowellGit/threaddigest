# Thread Digest

A personal, rules-compliant Reddit reader that surfaces Premiere Pro quality signals.
Plan and design records live in `docs/`. Setup and operation are documented in `docs/runbook/RUNBOOK.md`.

Quickstart (developer):

    make setup      # installs uv if missing, creates the venv, copies .env.example
    make check      # lint, types, tests, ratchets
    uv run threaddigest --version
