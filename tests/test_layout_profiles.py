from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles, make_role

from bot.layout import LayoutContext, compile_client, compile_hub
from bot.layout.compiler import ResourceKind
from bot.layout.loader import clear_layout_cache, load_layout, load_roles, validate_all_layouts
from bot.layout.schema import RoleDefaultsSpec


def _context(*, clients: int = 1, network_key: str | None = "stingers") -> LayoutContext:
    guild, bot, moderator, access, operator = make_guild_with_roles()
    client_roles = tuple(
        make_role(name=f"Client: {index}", role_id=60 + index, position=2)
        for index in range(clients)
    )
    guild.roles = [*guild.roles, *client_roles]
    return LayoutContext(
        guild=guild,
        bot_member=bot,
        access_role=access,
        moderator_role=moderator,
        operator_role=operator,
        client_role=client_roles[0] if client_roles else None,
        client_roles=client_roles,
        server_name="Acme",
        slug="acme",
        network_key=network_key,
    )


def _resource(resources, resource_id: str):
    return next(item for item in resources if item.id == resource_id)


def _overwrite(resource, target: MagicMock) -> discord.PermissionOverwrite:
    return resource.overwrites[target]


def test_configuration_loads_and_cross_references() -> None:
    clear_layout_cache()
    validate_all_layouts()
    assert load_roles().roles["bot_access"].target == "bot_access"
    assert set(load_layout().layout.categories) == {"moderation", "network", "leaders"}


def test_role_defaults_reject_unknown_discord_permission() -> None:
    with pytest.raises(ValueError, match="unknown Discord permissions"):
        RoleDefaultsSpec.model_validate(
            {"target": "everyone", "permissions": {"invent_channels": True}}
        )


def test_hub_matches_expected_structure_and_channel_types() -> None:
    resources = compile_hub(_context())
    categories = [item.name for item in resources if item.kind is ResourceKind.CATEGORY]
    assert categories == ["Moderation", "The Network", "Leaders"]
    assert _resource(resources, "network_announcements").kind is ResourceKind.ANNOUNCEMENT
    assert _resource(resources, "rules").community_slot == "rules"
    assert _resource(resources, "moderator_only").community_slot == "public_updates"
    assert _resource(resources, "rules").preserve_on_uninit
    assert _resource(resources, "moderator_only").preserve_on_uninit


@pytest.mark.parametrize(
    ("category_id", "channel_ids"),
    [
        ("moderation", ("moderator_only", "join_requests", "network_announcements")),
        ("network", ("rules", "join_the_network")),
        ("leaders", ("leaders_channel", "changelog")),
    ],
)
def test_category_profile_materializes_onto_children(
    category_id: str,
    channel_ids: tuple[str, ...],
) -> None:
    resources = compile_hub(_context(clients=2))
    category = _resource(resources, category_id)
    for channel_id in channel_ids:
        channel = _resource(resources, channel_id)
        for target, expected in category.overwrites.items():
            actual = channel.overwrites[target]
            if (
                category_id == "leaders"
                and channel_id == "leaders_channel"
                and "Client" in target.name
            ):
                assert actual.send_messages is True
                continue
            assert actual.pair() == expected.pair()


def test_channel_exception_changes_only_requested_fields() -> None:
    ctx = _context(clients=2)
    resources = compile_hub(ctx)
    category = _resource(resources, "leaders")
    leaders = _resource(resources, "leaders_channel")
    changelog = _resource(resources, "changelog")
    for client in ctx.client_roles:
        assert _overwrite(category, client).send_messages is False
        assert _overwrite(changelog, client).send_messages is False
        assert _overwrite(leaders, client).send_messages is True
        assert _overwrite(leaders, client).view_channel is True


def test_commands_adds_slash_permission_without_repeating_moderator_defaults() -> None:
    ctx = _context()
    resources = compile_hub(ctx)
    moderation = _resource(resources, "moderation")
    commands = _resource(resources, "commands")
    assert _overwrite(moderation, ctx.moderator_role).use_application_commands is None
    assert _overwrite(commands, ctx.moderator_role).use_application_commands is True
    assert _overwrite(commands, ctx.moderator_role).manage_channels is True


def test_client_layout_has_one_profile_and_subscription_pair() -> None:
    ctx = _context()
    base = compile_client(ctx, include_subscribed=False)
    assert [item.id for item in base] == ["client", "profile"]
    subscribed = compile_client(ctx, include_subscribed=True)
    assert [item.id for item in subscribed] == ["client", "profile", "publish", "subscribe"]
    assert _resource(subscribed, "profile").name == "acme-profile"
    assert _resource(subscribed, "publish").name == "acme-stingers-publish"
    assert _resource(subscribed, "subscribe").name == "acme-stingers-subscribe"
    assert _resource(subscribed, "subscribe").kind is ResourceKind.ANNOUNCEMENT


def test_client_category_defaults_propagate_until_profile_replacement() -> None:
    ctx = _context()
    resources = compile_client(ctx, include_subscribed=True)
    category = _resource(resources, "client")
    profile = _resource(resources, "profile")
    subscribe = _resource(resources, "subscribe")
    publish = _resource(resources, "publish")
    client = ctx.client_role
    assert client is not None
    assert _overwrite(profile, client).pair() == _overwrite(category, client).pair()
    assert _overwrite(subscribe, client).pair() == _overwrite(category, client).pair()
    assert _overwrite(publish, client).manage_webhooks is True
    assert _overwrite(publish, ctx.access_role).send_messages is False


def test_compiled_recipes_use_bot_access_role_not_bot_member_or_operator() -> None:
    ctx = _context(clients=2)
    bot_access = discord.utils.get(ctx.guild.roles, name="The Network Bot Access")
    assert bot_access is not None
    for resource in [*compile_hub(ctx), *compile_client(ctx, include_subscribed=True)]:
        assert bot_access in resource.overwrites
        assert ctx.bot_member not in resource.overwrites
        assert ctx.operator_role not in resource.overwrites
        assert ctx.bot_member in resource.managed_targets
        assert ctx.operator_role in resource.managed_targets
        assert set(ctx.client_roles) <= set(resource.managed_targets)
        assert ctx.operator_role in resource.managed_targets
        assert set(ctx.client_roles) <= set(resource.managed_targets)


def test_missing_bot_access_role_is_not_replaced_with_operator_or_member() -> None:
    ctx = _context()
    ctx.guild.roles = [role for role in ctx.guild.roles if role.name != "The Network Bot Access"]
    for resource in compile_hub(ctx):
        assert ctx.operator_role not in resource.overwrites
        assert ctx.bot_member not in resource.overwrites
