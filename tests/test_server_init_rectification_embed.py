from __future__ import annotations

from bot.cogs.servers import _server_init_rectification_embed
from bot.services.guild_init import GuildInitResult


def test_server_init_rectification_embed_lists_work_done() -> None:
    result = GuildInitResult(
        success=True,
        rectifications=[
            "Leaders access synced for **2** client role(s) on Leaders category.",
            "**Acme**: rectified category, #acme-profile.",
        ],
        rectification_skipped=["**Beta**: client role missing in Discord"],
    )

    embed = _server_init_rectification_embed(result)
    assert embed is not None
    assert embed.title == "Server Init — Permissions Rectified"
    field_names = {field.name for field in embed.fields}
    assert "Rectified" in field_names
    assert "Skipped" in field_names


def test_server_init_rectification_embed_when_no_clients() -> None:
    result = GuildInitResult(success=True)

    embed = _server_init_rectification_embed(result)
    assert embed is not None
    assert "No registered clients" in embed.description
