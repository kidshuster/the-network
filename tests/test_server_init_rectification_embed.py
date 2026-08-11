from __future__ import annotations

from bot.cogs.servers import _format_bullet_list, _server_init_rectification_embed
from bot.recipes.hub.initialize import GuildInitResult


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


def test_build_changelog_embed_splits_long_change_lists() -> None:
    from bot.core.hub.changelog import ReleaseNotes, build_changelog_embed

    changes = tuple(f"Change item {index} with extra detail" for index in range(80))
    notes = ReleaseNotes(version="9.9.9", summary="Big release", changes=changes)
    embed = build_changelog_embed(notes)

    for field in embed.fields:
        assert len(field.value) <= 1024


def test_format_bullet_list_truncates_to_discord_limit() -> None:
    items = [f"Entry {index}: {'x' * 80}" for index in range(50)]
    value = _format_bullet_list(items)
    assert len(value) <= 1024
