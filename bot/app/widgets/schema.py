from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from bot.contracts.widgets import ButtonStyle

FORBIDDEN_KEYS = frozenset({
    "require", "inject", "store", "finish", "on_success", "on_error", "field_map",
    "options_from", "foreach", "when", "disabled_when", "trigger", "open_modal",
    "open_view", "reply", "params", "custom_id", "action", "defer", "recipe",
    "handler", "authorize", "auth", "repository", "service",
})

_DISCORD_ROW_MAX = 4
_VIEW_COMPONENT_MAX = 25
_MODAL_TITLE_MAX = 45
_MODAL_FIELD_MAX = 5
_MODAL_LABEL_MAX = 45
_MODAL_DESC_MAX = 100
_MODAL_PLACEHOLDER_MAX = 100
_TEXT_MAX_LENGTH_MIN = 1
_TEXT_MAX_LENGTH_MAX = 4000
_FILE_MAX_VALUES_MAX = 10


def reject_forbidden(raw: dict[str, Any], *, where: str) -> None:
    if found := sorted(FORBIDDEN_KEYS.intersection(raw)):
        raise ValueError(f"{where}: forbidden executable keys {found}")


class StaticButtonSpec(BaseModel):
    type: Literal["button"] = "button"
    tag: str
    label: str = Field(min_length=1, max_length=80)
    style: ButtonStyle = "secondary"
    row: int | None = Field(default=None, ge=0, le=_DISCORD_ROW_MAX)
    emoji: str | None = None
    disabled: bool = False


class SlotSpec(BaseModel):
    slot: str = Field(min_length=1)


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
    def _unique_tags_slots_and_capacity(self) -> Self:
        tags = [c.tag for c in self.components if isinstance(c, StaticButtonSpec)]
        if len(tags) != len(set(tags)):
            raise ValueError("duplicate tag")
        slots = [c.slot for c in self.components if isinstance(c, SlotSpec)]
        if len(slots) != len(set(slots)):
            raise ValueError("duplicate slot")
        if len(self.components) > _VIEW_COMPONENT_MAX:
            raise ValueError(
                f"view exceeds Discord component limit {_VIEW_COMPONENT_MAX}"
            )
        rows: dict[int, int] = {}
        for component in self.components:
            if isinstance(component, StaticButtonSpec) and component.row is not None:
                rows[component.row] = rows.get(component.row, 0) + 1
                if rows[component.row] > 5:
                    raise ValueError(f"row {component.row} exceeds 5 buttons")
        return self


class ModalFieldSpec(BaseModel):
    id: str = Field(min_length=1)
    type: Literal["text", "file_upload", "short", "paragraph"] = "text"
    label: str = Field(min_length=1, max_length=_MODAL_LABEL_MAX)
    description: str | None = Field(default=None, max_length=_MODAL_DESC_MAX)
    placeholder: str | None = Field(default=None, max_length=_MODAL_PLACEHOLDER_MAX)
    max_length: int = Field(default=100, ge=_TEXT_MAX_LENGTH_MIN, le=_TEXT_MAX_LENGTH_MAX)
    required: bool = True
    max_values: int = Field(default=1, ge=1, le=_FILE_MAX_VALUES_MAX)

    @model_validator(mode="after")
    def _type_constraints(self) -> Self:
        if self.type == "file_upload" and self.placeholder is not None:
            raise ValueError("file_upload fields cannot have placeholder")
        return self


class ModalTemplateSpec(BaseModel):
    kind: Literal["modal"] = "modal"
    id: str | None = None
    title: str = Field(min_length=1, max_length=_MODAL_TITLE_MAX)
    fields: list[ModalFieldSpec] = Field(min_length=1, max_length=_MODAL_FIELD_MAX)

    @model_validator(mode="before")
    @classmethod
    def _reject_forbidden(cls, data: Any) -> Any:
        if isinstance(data, dict):
            reject_forbidden(data, where="modal")
        return data

    @model_validator(mode="after")
    def _normalize_and_unique_fields(self) -> Self:
        ids = [field.id for field in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate modal field id")
        self.fields = [
            field.model_copy(
                update={
                    "type": "text" if field.type in ("short", "paragraph") else field.type
                }
            )
            for field in self.fields
        ]
        return self
