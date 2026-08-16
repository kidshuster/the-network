from __future__ import annotations

from bot.core.triggers import TriggerKind, TriggerSpec

TRIGGERS: tuple[TriggerSpec, ...] = (
    TriggerSpec(id="request.submit", kind=TriggerKind.MODAL, recipe="request.submit"),
    TriggerSpec(id="request.approve", kind=TriggerKind.BUTTON, recipe="request.approve"),
    TriggerSpec(id="request.deny", kind=TriggerKind.BUTTON, recipe="request.deny"),
    TriggerSpec(id="network.create", kind=TriggerKind.MODAL, recipe="network.create"),
    TriggerSpec(id="network.delete", kind=TriggerKind.MODAL, recipe="network.delete"),
    TriggerSpec(id="subscription.create", kind=TriggerKind.BUTTON, recipe="subscription.create"),
    TriggerSpec(
        id="subscription.confirm_connected",
        kind=TriggerKind.BUTTON,
        recipe="subscription.confirm_connected",
    ),
    TriggerSpec(id="subscription.leave", kind=TriggerKind.BUTTON, recipe="subscription.leave"),
    TriggerSpec(id="blacklist.replace", kind=TriggerKind.BUTTON, recipe="blacklist.replace"),
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
    TriggerSpec(id="client.edit_profile", kind=TriggerKind.MODAL, recipe="client.edit_profile"),
    TriggerSpec(id="client.delete", kind=TriggerKind.BUTTON, recipe="client.delete"),
)
