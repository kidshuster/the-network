from __future__ import annotations

import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_interaction, make_member
from widget_helpers import wire_widget_bot

from bot.app.widgets import render_view
from bot.core.templates import render_text


@pytest.mark.asyncio
async def test_network_admin_create_button_requires_manage_guild() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = wire_widget_bot()
    bot.bot_context = object()
    bot.settings.guild_id = guild.id
    member = make_member(guild=guild, manage_guild=False)
    interaction = make_interaction(guild=guild, user=member)

    view = render_view("network_admin", bot)
    create_button = next(
        child for child in view.children if getattr(child, "label", None) == "Create Network"
    )
    await create_button.callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    assert render_text("manage_guild_required") in (
        interaction.response.send_message.await_args.args[0]
        if interaction.response.send_message.await_args.args
        else (interaction.response.send_message.await_args.kwargs.get("embed").description or "")
    )
    interaction.response.send_modal.assert_not_called()


@pytest.mark.asyncio
async def test_network_admin_create_button_opens_modal_for_admin() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    bot = wire_widget_bot()
    bot.bot_context = object()
    bot.settings.guild_id = guild.id
    member = make_member(guild=guild, manage_guild=True)
    interaction = make_interaction(guild=guild, user=member)

    view = render_view("network_admin", bot)
    create_button = next(
        child for child in view.children if getattr(child, "label", None) == "Create Network"
    )
    await create_button.callback(interaction)

    interaction.response.send_modal.assert_awaited_once()
    interaction.response.send_message.assert_not_called()
