from __future__ import annotations

import discord

from bot.messages import render_embed
from bot.services.message_formatter import sanitize_author

PROFILE_CARD_FOOTER = "The Network • client profile • use Edit Profile or network buttons below"


def build_client_profile_embed(
    *,
    server_name: str,
    display_name: str,
    enabled: bool,
    emoji_id: int | None = None,
    subscribed_networks: tuple[str, ...] = (),
) -> discord.Embed:
    author_name = sanitize_author(display_name.strip() or server_name)
    author_icon_url = ""
    if emoji_id is not None:
        author_icon_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png?size=128"

    has_subscriptions = bool(subscribed_networks)
    networks_value = ", ".join(f"`{key}`" for key in subscribed_networks)

    return render_embed(
        "client_profile",
        colour="green" if enabled else "red",
        author_name=author_name,
        author_icon_url=author_icon_url,
        server_name=server_name,
        status="Active" if enabled else "Disabled",
        has_subscriptions="1" if has_subscriptions else "",
        no_subscriptions="" if has_subscriptions else "1",
        networks_value=networks_value,
    )
