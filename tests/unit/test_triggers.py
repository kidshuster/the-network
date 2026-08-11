from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.app.triggers import build_trigger_catalog, dispatch, dispatch_event
from bot.core.triggers import TriggerCatalog, TriggerCatalogError, TriggerKind, TriggerSpec


def test_catalog_rejects_duplicate_ids_and_slash_keys() -> None:
    catalog = TriggerCatalog()
    catalog.register(
        TriggerSpec(
            id="a",
            kind=TriggerKind.SLASH,
            recipe="r",
            slash_group="server",
            slash_name="init",
            slash_description="x",
        )
    )
    with pytest.raises(TriggerCatalogError, match="Duplicate trigger"):
        catalog.register(
            TriggerSpec(
                id="a",
                kind=TriggerKind.BUTTON,
                recipe="r",
            )
        )
    with pytest.raises(TriggerCatalogError, match="Duplicate slash"):
        catalog.register(
            TriggerSpec(
                id="b",
                kind=TriggerKind.SLASH,
                recipe="r",
                slash_group="server",
                slash_name="init",
                slash_description="y",
            )
        )


def test_app_catalog_lists_entry_surfaces() -> None:
    catalog = build_trigger_catalog()
    slash = {(s.slash_group, s.slash_name) for s in catalog.list_by_kind(TriggerKind.SLASH)}
    assert slash == {
        ("server", "init"),
        ("server", "probe"),
        ("server", "sync-join-guide"),
        ("server", "uninit"),
    }
    assert {s.event for s in catalog.triggers_for_event("app.services")} == {"app.services"}
    assert {s.recipe for s in catalog.triggers_for_event("discord.message")} == {
        "relay.on_message"
    }
    assert "request.submit" in catalog.ids()
    assert catalog.get("request.submit").kind is TriggerKind.MODAL


async def test_dispatch_runs_injected_runner() -> None:
    catalog = TriggerCatalog()
    catalog.register(
        TriggerSpec(id="ui.demo", kind=TriggerKind.BUTTON, recipe="demo.recipe")
    )
    runner = AsyncMock(return_value="ok")
    assert await dispatch(catalog, runner, "ui.demo", value=1) == "ok"
    runner.assert_awaited_once_with("demo.recipe", value=1)


async def test_dispatch_event_runs_all_matching_recipes() -> None:
    catalog = TriggerCatalog()
    catalog.register_many(
        (
            TriggerSpec(
                id="e1",
                kind=TriggerKind.APP_EVENT,
                recipe="a",
                event="app.setup",
            ),
            TriggerSpec(
                id="e2",
                kind=TriggerKind.APP_EVENT,
                recipe="b",
                event="app.setup",
            ),
        )
    )
    seen: list[str] = []

    async def runner(name: str, **payload: object) -> str:
        del payload
        seen.append(name)
        return name

    assert await dispatch_event(catalog, runner, "app.setup") == ["a", "b"]
    assert seen == ["a", "b"]
