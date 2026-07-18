from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import discord

from bot.domain.errors import EmojiSyncError
from bot.domain.profile import ServerProfile
from bot.domain.profile_image import ProfileImage

logger = logging.getLogger(__name__)

EMOJI_NAME_RE = re.compile(r"^[a-z0-9_]{2,32}$")
SLUG_RE = re.compile(r"[^a-z0-9]+")
_GUILD_EMOJI_CAP_CODES = {30008, 30018}
_MISSING_PERMISSION_CODE = 50013


def _degraded_message_for_code(code: int | None) -> str | None:
    if code in _GUILD_EMOJI_CAP_CODES:
        return "Guild emoji limit reached; using fallback symbol."
    if code == _MISSING_PERMISSION_CODE:
        return "Bot lacks Manage Expressions permission; using fallback symbol."
    return None


def _warning_for_code(code: int | None) -> str | None:
    if code in _GUILD_EMOJI_CAP_CODES:
        return "Emoji creation failed due to guild emoji limit."
    if code == _MISSING_PERMISSION_CODE:
        return (
            "Grant the bot **Manage Expressions** permission on its role, "
            "Contact an administrator to update this server's profile image."
        )
    return None


@dataclass(frozen=True)
class EmojiResult:
    emoji_id: int | None
    emoji_name: str | None
    image_hash: str | None
    degraded_reason: str | None
    recreated: bool
    skipped: bool
    delete_emoji_id: int | None = None
    warning: str | None = None


def sanitize_slug(text: str) -> str:
    slug = SLUG_RE.sub("_", text.strip().lower())
    slug = slug.strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug or "unknown"


def build_emoji_name(
    slug: str,
    source_channel_id: int,
    *,
    collision_index: int = 0,
    used_names: set[str] | None = None,
) -> str:
    short_id = str(source_channel_id)[-6:]
    prefix = "net_"

    def make_name(collision_num: int) -> str:
        suffix = f"_{collision_num}" if collision_num >= 2 else ""
        tail = f"_{short_id}{suffix}"
        max_slug_len = 32 - len(prefix) - len(tail)
        if max_slug_len < 1:
            raise EmojiSyncError("Cannot fit emoji name within 32 characters.")
        trimmed = slug[:max_slug_len].rstrip("_")
        return f"{prefix}{trimmed}{tail}"

    name = make_name(collision_index)
    if used_names is not None:
        collision_num = collision_index if collision_index >= 2 else 0
        while name in used_names:
            collision_num = 2 if collision_num < 2 else collision_num + 1
            name = make_name(collision_num)
    if len(name) < 2 or not EMOJI_NAME_RE.match(name):
        raise EmojiSyncError(f"Generated emoji name is invalid: {name!r}")
    return name


class EmojiService:
    def _needs_emoji_repair(self, guild: discord.Guild, profile: ServerProfile) -> bool:
        if profile.emoji_id is None or profile.degraded_reason is not None:
            return True
        return discord.utils.get(guild.emojis, id=profile.emoji_id) is None

    async def sync_for_profile(
        self,
        guild: discord.Guild,
        profile: ServerProfile,
        image: ProfileImage,
        *,
        previous_hash: str | None,
        previous_emoji_id: int | None,
        force: bool = False,
    ) -> EmojiResult:
        if (
            not force
            and not self._needs_emoji_repair(guild, profile)
            and previous_hash == image.image_hash
        ):
            return EmojiResult(
                emoji_id=profile.emoji_id,
                emoji_name=profile.emoji_name,
                image_hash=profile.image_hash,
                degraded_reason=None,
                recreated=False,
                skipped=True,
            )

        slug = sanitize_slug(profile.server_name or profile.display_name)
        emoji_name = build_emoji_name(slug, profile.source_channel_id)
        emoji, failure_code = await self._create_emoji(guild, emoji_name, image.data)
        if emoji is None:
            degraded = _degraded_message_for_code(failure_code)
            warning = _warning_for_code(failure_code)
            return EmojiResult(
                emoji_id=None,
                emoji_name=None,
                image_hash=image.image_hash,
                degraded_reason=degraded or "Emoji creation failed; using fallback symbol.",
                recreated=False,
                skipped=False,
                warning=warning or "Emoji creation failed.",
            )

        delete_emoji_id = None
        if previous_emoji_id is not None and previous_emoji_id != emoji.id:
            delete_emoji_id = previous_emoji_id

        return EmojiResult(
            emoji_id=emoji.id,
            emoji_name=emoji.name,
            image_hash=image.image_hash,
            degraded_reason=None,
            recreated=True,
            skipped=False,
            delete_emoji_id=delete_emoji_id,
        )

    async def repair_emoji(
        self,
        guild: discord.Guild,
        profile: ServerProfile,
        image: ProfileImage,
    ) -> EmojiResult:
        return await self.sync_for_profile(
            guild,
            profile,
            image,
            previous_hash=profile.image_hash,
            previous_emoji_id=profile.emoji_id,
            force=True,
        )

    async def delete_emoji(self, guild: discord.Guild, emoji_id: int) -> None:
        await self._delete_emoji(guild, emoji_id)

    async def _create_emoji(
        self,
        guild: discord.Guild,
        name: str,
        image_bytes: bytes,
    ) -> tuple[discord.Emoji | None, int | None]:
        try:
            emoji = await guild.create_custom_emoji(name=name, image=image_bytes)
            return emoji, None
        except discord.HTTPException as exc:
            degraded = _degraded_message_for_code(exc.code)
            if degraded is not None:
                logger.warning(
                    "Custom emoji creation degraded",
                    extra={
                        "guild_id": guild.id,
                        "emoji_name": name,
                        "code": exc.code,
                        "reason": degraded,
                    },
                )
                return None, exc.code
            raise EmojiSyncError(f"Failed to create custom emoji: {exc}") from exc

    async def _delete_emoji(self, guild: discord.Guild, emoji_id: int) -> None:
        emoji = discord.utils.get(guild.emojis, id=emoji_id)
        if emoji is None:
            return
        try:
            await emoji.delete(reason="Profile image replaced")
        except discord.HTTPException as exc:
            logger.warning(
                "Failed to delete replaced emoji",
                extra={"guild_id": guild.id, "emoji_id": emoji_id, "error": str(exc)},
            )
