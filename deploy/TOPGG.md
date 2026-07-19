# Deploying The Network

## 1. Production host

The bot needs a always-on process with persistent storage for `data/relay.db`.

### Docker (recommended)

```bash
cp .env.example .env   # fill in secrets
chmod +x bin/package.sh bin/start.sh bin/stop.sh deploy/deploy.sh
./bin/package.sh
docker compose up -d
docker compose logs -f
```

### Bare metal

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
./bin/start.sh
```

Use `./deploy/deploy.sh` for systemd (pull, install deps, register service). Or keep `./bin/start.sh` running with pm2 or another supervisor.

## 1b. systemd (VPS / Pi without Docker)

```bash
git clone git@github.com:YOU/the-network.git
cd the-network
cp .env.example .env   # secrets
./deploy/deploy.sh
```

Updates:

```bash
./deploy/deploy.sh     # git pull + restart service
```

## 2. Required environment

| Variable | Purpose |
|----------|---------|
| `DISCORD_TOKEN` | Bot token |
| `GUILD_ID` | Central guild ID |
| `TOPGG_TOKEN` | Optional — top.gg API token for live server count |

See `.env.example` for the full list.

## 3. List on top.gg

The bot is **single-guild**: it runs in one central server you configure. top.gg will show `server_count: 1`, which is expected.

### Steps

1. Open [top.gg/manage](https://top.gg/manage) and sign in.
2. Click **Add Bot** and select **The-Network** (your application).
3. Paste the listing copy from [`topgg-listing.md`](topgg-listing.md):
   - Short description
   - Long description / tags
   - Invite URL (replace `YOUR_APPLICATION_ID`)
4. Under **API**, copy your **top.gg API token** into `.env`:

   ```
   TOPGG_TOKEN=your_token_here
   ```

5. Restart the bot. It posts guild count on startup and every 30 minutes.
6. Submit the listing for review if required.

### Invite URL

```
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&permissions=536871936&scope=bot+applications.commands
```

Permissions included: Manage Channels, Manage Roles, Manage Webhooks, Send Messages, Embed Links, Attach Files, Manage Messages (publish), Manage Expressions.

## 4. Verify

- Bot online in Discord
- `/network status` responds in the central guild
- Relay test: publish in a followed source channel → appears in output announcement channel
- top.gg dashboard shows updated server count (after `TOPGG_TOKEN` is set)

## 5. Updates

```bash
git pull
./bin/stop.sh          # bare metal
./bin/package.sh
docker compose up -d --build
```

Database migrations run automatically on startup.
