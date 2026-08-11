from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class StickySpec(BaseModel):
    template: str
    settings_key: str | None = None
    version: int = 1
    footer_marker: str
    strategy: Literal["ensure", "replace", "scoped"] = "ensure"
    pin: bool = False
    require_manage_messages: bool = False
    setting_format: Literal["location", "message_id"] = "location"


class StickyCatalog(BaseModel):
    stickies: dict[str, StickySpec]
