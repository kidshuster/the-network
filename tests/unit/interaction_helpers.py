from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord


def make_interaction(
    *,
    guild: discord.Guild | None = None,
    user: discord.Member | discord.User | None = None,
    channel: discord.abc.Messageable | None = None,
    deferred: bool = False,
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    interaction.channel = channel
    interaction.response = MagicMock()
    done = {"value": deferred}
    interaction.response.is_done = MagicMock(side_effect=lambda: done["value"])

    async def _defer(**_kwargs: object) -> None:
        done["value"] = True

    interaction.response.defer = AsyncMock(side_effect=_defer)
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.data = {}
    return interaction


def make_member(
    *,
    user_id: int = 555,
    guild: discord.Guild | None = None,
    roles: list[discord.Role] | None = None,
    manage_guild: bool = False,
) -> MagicMock:
    member = MagicMock(spec=discord.Member, id=user_id)
    member.roles = roles or []
    perms = MagicMock()
    perms.manage_guild = manage_guild
    member.guild_permissions = perms
    if guild is not None:
        member.guild = guild
    return member


def make_text_channel(
    *,
    channel_id: int = 500,
    name: str = "test-channel",
    guild: discord.Guild | None = None,
) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel, id=channel_id, name=name)
    channel.mention = f"#{name}"
    channel.guild = guild
    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()
    channel.edit = AsyncMock()
    channel.delete = AsyncMock()
    return channel


def make_message(
    *,
    message_id: int = 900,
    channel: discord.TextChannel | None = None,
    content: str = "",
) -> MagicMock:
    message = MagicMock(spec=discord.Message, id=message_id, content=content)
    message.channel = channel
    message.edit = AsyncMock()
    message.delete = AsyncMock()
    return message
