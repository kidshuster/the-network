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
  cogs/       Slash commands and event handlers
  services/   Business logic (relay, provisioning, guild init, etc.)
  domain/     Dataclasses and domain types
  db/         Models, repositories, migrations
  ui/         Discord views, buttons, modals
  messages/   YAML-driven message templates
tests/        pytest + pytest-asyncio (mock Discord objects)
deploy/       Production deploy docs and scripts
doc/          Design spec and planning (reference only)
```

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m bot.main          # run bot
ruff check .                # lint
mypy bot                    # type check
pytest                      # tests
```

## Conventions

- Use `from __future__ import annotations` in all modules.
- Keep Discord I/O in cogs/ui; put logic in services; keep pure types in domain.
- Settings live in `bot/config.py` — add new env vars there with pydantic Field aliases.
- Database changes need a migration in `bot/db/migrations.py`.
- Message copy lives in YAML under `bot/messages/` — avoid hardcoding user-facing strings in Python.
- Match existing test style: MagicMock with `spec=discord.*`, AsyncMock for coroutines.
- Minimize diff scope; do not edit unrelated code or add docs unless asked.
- `.cursor/` is gitignored; this file is the shared agent context for the repo.

## Do not touch

- `work/`, `.coordinator-cache/` — coordinator/foundry tooling
- `publish/` — generated Docker bundle (gitignored)
- `.env` — secrets
