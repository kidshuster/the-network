# Domain-specific bin helpers

Top-level `bin/` keeps the everyday commands: `start.sh`, `stop.sh`, `deploy.sh`.

This directory holds less obvious helpers:

| Script | Why it exists |
|--------|----------------|
| `deploy-source.sh` | Bare-metal venv + systemd from a source checkout (uncommon vs Docker install) |
| `check-no-guild-secrets.sh` | Fail if tracked env samples embed guild IDs or enable test mode |
| `test-install-scripts.sh` | Validate the-network-install start/stop/update contract |
| `test-install-bundle.sh` | Compatibility wrapper around `test-install-scripts.sh` |
| `use-staging-env.sh` | Swap `.env` to Testwork staging without hand-editing secrets |
| `lib/docker.sh` | Shared Docker CLI checks for `../deploy.sh` |
