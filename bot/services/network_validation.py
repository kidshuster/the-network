from __future__ import annotations

import discord

from bot.domain.errors import NetworkValidationError


def _channel_label(channel: discord.abc.GuildChannel) -> str:
    return f"#{channel.name}" if hasattr(channel, "name") else str(channel.id)


async def validate_network_channels(
    guild: discord.Guild,
    bot_member: discord.Member,
    feed_category: discord.CategoryChannel,
    output_channel: discord.abc.GuildChannel,
    concat_channel: discord.TextChannel | None,
) -> None:
    """Raise NetworkValidationError on invalid channel setup."""
    errors: list[str] = []

    if feed_category.guild.id != guild.id:
        errors.append("Feed category must belong to the configured central guild.")
    if output_channel.guild.id != guild.id:
        errors.append("Output channel must belong to the configured central guild.")
    if concat_channel is not None and concat_channel.guild.id != guild.id:
        errors.append("Concat channel must belong to the configured central guild.")

    if getattr(output_channel, "type", None) is not discord.ChannelType.news:
        errors.append(f"{_channel_label(output_channel)} must be an announcement channel.")

    if concat_channel is not None:
        if concat_channel.type is not discord.ChannelType.text:
            errors.append(f"{_channel_label(concat_channel)} must be a text channel.")
        if concat_channel.category_id != feed_category.id:
            errors.append(
                f"Concat channel {_channel_label(concat_channel)} must be inside "
                f"feed category {_channel_label(feed_category)}."
            )

    errors.extend(_check_bot_permissions(bot_member, feed_category, output_channel, concat_channel))

    if errors:
        raise NetworkValidationError("\n".join(errors))


def _check_bot_permissions(
    bot_member: discord.Member,
    feed_category: discord.CategoryChannel,
    output_channel: discord.abc.GuildChannel,
    concat_channel: discord.TextChannel | None,
) -> list[str]:
    issues: list[str] = []

    def check(channel: discord.abc.GuildChannel, perms: tuple[str, ...], label: str) -> None:
        resolved = channel.permissions_for(bot_member)
        missing = [p for p in perms if not getattr(resolved, p, False)]
        if missing:
            readable = ", ".join(p.replace("_", " ") for p in missing)
            issues.append(f"Missing permissions on {label}: {readable}")

    check(
        feed_category,
        ("view_channel", "read_message_history"),
        _channel_label(feed_category),
    )
    check(
        output_channel,
        (
            "view_channel",
            "read_message_history",
            "send_messages",
            "embed_links",
            "attach_files",
        ),
        _channel_label(output_channel),
    )
    if concat_channel is not None:
        check(
            concat_channel,
            ("view_channel", "send_messages", "embed_links", "attach_files"),
            _channel_label(concat_channel),
        )

    return issues
