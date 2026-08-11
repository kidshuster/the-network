from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import discord
import yaml
from pydantic import ValidationError

from bot.presentation.schema import (
    EmbedTemplateSpec,
    ModalTemplateSpec,
    RelayEmbedSpec,
    TextTemplateSpec,
)

_MESSAGES_DIR = Path(__file__).resolve().parent
_EMBEDS_DIR = _MESSAGES_DIR / "embeds"
_POPUPS_DIR = _MESSAGES_DIR / "popups"
_MODALS_DIR = _MESSAGES_DIR / "modals"

_COLOUR_MAP: dict[str, discord.Colour] = {
    "blurple": discord.Colour.blurple(),
    "green": discord.Colour.green(),
    "red": discord.Colour.red(),
    "gold": discord.Colour.gold(),
    "orange": discord.Colour.orange(),
    "dark_grey": discord.Colour.dark_grey(),
}

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

_cache: dict[str, Any] = {}


class MessageTemplateError(Exception):
    pass


def _substitute(text: str, ctx: dict[str, Any]) -> str:
    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in ctx:
            return match.group(0)
        value = ctx[key]
        if value is None:
            return ""
        return str(value)

    return _PLACEHOLDER_RE.sub(replacer, text)


def _field_visible(when: str | None, ctx: dict[str, Any]) -> bool:
    if when is None:
        return True
    substituted = _substitute(when, ctx).strip()
    return bool(substituted) and substituted not in ("0", "False", "false")


def resolve_colour(name: str, ctx: dict[str, Any] | None = None) -> discord.Colour:
    ctx = ctx or {}
    colour_key = str(ctx.get("colour", name))
    if colour_key in _COLOUR_MAP:
        return _COLOUR_MAP[colour_key]
    if colour_key.startswith("0x"):
        return discord.Colour(int(colour_key, 16))
    raise MessageTemplateError(f"Unknown colour: {colour_key}")


def _resolve_colour(name: str, ctx: dict[str, Any]) -> discord.Colour:
    return resolve_colour(name, ctx)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise MessageTemplateError(f"{path.name}: expected mapping at root")
    return raw


def _parse_template(name: str, path: Path) -> Any:
    raw = _load_yaml(path)
    kind = raw.get("kind", "embed")
    try:
        if kind == "embed":
            return EmbedTemplateSpec.model_validate(raw)
        if kind == "text":
            return TextTemplateSpec.model_validate(raw)
        if kind == "modal":
            return ModalTemplateSpec.model_validate(raw)
        if kind == "relay_embed":
            return RelayEmbedSpec.model_validate(raw)
    except ValidationError as exc:
        raise MessageTemplateError(f"{path.name}: {exc}") from exc
    raise MessageTemplateError(f"{path.name}: unknown kind {kind!r}")


def _find_template_path(name: str) -> Path:
    for directory in (_EMBEDS_DIR, _POPUPS_DIR, _MODALS_DIR):
        path = directory / f"{name}.yaml"
        if path.is_file():
            return path
    raise MessageTemplateError(f"Message template not found: {name}")


def load_template(name: str) -> Any:
    if name in _cache:
        return _cache[name]
    path = _find_template_path(name)
    spec = _parse_template(name, path)
    _cache[name] = spec
    return spec


def clear_template_cache() -> None:
    _cache.clear()


def render_embed(name: str, **ctx: Any) -> discord.Embed:
    spec = load_template(name)
    if not isinstance(spec, EmbedTemplateSpec):
        raise MessageTemplateError(f"{name} is not an embed template")

    embed = discord.Embed(colour=_resolve_colour(spec.colour, ctx))
    if spec.title is not None:
        embed.title = _substitute(spec.title, ctx)
    if spec.description is not None:
        embed.description = _substitute(spec.description, ctx)
    if spec.author_name is not None:
        author_kwargs: dict[str, str] = {
            "name": _substitute(spec.author_name, ctx),
        }
        if spec.author_icon_url is not None:
            icon = _substitute(spec.author_icon_url, ctx)
            if icon:
                author_kwargs["icon_url"] = icon
        embed.set_author(**author_kwargs)
    for field in spec.fields:
        if not _field_visible(field.when, ctx):
            continue
        embed.add_field(
            name=_substitute(field.name, ctx),
            value=_substitute(field.value, ctx),
            inline=field.inline,
        )
    if spec.footer is not None:
        embed.set_footer(text=_substitute(spec.footer, ctx))
    return embed


def render_text(name: str, **ctx: Any) -> str:
    spec = load_template(name)
    if not isinstance(spec, TextTemplateSpec):
        raise MessageTemplateError(f"{name} is not a text template")
    return _substitute(spec.content, ctx)


def modal_spec(name: str) -> ModalTemplateSpec:
    spec = load_template(name)
    if not isinstance(spec, ModalTemplateSpec):
        raise MessageTemplateError(f"{name} is not a modal template")
    return spec


def relay_embed_spec(name: str = "relay_message") -> RelayEmbedSpec:
    spec = load_template(name)
    if not isinstance(spec, RelayEmbedSpec):
        raise MessageTemplateError(f"{name} is not a relay embed template")
    return spec


def validate_all_templates() -> None:
    errors: list[str] = []
    for directory in (_EMBEDS_DIR, _POPUPS_DIR, _MODALS_DIR):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            name = path.stem
            try:
                _cache.pop(name, None)
                _parse_template(name, path)
            except MessageTemplateError as exc:
                errors.append(str(exc))
    if errors:
        raise MessageTemplateError("Invalid message templates:\n" + "\n".join(errors))
