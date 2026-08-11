from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

import discord

from bot.core.widgets import render_text

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.core.models.client import Client
    from bot.core.runtime import BotContext

ResponseVia = Literal["followup", "response"]


class MembershipPolicy(Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    ALLOW_NON_MEMBER = "allow_non_member"


async def _send_auth_message(
    interaction: discord.Interaction,
    content: str,
    *,
    via: ResponseVia,
    ephemeral: bool | None = True,
) -> None:
    kwargs: dict[str, Any] = {}
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
    membership_policy: MembershipPolicy,
    via: ResponseVia = "followup",
    ephemeral: bool | None = True,
) -> bool:
    member = interaction.user
    if membership_policy is MembershipPolicy.REQUIRED:
        if not isinstance(member, discord.Member):
            await _send_auth_message(
                interaction,
                render_text("invalid_member"),
                via=via,
                ephemeral=ephemeral,
            )
            return False
    elif membership_policy is MembershipPolicy.ALLOW_NON_MEMBER and not isinstance(
        member, discord.Member
    ):
        return True
    elif membership_policy is MembershipPolicy.OPTIONAL and not isinstance(member, discord.Member):
        return True

    if not isinstance(member, discord.Member):
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
