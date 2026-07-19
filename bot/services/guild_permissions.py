from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import discord

OverwriteMap = Mapping[
    discord.Role | discord.Member | discord.Object,
    discord.PermissionOverwrite,
]


def _bot_hub_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        manage_channels=True,
        manage_messages=True,
        manage_webhooks=True,
    )


def build_moderator_channel_overwrite() -> discord.PermissionOverwrite:
    """Channel overwrite for staff — manage_roles stays on the guild Moderator role."""
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        manage_channels=True,
        manage_webhooks=True,
        manage_messages=True,
        create_public_threads=True,
        send_messages_in_threads=True,
    )


def _can_configure_role(bot_member: discord.Member, role: discord.Role) -> bool:
    if bot_member.top_role.id == role.id:
        return False
    return bot_member.top_role.position > role.position


def _with_access_overwrite(
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    bot_member: discord.Member,
    access_role: discord.Role,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    if _can_configure_role(bot_member, access_role):
        overwrites[access_role] = build_network_access_overwrite()
    return overwrites


def _with_moderator_overwrite(
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    bot_member: discord.Member,
    moderator_role: discord.Role | None,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    """Skip Moderator channel overwrites when the bot cannot configure that role."""
    if moderator_role is None:
        return overwrites
    if not _can_configure_role(bot_member, moderator_role):
        return overwrites
    overwrites[moderator_role] = build_moderator_channel_overwrite()
    return overwrites


def _finalize_hub_overwrites(
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    overwrites = _with_access_overwrite(overwrites, bot_member, access_role)
    return _with_moderator_overwrite(overwrites, bot_member, human_moderator_role)


def build_moderation_only_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Moderation category — human moderators and the bot only."""
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(
            {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                bot_member: _bot_hub_overwrite(),
            },
            bot_member,
            human_moderator_role,
        ),
    )


def build_welcome_sink_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
) -> OverwriteMap:
    return cast(
        OverwriteMap,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
            ),
        },
    )


def build_everyone_readonly_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=False,
        add_reactions=False,
    )


def build_moderator_overwrite() -> discord.PermissionOverwrite:
    """Alias for channel overwrites."""
    return build_moderator_channel_overwrite()


def build_hub_public_category_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    return cast(
        OverwriteMap,
        _finalize_hub_overwrites(
            {
                guild.default_role: build_everyone_readonly_overwrite(),
                bot_member: _bot_hub_overwrite(),
            },
            bot_member,
            access_role,
            human_moderator_role,
        ),
    )


def build_network_access_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        manage_webhooks=True,
    )


def build_moderation_staff_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    return build_moderation_only_overwrites(guild, bot_member, human_moderator_role)


def build_subscribe_category_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    return cast(
        OverwriteMap,
        _finalize_hub_overwrites(
            {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                bot_member: _bot_hub_overwrite(),
            },
            bot_member,
            access_role,
            human_moderator_role,
        ),
    )


def build_subscribe_announcement_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Public read-only announcement outputs under Subscribe To Me!."""
    return cast(
        OverwriteMap,
        _finalize_hub_overwrites(
            {
                guild.default_role: build_everyone_readonly_overwrite(),
                bot_member: _bot_hub_overwrite(),
            },
            bot_member,
            access_role,
            human_moderator_role,
        ),
    )


def build_join_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    return cast(
        OverwriteMap,
        _finalize_hub_overwrites(
            {
                guild.default_role: build_everyone_readonly_overwrite(),
                bot_member: _bot_hub_overwrite(),
            },
            bot_member,
            access_role,
            human_moderator_role,
        ),
    )


def build_feed_category_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    return build_subscribe_category_overwrites(
        guild, bot_member, access_role, human_moderator_role
    )


def build_server_feed_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    server_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            manage_webhooks=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }
    if _can_configure_role(bot_member, server_role):
        base[server_role] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            manage_webhooks=True,
            send_messages=False,
            use_application_commands=False,
        )
    return cast(
        OverwriteMap,
        _finalize_hub_overwrites(base, bot_member, access_role, human_moderator_role),
    )


def build_commands_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Moderator-only command runner channel."""
    overwrites = dict(
        build_moderation_only_overwrites(guild, bot_member, human_moderator_role)
    )
    if (
        human_moderator_role is not None
        and _can_configure_role(bot_member, human_moderator_role)
    ):
        staff = build_moderator_channel_overwrite()
        staff.use_application_commands = True
        overwrites[human_moderator_role] = staff
    return cast(OverwriteMap, overwrites)
