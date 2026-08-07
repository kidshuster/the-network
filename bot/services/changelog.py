from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
import yaml

from bot.messages import render_embed

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

_CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "changelog" / "releases.yaml"
LAST_CHANGELOG_VERSION_KEY = "hub_changelog_last_version"
PACKAGE_NAME = "the-network"


@dataclass(frozen=True)
class ReleaseNotes:
    version: str
    summary: str
    changes: tuple[str, ...]


def installed_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0"


def _load_releases_catalog() -> dict[str, ReleaseNotes]:
    with _CHANGELOG_PATH.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("changelog releases.yaml must be a mapping")
    releases_raw = raw.get("releases")
    if not isinstance(releases_raw, dict):
        raise ValueError("changelog releases.yaml must contain a releases mapping")

    catalog: dict[str, ReleaseNotes] = {}
    for version_key, entry in releases_raw.items():
        if not isinstance(entry, dict):
            continue
        summary = str(entry.get("summary", "")).strip()
        changes_raw = entry.get("changes")
        changes: list[str] = []
        if isinstance(changes_raw, list):
            changes = [str(item).strip() for item in changes_raw if str(item).strip()]
        catalog[str(version_key)] = ReleaseNotes(
            version=str(version_key),
            summary=summary or f"Release {version_key}",
            changes=tuple(changes),
        )
    return catalog


def load_release_notes(release_version: str) -> ReleaseNotes | None:
    return _load_releases_catalog().get(release_version)


def build_changelog_embed(notes: ReleaseNotes) -> Any:
    changes_value = "\n".join(f"• {item}" for item in notes.changes) or "See release notes."
    return render_embed(
        "changelog_release",
        version=notes.version,
        summary=notes.summary,
        changes_value=changes_value,
    )


async def maybe_post_release_changelog(
    context: BotContext,
    channel: discord.TextChannel,
) -> bool:
    current = installed_version()
    last_posted = await context.settings_repo.get(LAST_CHANGELOG_VERSION_KEY)
    if last_posted == current:
        return False

    notes = load_release_notes(current)
    if notes is None:
        logger.warning(
            "No changelog entry for installed version",
            extra={"version": current},
        )
        await context.settings_repo.set(LAST_CHANGELOG_VERSION_KEY, current)
        return False

    embed = build_changelog_embed(notes)
    try:
        await channel.send(embed=embed, silent=True)
    except discord.HTTPException:
        logger.warning(
            "Could not post changelog release embed",
            extra={"version": current, "channel_id": channel.id},
        )
        return False

    await context.settings_repo.set(LAST_CHANGELOG_VERSION_KEY, current)
    logger.info(
        "Posted changelog release",
        extra={"version": current, "channel_id": channel.id},
    )
    return True


async def sync_changelog_on_ready(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
) -> None:
    """Ensure the Leaders changelog channel exists and post notes for new versions."""
    from bot.services.leaders_channel import ensure_leaders_channels
    from bot.services.network_provision import resolve_access_role

    bot_member = guild.me
    if bot_member is None:
        return

    access_role = resolve_access_role(
        guild,
        role_name=bot.settings.network_access_role_name,
    )
    if access_role is None:
        return

    from bot.services.guild_layout import resolve_human_moderator_role

    human_moderator_role = resolve_human_moderator_role(guild)
    _leaders, changelog = await ensure_leaders_channels(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
    )
    if changelog is None:
        return

    await maybe_post_release_changelog(context, changelog)
