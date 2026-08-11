from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProfileImage:
    """Normalized PNG bytes and SHA-256 hash for emoji generation."""

    data: bytes
    image_hash: str


@runtime_checkable
class ProfileImageAttachment(Protocol):
    """Minimal attachment surface used for profile image ingestion."""

    size: int
    content_type: str | None
    filename: str
    url: str

    async def read(self) -> bytes: ...
