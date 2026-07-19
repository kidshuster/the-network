# The Network

Discord bot that relays followed announcement messages through a central server. Partner servers publish to feed channels via Channel Follow; the bot transforms and republishes to network announcement channels for downstream followers.

## Phase 1 (current)

- Python 3.12 + discord.py 2.x
- Environment-based configuration (`.env`)
- SQLite with migration runner
- Structured JSON logging
- Guild-scoped `/status` slash command

## Discord Developer Portal setup

Before inviting, configure **Installation** (required for modern Discord apps):

1. [Developer Portal](https://discord.com/developers/applications) → **The Network** → **Installation**
2. Under **Installation Contexts**, enable **Guild Install**
3. Under **Default Install Settings → Guild Install**, add scopes:
   - `bot` (required — adds the bot user to your server)
   - `applications.commands` (required — enables slash commands)
4. Select permissions (at minimum: **Send Messages**, **Embed Links**; add more before relay phases)
5. **Save Changes**

If Guild Install only has `applications.commands`, the OAuth flow completes but the bot **never joins** the server.

### Invite link

After saving Installation settings, use the **Discord Provided Link** from the portal, or:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&permissions=536871936&scope=bot+applications.commands
```

You must have **Manage Server** on the target guild. After the bot joins, restart the process so `/status` syncs.

## Setup

1. Create a Discord application and bot in the [Developer Portal](https://discord.com/developers/applications).
2. Enable **Message Content Intent** and **Server Members Intent** if required for your deployment.
3. Invite the bot to your **central guild** with permissions to manage slash commands and (later) send/publish messages.
4. Copy `.env.example` to `.env` and fill in:

   | Variable | Required | Description |
   |----------|----------|-------------|
   | `DISCORD_TOKEN` | Yes | Bot token |
   | `GUILD_ID` | Yes | Central server ID |
   | `DISCORD_APPLICATION_ID` | No | Application ID (reference) |
   | `DISCORD_PUBLIC_KEY` | No | For HTTP interactions only |
   | `DATABASE_PATH` | No | Default `./data/relay.db` |

5. Install and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m bot.main
```

Or bare metal:

```bash
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
./bin/start.sh
```

Systemd deploy: `./deploy/deploy.sh` (see [`deploy/TOPGG.md`](deploy/TOPGG.md)).

6. In Discord, run `/status` in the configured guild to verify connectivity.

## Development

```bash
ruff check .
mypy bot
pytest
```

## Docker

```bash
./bin/package.sh
docker compose up -d
docker compose logs -f
```

Or manually:

```bash
docker build -t the-network .
docker run --env-file .env -v "$(pwd)/data:/app/data" --restart unless-stopped -d the-network
```

## Deploy & top.gg

See [`deploy/TOPGG.md`](deploy/TOPGG.md) for production hosting and listing on [top.gg](https://top.gg). Listing copy is in [`deploy/topgg-listing.md`](deploy/topgg-listing.md).

Set `TOPGG_TOKEN` in `.env` after creating your bot page so server count stays updated.

## GitHub

GitHub stores code and runs CI — it does **not** host the live bot. See [`deploy/GITHUB.md`](deploy/GITHUB.md) for the repo workflow.

## Raspberry Pi (Docker from GitHub Releases)

Pre-built multi-arch images (including **arm64** for Pi 4/5) are published on each release:

```bash
export GITHUB_USER=kidshuster
export IMAGE_TAG=1.0.0
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

Full guide: [`deploy/RASPBERRY_PI.md`](deploy/RASPBERRY_PI.md)

## Project docs

Planning artifacts live under `doc/` (design spec, architecture, wireframes). Implementation follows `doc/plan.md` phases 1–8.
