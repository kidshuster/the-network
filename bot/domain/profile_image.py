from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileImage:
    """Normalized PNG bytes and SHA-256 hash for emoji generation."""

    data: bytes
    image_hash: str
