from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles, make_role

from bot.constants import DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME
from bot.features.channels.layout import (
    LayoutContext,
    SubscriptionCompileInput,
    compile_client,
    compile_hub,
    managed,
)
from bot.features.channels.layout.compiler import ResourceKind
from bot.features.channels.layout.loader import (
    clear_layout_cache,
    load_layout,
    load_roles,
    validate_all_layouts,
)
from bot.features.channels.layout.roles import resolve_targets
from bot.features.channels.layout.schema import RoleDefaultsSpec


def test_resolve_bot_access_from_sequence_proxy_guild_roles() -> None:
    """discord.py 2.7+ exposes guild.roles as SequenceProxy, not list/tuple."""
    guild, bot, moderator, access, operator = make_guild_with_roles()
    bot_access = next(
        role for role in guild.roles if role.name == DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME
    )
    guild.roles = discord.utils.SequenceProxy(
        {role.id: role for role in guild.roles}.values(),
        sorted=False,
    )
    context = LayoutContext(
        guild=guild,
        bot_member=bot,
        access_role=access,
        moderator_role=moderator,
        operator_role=operator,
    )

    resolved = resolve_targets(context, "bot_access")

    assert resolved == (bot_access,)


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


def test_removed_yaml_resource_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(managed, "_hub_channel_by_id", lambda: {})
    monkeypatch.setattr(managed, "_hub_category_by_id", lambda: {})
    with pytest.raises(KeyError):
        managed.hub_channel_name("removed")
    with pytest.raises(KeyError):
        managed.hub_category_name("removed")


def test_role_defaults_reject_unknown_discord_permission() -> None:
    with pytest.raises(ValueError, match="unknown Discord permissions"):
        RoleDefaultsSpec.model_validate(
            {"target": "everyone", "permissions": {"invent_channels": True}}
        )


def test_hub_matches_expected_structure_and_channel_types() -> None:
    resources = compile_hub(_context())
    categories = [item.name for item in resources if item.kind is ResourceKind.CATEGORY]
    assert categories == ["Moderation", "The Network", "Leaders"]
    assert _resource(resources, "network_announcements").kind is ResourceKind.TEXT
    assert _resource(resources, "network_announcements").name == "📢-network-announcements"
    assert _resource(resources, "rules").community_slot == "rules"
    assert _resource(resources, "admin").community_slot == "public_updates"
    assert _resource(resources, "rules").preserve_on_uninit
    assert _resource(resources, "admin").preserve_on_uninit
    assert all(resource.id != "commands" for resource in resources)
    assert "commands" in load_layout().retired_channels


@pytest.mark.parametrize(
    ("category_id", "channel_ids"),
    [
        ("moderation", ("admin", "join_requests", "network_announcements")),
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
            if category_id == "moderation" and channel_id == "admin":
                assert actual.view_channel == expected.view_channel
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


def test_admin_adds_slash_permission_without_repeating_moderator_defaults() -> None:
    ctx = _context()
    resources = compile_hub(ctx)
    moderation = _resource(resources, "moderation")
    admin = _resource(resources, "admin")
    assert _overwrite(moderation, ctx.moderator_role).use_application_commands is None
    assert _overwrite(admin, ctx.moderator_role).use_application_commands is True
    assert _overwrite(admin, ctx.moderator_role).manage_channels is True


def test_client_layout_has_one_profile_and_subscription_pair() -> None:
    ctx = _context()
    base = compile_client(ctx, include_subscribed=False)
    assert [item.id for item in base] == ["client", "profile"]
    subscribed = compile_client(ctx, include_subscribed=True)
    assert [item.id for item in subscribed] == [
        "client",
        "profile",
        "publish",
        "subscribe",
        "announcements",
    ]
    assert _resource(subscribed, "profile").name == "📚-acme-profile"
    assert _resource(subscribed, "publish").name == "📤-acme-stingers-publish"
    assert _resource(subscribed, "subscribe").name == "🌐-acme-stingers-subscribe"
    assert _resource(subscribed, "announcements").name == "📢-acme-stingers-announcements"
    assert _resource(subscribed, "subscribe").kind is ResourceKind.ANNOUNCEMENT


def test_compile_client_emits_all_subscriptions_in_one_pass() -> None:
    ctx = _context(network_key=None)
    resources = compile_client(
        ctx,
        subscriptions=[
            SubscriptionCompileInput(network_key="stingers"),
            SubscriptionCompileInput(network_key="wasps"),
        ],
        category_position=3,
    )
    assert [item.id for item in resources] == [
        "client",
        "profile",
        "publish:stingers",
        "subscribe:stingers",
        "announcements:stingers",
        "publish:wasps",
        "subscribe:wasps",
        "announcements:wasps",
    ]
    assert _resource(resources, "client").position == 3
    assert _resource(resources, "publish:stingers").name == "📤-acme-stingers-publish"
    assert _resource(resources, "publish:wasps").name == "📤-acme-wasps-publish"


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
    assert ctx.access_role not in publish.overwrites
    assert ctx.access_role in publish.managed_targets


def test_compiled_recipes_use_bot_access_role_not_bot_member() -> None:
    ctx = _context(clients=2)
    bot_access = discord.utils.get(ctx.guild.roles, name="The Network Bot Access")
    assert bot_access is not None
    for resource in [*compile_hub(ctx), *compile_client(ctx, include_subscribed=True)]:
        assert bot_access in resource.overwrites
        assert ctx.bot_member not in resource.overwrites
        assert ctx.bot_member in resource.managed_targets
        assert ctx.operator_role in resource.managed_targets
        assert set(ctx.client_roles) <= set(resource.managed_targets)
        assert ctx.operator_role in resource.managed_targets
        assert set(ctx.client_roles) <= set(resource.managed_targets)


def test_missing_bot_access_role_is_not_replaced_with_bot_member() -> None:
    ctx = _context()
    ctx.guild.roles = [role for role in ctx.guild.roles if role.name != "The Network Bot Access"]
    for resource in compile_hub(ctx):
        assert ctx.bot_member not in resource.overwrites
