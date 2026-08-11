from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ReplySpec(BaseModel):
    embed: str | None = None
    popup: str | None = None
    map: dict[str, str] = Field(default_factory=dict)
    ephemeral: bool = True
    edit_message: bool = False
    clear_view: bool = False


class ActionSpec(BaseModel):
    trigger: str | None = None
    open_modal: str | None = None
    open_view: str | None = None
    reply: ReplySpec | None = None
    on_success: ReplySpec | None = None
    on_error: ReplySpec | None = None
    require: list[str | dict[str, Any]] = Field(default_factory=list)
    inject: list[str] = Field(default_factory=list)
    # Migration / local state helpers
    store: dict[str, str] | None = None
    finish: Literal["confirm", "cancel"] | None = None
    defer: bool = True


class ComponentSpec(BaseModel):
    type: Literal["button", "select"] = "button"
    id: str
    label: str | None = None
    style: str = "secondary"
    row: int | None = None
    custom_id: str | None = None
    disabled: bool = False
    disabled_when: str | None = None
    when: str | None = None
    foreach: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
    action: ActionSpec = Field(default_factory=ActionSpec)
    # Select
    placeholder: str | None = None
    min_values: int = 1
    max_values: int = 1
    options_from: str | None = None


class ViewTemplateSpec(BaseModel):
    kind: Literal["view"] = "view"
    id: str
    timeout: float | None = None
    components: list[ComponentSpec] = Field(default_factory=list)


class ModalOnSuccessSpec(BaseModel):
    reply: ReplySpec | None = None


class ModalTemplateExtras(BaseModel):
    """Fields layered onto ModalTemplateSpec via widget loading."""

    require: list[str | dict[str, Any]] = Field(default_factory=list)
    inject: list[str] = Field(default_factory=list)
    on_success: ReplySpec | None = None
    on_error: ReplySpec | None = None
    field_defaults: dict[str, str] = Field(default_factory=dict)
    # Map modal field ids → trigger kwargs (default: same names)
    field_map: dict[str, str] = Field(default_factory=dict)
