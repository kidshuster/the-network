from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.app.layout.loader import clear_layout_cache
from bot.features.recipes.hub import installs as installs_mod
from bot.features.recipes.hub.installs import (
    build_hub_install_plan,
    ensure_hub_installs,
    hub_sticky_settings_keys,
)


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    clear_layout_cache()
    yield
    clear_layout_cache()


def test_build_hub_install_plan_reads_layout_yaml() -> None:
    plan = build_hub_install_plan()
    by_resource = {item.resource_id: item.install for item in plan}
    assert "join_the_network" in by_resource
    assert by_resource["join_the_network"].sticky == "join-the-network"
    assert by_resource["join_the_network"].view == "join_network"
    assert by_resource["admin"].sticky == "network-admin"
    assert by_resource["rules"].sticky == "hub-rules"
    assert by_resource["network_announcements"].guide == "announcements"
    assert by_resource["changelog"].sync == "changelog_releases"


def test_hub_sticky_settings_keys_come_from_catalog() -> None:
    keys = hub_sticky_settings_keys()
    assert "hub_join_the_network_sticky" in keys
    assert "hub_network_admin_sticky" in keys
    assert "hub_rules_sticky_message" in keys


@pytest.mark.asyncio
async def test_ensure_hub_installs_dispatches_sticky_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    bot_member = MagicMock(spec=discord.Member)
    context = MagicMock()
    context.store.settings.get = AsyncMock(return_value=None)
    context.store.settings.set = AsyncMock()
    context.store.networks.list_all = AsyncMock(return_value=[])
    join = MagicMock(spec=discord.TextChannel)
    join.mention = "#join-the-network"
    view_registry = MagicMock()
    view = MagicMock(spec=discord.ui.View)
    view_registry.register_join_network_view.return_value = view
    view_registry.register_network_admin_view.return_value = view

    sync_join = AsyncMock(return_value=MagicMock(message=MagicMock(), reason=None))
    sync_rules = AsyncMock(return_value=MagicMock(message=MagicMock(), reason=None))
    sync_admin = AsyncMock(return_value=MagicMock(message=MagicMock(), reason=None))
    sync_guide = AsyncMock()
    sync_changelog = AsyncMock(return_value=1)

    monkeypatch.setattr(
        "bot.features.channels.stickies.join.sync_hub_join_sticky",
        sync_join,
    )
    monkeypatch.setattr(
        "bot.features.channels.stickies.rules.sync_rules_sticky",
        sync_rules,
    )
    monkeypatch.setattr(
        "bot.features.channels.stickies.admin.sync_network_admin_sticky",
        sync_admin,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.announcements.sync_announcements_guide",
        sync_guide,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog.sync_changelog_releases",
        sync_changelog,
    )
    monkeypatch.setattr(
        installs_mod,
        "resolve_hub_channel",
        lambda _guild, resource_id, **_kwargs: join,
    )

    result = await ensure_hub_installs(
        guild,
        bot_member,
        context=context,
        view_registry=view_registry,
        bound_ids={},
    )
    assert result.failed_steps == []
    assert result.success is True
    sync_join.assert_awaited()
    sync_rules.assert_awaited()
    sync_admin.assert_awaited()
    sync_guide.assert_awaited()
    sync_changelog.assert_awaited()
