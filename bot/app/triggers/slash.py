from __future__ import annotations

from bot.core.triggers import TriggerKind, TriggerSpec

_SERVER_GROUP = "Initialize and maintain the Discord hub server"

TRIGGERS: tuple[TriggerSpec, ...] = (
    TriggerSpec(
        id="server.init",
        kind=TriggerKind.SLASH,
        recipe="server.init",
        slash_group="server",
        slash_name="init",
        slash_description="Set up hub categories/channels and run permission smoke checks",
        slash_group_description=_SERVER_GROUP,
        default_permissions=("manage_guild",),
        presenter="present.server.init",
    ),
    TriggerSpec(
        id="server.probe",
        kind=TriggerKind.SLASH,
        recipe="server.probe",
        slash_group="server",
        slash_name="probe",
        slash_description="Run read-only checks for hub permissions, layout, and community slots",
        slash_group_description=_SERVER_GROUP,
        default_permissions=("manage_guild",),
        presenter="present.server.probe",
    ),
    TriggerSpec(
        id="server.uninit",
        kind=TriggerKind.SLASH,
        recipe="server.uninit",
        slash_group="server",
        slash_name="uninit",
        slash_description="Remove managed hub resources while preserving community channels",
        slash_group_description=_SERVER_GROUP,
        default_permissions=("manage_guild",),
        presenter="present.server.uninit",
    ),
    TriggerSpec(
        id="server.sync_join_guide",
        kind=TriggerKind.SLASH,
        recipe="server.sync_join_guide",
        slash_group="server",
        slash_name="sync-join-guide",
        slash_description="Refresh the join guide in the join-the-network channel",
        slash_group_description=_SERVER_GROUP,
        default_permissions=("manage_guild",),
        presenter="present.server.sync_join_guide",
    ),
)
