# GitHub — what works and what doesn't

## Short answer

| Goal | GitHub? |
|------|---------|
| Store source code | **Yes** |
| Run tests on every push (CI) | **Yes** — GitHub Actions |
| Run the Discord bot 24/7 | **No** — bots need an always-on host elsewhere |
| Replace top.gg as a bot directory | **No** — use top.gg (or your own README) for discovery |

GitHub is for **code and automation**, not for keeping a Discord gateway connection open.

## Recommended setup

```
GitHub repo  →  CI (pytest on push)
            →  Deploy hook to a small host (Railway, Render, Fly.io, VPS, Docker)
            →  Bot runs on that host with DISCORD_TOKEN + GUILD_ID in env secrets
```

Your bot stays online on a host; GitHub holds the code and verifies changes.

## 1. Push this project to GitHub

From the project root (do **not** commit `.env` — it is gitignored):

```bash
git init
git add .
git commit -m "Initial release v1.0.0"
gh repo create the-network --private --source=. --push
```

Use `--public` if you want the repo visible. Never push `DISCORD_TOKEN`.

## 2. CI (included)

`.github/workflows/ci.yml` runs `pytest` on push and pull requests. No secrets required.

## 3. Where to actually run the bot

Pick one host and connect it to your GitHub repo:

### Railway / Render / Fly.io

- Connect the GitHub repo in their dashboard
- Set environment variables: `DISCORD_TOKEN`, `GUILD_ID`, optional `TOPGG_TOKEN`
- Mount or use persistent disk for `DATABASE_PATH` / `data/relay.db`
- Start command: `python -m bot.main` or use the included `Dockerfile`

### VPS or home server (what you use now)

```bash
git clone git@github.com:YOU/the-network.git
cd the-network
cp .env.example .env   # fill in locally, never commit
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
./bin/run.sh
```

Pull updates with `git pull && ./bin/stop.sh && ./bin/run.sh`.

### Docker on any server

```bash
git clone ...
docker compose up -d --build
```

## 4. top.gg vs GitHub

- **GitHub** — source code, issues, CI, releases
- **top.gg** — optional public bot listing and stats (still needs a running bot somewhere)

You can skip top.gg entirely if this bot is private to your hub.

## 5. GitHub Releases (optional)

Tag versions for deploys:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Hosts can deploy from tags or from `main`.

## Releases & Raspberry Pi

Tagged releases (`v1.0.0`, …) trigger a GitHub Action that:

1. Builds a multi-arch Docker image (`amd64`, `arm64`, `arm/v7`)
2. Pushes to `ghcr.io/<owner>/the-network`
3. Creates a GitHub Release page with pull instructions

On a Pi:

```bash
export IMAGE_TAG=1.0.0
docker compose -f docker-compose.release.yml pull && docker compose -f docker-compose.release.yml up -d
```

See [`deploy/RASPBERRY_PI.md`](deploy/RASPBERRY_PI.md).
