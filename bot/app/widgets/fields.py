from __future__ import annotations

from typing import Any

import discord

from bot.core.templates import modal_spec
from bot.core.templates.schema import ModalFieldSpec, ModalTemplateSpec


def add_modal_fields(
    modal: discord.ui.Modal,
    spec: ModalTemplateSpec,
    *,
    defaults: dict[str, str] | None = None,
) -> dict[str, discord.ui.Label[Any]]:
    defaults = defaults or {}
    fields_by_id: dict[str, discord.ui.Label[Any]] = {}
    for field in spec.fields:
        item = _build_modal_item(field, default=defaults.get(field.id))
        fields_by_id[field.id] = item
        modal.add_item(item)
    return fields_by_id


def modal_text_value(field: discord.ui.Label[Any]) -> str:
    component = field.component
    if not isinstance(component, discord.ui.TextInput):
        raise TypeError("Expected a text input modal field")
    return component.value.strip()


def modal_file_attachments(field: discord.ui.Label[Any]) -> list[discord.Attachment]:
    component = field.component
    if not isinstance(component, discord.ui.FileUpload):
        return []
    return list(component.values)


def collect_modal_values(
    fields: dict[str, discord.ui.Label[Any]],
    spec: ModalTemplateSpec,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in spec.fields:
        label = fields[field.id]
        if field.type == "file_upload":
            attachments = modal_file_attachments(label)
            values[field.id] = attachments[0] if attachments else None
            values[f"{field.id}_attachments"] = attachments
        else:
            values[field.id] = modal_text_value(label)
    return values


def _build_modal_item(
    field: ModalFieldSpec,
    *,
    default: str | None = None,
) -> discord.ui.Label[Any]:
    if field.type == "file_upload":
        return discord.ui.Label(
            text=field.label,
            description=field.description or discord.utils.MISSING,
            component=discord.ui.FileUpload(
                required=field.required,
                max_values=field.max_values,
            ),
        )
    text: discord.ui.TextInput[Any] = discord.ui.TextInput(
        placeholder=field.placeholder or discord.utils.MISSING,
        max_length=field.max_length,
        required=field.required,
    )
    if default is not None:
        text.default = default
    return discord.ui.Label(
        text=field.label,
        description=field.description or discord.utils.MISSING,
        component=text,
    )


def load_modal_spec(name: str) -> ModalTemplateSpec:
    return modal_spec(name)
