from __future__ import annotations

from bot.core.triggers import TriggerKind, TriggerSpec

TRIGGERS: tuple[TriggerSpec, ...] = (
    TriggerSpec(
        id="app.initialize_relay",
        kind=TriggerKind.APP_EVENT,
        recipe="app.initialize_relay",
        event="app.services",
    ),
    TriggerSpec(
        id="app.validate_features",
        kind=TriggerKind.APP_EVENT,
        recipe="app.validate_features",
        event="app.setup",
    ),
    TriggerSpec(
        id="app.register_persistent_views",
        kind=TriggerKind.APP_EVENT,
        recipe="app.register_persistent_views",
        event="app.setup",
    ),
    TriggerSpec(
        id="app.sync_subscription_stickies",
        kind=TriggerKind.APP_EVENT,
        recipe="app.sync_subscription_stickies",
        event="app.ready",
    ),
    TriggerSpec(
        id="app.sync_changelog",
        kind=TriggerKind.APP_EVENT,
        recipe="app.sync_changelog",
        event="app.ready",
    ),
    TriggerSpec(
        id="relay.on_message",
        kind=TriggerKind.DISCORD_EVENT,
        recipe="relay.on_message",
        event="discord.message",
    ),
    TriggerSpec(
        id="subscription.webhook_updated",
        kind=TriggerKind.DISCORD_EVENT,
        recipe="subscription.webhook_updated",
        event="discord.webhooks_update",
    ),
)
