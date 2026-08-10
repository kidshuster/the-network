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
  cogs/          Slash commands and event handlers
  layout/        YAML layout compile/apply (hub + client)
  permissions/   Discord permission I/O + probe helpers
  hub/           Guild/hub lifecycle and hub-only features
  clients/       Client lifecycle, profiles, subscriptions
  networks/      Network CRUD, routing, role validation
  relay/         Announcement relay pipeline
  stickies/      Sticky message sync helpers
  onboarding/    Join-request / accept flow
  discord_util/  Low-level Discord helpers (cleanup, errors, steps)
  media/         Emoji + image helpers
  parsers/       Profile and date parsers
  integrations/  Third-party integrations (e.g. Top.gg)
  domain/        Dataclasses and domain types
  db/            Models, repositories, migrations
  ui/            Discord views, buttons, modals
  messages/      YAML-driven message templates
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
- Keep Discord I/O in cogs/ui; put logic in domain packages (`hub/`, `clients/`, `relay/`, etc.); keep pure types in domain.
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
