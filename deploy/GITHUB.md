# GitHub — what works and what doesn't

## Short answer

| Goal | GitHub? |
|------|---------|
| Store source code | **Yes** |
| Run tests on every push (CI) | **Yes** — GitHub Actions |
| Run the Discord bot 24/7 | **No** — bots need an always-on host elsewhere |

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
- Set environment variables: `DISCORD_TOKEN` and `GUILD_ID`
- Mount or use persistent disk for `DATABASE_PATH` / `data/relay.db`
- Start command: `python -m bot.main` or use the included `Dockerfile`

### VPS or home server (what you use now)

```bash
git clone git@github.com:YOU/the-network.git
cd the-network
cp .env.example .env   # fill in locally, never commit
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
./bin/start.sh
```

Pull updates with `git pull && ./deploy/deploy.sh` (systemd) or `git pull && ./bin/stop.sh && ./bin/start.sh` (manual).

### One-command systemd deploy

After cloning:

```bash
git clone git@github.com:YOU/the-network.git
cd the-network
cp .env.example .env   # fill in DISCORD_TOKEN and GUILD_ID
./deploy/deploy.sh
```

`deploy.sh` pulls latest changes, installs Python deps, writes `/etc/systemd/system/the-network.service`, and enables the service. It calls `bin/start.sh` / `bin/stop.sh` for process management.

### Docker on any server (deploy repo — recommended)

Publish from your dev machine:

```bash
docker login ghcr.io
./bin/publish.sh
```

On the host (Pi, VPS, etc.):

```bash
git clone git@github.com:YOU/the-network-run.git
cd the-network-run
cp .env.example .env
./scripts/enable.sh
```

See [`deploy/RASPBERRY_PI.md`](RASPBERRY_PI.md).

### Docker from source clone

```bash
git clone git@github.com:YOU/the-network.git
cd the-network
./bin/package.sh
cd publish && cp .env.example .env && ./scripts/start.sh
```

## 4. GitHub Releases (optional)

Tag versions for deploys:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Hosts can deploy from tags or from `main`.

## Releases & Raspberry Pi

Two ways to publish:

1. **`./bin/publish.sh`** — builds multi-arch image, pushes to GHCR, updates **the-network-run** deploy repo
2. **Git tag** (`git push origin v1.1.0`) — GitHub Actions builds and pushes to GHCR (use `./bin/publish.sh --via-ci` to sync deploy repo only)

On a Pi, clone **the-network-run** and run `./scripts/enable.sh`. See [`deploy/RASPBERRY_PI.md`](RASPBERRY_PI.md).
