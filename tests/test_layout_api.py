from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord_helpers import http_50013, make_guild_with_roles, make_role

from bot.layout import (
    ApplyMode,
    LayoutContext,
    apply_layout,
    compile_client,
    compile_hub,
    compile_hub_slice,
    preset_overwrite,
)
from bot.layout.compiler import ResourceKind
from bot.layout.loader import (
    LayoutTemplateError,
    clear_layout_cache,
    load_client_layout,
    load_hub_layout,
    load_presets,
    validate_all_layouts,
)
from bot.layout.schema import HubLayoutSpec

CapabilityMap = dict[str, bool | None]
RoleKey = str

TRACKED_CAPABILITIES: tuple[str, ...] = (
    "view_channel",
    "read_message_history",
    "send_messages",
    "embed_links",
    "attach_files",
    "manage_webhooks",
    "manage_channels",
    "manage_messages",
    "create_public_threads",
    "send_messages_in_threads",
    "add_reactions",
    "use_application_commands",
)

POST_LOCKDOWN: CapabilityMap = {
    "send_messages": False,
    "add_reactions": False,
    "create_public_threads": False,
    "send_messages_in_threads": False,
}

CATEGORY_LOCKDOWN: CapabilityMap = {
    "send_messages": False,
    "add_reactions": False,
}


@dataclass(frozen=True)
class ScenarioCtx:
    guild: MagicMock
    bot: MagicMock
    human_mod: MagicMock
    access: MagicMock
    operator: MagicMock
    client: MagicMock

    def role(self, key: RoleKey) -> discord.Role | discord.Member:
        return {
            "everyone": self.guild.default_role,
            "access": self.access,
            "client": self.client,
            "moderator": self.human_mod,
            "bot": self.bot,
            "operator": self.operator,
        }[key]


@dataclass(frozen=True)
class OverwriteScenario:
    name: str
    build: Callable[[ScenarioCtx], Mapping[Any, discord.PermissionOverwrite]]
    expectations: dict[RoleKey, CapabilityMap | None]


def _make_ctx() -> ScenarioCtx:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    client = make_role(name="Client: Acme", role_id=60, position=1)
    guild.roles = [*guild.roles, client]
    return ScenarioCtx(guild, bot, human_mod, access, operator, client)


def _layout_ctx(ctx: ScenarioCtx) -> LayoutContext:
    return LayoutContext(
        guild=ctx.guild,
        bot_member=ctx.bot,
        access_role=ctx.access,
        moderator_role=ctx.human_mod,
        operator_role=ctx.operator,
        client_role=ctx.client,
        client_roles=(ctx.client,),
        server_name="Acme",
        slug="acme",
        network_key="stingers",
    )


def _hub_overwrites(ctx: ScenarioCtx, resource_id: str, *, category: bool | None = None):
    for resource in compile_hub(_layout_ctx(ctx)):
        if resource.id != resource_id:
            continue
        if category is True and resource.kind is not ResourceKind.CATEGORY:
            continue
        if category is False and resource.kind is ResourceKind.CATEGORY:
            continue
        return resource.overwrites
    raise AssertionError(f"resource {resource_id!r} not found")


def _client_overwrites(
    ctx: ScenarioCtx,
    resource_id: str,
    *,
    include_subscribed: bool = False,
):
    resources = compile_client(
        _layout_ctx(ctx),
        include_subscribed=include_subscribed,
        channel_ids=None if resource_id == "client" else {resource_id},
    )
    return next(r.overwrites for r in resources if r.id == resource_id)


def _assert_capabilities(
    overwrite: discord.PermissionOverwrite,
    expected: CapabilityMap,
    *,
    scenario: str,
    role: RoleKey,
) -> None:
    for capability, value in expected.items():
        actual = getattr(overwrite, capability)
        assert actual is value, (
            f"{scenario} / {role} / {capability}: expected {value!r}, got {actual!r}"
        )


def _assert_scenario(scenario: OverwriteScenario, ctx: ScenarioCtx) -> None:
    overwrites = dict(scenario.build(ctx))
    for role_key, expected in scenario.expectations.items():
        role = ctx.role(role_key)
        if expected is None:
            assert role not in overwrites, f"{scenario.name}: {role_key} should be absent"
            continue
        assert role in overwrites, f"{scenario.name}: {role_key} missing"
        _assert_capabilities(
            overwrites[role],
            expected,
            scenario=scenario.name,
            role=role_key,
        )


# --- schema / compile -------------------------------------------------------


def test_validate_all_layouts_ok() -> None:
    clear_layout_cache()
    validate_all_layouts()
    assert load_presets().presets
    assert load_hub_layout().categories
    assert load_client_layout().category.name


def test_hub_community_slots_unique() -> None:
    hub = load_hub_layout()
    slots = [c.community_slot for c in hub.channels if c.community_slot]
    assert slots.count("rules") == 1
    assert slots.count("moderators") == 1


def test_hub_rejects_duplicate_community_slot() -> None:
    with pytest.raises(ValueError):
        HubLayoutSpec.model_validate(
            {
                "kind": "hub_layout",
                "categories": [{"id": "network", "name": "The Network"}],
                "channels": [
                    {
                        "id": "rules",
                        "name": "rules",
                        "category": "network",
                        "community_slot": "rules",
                    },
                    {
                        "id": "rules2",
                        "name": "rules-2",
                        "category": "network",
                        "community_slot": "rules",
                    },
                ],
            }
        )


def test_compile_hub_includes_categories_and_community_channels() -> None:
    ctx = _make_ctx()
    clients = (
        make_role(name="Client: A", role_id=61, position=1),
        make_role(name="Client: B", role_id=62, position=1),
    )
    layout_ctx = LayoutContext(
        guild=ctx.guild,
        bot_member=ctx.bot,
        access_role=ctx.access,
        moderator_role=ctx.human_mod,
        operator_role=ctx.operator,
        client_roles=clients,
    )
    resources = compile_hub(layout_ctx)
    ids = {r.id for r in resources}
    assert {
        "moderation",
        "network",
        "leaders",
        "rules",
        "moderator_only",
        "join_the_network",
        "commands",
        "changelog",
        "network_announcements",
    } <= ids
    rules = next(r for r in resources if r.id == "rules")
    assert rules.community_slot == "rules"
    assert rules.preserve_on_uninit is True
    leaders_cat = next(
        r for r in resources if r.id == "leaders" and r.kind is ResourceKind.CATEGORY
    )
    assert clients[0] in leaders_cat.overwrites
    assert clients[1] in leaders_cat.overwrites


def test_compile_hub_slice_selects_leaders() -> None:
    ctx = _make_ctx()
    resources = compile_hub_slice(
        _layout_ctx(ctx),
        category_ids={"leaders"},
        channel_ids={"leaders", "changelog"},
    )
    ids = {r.id for r in resources}
    assert "leaders" in ids
    assert "changelog" in ids
    assert "moderation" not in ids


def test_compile_client_profile_and_subscribed() -> None:
    ctx = _make_ctx()
    base = compile_client(_layout_ctx(ctx))
    assert {r.id for r in base} == {"client", "profile"}
    assert next(r for r in base if r.id == "client").name == "Acme"
    assert next(r for r in base if r.id == "profile").name == "acme-profile"

    subscribed = compile_client(_layout_ctx(ctx), include_subscribed=True)
    ids = {r.id for r in subscribed}
    assert {"publish", "subscribe"} <= ids
    publish = next(r for r in subscribed if r.id == "publish")
    assert publish.name == "acme-stingers-publish"
    assert ctx.client in publish.overwrites


def test_unknown_preset_fails_validation() -> None:
    presets = load_presets()
    assert "everyone_hidden" in presets.presets
    with pytest.raises(LayoutTemplateError, match="unknown preset"):
        raise LayoutTemplateError("hub channel rules: unknown preset 'not_a_real_preset'")


# --- overwrite truth table (YAML-driven) ------------------------------------


OVERWRITE_SCENARIOS: tuple[OverwriteScenario, ...] = (
    OverwriteScenario(
        name="hub_moderation_category",
        build=lambda ctx: _hub_overwrites(ctx, "moderation"),
        expectations={
            "everyone": {"view_channel": False, **CATEGORY_LOCKDOWN},
            "moderator": {
                "view_channel": True,
                "send_messages": True,
                "manage_channels": True,
                "use_application_commands": True,
            },
            "bot": {"view_channel": True, "manage_channels": True},
            "access": None,
            "client": None,
        },
    ),
    OverwriteScenario(
        name="hub_moderation_channel",
        build=lambda ctx: _hub_overwrites(ctx, "moderator_only"),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "moderator": {
                "view_channel": True,
                "send_messages": True,
                "create_public_threads": True,
            },
            "bot": None,
            "access": None,
        },
    ),
    OverwriteScenario(
        name="hub_commands_channel",
        build=lambda ctx: _hub_overwrites(ctx, "commands"),
        expectations={
            "everyone": {"view_channel": False},
            "moderator": {
                "view_channel": True,
                "use_application_commands": True,
            },
            "bot": None,
        },
    ),
    OverwriteScenario(
        name="hub_join_channel",
        build=lambda ctx: _hub_overwrites(ctx, "join_the_network"),
        expectations={
            "everyone": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "moderator": {"view_channel": True, "send_messages": True},
        },
    ),
    OverwriteScenario(
        name="hub_network_category",
        build=lambda ctx: _hub_overwrites(ctx, "network"),
        expectations={
            "everyone": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "bot": {"view_channel": True, "manage_channels": True},
        },
    ),
    OverwriteScenario(
        name="hub_network_announcements",
        build=lambda ctx: _hub_overwrites(ctx, "network_announcements"),
        expectations={
            "everyone": {"view_channel": False},
            "moderator": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "operator": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
        },
    ),
    OverwriteScenario(
        name="client_category",
        build=lambda ctx: _client_overwrites(ctx, "client"),
        expectations={
            "everyone": {"view_channel": False, **CATEGORY_LOCKDOWN},
            "client": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "bot": {"view_channel": True, "manage_channels": True},
        },
    ),
    OverwriteScenario(
        name="client_profile_channel",
        build=lambda ctx: _client_overwrites(ctx, "profile"),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "client": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "bot": None,
        },
    ),
    OverwriteScenario(
        name="client_publish_channel",
        build=lambda ctx: _client_overwrites(ctx, "publish", include_subscribed=True),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "client": {
                "view_channel": True,
                "send_messages": False,
                "manage_webhooks": True,
            },
            "access": {
                "view_channel": True,
                "send_messages": False,
                "manage_webhooks": True,
            },
            "bot": None,
        },
    ),
    OverwriteScenario(
        name="client_subscribe_channel",
        build=lambda ctx: _client_overwrites(ctx, "subscribe", include_subscribed=True),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "client": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "bot": None,
        },
    ),
    OverwriteScenario(
        name="leaders_category",
        build=lambda ctx: _hub_overwrites(ctx, "leaders", category=True),
        expectations={
            "everyone": {"view_channel": False},
            "client": {
                "view_channel": True,
                "send_messages": True,
                "add_reactions": True,
            },
            "access": {"view_channel": False},
            "operator": {"view_channel": True, "manage_channels": True},
        },
    ),
    OverwriteScenario(
        name="leaders_channel",
        build=lambda ctx: _hub_overwrites(ctx, "leaders", category=False),
        expectations={
            "everyone": {"view_channel": False},
            "client": {"view_channel": True, "send_messages": True},
            "access": {"view_channel": False},
            "operator": {"view_channel": True, "manage_channels": True},
            "moderator": {"view_channel": True, "send_messages": True},
        },
    ),
    OverwriteScenario(
        name="leaders_changelog_channel",
        build=lambda ctx: _hub_overwrites(ctx, "changelog"),
        expectations={
            "everyone": {"view_channel": False},
            "client": {
                "view_channel": True,
                "send_messages": False,
                "add_reactions": False,
            },
            "moderator": {"view_channel": True, "send_messages": True},
        },
    ),
)


@pytest.mark.parametrize(
    "scenario",
    OVERWRITE_SCENARIOS,
    ids=[s.name for s in OVERWRITE_SCENARIOS],
)
def test_layout_overwrite_truth_table(scenario: OverwriteScenario) -> None:
    _assert_scenario(scenario, _make_ctx())


def test_publish_vs_profile_client_policy_divergence() -> None:
    ctx = _make_ctx()
    publish = dict(_client_overwrites(ctx, "publish", include_subscribed=True))
    profile = dict(_client_overwrites(ctx, "profile"))
    assert publish[ctx.client].manage_webhooks is True
    assert publish[ctx.client].send_messages is False
    assert profile[ctx.client].manage_webhooks is None
    assert profile[ctx.client].send_messages is False


def test_hub_moderation_and_client_category_diverge() -> None:
    ctx = _make_ctx()
    hub = dict(_hub_overwrites(ctx, "moderation"))
    client = dict(_client_overwrites(ctx, "client"))
    assert hub[ctx.guild.default_role].view_channel is False
    assert client[ctx.guild.default_role].view_channel is False
    assert ctx.access not in hub
    assert ctx.access in client
    assert ctx.client not in hub
    assert ctx.client in client


# --- apply_layout stress ----------------------------------------------------


def _layout_guild() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    guild.categories = []
    guild.text_channels = []
    bot.guild = guild
    bot.guild_permissions.manage_channels = True
    return guild, bot, human_mod, access, operator


def _make_category(name: str, cat_id: int) -> MagicMock:
    cat = MagicMock(spec=discord.CategoryChannel)
    cat.id = cat_id
    cat.name = name
    cat.channels = []
    cat.overwrites = {}
    cat.edit = AsyncMock()
    cat.delete = AsyncMock()
    return cat


def _make_text(
    name: str,
    channel_id: int,
    *,
    category: MagicMock | None = None,
) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.name = name
    channel.category = category
    channel.category_id = category.id if category is not None else None
    channel.overwrites = {}
    channel.topic = None
    channel.edit = AsyncMock()
    channel.delete = AsyncMock()
    channel.is_news = MagicMock(return_value=False)
    return channel


@pytest.mark.asyncio
async def test_apply_layout_ensure_creates_missing_category() -> None:
    guild, bot, human_mod, access, operator = _layout_guild()
    created = _make_category("Acme", 500)
    guild.create_category = AsyncMock(return_value=created)

    ctx = LayoutContext(
        guild=guild,
        bot_member=bot,
        access_role=access,
        moderator_role=human_mod,
        operator_role=operator,
        client_role=make_role(name="Client: Acme", role_id=60, position=1),
        server_name="Acme",
        slug="acme",
        reason="test",
    )
    with patch(
        "bot.hub.notifications.ensure_guild_only_mention_notifications",
        new=AsyncMock(),
    ):
        batch = await apply_layout(
            ctx,
            compile_client(ctx, channel_ids={"client"}),
            mode=ApplyMode.ENSURE,
        )
    assert batch.success
    assert isinstance(batch.resource("client"), discord.CategoryChannel)
    guild.create_category.assert_awaited()


@pytest.mark.asyncio
async def test_apply_layout_reconcile_only_skips_missing() -> None:
    guild, bot, human_mod, access, operator = _layout_guild()
    ctx = LayoutContext(
        guild=guild,
        bot_member=bot,
        access_role=access,
        moderator_role=human_mod,
        operator_role=operator,
        client_role=make_role(name="Client: Acme", role_id=60, position=1),
        server_name="Acme",
        slug="acme",
        reason="test",
    )
    batch = await apply_layout(
        ctx,
        compile_client(ctx),
        mode=ApplyMode.RECONCILE_ONLY,
    )
    assert not batch.success
    assert any("missing" in (r.detail or "") for r in batch.results)


@pytest.mark.asyncio
async def test_apply_layout_continues_after_category_failure() -> None:
    guild, bot, human_mod, access, operator = _layout_guild()
    guild.create_category = AsyncMock(side_effect=http_50013())
    channel = _make_text("acme-profile", 801)
    guild.create_text_channel = AsyncMock(return_value=channel)

    client_role = make_role(name="Client: Acme", role_id=60, position=1)
    ctx = LayoutContext(
        guild=guild,
        bot_member=bot,
        access_role=access,
        moderator_role=human_mod,
        operator_role=operator,
        client_role=client_role,
        server_name="Acme",
        slug="acme",
        reason="test",
    )
    with patch(
        "bot.hub.notifications.ensure_guild_only_mention_notifications",
        new=AsyncMock(),
    ):
        batch = await apply_layout(ctx, compile_client(ctx), mode=ApplyMode.ENSURE)
    assert any(r.resource_id == "client" and not r.success for r in batch.results)
    assert any(r.resource_id == "profile" for r in batch.results)


@pytest.mark.asyncio
async def test_apply_layout_teardown_preserves_community_and_skips_client() -> None:
    guild, bot, human_mod, access, operator = _layout_guild()
    moderation = _make_category("Moderation", 1)
    network = _make_category("The Network", 2)
    client_cat = _make_category("Acme", 3)
    rules = _make_text("rules", 10, category=network)
    join = _make_text("join-the-network", 11, category=network)
    guild.categories = [moderation, network, client_cat]
    guild.text_channels = [rules, join]
    guild.rules_channel = rules
    guild.get_channel = MagicMock(
        side_effect=lambda cid: {
            join.id: join,
            network.id: network,
            moderation.id: moderation,
        }.get(cid)
    )

    async def fake_delete(g: discord.Guild, channel_id: int, *, label: str) -> bool:
        _ = (g, label)
        return channel_id in {join.id, network.id, moderation.id}

    ctx = LayoutContext(
        guild=guild,
        bot_member=bot,
        access_role=access,
        moderator_role=human_mod,
        operator_role=operator,
        reason="teardown",
    )
    with patch("bot.discord_util.cleanup.delete_channel", new=fake_delete):
        batch = await apply_layout(
            ctx,
            compile_hub(ctx),
            mode=ApplyMode.TEARDOWN_HUB,
        )

    detach_ids = {r.resource_id for r in batch.results if r.resource_id.startswith("detach:")}
    delete_ids = {r.resource_id for r in batch.results if r.resource_id.startswith("delete")}
    assert "detach:rules" in detach_ids
    assert "delete:join-the-network" in delete_ids
    assert not any("Acme" in rid for rid in delete_ids)
    rules.edit.assert_awaited()


def test_preset_overwrite_everyone_hidden() -> None:
    hidden = preset_overwrite("everyone_hidden")
    assert hidden.view_channel is False
    assert hidden.create_public_threads is False
