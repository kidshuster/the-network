# Raspberry Pi deployment

Run The Network from the **the-network-run** deploy repo (recommended) or pull the Docker image from GHCR directly. Images support **arm64** (Pi 4/5 with 64-bit Raspberry Pi OS) and **amd64**.

## Requirements

- Raspberry Pi 4 or 5 (recommended), 64-bit Raspberry Pi OS
- Docker and Docker Compose plugin

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
# log out and back in
```

---

## Recommended: deploy repo (the-network-run)

The deploy repo is published by `./bin/publish.sh` from the source repository. It contains compose, env template, and scripts — no application source code.

### 1. Clone

```bash
git clone git@github.com:YOUR_USER/the-network-run.git ~/the-network-run
cd ~/the-network-run
```

Replace `YOUR_USER` with your GitHub username (default upstream: `kidshuster`).

### 2. Configure environment

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` — **required**:

- `DISCORD_TOKEN` — bot token from the Developer Portal
- `GUILD_ID` — central hub guild ID

`DATABASE_PATH` must stay `/app/data/relay.db` (container path; `./data` is mounted as a volume).

### 3. Start with systemd (survives reboot)

```bash
chmod +x scripts/*.sh
./scripts/enable.sh
./scripts/logs.sh
```

`enable.sh` installs `the-network-docker.service`, enables it on boot, and starts the container.

### 4. Verify

- Bot shows online in Discord
- `/status` or `/network status` in the central guild
- Run `/server init` once to lay out hub channels (if not done already)

### 5. Updates

When a new release is published to the deploy repo:

```bash
cd ~/the-network-run
git pull
./scripts/update.sh
```

Or with systemd:

```bash
git pull
sudo systemctl restart the-network-docker.service
```

Your `data/` directory keeps the SQLite database across updates.

### Lifecycle scripts

| Script | Purpose |
|--------|---------|
| `./scripts/start.sh` | Start container (no systemd) |
| `./scripts/stop.sh` | Stop container |
| `./scripts/logs.sh` | Follow logs |
| `./scripts/update.sh` | Pull image and recreate container |
| `./scripts/enable.sh` | Install systemd unit + start on boot |
| `./scripts/disable.sh` | Stop, disable systemd, remove unit |

---

## Alternative: manual GHCR pull

If you prefer not to use the deploy repo, pull from [GitHub Releases](https://github.com/kidshuster/the-network/releases) / GHCR:

```bash
mkdir -p ~/the-network/data
cd ~/the-network
curl -fsSL -o docker-compose.release.yml \
  https://raw.githubusercontent.com/kidshuster/the-network/v1.1.0/docker-compose.release.yml
cp .env.example .env   # from source repo, or create manually — see below
export GITHUB_USER=kidshuster
export IMAGE_TAG=1.1.0
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

Minimal `.env` for the container:

```bash
cat > .env <<'EOF'
DISCORD_TOKEN=your_bot_token
GUILD_ID=your_central_guild_id
DATABASE_PATH=/app/data/relay.db
LOG_LEVEL=INFO
NETWORK_ACCESS_ROLE_NAME=The Network
EOF
chmod 600 .env
```

If the GHCR package is **private**, log in once:

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

(PAT needs `read:packages`.)

---

## Publishing from development machine

From the **source** repo:

```bash
docker login ghcr.io
./bin/publish.sh
```

This builds a multi-arch image, pushes to `ghcr.io/YOUR_USER/the-network:<version>`, and updates the **the-network-run** deploy repo.

Set `THE_NETWORK_DEPLOY_REPO` if your deploy repo URL differs:

```bash
export THE_NETWORK_DEPLOY_REPO=git@github.com:YOU/the-network-run.git
./bin/publish.sh
```

Use `./bin/publish.sh --via-ci` if the image was already built by GitHub Actions on a git tag.

---

## Bare metal (no Docker)

Use `./deploy/deploy.sh` from a full source clone for systemd + Python venv. See [`deploy/GITHUB.md`](GITHUB.md).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `pull access denied` | `docker login ghcr.io` or make the GHCR package public |
| Wrong architecture | Use 64-bit Pi OS; image manifest selects arm64 automatically |
| Bot offline after reboot | Run `./scripts/enable.sh` (systemd + `restart: unless-stopped`) |
| Docker permission denied | Re-login after `usermod -aG docker` |
| Permission errors in Discord | Re-check bot role order (Moderator above The Network) per README |

## Image reference

```
ghcr.io/kidshuster/the-network:latest
ghcr.io/kidshuster/the-network:1.1.0
```

Tags match semver from `pyproject.toml` / git tags (`v1.1.0` → Docker tag `1.1.0`).
