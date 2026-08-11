from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

import discord

from bot.app.discord.checks import ensure_manage_guild
from bot.core.templates import render_text

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext
    from bot.core.models.client import Client

ResponseVia = Literal["followup", "response"]


class MembershipPolicy(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    ALLOW_NON_MEMBER = "allow_non_member"


@dataclass(frozen=True)
class HubValidation:
    guild: discord.Guild
    context: BotContext


async def _send(
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


def validate_client_modal_context(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
) -> HubValidation | str:
    return validate_hub_context(
        bot,
        interaction,
        guild_only_key="hub_guild_form_only",
    )


def validate_hub_modal_context(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    *,
    guild_only_key: str = "central_guild_only",
) -> HubValidation | str:
    return validate_hub_context(bot, interaction, guild_only_key=guild_only_key)


def validate_hub_context(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    *,
    guild_only_key: str = "central_guild_only",
) -> HubValidation | str:
    guild = interaction.guild
    if guild is None or guild.id != bot.settings.guild_id:
        return render_text(guild_only_key)
    context = bot.bot_context
    if context is None:
        return render_text("bot_not_ready")
    return HubValidation(guild=guild, context=context)


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
            await _send(
                interaction,
                render_text("invalid_member"),
                via=via,
                ephemeral=ephemeral,
            )
            return False
    elif membership_policy in (
        MembershipPolicy.ALLOW_NON_MEMBER,
        MembershipPolicy.OPTIONAL,
    ) and not isinstance(member, discord.Member):
        return True

    if not isinstance(member, discord.Member):
        return True

    client_role = guild.get_role(client.client_role_id)
    if client_role is None or (
        client_role not in member.roles and not member.guild_permissions.manage_guild
    ):
        await _send(
            interaction,
            render_text(popup_key),
            via=via,
            ephemeral=ephemeral,
        )
        return False
    return True


def _parse_requirement(
    requirement: str | dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if isinstance(requirement, str):
        return requirement, {}
    if len(requirement) != 1:
        raise ValueError(f"Invalid require entry: {requirement!r}")
    name = next(iter(requirement))
    raw = requirement[name]
    if raw is None:
        return name, {}
    if isinstance(raw, dict):
        return name, raw
    return name, {}


async def check_requires(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    requires: list[str | dict[str, Any]],
    *,
    params: dict[str, Any],
    via: ResponseVia = "response",
) -> HubValidation | str | None:
    """Return HubValidation if hub checks ran, error string, ``__abort__``, or None."""
    hub: HubValidation | None = None
    for requirement in requires:
        name, options = _parse_requirement(requirement)
        if name == "hub_guild":
            key = str(options.get("popup", "central_guild_only"))
            validated = validate_hub_context(bot, interaction, guild_only_key=key)
            if isinstance(validated, str):
                return validated
            hub = validated
        elif name == "manage_guild":
            if interaction.response.is_done():
                member = interaction.user
                if (
                    not isinstance(member, discord.Member)
                    or not member.guild_permissions.manage_guild
                ):
                    await interaction.followup.send(
                        render_text("manage_guild_required"),
                        ephemeral=True,
                    )
                    return "__abort__"
            elif not await ensure_manage_guild(interaction):
                return "__abort__"
        elif name == "client_role":
            if hub is None:
                validated = validate_hub_context(bot, interaction)
                if isinstance(validated, str):
                    return validated
                hub = validated
            client_id = options.get("client_id", params.get("client_id"))
            if client_id is None and "subscription_id" in params:
                subscription = await hub.context.store.clients.get_subscription_by_id(
                    int(params["subscription_id"])
                )
                if subscription is not None:
                    client_id = subscription.client_id
            if client_id is None and "client" in params:
                client_id = getattr(params["client"], "id", None)
            if client_id is None:
                return render_text(str(options.get("missing_popup", "client_not_found")))
            client = params.get("client")
            if client is None:
                client = await hub.context.store.clients.get_by_id(int(client_id))
            if client is None:
                return render_text(str(options.get("missing_popup", "client_not_found")))
            membership = MembershipPolicy(
                str(options.get("membership", MembershipPolicy.REQUIRED))
            )
            ephemeral = options.get("ephemeral", True)
            ok = await ensure_client_access(
                interaction,
                hub.guild,
                client,
                popup_key=str(options.get("popup", "client_role_required_edit")),
                membership_policy=membership,
                via=via,
                ephemeral=ephemeral,
            )
            if not ok:
                return "__abort__"
            params.setdefault("client", client)
        elif name == "bot_ready":
            if bot.bot_context is None:
                return render_text("bot_not_ready")
        else:
            raise ValueError(f"Unknown widget policy {name!r}")
    return hub
