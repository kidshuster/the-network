# Smoke testing

Live smoke scripts hit the **real Discord API**. They are excluded from pytest and CI.
Use `./test` as the single entry point for local and pre-deploy validation.

## Commands

| Command | What runs | When |
|---------|-----------|------|
| `./test` or `./test --dev` | ruff, mypy, pytest | Every change (~1 min) |
| `./test --full` | dev gate + `bin/smoke_testwork.sh` | Before deploy (~15–30 min) |

```bash
# Daily development
./test --dev

# Pre-deploy (stop the bot first)
./test --full

# Restart bot after smoke (default: leave stopped)
./test --full --smoke-restart
```

## Guild layout

| Env file | Purpose |
|----------|---------|
| `.env` | Active config (gitignored) |
| `.env.staging` | **Burn-in / Testwork** guild — safe for repeated smoke |
| `.env.production` | Production hub backup — switch with care |

Use a **dedicated staging guild** for smoke so rate limits do not take down your real hub:

```bash
cp .env.example .env.staging
# Edit: DISCORD_TOKEN, GUILD_ID, DATABASE_PATH=./data/staging.db

bin/use-staging-env.sh staging   # copies .env.staging → .env
./test --full
bin/use-staging-env.sh production   # restore when done
```

Initialize the staging guild once with `/server init` before the first `--full` run.

## Rate limits

Discord rate-limits **per guild** mutations (roles, channels, categories). Running
the full suite twice in a row, or many probe retries, can trigger long `retry_after`
windows (minutes to hours).

**Prevention (built in):**

- Pacing between probe phases and role creates (`bot/smoke/pacing.py`)
- Pauses between smoke steps in `bin/smoke_testwork.sh`
- Fast-fail on 429 via `max_ratelimit_timeout` on smoke Discord clients

**Tune with env vars:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SMOKE_STEP_DELAY_SEC` | 8 | Pause between each `bin/smoke_*.sh` step |
| `SMOKE_DUPLICATE_PROBE_DELAY_SEC` | 15 | Extra pause after probe-only before join E2E |
| `SMOKE_PROBE_PHASE_DELAY_SEC` | 2 | Operator probe → provision probe |
| `SMOKE_ROLE_CREATE_DELAY_SEC` | 1.5 | Before each probe `create_role` |

Set any to `0` to disable. Increase if you still see `RateLimited` errors.

**If smoke fails with rate limits:** wait for the reported `retry_after`, or use a
fresh staging guild. `./test --dev` always works offline.

## What `--full` runs

`bin/smoke_testwork.sh` (see script for details):

1. Artifact cleanup
2. Button/command parity
3. Pre-init provision probe (`--probe-only`)
4. Join-approval E2E
5. Setup welcome smoke
6. Hub announcements smoke
7. Hub rebuild smoke
8. Server init stress probes
9. Teardown (removes smoke clients and Discord artifacts)

## pytest vs live

| Layer | Tool | Discord |
|-------|------|---------|
| Unit / integration | `pytest` | Mocked |
| Live probes | `bin/smoke_*.sh` | Real API |

494+ pytest tests cover business logic; live smoke verifies permissions, provisioning,
and hub layout against Discord’s actual behavior.
