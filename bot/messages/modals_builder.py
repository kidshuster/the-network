from __future__ import annotations

from typing import Any

import discord

from bot.messages.loader import modal_spec
from bot.messages.schema import ModalFieldSpec, ModalTemplateSpec


def add_modal_fields(
    modal: discord.ui.Modal,
    spec: ModalTemplateSpec,
) -> dict[str, discord.ui.Label[Any]]:
    fields_by_id: dict[str, discord.ui.Label[Any]] = {}
    for field in spec.fields:
        item = _build_modal_item(field)
        fields_by_id[field.id] = item
        modal.add_item(item)
    return fields_by_id


def apply_modal_spec(
    modal: discord.ui.Modal,
    name: str,
) -> dict[str, discord.ui.Label[Any]]:
    spec = modal_spec(name)
    modal.title = spec.title
    return add_modal_fields(modal, spec)


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


def _build_modal_item(field: ModalFieldSpec) -> discord.ui.Label[Any]:
    if field.type == "file_upload":
        return discord.ui.Label(
            text=field.label,
            description=field.description or discord.utils.MISSING,
            component=discord.ui.FileUpload(
                required=field.required,
                max_values=field.max_values,
            ),
        )
    return discord.ui.Label(
        text=field.label,
        description=field.description or discord.utils.MISSING,
        component=discord.ui.TextInput(
            placeholder=field.placeholder or discord.utils.MISSING,
            max_length=field.max_length,
            required=field.required,
        ),
    )
