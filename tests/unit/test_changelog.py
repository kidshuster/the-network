from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.features.recipes.hub.changelog import (
    ReleaseNotes,
    pending_channel_release_versions,
    pending_release_versions,
    sync_changelog_releases,
    version_key,
)


def test_version_key_sorts_semver() -> None:
    versions = ["1.1.20", "1.1.9", "1.1.16", "1.2.0"]
    assert sorted(versions, key=version_key) == ["1.1.9", "1.1.16", "1.1.20", "1.2.0"]


def test_pending_release_versions_backfills_from_scratch() -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",), post=True),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",), post=True),
        "1.1.20": ReleaseNotes("1.1.20", "c", ("three",), post=True),
    }
    pending = pending_release_versions(
        catalog,
        last_posted=None,
        up_to="1.1.20",
    )
    assert pending == ["1.1.16", "1.1.19", "1.1.20"]


def test_pending_release_versions_skips_already_posted() -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",), post=True),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",), post=True),
        "1.1.20": ReleaseNotes("1.1.20", "c", ("three",), post=True),
    }
    pending = pending_release_versions(
        catalog,
        last_posted="1.1.19",
        up_to="1.1.20",
    )
    assert pending == ["1.1.20"]


def test_pending_channel_release_versions_only_postable() -> None:
    catalog = {
        "1.3.0": ReleaseNotes("1.3.0", "minor", ("a",), post=True),
        "1.3.1": ReleaseNotes("1.3.1", "patch", ("b",)),
        "1.4.0": ReleaseNotes("1.4.0", "next", ("c",), post=True),
    }
    pending = pending_channel_release_versions(
        catalog,
        last_posted=None,
        up_to="1.3.1",
    )
    assert pending == ["1.3.0"]


def test_pending_channel_release_versions_skips_patches_after_cursor() -> None:
    catalog = {
        "1.3.0": ReleaseNotes("1.3.0", "minor", ("a",), post=True),
        "1.3.1": ReleaseNotes("1.3.1", "patch", ("b",)),
        "1.4.0": ReleaseNotes("1.4.0", "next", ("c",), post=True),
    }
    pending = pending_channel_release_versions(
        catalog,
        last_posted="1.3.0",
        up_to="1.3.1",
    )
    assert pending == []


@pytest.mark.asyncio
async def test_sync_changelog_releases_posts_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",), post=True),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",), post=True),
    }
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog._load_releases_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog.installed_version",
        lambda: "1.1.19",
    )

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 999
    channel.send = AsyncMock()

    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(return_value=None)
    settings_repo.set = AsyncMock()
    context = MagicMock()
    context.store.settings = settings_repo

    posted = await sync_changelog_releases(context, channel)

    assert posted == 2
    assert channel.send.await_count == 2
    settings_repo.set.assert_any_await("hub_changelog_last_version", "1.1.16")
    settings_repo.set.assert_any_await("hub_changelog_last_version", "1.1.19")


@pytest.mark.asyncio
async def test_sync_changelog_releases_posts_only_postable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = {
        "1.3.0": ReleaseNotes("1.3.0", "minor", ("a",), post=True),
        "1.3.1": ReleaseNotes("1.3.1", "patch", ("b",)),
    }
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog._load_releases_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog.installed_version",
        lambda: "1.3.1",
    )

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 999
    channel.send = AsyncMock()

    stored: dict[str, str | None] = {"hub_changelog_last_version": None}

    async def settings_get(key: str) -> str | None:
        return stored.get(key)

    async def settings_set(key: str, value: str) -> None:
        stored[key] = value

    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(side_effect=settings_get)
    settings_repo.set = AsyncMock(side_effect=settings_set)
    context = MagicMock()
    context.store.settings = settings_repo

    posted = await sync_changelog_releases(context, channel)

    assert posted == 1
    assert channel.send.await_count == 1
    assert stored["hub_changelog_last_version"] == "1.3.1"
    settings_repo.set.assert_any_await("hub_changelog_last_version", "1.3.0")
    settings_repo.set.assert_any_await("hub_changelog_last_version", "1.3.1")


@pytest.mark.asyncio
async def test_sync_changelog_releases_advances_cursor_on_patch_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = {
        "1.3.0": ReleaseNotes("1.3.0", "minor", ("a",), post=True),
        "1.3.1": ReleaseNotes("1.3.1", "patch", ("b",)),
    }
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog._load_releases_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog.installed_version",
        lambda: "1.3.1",
    )

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 999
    channel.send = AsyncMock()

    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(return_value="1.3.0")
    settings_repo.set = AsyncMock()
    context = MagicMock()
    context.store.settings = settings_repo

    posted = await sync_changelog_releases(context, channel)

    assert posted == 0
    channel.send.assert_not_awaited()
    settings_repo.set.assert_awaited_once_with("hub_changelog_last_version", "1.3.1")


@pytest.mark.asyncio
async def test_sync_changelog_releases_stops_on_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",), post=True),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",), post=True),
    }
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog._load_releases_catalog",
        lambda: catalog,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.changelog.installed_version",
        lambda: "1.1.19",
    )

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 999
    channel.send = AsyncMock(side_effect=[None, discord.HTTPException(MagicMock(), "fail")])

    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(return_value=None)
    settings_repo.set = AsyncMock()
    context = MagicMock()
    context.store.settings = settings_repo

    posted = await sync_changelog_releases(context, channel)

    assert posted == 1
    settings_repo.set.assert_awaited_once_with("hub_changelog_last_version", "1.1.16")
