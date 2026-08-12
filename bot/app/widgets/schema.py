from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

FORBIDDEN_KEYS = frozenset({
    "require", "inject", "store", "finish", "on_success", "on_error", "field_map",
    "options_from", "foreach", "when", "disabled_when", "trigger", "open_modal",
    "open_view", "reply", "params", "custom_id", "action", "defer", "recipe",
    "handler", "authorize", "auth", "repository", "service",
})

def reject_forbidden(raw: dict[str, Any], *, where: str) -> None:
    if found := sorted(FORBIDDEN_KEYS.intersection(raw)):
        raise ValueError(f"{where}: forbidden executable keys {found}")

class StaticButtonSpec(BaseModel):
    type: Literal["button"] = "button"
    tag: str | None = None
    id: str | None = None
    label: str
    style: str = "secondary"
    row: int | None = None
    emoji: str | None = None
    disabled: bool = False

    @model_validator(mode="before")
    @classmethod
    def _legacy_id_to_tag(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("tag") is None and data.get("id") is not None:
            data = {**data, "tag": data["id"]}
        return data

    @model_validator(mode="after")
    def _require_tag(self) -> Self:
        if self.tag is None:
            raise ValueError("button requires tag")
        return self

class SlotSpec(BaseModel):
    slot: str

class ViewTemplateSpec(BaseModel):
    kind: Literal["view"] = "view"
    id: str
    timeout: float | None = None
    components: list[StaticButtonSpec | SlotSpec] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden(cls, data: Any) -> Any:
        if isinstance(data, dict):
            reject_forbidden(data, where="view")
            for index, component in enumerate(data.get("components") or []):
                if isinstance(component, dict):
                    reject_forbidden(component, where=f"components[{index}]")
        return data

    @model_validator(mode="after")
    def _unique_tags_and_slots(self) -> Self:
        tags = [c.tag for c in self.components if isinstance(c, StaticButtonSpec)]
        if len(tags) != len(set(tags)):
            raise ValueError("duplicate tag")
        slots = [c.slot for c in self.components if isinstance(c, SlotSpec)]
        if len(slots) != len(set(slots)):
            raise ValueError("duplicate slot")
        return self

class ModalFieldSpec(BaseModel):
    id: str
    type: Literal["text", "file_upload", "short", "paragraph"] = "text"
    label: str = Field(max_length=45)
    description: str | None = Field(default=None, max_length=100)
    placeholder: str | None = None
    max_length: int = 100
    required: bool = True
    max_values: int = 1

class ModalTemplateSpec(BaseModel):
    kind: Literal["modal"] = "modal"
    id: str | None = None
    title: str
    fields: list[ModalFieldSpec]

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden(cls, data: Any) -> Any:
        if isinstance(data, dict):
            reject_forbidden(data, where="modal")
        return data

    @model_validator(mode="after")
    def _normalize_field_types(self) -> Self:
        self.fields = [
            field.model_copy(
                update={
                    "type": "text" if field.type in ("short", "paragraph") else field.type
                }
            )
            for field in self.fields
        ]
        return self
