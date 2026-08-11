from __future__ import annotations

import discord

# Cap discord.py 429 backoff so smoke scripts fail fast instead of hanging ~8 minutes.
SMOKE_MAX_RATELIMIT_TIMEOUT = 60.0


def create_smoke_discord_client(*, members: bool = False) -> discord.Client:
    """Discord client for live smoke scripts — bounded rate-limit waits."""
    intents = discord.Intents.default()
    if members:
        intents.members = True
    return discord.Client(
        intents=intents,
        max_ratelimit_timeout=SMOKE_MAX_RATELIMIT_TIMEOUT,
    )
