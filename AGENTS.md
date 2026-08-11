# The Network — Agent Instructions

Discord bot that relays followed announcement messages through a central server. Partner servers publish to feed channels via Channel Follow; the bot transforms and republishes to network announcement channels.

## Stack

- Python 3.12, discord.py 2.x (async)
- SQLite via aiosqlite + migration runner
- pydantic-settings for `.env` configuration
- Structured JSON logging

## Layout

```
bot/
  adapters/      Discord command/event boundary and error reporting
  core/          Reusable workhorse APIs, persistence, and domain types
  channels/      Server layout, channel resolution, sticky reconciliation, channel templates
  widgets/       Recipes, views, presenters, modals, and interaction templates
  smoke/         Live Discord behavioral probes
tests/           pytest + pytest-asyncio (mock Discord objects)
deploy/          Production deploy docs and scripts
doc/             Design spec and planning (reference only)
```

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m bot.main          # run bot
./test --dev                # ruff + mypy + pytest (default)
./test --full               # dev gate + live Testwork smoke (pre-deploy)
ruff check .                # lint only
mypy bot                    # type check only
pytest                      # tests only
```

See `docs/smoke-testing.md` for staging guild setup and smoke pacing.

## Conventions

- Use `from __future__ import annotations` in all modules.
- Keep orchestration in widget recipes and Discord registration in adapters.
- Route layout, channel resolution, permissions, and sticky reconciliation through their public APIs.
- Settings live in `bot/config.py` — add new env vars there with pydantic Field aliases.
- Database changes need a migration in `bot/db/migrations.py`.
- Channel-installed copy lives under `bot/channels/templates/`; interaction copy lives under
  `bot/widgets/templates/`. Avoid hardcoding user-facing strings in Python.
- Match existing test style: MagicMock with `spec=discord.*`, AsyncMock for coroutines.
- Minimize diff scope; do not edit unrelated code or add docs unless asked.
- `.cursor/` is gitignored; this file is the shared agent context for the repo.

## Do not touch

- `work/`, `.coordinator-cache/` — coordinator/foundry tooling
- `publish/` — generated Docker bundle (gitignored)
- `.env` — secrets
