# Raspberry Pi deployment

Run The Network from the pre-built Docker image published on each [GitHub Release](https://github.com/kidshuster/the-network/releases). Images support **arm64** (Pi 4/5 with 64-bit Raspberry Pi OS) and **amd64**.

## Requirements

- Raspberry Pi 4 or 5 (recommended), 64-bit Raspberry Pi OS
- Docker and Docker Compose plugin

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
# log out and back in
```

## 1. Install directory

```bash
mkdir -p ~/the-network/data
cd ~/the-network
```

## 2. Environment file

Create `.env` (never commit this):

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

## 3. Compose file

Download the release compose file or copy from the repo:

```bash
curl -fsSL -o docker-compose.release.yml \
  https://raw.githubusercontent.com/kidshuster/the-network/v1.0.0/docker-compose.release.yml
```

Set your GitHub username if different:

```bash
export GITHUB_USER=kidshuster
export IMAGE_TAG=1.0.0   # match the release tag without the v prefix
```

## 4. Pull and run

If the GHCR package is **private**, log in once:

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

(PAT needs `read:packages`.)

```bash
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
docker compose -f docker-compose.release.yml logs -f
```

## 5. Updates

When a new release is published:

```bash
export IMAGE_TAG=1.1.0   # new version
docker compose -f docker-compose.release.yml pull
docker compose -f docker-compose.release.yml up -d
```

Your `data/` volume keeps the SQLite database across updates.

## 6. Verify

- Bot shows online in Discord
- `/network status` works in the central guild
- Publish a test announcement through a followed feed channel

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `pull access denied` | `docker login ghcr.io` or make the package public in GitHub → Packages → Package settings |
| Wrong architecture | Use 64-bit Pi OS; image manifest selects arm64 automatically |
| Bot offline after reboot | `docker compose ... up -d` with `restart: unless-stopped` (included) |
| Permission errors in Discord | Re-check bot role order (Moderator above The Network) per README |

## Image reference

```
ghcr.io/kidshuster/the-network:latest
ghcr.io/kidshuster/the-network:1.0.0
```

Tags match semver from git tags (`v1.0.0` → Docker tag `1.0.0`).
