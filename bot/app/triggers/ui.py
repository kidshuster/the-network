from __future__ import annotations

from bot.core.triggers import TriggerKind, TriggerSpec

TRIGGERS: tuple[TriggerSpec, ...] = (
    TriggerSpec(id="request.submit", kind=TriggerKind.MODAL, recipe="request.submit"),
    TriggerSpec(id="request.join.open", kind=TriggerKind.BUTTON, recipe="request.join.open"),
    TriggerSpec(id="request.approve", kind=TriggerKind.BUTTON, recipe="request.approve"),
    TriggerSpec(id="request.deny", kind=TriggerKind.BUTTON, recipe="request.deny"),
    TriggerSpec(id="network.create", kind=TriggerKind.MODAL, recipe="network.create"),
    TriggerSpec(id="network.create.open", kind=TriggerKind.BUTTON, recipe="network.create.open"),
    TriggerSpec(id="network.delete", kind=TriggerKind.MODAL, recipe="network.delete"),
    TriggerSpec(id="network.delete.open", kind=TriggerKind.BUTTON, recipe="network.delete.open"),
    TriggerSpec(id="subscription.create", kind=TriggerKind.BUTTON, recipe="subscription.create"),
    TriggerSpec(
        id="subscription.confirm_connected",
        kind=TriggerKind.BUTTON,
        recipe="subscription.confirm_connected",
    ),
    TriggerSpec(id="subscription.leave", kind=TriggerKind.BUTTON, recipe="subscription.leave"),
    TriggerSpec(
        id="subscription.blacklist.open",
        kind=TriggerKind.BUTTON,
        recipe="subscription.blacklist.open",
    ),
    TriggerSpec(id="blacklist.replace", kind=TriggerKind.SELECT, recipe="blacklist.replace"),
    TriggerSpec(
        id="client.toggle_timecode",
        kind=TriggerKind.BUTTON,
        recipe="client.toggle_timecode",
    ),
    TriggerSpec(
        id="client.toggle_read_only",
        kind=TriggerKind.BUTTON,
        recipe="client.toggle_read_only",
    ),
    TriggerSpec(id="client.edit.open", kind=TriggerKind.BUTTON, recipe="client.edit.open"),
    TriggerSpec(id="client.edit_profile", kind=TriggerKind.MODAL, recipe="client.edit_profile"),
    TriggerSpec(
        id="client.delete.confirm",
        kind=TriggerKind.BUTTON,
        recipe="client.delete.confirm",
    ),
    TriggerSpec(id="client.delete", kind=TriggerKind.BUTTON, recipe="client.delete"),
    TriggerSpec(
        id="admin.client.delete.open",
        kind=TriggerKind.BUTTON,
        recipe="admin.client.delete.open",
    ),
    TriggerSpec(id="ui.dismiss", kind=TriggerKind.BUTTON, recipe="ui.dismiss"),
)
