# The Network

Discord bot that relays partner announcement messages through a central hub. Partner
servers publish via Channel Follow; the bot transforms (including optional Discord
timecodes) and republishes to network announcement channels for downstream followers.

## Architecture

```text
Discord → bot/app → bot/features → bot/core
                  ↘─────────────→ bot/core
```

| Layer | Owns |
|-------|------|
| **`bot/app`** | Runtime only: bot lifecycle, recipe registry/execution, Discord trigger dispatch, generic presenters/errors. Shallow adapters: validate → run recipe → present. |
| **`bot/features`** | The Network processes: `@recipe` definitions, layout/permission YAML, resource IDs, stickies, widgets/templates, changelog. |
| **`bot/core`** | Reusable workhorses (DB, permissions, channel/role ops, media, parsers). No hub-specific vocabulary. |

Optional `bot/contracts/` holds immutable recipe/widget metadata when needed to break import cycles.

Stack: Python 3.12+, discord.py 2.x, SQLite, YAML-driven hub layout, structured logging.

## Discord Developer Portal setup

Before inviting, configure **Installation** (required for modern Discord apps):

1. [Developer Portal](https://discord.com/developers/applications) → your app → **Installation**
2. Under **Installation Contexts**, enable **Guild Install**
3. Under **Default Install Settings → Guild Install**, add scopes:
   - `bot` (required — adds the bot user to your server)
   - `applications.commands` (required — enables slash commands)
4. Select permissions (at minimum: **Send Messages**, **Embed Links**)
5. **Save Changes**

If Guild Install only has `applications.commands`, the OAuth flow completes but the bot
**never joins** the server.

### Invite link

After saving Installation settings, use the **Discord Provided Link** from the portal, or:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&permissions=536871936&scope=bot+applications.commands
```

You must have **Manage Server** on the target guild. After the bot joins, restart the
process so slash commands sync.

## Setup (source / development)

1. Create a Discord application and bot in the [Developer Portal](https://discord.com/developers/applications).
2. Enable **Message Content Intent** and **Server Members Intent** as required.
3. Invite the bot to your **central (hub) guild**.
4. Copy `.env.example` to `.env` and fill in:

   | Variable | Required | Description |
   |----------|----------|-------------|
   | `DISCORD_TOKEN` | Yes | Bot token |
   | `GUILD_ID` | Yes | Central hub server ID |
   | `DISCORD_APPLICATION_ID` | No | Application ID (reference) |
   | `DISCORD_PUBLIC_KEY` | No | For HTTP interactions only |
   | `DATABASE_PATH` | No | Default `./data/relay.db` |

5. Install and run:

```bash
git submodule update --init install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m bot.main
```

Or:

```bash
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
./bin/start.sh
```

Bare-metal systemd (source tree): `./bin/domain/deploy-source.sh` (uncommon; prefer Docker).

6. In Discord, run `/status` in the hub guild. On a new hub, run `/server init` once.

## Development

```bash
git submodule update --init install
./test --dev                # ruff + mypy + pytest + mock smoke
./test --full               # also run live Testwork smoke
ruff check .
mypy bot tests/core
pytest tests/unit
./bin/domain/test-install-scripts.sh
```

Everyday scripts live in `bin/` (`start`, `stop`, `restart`, `deploy`). Less common helpers
are under `bin/domain/`. Testwork guild IDs/tokens stay in gitignored `.env` / `.env.staging`.

## Install / Docker (production)

Runtime install content lives in the **`install/`** git submodule
([the-network-install](https://github.com/kidshuster/the-network-install)). Clone that
repo alone on any host — no application source required.

```bash
git clone git@github.com:kidshuster/the-network-install.git
cd the-network-install
cp .env.example .env   # DISCORD_TOKEN, GUILD_ID
chmod +x scripts/*.sh
./scripts/enable.sh
```

Images support **amd64** and **arm64** (Pi 4/5 with 64-bit Raspberry Pi OS).

### Deploy a release (from this source repo)

```bash
docker login ghcr.io
./bin/deploy.sh
```

This gates on tests, builds/pushes the multi-arch image to GHCR, and updates/pushes the
`install/` submodule. Options: `--via-ci`, `--skip-image`, `--skip-install`.

On the live host, pull and swap with `./scripts/update.sh` in the-network-install.

### Local image smoke

```bash
docker build -t the-network .
docker run --env-file .env -v "$(pwd)/data:/app/data" --restart unless-stopped -d the-network
```

## Local agent workspace

Design archives, Cursor rules, and agent notes live under untracked `cursor/`
(symlinked as `.cursor` for IDE discovery). They are not part of the published repo.

Architecture contract and active correction plan (agents):

- `cursor/CURSOR_ARCHITECTURE_GOALS.md`
- `cursor/docs/refactor-correction-plan.md`
- summary via `AGENTS.md` (symlink into `cursor/` when present)
