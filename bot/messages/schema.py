from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EmbedFieldSpec(BaseModel):
    name: str
    value: str
    inline: bool = False
    when: str | None = None


class InteractionOptionSpec(BaseModel):
    label: str
    value: str
    description: str | None = None


class InteractionSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    kind: Literal["button", "select"]
    recipe: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    label: str
    style: Literal["primary", "secondary", "success", "danger"] = "secondary"
    inputs: dict[str, Any] = Field(default_factory=dict)
    options: list[InteractionOptionSpec] = Field(default_factory=list)
    placeholder: str | None = None


class EmbedTemplateSpec(BaseModel):
    kind: Literal["embed"] = "embed"
    title: str | None = None
    description: str | None = None
    colour: str = "blurple"
    fields: list[EmbedFieldSpec] = Field(default_factory=list)
    footer: str | None = None
    author_name: str | None = None
    author_icon_url: str | None = None
    interactions: list[InteractionSpec] = Field(default_factory=list)


class TextTemplateSpec(BaseModel):
    kind: Literal["text"] = "text"
    content: str
    interactions: list[InteractionSpec] = Field(default_factory=list)


class ModalFieldSpec(BaseModel):
    id: str
    type: Literal["text", "file_upload"] = "text"
    label: str = Field(max_length=45)
    description: str | None = Field(default=None, max_length=100)
    placeholder: str | None = None
    max_length: int = 100
    required: bool = True
    max_values: int = 1


class ModalTemplateSpec(BaseModel):
    kind: Literal["modal"] = "modal"
    title: str
    fields: list[ModalFieldSpec]


class RelayEmbedSpec(BaseModel):
    kind: Literal["relay_embed"] = "relay_embed"
    colour: str = "blurple"
    degraded_emoji_prefix: bool = True
