from __future__ import annotations

import discord

from bot.constants import DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME
from bot.core.hub.resolve import (
    resolve_access_role as layout_resolve_access_role,
)
from bot.core.hub.resolve import (
    resolve_operator_role as layout_resolve_operator_role,
)
from bot.core.models.errors import NetworkValidationError

_REQUIRED_OPERATOR_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("manage_channels", "Manage Channels"),
    ("manage_roles", "Manage Roles"),
    ("manage_webhooks", "Manage Webhooks"),
    ("send_messages", "Send Messages"),
    ("embed_links", "Embed Links"),
    ("attach_files", "Attach Files"),
    ("read_message_history", "Read Message History"),
    ("manage_messages", "Manage Messages"),
    ("manage_emojis_and_stickers", "Manage Emojis and Stickers"),
    ("create_expressions", "Create Expressions"),
)


async def ensure_bot_access_role(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    reason: str,
) -> discord.Role:
    """Ensure the sole configurable role used in channel overwrites exists."""
    role = discord.utils.get(guild.roles, name=DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME,
            permissions=discord.Permissions.none(),
            mentionable=False,
            hoist=False,
            reason=reason,
        )
    hierarchy_invalid = (
        isinstance(role.position, int)
        and isinstance(bot_member.top_role.position, int)
        and role.position >= bot_member.top_role.position
    )
    if role.managed is True or hierarchy_invalid:
        raise NetworkValidationError(
            f"**{DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME}** must be an unmanaged role "
            "below the bot's highest role."
        )
    if role not in bot_member.roles:
        await bot_member.add_roles(role, reason=reason)
    return role


def format_operator_setup_instructions(
    operator_role_name: str,
    access_role_name: str,
) -> str:
    perm_lines = "\n".join(f"• **{label}**" for _, label in _REQUIRED_OPERATOR_PERMISSIONS)
    return (
        f"Set up **{operator_role_name}** before continuing "
        f"(this is the only manual step):\n\n"
        f"1. **Server Settings → Roles** — create **{operator_role_name}**\n"
        f"2. Drag **{operator_role_name}** **above** **{access_role_name}** "
        f"in the role list\n"
        f"3. **Server Settings → Members** — assign **{operator_role_name}** to the bot\n"
        f"4. On **{operator_role_name}**, enable:\n{perm_lines}\n\n"
        f"Then run `/server init` again."
    )


def resolve_access_role_by_name(
    guild: discord.Guild,
    *,
    role_name: str,
    explicit_role: discord.Role | None = None,
) -> discord.Role:
    if explicit_role is not None:
        if explicit_role.guild.id != guild.id:
            raise NetworkValidationError("Access role must belong to this guild.")
        return explicit_role

    role = layout_resolve_access_role(guild, role_name=role_name)
    if role is None:
        raise NetworkValidationError(
            f"Could not find access role {role_name!r}. Discord auto-creates **The Network** "
            "when the bot joins — ensure the bot is in this server."
        )
    return role


def resolve_operator_role_by_name(
    guild: discord.Guild,
    *,
    role_name: str,
    explicit_role: discord.Role | None = None,
) -> discord.Role | None:
    if explicit_role is not None:
        if explicit_role.guild.id != guild.id:
            raise NetworkValidationError("Operator role must belong to this guild.")
        return explicit_role
    return layout_resolve_operator_role(guild, role_name=role_name)


def resolve_access_role(
    guild: discord.Guild,
    *,
    role_name: str,
    explicit_role: discord.Role | None = None,
) -> discord.Role:
    return resolve_access_role_by_name(
        guild,
        role_name=role_name,
        explicit_role=explicit_role,
    )


def resolve_bot_role_by_name(
    guild: discord.Guild,
    *,
    role_name: str,
    explicit_role: discord.Role | None = None,
) -> discord.Role:
    """Backwards-compatible alias for the hub access role."""
    return resolve_access_role_by_name(
        guild,
        role_name=role_name,
        explicit_role=explicit_role,
    )


def _operator_has_permission(
    permissions: discord.Permissions,
    attr: str,
) -> bool:
    if attr == "manage_emojis_and_stickers":
        return bool(
            getattr(permissions, "manage_emojis_and_stickers", False)
            or getattr(permissions, "manage_expressions", False)
            or getattr(permissions, "manage_emojis", False)
        )
    if attr == "create_expressions":
        return bool(getattr(permissions, "create_expressions", False))
    return bool(getattr(permissions, attr, False))


def validate_operator_setup(
    bot_member: discord.Member,
    operator_role: discord.Role | None,
    access_role: discord.Role,
    *,
    operator_role_name: str,
) -> None:
    if operator_role is None:
        raise NetworkValidationError(
            format_operator_setup_instructions(operator_role_name, access_role.name)
        )

    if operator_role not in bot_member.roles:
        raise NetworkValidationError(
            f"Assign **{operator_role_name}** to the bot in Server Settings → Members.\n\n"
            + format_operator_setup_instructions(operator_role_name, access_role.name)
        )

    top = bot_member.top_role
    if top.id != operator_role.id:
        raise NetworkValidationError(
            f"The bot's highest role must be **{operator_role_name}** "
            f"(currently **{top.name}**). Drag **{operator_role_name}** above every other "
            f"role on the bot member.\n\n"
            + format_operator_setup_instructions(operator_role_name, access_role.name)
        )

    if top.position <= access_role.position:
        raise NetworkValidationError(
            f"**{operator_role_name}** (position {top.position}) must be **above** "
            f"**{access_role.name}** (position {access_role.position}) in "
            "Server Settings → Roles.\n\n"
            + format_operator_setup_instructions(operator_role_name, access_role.name)
        )

    missing = [
        label
        for attr, label in _REQUIRED_OPERATOR_PERMISSIONS
        if not _operator_has_permission(operator_role.permissions, attr)
    ]
    if missing:
        raise NetworkValidationError(
            f"Enable these permissions on **{operator_role_name}**:\n"
            + "\n".join(f"• **{item}**" for item in missing)
            + "\n\n"
            + format_operator_setup_instructions(operator_role_name, access_role.name)
        )


def validate_provision_permissions(
    bot_member: discord.Member,
    access_role: discord.Role,
    *,
    operator_role: discord.Role | None,
    operator_role_name: str,
) -> None:
    """Ensure the bot operator role can configure hub and network infrastructure."""
    validate_operator_setup(
        bot_member,
        operator_role,
        access_role,
        operator_role_name=operator_role_name,
    )

    perms = bot_member.guild_permissions
    issues: list[str] = []
    if not perms.manage_channels:
        issues.append("**Manage Channels** — required to create categories and channels.")
    if not perms.manage_roles:
        issues.append("**Manage Roles** — required to set private channel permission overwrites.")
    if not perms.manage_webhooks:
        issues.append("**Manage Webhooks** — required for partner feed channels.")

    if issues:
        raise NetworkValidationError(
            "Bot cannot provision network infrastructure yet:\n"
            + "\n".join(f"• {item}" for item in issues)
            + f"\n\nThese come from **{operator_role_name}** — check that role's permissions."
        )


def validate_hub_permissions(
    bot_member: discord.Member,
    access_role: discord.Role,
    *,
    operator_role: discord.Role | None,
    operator_role_name: str,
    human_moderator_role: discord.Role | None,
) -> None:
    """Ensure the bot can run `/server init` and configure hub channel overwrites."""
    validate_provision_permissions(
        bot_member,
        access_role,
        operator_role=operator_role,
        operator_role_name=operator_role_name,
    )

    if human_moderator_role is None:
        return

    top = bot_member.top_role
    if top.position <= human_moderator_role.position:
        raise NetworkValidationError(
            "Bot cannot initialize the hub yet:\n"
            f"• **{operator_role_name}** (position {top.position}) must be **above** "
            f"**{human_moderator_role.name}** (position {human_moderator_role.position}) "
            "in Server Settings → Roles.\n\n"
            f"Expected order: **{operator_role_name}** → **{access_role.name}** → "
            "**Moderator** → **Partner:** → @everyone"
        )
