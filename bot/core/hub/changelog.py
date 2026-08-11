from __future__ import annotations

import logging
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

import discord
import yaml

from bot.core.templates import render_embed

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.core.runtime import BotContext

logger = logging.getLogger(__name__)

_MAX_EMBED_FIELD_CHARS = 1024

_CHANGELOG_PATH = (
    Path(__file__).resolve().parents[2] / "widgets" / "changelog" / "releases.yaml"
)
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


def version_key(release_version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in release_version.strip().lstrip("v").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _load_releases_catalog() -> dict[str, ReleaseNotes]:
    with _CHANGELOG_PATH.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("changelog releases.yaml must be a mapping")
    releases_raw = raw.get("releases")
    if not isinstance(releases_raw, dict):
        raise ValueError("changelog releases.yaml must contain a releases mapping")

    catalog: dict[str, ReleaseNotes] = {}
    for version_key_str, entry in releases_raw.items():
        if not isinstance(entry, dict):
            continue
        summary = str(entry.get("summary", "")).strip()
        changes_raw = entry.get("changes")
        changes: list[str] = []
        if isinstance(changes_raw, list):
            changes = [str(item).strip() for item in changes_raw if str(item).strip()]
        catalog[str(version_key_str)] = ReleaseNotes(
            version=str(version_key_str),
            summary=summary or f"Release {version_key_str}",
            changes=tuple(changes),
        )
    return catalog


def load_release_notes(release_version: str) -> ReleaseNotes | None:
    return _load_releases_catalog().get(release_version)


def pending_release_versions(
    catalog: dict[str, ReleaseNotes],
    *,
    last_posted: str | None,
    up_to: str,
) -> list[str]:
    """Catalog versions after last_posted up to installed, oldest first."""
    cap = version_key(up_to)
    last = version_key(last_posted) if last_posted else None
    pending: list[str] = []
    for release_version in catalog:
        key = version_key(release_version)
        if key > cap:
            continue
        if last is not None and key <= last:
            continue
        pending.append(release_version)
    pending.sort(key=version_key)
    return pending


def _chunk_bullet_lines(items: tuple[str, ...], *, prefix: str = "• ") -> list[str]:
    chunks: list[str] = []
    current = ""
    for item in items:
        line = f"{prefix}{item}\n"
        if len(current) + len(line) > _MAX_EMBED_FIELD_CHARS:
            if current:
                chunks.append(current.rstrip())
            if len(line) > _MAX_EMBED_FIELD_CHARS:
                chunks.append(line[: _MAX_EMBED_FIELD_CHARS - 1].rstrip())
                current = ""
            else:
                current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip())
    return chunks or ["See release notes."]


def build_changelog_embed(notes: ReleaseNotes) -> discord.Embed:
    embed = render_embed(
        "changelog_release",
        version=notes.version,
        summary=notes.summary,
        changes_value="See release notes.",
    )
    embed.clear_fields()
    for index, chunk in enumerate(_chunk_bullet_lines(notes.changes)):
        field_name = "What's new" if index == 0 else "What's new (cont.)"
        embed.add_field(name=field_name, value=chunk, inline=False)
    return embed


async def sync_changelog_releases(
    context: BotContext,
    channel: discord.TextChannel,
) -> int:
    """Post missing release notes in version order up to the installed package version."""
    installed = installed_version()
    catalog = _load_releases_catalog()
    last_posted = await context.store.settings.get(LAST_CHANGELOG_VERSION_KEY)
    versions = pending_release_versions(
        catalog,
        last_posted=last_posted,
        up_to=installed,
    )

    posted_count = 0
    for release_version in versions:
        notes = catalog[release_version]
        embed = build_changelog_embed(notes)
        try:
            await channel.send(embed=embed, silent=True)
        except discord.HTTPException:
            logger.warning(
                "Could not post changelog release embed",
                extra={"version": release_version, "channel_id": channel.id},
            )
            break

        await context.store.settings.set(LAST_CHANGELOG_VERSION_KEY, release_version)
        posted_count += 1
        logger.info(
            "Posted changelog release",
            extra={"version": release_version, "channel_id": channel.id},
        )

    current_last = await context.store.settings.get(LAST_CHANGELOG_VERSION_KEY)
    if version_key(installed) > version_key(current_last or "0"):
        remaining = pending_release_versions(
            catalog,
            last_posted=current_last,
            up_to=installed,
        )
        if not remaining:
            if load_release_notes(installed) is None:
                logger.warning(
                    "No changelog entry for installed version",
                    extra={"version": installed},
                )
            await context.store.settings.set(LAST_CHANGELOG_VERSION_KEY, installed)

    return posted_count


async def sync_changelog_for_guild(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    *,
    access_role: discord.Role,
    human_moderator_role: discord.Role | None,
    operator_role: discord.Role | None = None,
) -> tuple[discord.TextChannel | None, int]:
    """Ensure the Leaders changelog channel exists and backfill pending release notes."""
    from bot.core.hub.leaders import ensure_leaders_channels

    _leaders, changelog, _sync_result = await ensure_leaders_channels(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        operator_role=operator_role,
    )
    if changelog is None:
        return None, 0

    posted = await sync_changelog_releases(context, changelog)
    return changelog, posted


async def sync_changelog_on_ready(
    bot: NetworkRelayBot,
    context: BotContext,
    guild: discord.Guild,
) -> None:
    """Ensure the Leaders changelog channel exists and post notes for new versions."""
    from bot.core.networks.roles import resolve_access_role

    bot_member = guild.me
    if bot_member is None:
        return

    access_role = resolve_access_role(
        guild,
        role_name=bot.settings.network_access_role_name,
    )
    if access_role is None:
        return

    from bot.core.channels.resolve import resolve_human_moderator_role
    from bot.core.networks.roles import resolve_operator_role_by_name

    human_moderator_role = resolve_human_moderator_role(guild)
    operator_role = resolve_operator_role_by_name(
        guild,
        role_name=bot.settings.network_operator_role_name,
    )
    await sync_changelog_for_guild(
        guild,
        bot_member,
        context,
        access_role=access_role,
        human_moderator_role=human_moderator_role,
        operator_role=operator_role,
    )
