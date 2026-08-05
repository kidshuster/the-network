from __future__ import annotations

from collections.abc import Iterable, Mapping
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
    """Channel overwrite for human staff — manage_roles stays on the guild Moderator role."""
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


def build_moderator_category_overwrite(
    *,
    allow_slash_commands: bool = False,
) -> discord.PermissionOverwrite:
    """Category overwrite for staff — no thread flags (invalid on categories)."""
    overwrite = discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        manage_channels=True,
        manage_webhooks=True,
        manage_messages=True,
    )
    if allow_slash_commands:
        overwrite.use_application_commands = True
    return overwrite


def _can_configure_role(bot_member: discord.Member, role: discord.Role) -> bool:
    if role.is_default():
        return True
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


def build_network_access_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        manage_webhooks=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
    )


def strip_bot_member_overwrites(
    bot_member: discord.Member,
    overwrites: Mapping[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    """Discord rejects channel overwrites targeting the bot itself (50013)."""
    return {
        target: overwrite
        for target, overwrite in overwrites.items()
        if not (isinstance(target, discord.Member) and target.id == bot_member.id)
    }


def filter_configurable_overwrites(
    bot_member: discord.Member,
    overwrites: Mapping[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    *,
    for_channel: bool = False,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    """Drop role overwrites the bot cannot set — prevents 50013 on channel/category edits."""
    filtered: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {}
    for target, overwrite in overwrites.items():
        if isinstance(target, discord.Role):
            if _can_configure_role(bot_member, target):
                filtered[target] = overwrite
            continue
        if isinstance(target, discord.Member):
            if for_channel:
                continue
            if target.id == bot_member.id:
                filtered[target] = overwrite
            continue
        filtered[target] = overwrite
    return filtered


def _overwrite_base(
    guild: discord.Guild,
    bot_member: discord.Member,
    everyone_overwrite: discord.PermissionOverwrite,
    *,
    for_category: bool,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    """Category overwrites may include the bot; channel overwrites must not (50013)."""
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {guild.default_role: everyone_overwrite}
    if for_category:
        base[bot_member] = _bot_hub_overwrite()
    return base


def _with_moderator_overwrite(
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    bot_member: discord.Member,
    human_moderator_role: discord.Role | None,
    *,
    for_category: bool = False,
    for_announcement: bool = False,
    allow_slash_commands: bool = False,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    if human_moderator_role is None:
        return overwrites
    if not _can_configure_role(bot_member, human_moderator_role):
        return overwrites
    if for_announcement:
        overwrites[human_moderator_role] = build_moderator_announcement_overwrite()
    elif for_category:
        overwrites[human_moderator_role] = build_moderator_category_overwrite(
            allow_slash_commands=allow_slash_commands,
        )
    else:
        overwrites[human_moderator_role] = build_moderator_channel_overwrite()
    return overwrites


def _finalize_hub_overwrites(
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    *,
    for_category: bool = False,
    for_announcement: bool = False,
    allow_slash_commands: bool = False,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    overwrites = _with_access_overwrite(overwrites, bot_member, access_role)
    return _with_moderator_overwrite(
        overwrites,
        bot_member,
        human_moderator_role,
        for_category=for_category,
        for_announcement=for_announcement,
        allow_slash_commands=allow_slash_commands,
    )


def build_moderation_only_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    human_moderator_role: discord.Role | None,
    *,
    for_category: bool = False,
    allow_slash_commands: bool = False,
) -> OverwriteMap:
    """Moderation category — human moderators and the bot only."""
    hidden = (
        build_everyone_hidden_category_overwrite
        if for_category
        else build_everyone_hidden_overwrite
    )
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(
            _overwrite_base(guild, bot_member, hidden(), for_category=for_category),
            bot_member,
            human_moderator_role,
            for_category=for_category,
            allow_slash_commands=allow_slash_commands,
        ),
    )


def build_welcome_sink_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
) -> OverwriteMap:
    """Hidden from @everyone; bot reaches the channel via Manage Channels."""
    _ = bot_member
    return cast(
        OverwriteMap,
        {guild.default_role: build_everyone_hidden_overwrite()},
    )


def _post_and_thread_lockdown() -> dict[str, bool]:
    """Explicit denies so hub channels never inherit post/thread rights from the guild."""
    return {
        "send_messages": False,
        "add_reactions": False,
        "create_public_threads": False,
        "create_private_threads": False,
        "send_messages_in_threads": False,
    }


def _category_post_lockdown() -> dict[str, bool]:
    """Category-safe lockdown — omit thread flags (not valid on category overwrites)."""
    return {
        "send_messages": False,
        "add_reactions": False,
    }


def build_network_access_feed_overwrite() -> discord.PermissionOverwrite:
    """Hub members can view feed sources; posts arrive via Channel Follow webhooks only."""
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        manage_webhooks=True,
        embed_links=True,
        attach_files=True,
        **_post_and_thread_lockdown(),
    )


def build_everyone_readonly_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        **_post_and_thread_lockdown(),
    )


def build_everyone_readonly_category_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        **_category_post_lockdown(),
    )


def build_everyone_hidden_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=False,
        **_post_and_thread_lockdown(),
    )


def build_everyone_hidden_category_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=False,
        **_category_post_lockdown(),
    )


def build_moderator_overwrite() -> discord.PermissionOverwrite:
    """Alias for channel overwrites."""
    return build_moderator_channel_overwrite()


def build_client_leader_category_overwrite() -> discord.PermissionOverwrite:
    """Client server leaders — view, read history, and post in Leaders category."""
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        add_reactions=True,
    )


def build_client_leader_channel_overwrite() -> discord.PermissionOverwrite:
    """Client server leaders — view and post in #leaders."""
    return build_client_leader_category_overwrite()


def build_leaders_category_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    client_roles: Iterable[discord.Role],
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Leaders category — hidden from @everyone and hub access; client roles can post."""
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = _overwrite_base(
        guild,
        bot_member,
        build_everyone_hidden_category_overwrite(),
        for_category=True,
    )
    for role in client_roles:
        if _can_configure_role(bot_member, role):
            base[role] = build_client_leader_category_overwrite()
    if _can_configure_role(bot_member, access_role):
        base[access_role] = build_everyone_hidden_category_overwrite()
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(
            base,
            bot_member,
            human_moderator_role,
            for_category=True,
        ),
    )


def build_leaders_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    client_roles: Iterable[discord.Role],
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Hidden from @everyone and hub access role; visible only to client roles."""
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {
        guild.default_role: build_everyone_hidden_overwrite(),
    }
    for role in client_roles:
        if _can_configure_role(bot_member, role):
            base[role] = build_client_leader_channel_overwrite()
    if _can_configure_role(bot_member, access_role):
        base[access_role] = build_everyone_hidden_overwrite()
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(base, bot_member, human_moderator_role),
    )


def build_hub_public_category_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    *,
    for_category: bool = False,
) -> OverwriteMap:
    everyone = (
        build_everyone_readonly_category_overwrite
        if for_category
        else build_everyone_readonly_overwrite
    )
    return cast(
        OverwriteMap,
        _finalize_hub_overwrites(
            _overwrite_base(
                guild,
                bot_member,
                everyone(),
                for_category=for_category,
            ),
            bot_member,
            access_role,
            human_moderator_role,
            for_category=for_category,
        ),
    )


def build_partner_feed_overwrite() -> discord.PermissionOverwrite:
    """Partner server role — view and follow the feed channel, no posting."""
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        manage_webhooks=True,
        **_post_and_thread_lockdown(),
    )


def build_moderation_staff_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    human_moderator_role: discord.Role | None,
    *,
    for_category: bool = False,
    allow_slash_commands: bool = False,
) -> OverwriteMap:
    return build_moderation_only_overwrites(
        guild,
        bot_member,
        human_moderator_role,
        for_category=for_category,
        allow_slash_commands=allow_slash_commands,
    )


def build_subscribe_category_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Subscribe To Me! — public read-only announcements."""
    return cast(
        OverwriteMap,
        _finalize_hub_overwrites(
            _overwrite_base(
                guild,
                bot_member,
                build_everyone_readonly_category_overwrite(),
                for_category=True,
            ),
            bot_member,
            access_role,
            human_moderator_role,
            for_category=True,
        ),
    )


def build_everyone_readonly_announcement_overwrite() -> discord.PermissionOverwrite:
    """Announcement channels reject thread and reaction flags on overwrites."""
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=False,
    )


def build_everyone_hidden_announcement_overwrite() -> discord.PermissionOverwrite:
    """Hidden @everyone overwrite safe for announcement feed channels."""
    return discord.PermissionOverwrite(
        view_channel=False,
        send_messages=False,
    )


def build_partner_feed_announcement_overwrite() -> discord.PermissionOverwrite:
    """Partner feed announcement channel — view and follow, no invalid flags."""
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        manage_webhooks=True,
        use_application_commands=False,
        send_messages=False,
    )


def build_moderator_announcement_overwrite() -> discord.PermissionOverwrite:
    """Staff overwrite for announcement feed channels (no thread flags)."""
    return discord.PermissionOverwrite(
        view_channel=True,
        read_message_history=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        manage_channels=True,
        manage_webhooks=True,
        manage_messages=True,
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
                guild.default_role: build_everyone_readonly_announcement_overwrite(),
            },
            bot_member,
            access_role,
            human_moderator_role,
            for_announcement=True,
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
            _overwrite_base(
                guild,
                bot_member,
                build_everyone_readonly_overwrite(),
                for_category=False,
            ),
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
        guild,
        bot_member,
        access_role,
        human_moderator_role,
    )


def _with_access_feed_overwrite(
    overwrites: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    bot_member: discord.Member,
    access_role: discord.Role,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    if _can_configure_role(bot_member, access_role):
        overwrites[access_role] = build_network_access_feed_overwrite()
    return overwrites


def build_server_feed_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    server_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Partner feed source channels — text channels that receive Channel Follow webhooks."""
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {
        guild.default_role: build_everyone_hidden_overwrite(),
    }
    if _can_configure_role(bot_member, server_role):
        base[server_role] = build_partner_feed_overwrite()
    overwrites = _with_access_feed_overwrite(base, bot_member, access_role)
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(
            overwrites,
            bot_member,
            human_moderator_role,
        ),
    )


def prepare_server_feed_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    server_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    """Build and filter partner feed overwrites for channel creation."""
    return filter_configurable_overwrites(
        bot_member,
        build_server_feed_channel_overwrites(
            guild,
            bot_member,
            server_role,
            access_role,
            human_moderator_role,
        ),
        for_channel=True,
    )


async def create_text_channel_with_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    name: str,
    overwrites: Mapping[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ],
    reason: str,
    category: discord.CategoryChannel | None = None,
    topic: str | None = None,
    news: bool = False,
    sync_permissions: bool | None = None,
) -> discord.TextChannel:
    """Create a text channel, then apply overwrites (required for restricted categories)."""
    from bot.services.guild_notifications import ensure_guild_only_mention_notifications

    await ensure_guild_only_mention_notifications(
        guild,
        bot_member,
        reason=reason,
    )
    kwargs: dict[str, object] = {"name": name, "reason": reason}
    if category is not None:
        kwargs["category"] = category
    if topic is not None:
        kwargs["topic"] = topic
    if news:
        kwargs["news"] = True
    if category is not None and sync_permissions is not None:
        kwargs["sync_permissions"] = sync_permissions
    channel = await guild.create_text_channel(**kwargs)  # type: ignore[arg-type]
    safe = filter_configurable_overwrites(bot_member, overwrites, for_channel=True)
    if sync_permissions is False:
        await channel.edit(
            sync_permissions=False,
            overwrites=safe,
            reason=reason,
        )
    else:
        for target, overwrite in safe.items():
            await channel.set_permissions(target, overwrite=overwrite, reason=reason)
    return channel


async def sync_partner_feed_channel_permissions(
    channel: discord.abc.GuildChannel,
    bot_member: discord.Member,
    server_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    *,
    reason: str,
) -> None:
    """Sync partner feed permissions using access-role overwrites."""
    overwrites = dict(
        build_server_feed_channel_overwrites(
            channel.guild,
            bot_member,
            server_role,
            access_role,
            human_moderator_role,
        )
    )
    safe = filter_configurable_overwrites(bot_member, overwrites, for_channel=True)
    await channel.edit(overwrites=safe, reason=reason)


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


def build_client_role_name(server_name: str) -> str:
    return f"Client: {server_name.strip()}"[:100]


def build_client_category_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    client_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = _overwrite_base(
        guild,
        bot_member,
        build_everyone_hidden_category_overwrite(),
        for_category=True,
    )
    if _can_configure_role(bot_member, client_role):
        base[client_role] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            **_category_post_lockdown(),
        )
    overwrites = _with_access_overwrite(base, bot_member, access_role)
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(
            overwrites,
            bot_member,
            human_moderator_role,
            for_category=True,
        ),
    )


def build_client_profile_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    client_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {
        guild.default_role: build_everyone_hidden_overwrite(),
    }
    if _can_configure_role(bot_member, client_role):
        base[client_role] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            **_post_and_thread_lockdown(),
        )
    overwrites = _with_access_overwrite(base, bot_member, access_role)
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(overwrites, bot_member, human_moderator_role),
    )


def build_client_publish_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    client_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Publish channel overwrites — access role must be explicit when sync is off."""
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {
        guild.default_role: build_everyone_hidden_overwrite(),
    }
    if _can_configure_role(bot_member, client_role):
        base[client_role] = build_partner_feed_overwrite()
    overwrites = _with_access_overwrite(base, bot_member, access_role)
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(overwrites, bot_member, human_moderator_role),
    )


def build_client_subscribe_channel_overwrites(
    guild: discord.Guild,
    bot_member: discord.Member,
    client_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
) -> OverwriteMap:
    """Subscribe channel overwrites — access role must be explicit when sync is off."""
    base: dict[
        discord.Role | discord.Member | discord.Object,
        discord.PermissionOverwrite,
    ] = {
        guild.default_role: build_everyone_hidden_overwrite(),
    }
    if _can_configure_role(bot_member, client_role):
        base[client_role] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            **_post_and_thread_lockdown(),
        )
    overwrites = _with_access_overwrite(base, bot_member, access_role)
    return cast(
        OverwriteMap,
        _with_moderator_overwrite(overwrites, bot_member, human_moderator_role),
    )


async def sync_client_category_permissions(
    category: discord.CategoryChannel,
    bot_member: discord.Member,
    client_role: discord.Role,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    *,
    reason: str,
) -> None:
    overwrites = dict(
        build_client_category_overwrites(
            category.guild,
            bot_member,
            client_role,
            access_role,
            human_moderator_role,
        )
    )
    safe = filter_configurable_overwrites(bot_member, overwrites)
    await category.edit(overwrites=safe, reason=reason)
