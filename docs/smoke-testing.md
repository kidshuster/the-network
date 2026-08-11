# Smoke testing

Live smoke scripts hit the **real Discord API**. They are excluded from pytest and CI.
Use `./test` as the single entry point for local and pre-deploy validation.

## Commands

| Command | What runs | When |
|---------|-----------|------|
| `./test` or `./test --dev` | ruff, mypy, pytest | Every change (~1 min) |
| `./test --full` | dev gate + consolidated `tests/live` suite | Before deploy (~15–30 min) |

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

- Optional quota diagnostic (`./test --full --check-quota`) probes the same Discord
  buckets. It is off by default because checking consumes six create/delete calls.
- One shared gateway session for the standard suite (`tests/live/suite.py`)
- Each destructive permission/provision probe runs once in the standard suite
- Pacing between destructive phases and role creates (`tests/live/pacing.py`)
- Fast-fail on 429 via `max_ratelimit_timeout` on smoke Discord clients

**Tune with env vars:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `SMOKE_PHASE_DELAY_SEC` | 2 | Pause between mutation-heavy phases |
| `SMOKE_PROBE_PHASE_DELAY_SEC` | 2 | Operator probe → provision probe |
| `SMOKE_ROLE_CREATE_DELAY_SEC` | 1.5 | Before each probe `create_role` |
| `SMOKE_MAX_RETRY_AFTER_SEC` | 30 | Quota check fails if 429 `retry_after` exceeds this |
| `SMOKE_MIN_RATE_LIMIT_REMAINING` | 1 | Quota check fails if remaining requests drop below this |

Set any to `0` to disable pacing delays. Increase pacing if you still see
`RateLimited` errors during smoke.

**Check quota manually:**

```bash
tests/live/smoke_check_quota.sh  # explicit diagnostic; consumes mutation quota
./test --full                   # standard lower-call suite
```

**If smoke fails with rate limits:** wait for the reported `retry_after`, or use a
fresh staging guild. `./test --dev` always works offline.

## What `--full` runs

`tests/live/smoke_testwork.sh` opens one gateway session and runs:

1. Stale smoke-artifact cleanup
2. Operator and client-provision permission probe
3. Join-approval E2E
4. Setup, sticky, welcome, blacklist, and relay behavior
5. Hub announcement dispatch
6. Hub uninit/init and network recreation with client survival checks
7. Permission and layout drift rectification
8. Smoke-only teardown

Before and after every destructive phase, the suite verifies that every non-smoke
client still has its database row, role, category, and profile channel. Repeated
burn-in is intentionally separate: `tests/live/smoke_server_init.sh --stress`.

## pytest vs live

| Layer | Tool | Discord |
|-------|------|---------|
| Unit / integration | `pytest tests/unit` | Mocked |
| Live probes | `tests/live/smoke_*.sh` | Real API |

Unit tests cover `bot/channels/layout`, the permission API, recipes, adapters, and
deletion boundaries. Live smoke verifies YAML layout, permission rectification,
relay behavior, and client retention against Discord's actual behavior.
