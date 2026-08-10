from __future__ import annotations

import pytest
from permission_truth_table import (
    CATEGORY_LOCKDOWN,
    POST_LOCKDOWN,
    PermissionScenarioContext,
    PermissionTruthTableScenario,
    assert_truth_table,
    make_permission_context,
)

from bot.services.guild_permissions import (
    build_changelog_channel_overwrites,
    build_client_category_overwrites,
    build_client_profile_channel_overwrites,
    build_client_publish_channel_overwrites,
    build_client_subscribe_channel_overwrites,
    build_commands_channel_overwrites,
    build_join_channel_overwrites,
    build_leaders_category_overwrites,
    build_leaders_channel_overwrites,
    build_moderation_staff_overwrites,
    build_server_feed_channel_overwrites,
    build_subscribe_announcement_channel_overwrites,
    build_subscribe_category_overwrites,
    build_welcome_sink_overwrites,
)

HUB_SCENARIOS: tuple[PermissionTruthTableScenario, ...] = (
    PermissionTruthTableScenario(
        name="hub_moderation_category",
        policy="hub",
        build=lambda ctx: build_moderation_staff_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.human_mod,
            for_category=True,
        ),
        expectations={
            "everyone": {"view_channel": False, **CATEGORY_LOCKDOWN},
            "moderator": {
                "view_channel": True,
                "send_messages": True,
                "manage_channels": True,
                "manage_webhooks": True,
            },
            "bot": {
                "view_channel": True,
                "manage_channels": True,
                "manage_webhooks": True,
            },
            "access": None,
            "client": None,
        },
    ),
    PermissionTruthTableScenario(
        name="hub_moderation_channel",
        policy="hub",
        build=lambda ctx: build_moderation_staff_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.human_mod,
        ),
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
    PermissionTruthTableScenario(
        name="hub_commands_channel",
        policy="hub",
        build=lambda ctx: build_commands_channel_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.human_mod,
        ),
        expectations={
            "everyone": {"view_channel": False},
            "moderator": {
                "view_channel": True,
                "use_application_commands": True,
            },
            "bot": None,
        },
    ),
    PermissionTruthTableScenario(
        name="hub_join_channel",
        policy="hub",
        build=lambda ctx: build_join_channel_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.access,
            ctx.human_mod,
        ),
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
    PermissionTruthTableScenario(
        name="hub_subscribe_category",
        policy="hub",
        build=lambda ctx: build_subscribe_category_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.access,
            ctx.human_mod,
        ),
        expectations={
            "everyone": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "client": None,
        },
    ),
    PermissionTruthTableScenario(
        name="hub_subscribe_announcement_channel",
        policy="hub",
        build=lambda ctx: build_subscribe_announcement_channel_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.access,
            ctx.human_mod,
        ),
        expectations={
            "everyone": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "moderator": {
                "view_channel": True,
                "send_messages": True,
                "create_public_threads": None,
            },
        },
    ),
    PermissionTruthTableScenario(
        name="hub_server_feed_channel",
        policy="hub",
        build=lambda ctx: build_server_feed_channel_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.server_role,
            ctx.access,
            ctx.human_mod,
        ),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "server": {
                "view_channel": True,
                "manage_webhooks": True,
                "send_messages": False,
            },
            "access": {
                "view_channel": True,
                "manage_webhooks": True,
                "send_messages": False,
            },
            "client": None,
        },
        filter_for_channel=True,
    ),
    PermissionTruthTableScenario(
        name="hub_welcome_sink",
        policy="hub",
        build=lambda ctx: build_welcome_sink_overwrites(ctx.guild, ctx.bot),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "access": None,
            "bot": None,
        },
    ),
)

CLIENT_SCENARIOS: tuple[PermissionTruthTableScenario, ...] = (
    PermissionTruthTableScenario(
        name="client_category",
        policy="client",
        build=lambda ctx: build_client_category_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.client,
            ctx.access,
            ctx.human_mod,
        ),
        expectations={
            "everyone": {"view_channel": False, **CATEGORY_LOCKDOWN},
            "client": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "moderator": {"view_channel": True, "send_messages": True},
            "bot": {"view_channel": True, "manage_channels": True},
        },
    ),
    PermissionTruthTableScenario(
        name="client_profile_channel",
        policy="client",
        build=lambda ctx: build_client_profile_channel_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.client,
            ctx.access,
            ctx.human_mod,
        ),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "client": {"view_channel": True, "send_messages": False},
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "moderator": {
                "view_channel": True,
                "send_messages": True,
                "create_public_threads": True,
            },
            "bot": None,
        },
        filter_for_channel=True,
    ),
    PermissionTruthTableScenario(
        name="client_publish_channel",
        policy="client",
        build=lambda ctx: build_client_publish_channel_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.client,
            ctx.access,
            ctx.human_mod,
        ),
        expectations={
            "everyone": {"view_channel": False, **POST_LOCKDOWN},
            "client": {
                "view_channel": True,
                "send_messages": False,
                "manage_webhooks": True,
            },
            "access": {
                "view_channel": True,
                "send_messages": True,
                "manage_webhooks": True,
            },
            "bot": None,
        },
        filter_for_channel=True,
    ),
    PermissionTruthTableScenario(
        name="client_subscribe_channel",
        policy="client",
        build=lambda ctx: build_client_subscribe_channel_overwrites(
            ctx.guild,
            ctx.bot,
            ctx.client,
            ctx.access,
            ctx.human_mod,
        ),
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
        filter_for_channel=True,
    ),
)

LEADERS_SCENARIOS: tuple[PermissionTruthTableScenario, ...] = (
    PermissionTruthTableScenario(
        name="leaders_category",
        policy="leaders",
        build=lambda ctx: build_leaders_category_overwrites(
            ctx.guild,
            ctx.bot,
            [ctx.client],
            ctx.access,
            ctx.human_mod,
            operator_role=ctx.operator,
        ),
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
    PermissionTruthTableScenario(
        name="leaders_channel",
        policy="leaders",
        build=lambda ctx: build_leaders_channel_overwrites(
            ctx.guild,
            ctx.bot,
            [ctx.client],
            ctx.access,
            ctx.human_mod,
            operator_role=ctx.operator,
        ),
        expectations={
            "everyone": {"view_channel": False},
            "client": {"view_channel": True, "send_messages": True},
            "access": {"view_channel": False},
            "operator": {"view_channel": True, "manage_channels": True},
        },
        filter_for_channel=True,
    ),
    PermissionTruthTableScenario(
        name="leaders_changelog_channel",
        policy="leaders",
        build=lambda ctx: build_changelog_channel_overwrites(
            ctx.guild,
            ctx.bot,
            [ctx.client],
            ctx.access,
            ctx.human_mod,
            operator_role=ctx.operator,
        ),
        expectations={
            "everyone": {"view_channel": False},
            "client": {
                "view_channel": True,
                "send_messages": False,
                "add_reactions": False,
            },
            "moderator": {"view_channel": True, "send_messages": True},
        },
        filter_for_channel=True,
    ),
)

ALL_SCENARIOS = (*HUB_SCENARIOS, *CLIENT_SCENARIOS, *LEADERS_SCENARIOS)


@pytest.fixture
def permission_ctx() -> PermissionScenarioContext:
    return make_permission_context()


@pytest.mark.parametrize(
    "scenario",
    ALL_SCENARIOS,
    ids=[scenario.name for scenario in ALL_SCENARIOS],
)
def test_permission_truth_table(
    permission_ctx: PermissionScenarioContext,
    scenario: PermissionTruthTableScenario,
) -> None:
    assert_truth_table(scenario, permission_ctx)


def test_hub_and_client_policies_diverge_on_publish_vs_profile(
    permission_ctx: PermissionScenarioContext,
) -> None:
    """Guardrail: client publish is webhook-only; profile is view-only for the client role."""
    publish = dict(
        build_client_publish_channel_overwrites(
            permission_ctx.guild,
            permission_ctx.bot,
            permission_ctx.client,
            permission_ctx.access,
            permission_ctx.human_mod,
        )
    )
    profile = dict(
        build_client_profile_channel_overwrites(
            permission_ctx.guild,
            permission_ctx.bot,
            permission_ctx.client,
            permission_ctx.access,
            permission_ctx.human_mod,
        )
    )
    client_publish = publish[permission_ctx.client]
    client_profile = profile[permission_ctx.client]

    assert client_publish.manage_webhooks is True
    assert client_publish.send_messages is False
    assert client_profile.manage_webhooks is None
    assert client_profile.send_messages is False


def test_hub_moderation_and_client_category_both_hide_everyone(
    permission_ctx: PermissionScenarioContext,
) -> None:
    """Shared deny-everyone pattern must not collapse into the same role grants."""
    hub = dict(
        build_moderation_staff_overwrites(
            permission_ctx.guild,
            permission_ctx.bot,
            permission_ctx.human_mod,
            for_category=True,
        )
    )
    client = dict(
        build_client_category_overwrites(
            permission_ctx.guild,
            permission_ctx.bot,
            permission_ctx.client,
            permission_ctx.access,
            permission_ctx.human_mod,
        )
    )

    assert hub[permission_ctx.guild.default_role].view_channel is False
    assert client[permission_ctx.guild.default_role].view_channel is False
    assert permission_ctx.access not in hub
    assert permission_ctx.access in client
    assert permission_ctx.client not in hub
    assert permission_ctx.client in client
