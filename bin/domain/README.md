# Domain-specific bin helpers

Top-level `bin/` keeps the everyday commands: `start.sh`, `stop.sh`, `deploy.sh`.

This directory holds less obvious helpers:

| Script | Why it exists |
|--------|----------------|
| `deploy-source.sh` | Bare-metal venv + systemd from a source checkout (uncommon vs Docker install) |
| `use-staging-env.sh` | Swap `.env` to Testwork staging without hand-editing secrets |
| `test-install-bundle.sh` | CI check that `install/` submodule is a complete Docker runtime |
| `lib/docker.sh` | Shared Docker CLI checks for `../deploy.sh` |
