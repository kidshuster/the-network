from __future__ import annotations

import hashlib
import io
import logging

import discord
from PIL import Image, UnidentifiedImageError

from bot.constants import (
    EMOJI_SIZE,
    MAX_EMOJI_FILE_BYTES,
    MAX_PROFILE_IMAGE_DOWNLOAD_BYTES,
)
from bot.domain.errors import ProfileValidationError
from bot.domain.profile_image import ProfileImage

logger = logging.getLogger(__name__)

_SUPPORTED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _is_supported_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/") and "svg" in content_type:
        return False
    if content_type in _SUPPORTED_CONTENT_TYPES:
        return True
    filename = attachment.filename.lower()
    return any(filename.endswith(ext) for ext in _SUPPORTED_EXTENSIONS)


def find_first_image_attachment(message: discord.Message) -> discord.Attachment | None:
    for attachment in message.attachments:
        if _is_supported_attachment(attachment):
            return attachment
    return None


def normalize_image_bytes(raw: bytes) -> ProfileImage:
    try:
        image = Image.open(io.BytesIO(raw))
    except UnidentifiedImageError as exc:
        raise ProfileValidationError("Profile image could not be decoded.") from exc

    if getattr(image, "is_animated", False):
        image.seek(0)

    rgba = image.convert("RGBA")
    width, height = rgba.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    cropped = rgba.crop((left, top, left + side, top + side))
    resized = cropped.resize((EMOJI_SIZE, EMOJI_SIZE), Image.Resampling.LANCZOS)

    png_bytes = _encode_png_under_limit(resized)
    image_hash = hashlib.sha256(png_bytes).hexdigest()
    return ProfileImage(data=png_bytes, image_hash=image_hash)


def _encode_png_under_limit(image: Image.Image) -> bytes:
    size = EMOJI_SIZE
    while size >= 32:
        resized = image.resize((size, size), Image.Resampling.LANCZOS)
        png_bytes = _save_png(resized)
        if len(png_bytes) <= MAX_EMOJI_FILE_BYTES:
            return png_bytes
        size -= 16
    raise ProfileValidationError("Profile image is too large to fit Discord emoji limits.")


def _save_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


async def read_profile_image_attachment(attachment: discord.Attachment) -> ProfileImage:
    max_mb = MAX_PROFILE_IMAGE_DOWNLOAD_BYTES // (1024 * 1024)
    if attachment.size and attachment.size > MAX_PROFILE_IMAGE_DOWNLOAD_BYTES:
        raise ProfileValidationError(f"Profile image exceeds the {max_mb}MB limit.")

    if not _is_supported_attachment(attachment):
        raise ProfileValidationError(
            "Profile image must be a PNG, JPG, WebP, or GIF file."
        )

    try:
        raw = await attachment.read()
    except discord.HTTPException as exc:
        raise ProfileValidationError("Failed to read profile image attachment.") from exc

    if len(raw) > MAX_PROFILE_IMAGE_DOWNLOAD_BYTES:
        raise ProfileValidationError(f"Profile image exceeds the {max_mb}MB limit.")

    return normalize_image_bytes(raw)


async def download_profile_image_from_url(url: str) -> ProfileImage:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        raise ProfileValidationError("Profile image URL must start with http:// or https://.")

    try:
        import aiohttp
    except ImportError as exc:
        raise ProfileValidationError("Image download is unavailable.") from exc

    max_mb = MAX_PROFILE_IMAGE_DOWNLOAD_BYTES // (1024 * 1024)
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(cleaned) as response:
                if response.status != 200:
                    raise ProfileValidationError(
                        f"Could not download profile image (HTTP {response.status})."
                    )
                content_type = (response.headers.get("Content-Type") or "").lower()
                if content_type.startswith("image/") and "svg" in content_type:
                    raise ProfileValidationError("SVG images are not supported.")
                raw = await response.read()
    except aiohttp.ClientError as exc:
        raise ProfileValidationError("Failed to download profile image URL.") from exc

    if len(raw) > MAX_PROFILE_IMAGE_DOWNLOAD_BYTES:
        raise ProfileValidationError(f"Profile image exceeds the {max_mb}MB limit.")

    return normalize_image_bytes(raw)


async def extract_profile_image(message: discord.Message) -> ProfileImage | None:
    attachment = find_first_image_attachment(message)
    if attachment is None:
        return None

    max_mb = MAX_PROFILE_IMAGE_DOWNLOAD_BYTES // (1024 * 1024)
    if attachment.size and attachment.size > MAX_PROFILE_IMAGE_DOWNLOAD_BYTES:
        raise ProfileValidationError(f"Profile image exceeds the {max_mb}MB limit.")

    try:
        raw = await attachment.read()
    except discord.HTTPException as exc:
        raise ProfileValidationError("Failed to download profile image attachment.") from exc

    if len(raw) > MAX_PROFILE_IMAGE_DOWNLOAD_BYTES:
        raise ProfileValidationError(f"Profile image exceeds the {max_mb}MB limit.")

    return normalize_image_bytes(raw)
