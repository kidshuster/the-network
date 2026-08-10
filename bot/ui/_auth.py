from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import discord

from bot.messages import render_text

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext
    from bot.domain.client import Client

ResponseVia = Literal["followup", "response"]


async def _send_auth_message(
    interaction: discord.Interaction,
    content: str,
    *,
    via: ResponseVia,
    ephemeral: bool | None = True,
) -> None:
    kwargs: dict[str, object] = {}
    if ephemeral is not None:
        kwargs["ephemeral"] = ephemeral
    if via == "followup":
        await interaction.followup.send(content, **kwargs)
    else:
        await interaction.response.send_message(content, **kwargs)


async def ensure_client_access(
    interaction: discord.Interaction,
    guild: discord.Guild,
    client: Client,
    *,
    popup_key: str,
    via: ResponseVia = "followup",
    require_member: bool = False,
    allow_non_member: bool = False,
    ephemeral: bool | None = True,
) -> bool:
    member = interaction.user
    if require_member:
        if not isinstance(member, discord.Member):
            await _send_auth_message(
                interaction,
                render_text("invalid_member"),
                via=via,
                ephemeral=ephemeral,
            )
            return False
    elif allow_non_member and not isinstance(member, discord.Member):
        return True
    elif not isinstance(member, discord.Member):
        return True

    client_role = guild.get_role(client.client_role_id)
    if client_role is None or (
        client_role not in member.roles and not member.guild_permissions.manage_guild
    ):
        await _send_auth_message(
            interaction,
            render_text(popup_key),
            via=via,
            ephemeral=ephemeral,
        )
        return False
    return True


@dataclass(frozen=True)
class HubModalValidation:
    guild: discord.Guild
    context: BotContext


def validate_client_modal_context(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
) -> HubModalValidation | str:
    guild = interaction.guild
    if guild is None:
        return render_text("hub_guild_form_only")
    if guild.id != bot.settings.guild_id:
        return render_text("hub_guild_form_only")
    context = bot.bot_context
    if context is None:
        return render_text("bot_not_ready")
    return HubModalValidation(guild=guild, context=context)


def validate_hub_modal_context(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    *,
    guild_only_key: str = "central_guild_only",
) -> HubModalValidation | str:
    guild = interaction.guild
    if guild is None or guild.id != bot.settings.guild_id:
        return render_text(guild_only_key)
    context = bot.bot_context
    if context is None:
        return render_text("bot_not_ready")
    return HubModalValidation(guild=guild, context=context)
