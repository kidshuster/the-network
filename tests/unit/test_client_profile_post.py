from __future__ import annotations

from bot.features.recipes.hub.clients.profile_post import build_client_profile_embed


def test_build_client_profile_embed_shows_network_status_per_line() -> None:
    embed = build_client_profile_embed(
        server_name="My Server",
        display_name="My Display",
        enabled=True,
        subscribed_networks=(
            ("stingers", "Active"),
            ("beta", "Disabled"),
            ("gamma", "Not Configured"),
        ),
    )

    networks_field = next(field for field in embed.fields if field.name == "Subscribed networks")
    assert "`stingers` — Active" in networks_field.value
    assert "`beta` — Disabled" in networks_field.value
    assert "`gamma` — Not Configured" in networks_field.value
