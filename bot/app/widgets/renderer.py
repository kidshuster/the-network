from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import discord

from bot.app.widgets import custom_id
from bot.app.widgets.dispatch import RenderedModal, RenderedView
from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.loader import load_modal, load_view
from bot.app.widgets.models import ActionBinding, ButtonSpec, SelectSpec
from bot.app.widgets.schema import SlotSpec, StaticButtonSpec
from bot.core.templates import render_embed as core_render_embed
from bot.core.templates import render_text as core_render_text

_STYLE = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
    "link": discord.ButtonStyle.link,
}


def embed(template_id: str, **values: Any) -> discord.Embed:
    return core_render_embed(template_id, **values)


def text(template_id: str, **values: Any) -> str:
    return core_render_text(template_id, **values)


def message(
    template_id: str,
    *,
    values: Mapping[str, Any] | None = None,
    view: discord.ui.View | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"embed": embed(template_id, **dict(values or {}))}
    if view is not None:
        payload["view"] = view
    return payload


def view(
    bot: Any,
    template_id: str,
    *,
    values: Mapping[str, Any] | None = None,
    bindings: Mapping[str, ActionBinding] | None = None,
    slots: Mapping[str, Sequence[ButtonSpec | SelectSpec]] | None = None,
) -> RenderedView:
    del values
    spec = load_view(template_id)
    bindings = dict(bindings or {})
    slots = {key: tuple(items) for key, items in dict(slots or {}).items()}
    rendered = RenderedView(bot, timeout=spec.timeout, template_id=template_id)
    used_bindings: set[str] = set()
    used_slots: set[str] = set()

    for component in spec.components:
        if isinstance(component, SlotSpec):
            items = slots.get(component.slot)
            if items is None:
                raise TemplateRenderError(
                    "missing required slot",
                    template_id=template_id,
                    element_id=component.slot,
                )
            used_slots.add(component.slot)
            for item in items:
                _add_dynamic(rendered, item)
            continue

        if isinstance(component, StaticButtonSpec):
            binding = bindings.get(component.id)
            if binding is None and not component.disabled:
                raise TemplateRenderError(
                    "missing required action binding",
                    template_id=template_id,
                    element_id=component.id,
                )
            if binding is not None:
                used_bindings.add(component.id)
            _add_button(
                rendered,
                ButtonSpec(
                    id=component.id,
                    label=component.label,
                    style=component.style,  # type: ignore[arg-type]
                    action=binding,
                    disabled=component.disabled or binding is None,
                    row=component.row,
                    emoji=component.emoji,
                ),
            )

    extra_bindings = set(bindings) - used_bindings
    if extra_bindings:
        raise TemplateRenderError(
            f"unexpected action bindings {sorted(extra_bindings)}",
            template_id=template_id,
        )
    extra_slots = set(slots) - used_slots
    if extra_slots:
        raise TemplateRenderError(
            f"unexpected slots {sorted(extra_slots)}",
            template_id=template_id,
        )
    return rendered


def modal(
    bot: Any,
    template_id: str,
    *,
    values: Mapping[str, Any] | None = None,
    defaults: Mapping[str, str] | None = None,
    submit: ActionBinding | None = None,
) -> RenderedModal:
    if submit is None:
        raise TemplateRenderError("modal requires submit binding", template_id=template_id)
    spec = load_modal(template_id)
    values = dict(values or {})
    defaults = dict(defaults or {})
    title = _substitute(spec.title, values)
    rendered = RenderedModal(bot, title=title, submit=submit, template_id=template_id)
    for field in spec.fields:
        default = defaults.get(field.id)
        if field.type == "file_upload":
            label: discord.ui.Label[Any] = discord.ui.Label(
                text=field.label,
                description=field.description or discord.utils.MISSING,
                component=discord.ui.FileUpload(
                    required=field.required,
                    max_values=field.max_values,
                ),
            )
            rendered.field_ids.append(field.id)
            rendered.file_fields.add(field.id)
            rendered.add_item(label)
            rendered._labels[field.id] = label
            continue
        text_input: discord.ui.TextInput[Any] = discord.ui.TextInput(
            placeholder=field.placeholder or discord.utils.MISSING,
            max_length=field.max_length,
            required=field.required,
        )
        if default is not None:
            text_input.default = default
        label = discord.ui.Label(
            text=field.label,
            description=field.description or discord.utils.MISSING,
            component=text_input,
        )
        rendered.field_ids.append(field.id)
        rendered.add_item(label)
        rendered._labels[field.id] = label
    return rendered


def _substitute(template: str, values: Mapping[str, Any]) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", "" if value is None else str(value))
    if "{" in result and "}" in result:
        raise TemplateRenderError(f"unresolved placeholder in {template!r}")
    return result


def _add_dynamic(target: RenderedView, item: ButtonSpec | SelectSpec) -> None:
    if isinstance(item, ButtonSpec):
        _add_button(target, item)
    else:
        _add_select(target, item)


def _add_button(target: RenderedView, spec: ButtonSpec) -> None:
    kwargs: dict[str, Any] = {
        "label": spec.label,
        "style": _STYLE.get(spec.style, discord.ButtonStyle.secondary),
        "disabled": spec.disabled,
    }
    if spec.row is not None:
        kwargs["row"] = spec.row
    if spec.emoji is not None:
        kwargs["emoji"] = spec.emoji
    if spec.action is not None and not spec.disabled:
        kwargs["custom_id"] = custom_id.encode(spec.action)
    button: discord.ui.Button[Any] = discord.ui.Button(**kwargs)
    if spec.action is not None and not spec.disabled:
        binding = spec.action

        async def _callback(interaction: discord.Interaction) -> None:
            from bot.app.widgets.dispatch import handle_binding

            await handle_binding(target.bot, interaction, binding)

        button.callback = _callback  # type: ignore[method-assign]
    target.add_item(button)


def _add_select(target: RenderedView, spec: SelectSpec) -> None:
    options = [
        discord.SelectOption(
            label=option.label[:100],
            value=option.value,
            description=(option.description[:100] if option.description else None),
            emoji=option.emoji,
            default=option.default,
        )
        for option in spec.options
    ][:25]
    select: discord.ui.Select[Any] = discord.ui.Select(
        placeholder=spec.placeholder[:150],
        min_values=spec.min_values,
        max_values=min(spec.max_values, max(len(options), 1)),
        options=options,
        custom_id=custom_id.encode(spec.action),
        row=spec.row,
    )
    binding = spec.action

    async def _callback(interaction: discord.Interaction) -> None:
        from bot.app.widgets.dispatch import handle_binding

        raw: dict[str, Any] = (
            dict(interaction.data) if isinstance(interaction.data, dict) else {}
        )
        values = raw.get("values")
        selected = [str(v) for v in values] if isinstance(values, list) else []
        arguments: dict[str, Any] = dict(binding.arguments)
        arguments["selected_client_ids"] = selected
        arguments["select_values"] = selected
        await handle_binding(
            target.bot,
            interaction,
            ActionBinding(action=binding.action, arguments=arguments),
        )

    select.callback = _callback  # type: ignore[method-assign]
    target.add_item(select)
