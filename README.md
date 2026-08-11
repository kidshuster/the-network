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

Bare-metal systemd (source tree): `./bin/deploy.sh`.

6. In Discord, run `/status` in the configured guild to verify connectivity.

## Development

```bash
git submodule update --init install
./test --dev                # ruff + mypy + pytest (tests/unit)
./test --full               # also run tests/live Testwork smoke
ruff check .
mypy bot tests/core
pytest tests/unit
./bin/test_deploy_bundle.sh # validate install/ submodule
```

All pytest tests live under `tests/unit/`; all real-Discord Testwork probes live
under `tests/core/` and `tests/live/` (both tracked). Testwork guild IDs/tokens stay in gitignored
`.env` / `.env.staging` only. Local agent notes live under untracked `cursor/`.

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

### Publish a release (from this source repo)

```bash
docker login ghcr.io
./bin/publish.sh
```

This builds/pushes the multi-arch image to GHCR and updates/pushes the `install/`
submodule (`the-network-install`). Options: `--via-ci`, `--skip-image`, `--skip-install`.

Then commit the submodule pointer here:

```bash
git add install && git commit -m "Bump install submodule"
```

### Local image smoke

```bash
docker build -t the-network .
docker run --env-file .env -v "$(pwd)/data:/app/data" --restart unless-stopped -d the-network
```

## Local agent workspace

Design archives, Cursor rules, and agent notes live under untracked `cursor/`
(symlinked as `.cursor` for IDE discovery). They are not part of the published repo.
