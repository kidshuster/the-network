from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from tests.core.probes import ProbeOutcome

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios"


@dataclass
class MockClient:
    name: str
    smoke: bool = False
    role: bool = True
    category: bool = True
    profile: bool = True
    subscriptions: set[str] = field(default_factory=set)


@dataclass
class MockDiscordState:
    layout_present: bool = True
    permissions_valid: bool = True
    leaders_access: bool = True
    announcement_channel_regular: bool = True
    missing_channels: set[str] = field(default_factory=set)
    misplaced_channels: set[str] = field(default_factory=set)
    wrong_channel_types: set[str] = field(default_factory=set)
    stale_permission_targets: set[str] = field(default_factory=set)
    stale_roles: set[str] = field(default_factory=set)
    duplicate_channels: set[str] = field(default_factory=set)
    hidden_community_channels: set[str] = field(default_factory=set)
    clients: dict[str, MockClient] = field(default_factory=dict)
    artifacts: set[str] = field(default_factory=set)
    operations: list[str] = field(default_factory=list)
    protected_snapshot: dict[str, tuple[Any, ...]] = field(default_factory=dict)

    def snapshot_protected(self) -> None:
        self.protected_snapshot = {
            name: (
                client.role,
                client.category,
                client.profile,
                tuple(sorted(client.subscriptions)),
            )
            for name, client in self.clients.items()
            if not client.smoke
        }

    def assert_protected(self) -> None:
        current = {
            name: (
                client.role,
                client.category,
                client.profile,
                tuple(sorted(client.subscriptions)),
            )
            for name, client in self.clients.items()
            if not client.smoke
        }
        if current != self.protected_snapshot:
            raise RuntimeError(
                f"protected clients changed: expected={self.protected_snapshot}, current={current}"
            )


@dataclass
class MockContext:
    state: MockDiscordState


def load_mock_context(name: str = "healthy") -> MockContext:
    path = SCENARIO_DIR / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(sorted(item.stem for item in SCENARIO_DIR.glob("*.yaml")))
        raise ValueError(f"Unknown mock scenario {name!r}; available: {available}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    state = MockDiscordState(
        layout_present=bool(payload.get("layout_present", True)),
        permissions_valid=bool(payload.get("permissions_valid", True)),
        leaders_access=bool(payload.get("leaders_access", True)),
        announcement_channel_regular=bool(
            payload.get("announcement_channel_regular", True)
        ),
        missing_channels=set(payload.get("missing_channels", [])),
        misplaced_channels=set(payload.get("misplaced_channels", [])),
        wrong_channel_types=set(payload.get("wrong_channel_types", [])),
        stale_permission_targets=set(payload.get("stale_permission_targets", [])),
        stale_roles=set(payload.get("stale_roles", [])),
        duplicate_channels=set(payload.get("duplicate_channels", [])),
        hidden_community_channels=set(payload.get("hidden_community_channels", [])),
        artifacts=set(payload.get("artifacts", [])),
    )
    for raw in payload.get("clients", []):
        client = MockClient(
            name=str(raw["name"]),
            smoke=bool(raw.get("smoke", False)),
            role=bool(raw.get("role", True)),
            category=bool(raw.get("category", True)),
            profile=bool(raw.get("profile", True)),
            subscriptions=set(raw.get("subscriptions", [])),
        )
        state.clients[client.name] = client
    state.snapshot_protected()
    return MockContext(state)


async def run_mock_probe(
    name: str,
    context: MockContext,
    *,
    pause_after: bool = False,
) -> ProbeOutcome:
    # Mock calls share the live backend contract but never wait for Discord buckets.
    _ = pause_after
    state = context.state
    state.operations.append(name)

    if name == "artifacts.cleanup":
        count = len(state.artifacts)
        state.artifacts.clear()
        return ProbeOutcome("artifact cleanup", f"removed {count} stale artifact(s)")
    if name == "permissions.provision":
        if not state.permissions_valid:
            raise RuntimeError("simulated Discord permission denial")
        state.artifacts.update({"probe-role", "probe-category", "probe-webhook"})
        state.artifacts.difference_update({"probe-role", "probe-category", "probe-webhook"})
        return ProbeOutcome("permission/provision", "simulated create/overwrite/delete passed")
    if name == "onboarding.join_approval":
        state.clients["Smoke Accept mock"] = MockClient(
            "Smoke Accept mock", smoke=True, subscriptions={"smoke"}
        )
        del state.clients["Smoke Accept mock"]
        return ProbeOutcome("join approval", "accept, subscribe, cleanup, and deny passed")
    if name == "relay.setup_welcome":
        return ProbeOutcome("setup/welcome relay", "sticky and welcome delivery passed")
    if name == "relay.hub_announcement":
        if not state.announcement_channel_regular:
            raise RuntimeError("network-announcements is not a regular text channel")
        return ProbeOutcome("hub announcement relay", "fan-out dispatch passed")
    if name == "hub.rebuild":
        smoke = MockClient("Smoke Rebuild mock", smoke=True, subscriptions={"smoke"})
        state.clients[smoke.name] = smoke
        state.layout_present = False
        state.layout_present = True
        state.assert_protected()
        return ProbeOutcome("hub rebuild", "client resources and subscription preserved")
    if name == "hub.operator":
        if not state.permissions_valid:
            raise RuntimeError("operator permissions are invalid")
        return ProbeOutcome("operator setup", "role hierarchy valid")
    if name == "hub.manage_server":
        return ProbeOutcome("manage server", "notification setting supported")
    if name == "hub.moderator_channel":
        if "moderator-only" in state.hidden_community_channels:
            raise RuntimeError("moderator-only exists but denies the bot view access")
        if "moderator-only" in state.misplaced_channels:
            raise RuntimeError("moderator-only channel is outside Moderation")
        if not state.layout_present:
            raise RuntimeError("moderator-only channel is missing")
        return ProbeOutcome("moderator-only channel", "community channel placement valid")
    if name == "hub.layout":
        if not state.layout_present:
            raise RuntimeError("hub layout resources are missing")
        problems = sorted(
            state.missing_channels
            | state.misplaced_channels
            | state.wrong_channel_types
            | state.duplicate_channels
        )
        if problems:
            raise RuntimeError("malformed hub channels: " + ", ".join(problems))
        return ProbeOutcome("hub layout", "compiled layout matches simulated guild")
    if name == "hub.announcement_channel":
        if not state.announcement_channel_regular:
            raise RuntimeError("network-announcements must be a regular text channel")
        return ProbeOutcome("hub announcements wiring", "direct relay dispatch configured")
    if name == "hub.leaders_access":
        if not state.leaders_access or "leaders-channel" in state.stale_permission_targets:
            raise RuntimeError("client role cannot view leaders channel")
        return ProbeOutcome("leaders access", "all client roles can view leaders")
    if name == "hub.leaders_drift":
        state.leaders_access = False
        state.stale_permission_targets.add("leaders-channel")
        state.leaders_access = True
        state.stale_permission_targets.discard("leaders-channel")
        return ProbeOutcome("leaders drift", "stale overwrite rectified")
    if name in {"hub.client_layout_reinit", "hub.reinit"}:
        if state.hidden_community_channels:
            blockers = ", ".join(sorted(state.hidden_community_channels))
            raise RuntimeError(f"community channels hidden from bot: {blockers}")
        state.layout_present = True
        state.permissions_valid = True
        state.leaders_access = True
        state.missing_channels.clear()
        state.misplaced_channels.clear()
        state.wrong_channel_types.clear()
        state.stale_permission_targets.clear()
        state.stale_roles.clear()
        state.duplicate_channels.clear()
        return ProbeOutcome(name, "layout and permission drift rectified")
    if name == "hub.leaders_delete_reinit":
        state.layout_present = False
        state.layout_present = True
        state.leaders_access = True
        return ProbeOutcome("leaders delete/reinit", "channel recreated idempotently")
    if name == "hub.leaders_idempotent_reinit":
        state.layout_present = True
        state.leaders_access = True
        return ProbeOutcome("leaders idempotent reinit", "two passes converged")
    if name == "clients.protected":
        state.assert_protected()
        return ProbeOutcome(
            "protected clients", f"{len(state.protected_snapshot)} client(s) unchanged"
        )
    if name == "artifacts.teardown":
        state.clients = {
            key: client for key, client in state.clients.items() if not client.smoke
        }
        state.artifacts.clear()
        return ProbeOutcome("smoke teardown", "all simulated smoke resources removed")
    raise KeyError(f"Mock backend does not implement probe {name!r}")
