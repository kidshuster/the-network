from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.core.hub.changelog import (
    ReleaseNotes,
    pending_release_versions,
    sync_changelog_releases,
    version_key,
)


def test_version_key_sorts_semver() -> None:
    versions = ["1.1.20", "1.1.9", "1.1.16", "1.2.0"]
    assert sorted(versions, key=version_key) == ["1.1.9", "1.1.16", "1.1.20", "1.2.0"]


def test_pending_release_versions_backfills_from_scratch() -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",)),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",)),
        "1.1.20": ReleaseNotes("1.1.20", "c", ("three",)),
    }
    pending = pending_release_versions(
        catalog,
        last_posted=None,
        up_to="1.1.20",
    )
    assert pending == ["1.1.16", "1.1.19", "1.1.20"]


def test_pending_release_versions_skips_already_posted() -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",)),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",)),
        "1.1.20": ReleaseNotes("1.1.20", "c", ("three",)),
    }
    pending = pending_release_versions(
        catalog,
        last_posted="1.1.19",
        up_to="1.1.20",
    )
    assert pending == ["1.1.20"]


@pytest.mark.asyncio
async def test_sync_changelog_releases_posts_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",)),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",)),
    }
    monkeypatch.setattr("bot.core.hub.changelog._load_releases_catalog", lambda: catalog)
    monkeypatch.setattr("bot.core.hub.changelog.installed_version", lambda: "1.1.19")

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
async def test_sync_changelog_releases_stops_on_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = {
        "1.1.16": ReleaseNotes("1.1.16", "a", ("one",)),
        "1.1.19": ReleaseNotes("1.1.19", "b", ("two",)),
    }
    monkeypatch.setattr("bot.core.hub.changelog._load_releases_catalog", lambda: catalog)
    monkeypatch.setattr("bot.core.hub.changelog.installed_version", lambda: "1.1.19")

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
