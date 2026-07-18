from __future__ import annotations

import io

from PIL import Image

from bot.services.image_service import normalize_image_bytes


def _make_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_normalize_image_produces_stable_hash() -> None:
    png = _make_png(32, 32, (255, 128, 64))
    first = normalize_image_bytes(png)
    second = normalize_image_bytes(png)
    assert first.image_hash == second.image_hash
    assert first.data.startswith(b"\x89PNG\r\n\x1a\n")


def test_normalize_image_changes_hash_when_pixels_change() -> None:
    red = normalize_image_bytes(_make_png(64, 64, (255, 0, 0)))
    blue = normalize_image_bytes(_make_png(64, 64, (0, 0, 255)))
    assert red.image_hash != blue.image_hash


def test_normalize_image_crops_to_square() -> None:
    wide = normalize_image_bytes(_make_png(120, 40, (10, 20, 30)))
    assert len(wide.data) > 0
    assert len(wide.image_hash) == 64
