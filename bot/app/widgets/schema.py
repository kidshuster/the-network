from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

FORBIDDEN_KEYS = frozenset(
    {
        "require",
        "inject",
        "store",
        "finish",
        "on_success",
        "on_error",
        "field_map",
        "options_from",
        "foreach",
        "when",
        "disabled_when",
        "trigger",
        "open_modal",
        "open_view",
        "reply",
        "params",
        "custom_id",
        "action",
        "defer",
    }
)


def reject_forbidden(raw: dict[str, Any], *, where: str) -> None:
    found = sorted(FORBIDDEN_KEYS.intersection(raw))
    if found:
        raise ValueError(f"{where}: forbidden executable keys {found}")


class StaticButtonSpec(BaseModel):
    type: Literal["button"] = "button"
    id: str
    label: str
    style: str = "secondary"
    row: int | None = None
    emoji: str | None = None
    disabled: bool = False


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
        normalized: list[ModalFieldSpec] = []
        for field in self.fields:
            field_type = field.type
            if field_type in ("short", "paragraph"):
                field_type = "text"
            normalized.append(field.model_copy(update={"type": field_type}))
        self.fields = normalized
        return self
