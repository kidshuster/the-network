from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_interaction, make_member

from bot.presentation import render_text
from bot.ui.network_admin_views import NetworkAdminView


@pytest.mark.asyncio
async def test_network_admin_create_button_requires_manage_guild() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = MagicMock()
    bot.bot_context = MagicMock()
    member = make_member(guild=guild, manage_guild=False)
    interaction = make_interaction(guild=guild, user=member)

    view = NetworkAdminView(bot)
    create_button = next(
        child for child in view.children if getattr(child, "label", None) == "Create Network"
    )
    await create_button.callback(interaction)

    interaction.response.send_message.assert_awaited_once_with(
        render_text("manage_guild_required"),
        ephemeral=True,
    )
    interaction.response.send_modal.assert_not_called()


@pytest.mark.asyncio
async def test_network_admin_create_button_opens_modal_for_admin() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = MagicMock()
    bot.bot_context = MagicMock()
    member = make_member(guild=guild, manage_guild=True)
    interaction = make_interaction(guild=guild, user=member)

    view = NetworkAdminView(bot)
    create_button = next(
        child for child in view.children if getattr(child, "label", None) == "Create Network"
    )
    await create_button.callback(interaction)

    interaction.response.send_modal.assert_awaited_once()
    interaction.response.send_message.assert_not_called()
