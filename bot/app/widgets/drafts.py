from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import discord

from bot.app.widgets import custom_id
from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.loader import load_modal, load_view
from bot.app.widgets.schema import SlotSpec, StaticButtonSpec
from bot.contracts.widgets import ButtonSpec, RecipeHandler, SelectSpec

_STYLE = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
    "link": discord.ButtonStyle.link,
}

def _err(detail: str, *, template_id: str, element_id: str | None = None) -> TemplateRenderError:
    return TemplateRenderError(detail, template_id=template_id, element_id=element_id)

def _sub(text: str | None, values: Mapping[str, Any], *, tid: str, field: str) -> str | None:
    if text is None:
        return None
    result = text
    for key, value in values.items():
        result = result.replace("{" + key + "}", "" if value is None else str(value))
    if "{" in result and "}" in result:
        raise _err(f"unresolved placeholder in {field}", template_id=tid, element_id=field)
    return result

def _validate(registry: Any, handler: RecipeHandler, *, tid: str, element_id: str) -> None:
    if not registry.has(handler.recipe):
        raise _err(
            f"unregistered recipe {handler.recipe!r}",
            template_id=tid,
            element_id=element_id,
        )
    try:
        custom_id.encode(handler)
    except TemplateRenderError as exc:
        raise _err(str(exc), template_id=tid, element_id=element_id) from exc

def _button_spec(item: ButtonSpec, values: Mapping[str, Any], tid: str) -> ButtonSpec:
    return ButtonSpec(
        tag=item.tag,
        label=_sub(item.label, values, tid=tid, field=f"{item.tag}.label") or "",
        style=item.style,
        handler=item.handler,
        disabled=item.disabled,
        row=item.row,
        emoji=item.emoji,
    )

class ViewDraft:
    def __init__(self, template_id: str, values: Mapping[str, Any] | None = None) -> None:
        self.template_id = template_id
        self._values = dict(values or {})
        self._bindings: dict[str, RecipeHandler] = {}
        self._slots: dict[str, tuple[ButtonSpec | SelectSpec, ...]] = {}
        self._spec = load_view(template_id)

    def bind(self, tag: str, handler: RecipeHandler) -> ViewDraft:
        if tag in self._bindings:
            raise _err("tag bound twice", template_id=self.template_id, element_id=tag)
        self._bindings[tag] = handler
        return self

    def fill(self, slot: str, components: Sequence[ButtonSpec | SelectSpec]) -> ViewDraft:
        if slot in self._slots:
            raise _err("slot filled twice", template_id=self.template_id, element_id=slot)
        self._slots[slot] = tuple(components)
        return self

    def build(self, bot: Any) -> discord.ui.View:
        tid, reg, comps = self.template_id, bot.recipe_registry, self._spec.components
        static = {
            c.tag
            for c in comps
            if isinstance(c, StaticButtonSpec) and c.tag and not c.disabled
        }
        all_static = {c.tag for c in comps if isinstance(c, StaticButtonSpec) and c.tag}
        slots = {c.slot for c in comps if isinstance(c, SlotSpec)}
        for label, bad in (
            ("unbound tags", static - set(self._bindings)),
            ("unknown tags", set(self._bindings) - all_static),
            ("missing slots", slots - set(self._slots)),
            ("unknown slots", set(self._slots) - slots),
        ):
            if bad:
                raise _err(f"{label} {sorted(bad)}", template_id=tid)
        for tag, handler in self._bindings.items():
            _validate(reg, handler, tid=tid, element_id=tag)
        for slot, items in self._slots.items():
            for item in items:
                item_handler = item.handler
                eid = getattr(item, "tag", slot)
                if item_handler is None and not (
                    isinstance(item, ButtonSpec) and item.disabled
                ):
                    raise _err(
                        "dynamic interactable missing handler",
                        template_id=tid,
                        element_id=eid,
                    )
                if item_handler is not None:
                    _validate(reg, item_handler, tid=tid, element_id=eid)

        from bot.app.widgets.dispatch import RenderedView

        rendered = RenderedView(bot, timeout=self._spec.timeout, template_id=tid)
        for component in comps:
            if isinstance(component, SlotSpec):
                for item in self._slots[component.slot]:
                    if isinstance(item, SelectSpec):
                        _add_select(rendered, item)
                    else:
                        _add_button(rendered, _button_spec(item, self._values, tid))
                continue
            bound_tag = component.tag
            assert bound_tag is not None
            bound = self._bindings.get(bound_tag)
            _add_button(
                rendered,
                ButtonSpec(
                    tag=bound_tag,
                    label=_sub(
                        component.label, self._values, tid=tid, field=f"{bound_tag}.label"
                    )
                    or "",
                    style=component.style,  # type: ignore[arg-type]
                    handler=bound,
                    disabled=component.disabled or bound is None,
                    row=component.row,
                    emoji=_sub(component.emoji, self._values, tid=tid, field=f"{bound_tag}.emoji"),
                ),
            )
        if len(rendered.children) > 25:
            raise _err("view exceeds Discord component limit", template_id=tid)
        return rendered

class ModalDraft:
    def __init__(self, template_id: str, values: Mapping[str, Any] | None = None) -> None:
        self.template_id = template_id
        self._values = dict(values or {})
        self._defaults: dict[str, str] = {}
        self._submit: RecipeHandler | None = None
        self._spec = load_modal(template_id)

    def defaults(self, **values: str) -> ModalDraft:
        self._defaults.update({key: str(value) for key, value in values.items()})
        return self

    def on_submit(self, handler: RecipeHandler) -> ModalDraft:
        if self._submit is not None:
            raise _err("submit recipe already attached", template_id=self.template_id)
        self._submit = handler
        return self

    def build(self, bot: Any) -> discord.ui.Modal:
        tid = self.template_id
        if self._submit is None:
            raise _err("modal requires submit recipe", template_id=tid)
        _validate(bot.recipe_registry, self._submit, tid=tid, element_id="submit")
        from bot.app.widgets.dispatch import RenderedModal

        rendered = RenderedModal(
            bot,
            title=_sub(self._spec.title, self._values, tid=tid, field="title") or "",
            submit=self._submit,
            template_id=tid,
        )
        for field in self._spec.fields:
            label_text = _sub(field.label, self._values, tid=tid, field=f"{field.id}.label") or ""
            description = _sub(
                field.description, self._values, tid=tid, field=f"{field.id}.description"
            )
            if field.type == "file_upload":
                component: Any = discord.ui.FileUpload(
                    required=field.required, max_values=field.max_values
                )
                rendered.file_fields.add(field.id)
            else:
                component = discord.ui.TextInput(
                    placeholder=_sub(
                        field.placeholder, self._values, tid=tid, field=f"{field.id}.placeholder"
                    )
                    or discord.utils.MISSING,
                    max_length=field.max_length,
                    required=field.required,
                )
                if (default := self._defaults.get(field.id)) is not None:
                    component.default = default
            label: discord.ui.Label[Any] = discord.ui.Label(
                text=label_text,
                description=description or discord.utils.MISSING,
                component=component,
            )
            rendered.field_ids.append(field.id)
            rendered.add_item(label)
            rendered._labels[field.id] = label
        return rendered

def view(template_id: str, **values: Any) -> ViewDraft:
    return ViewDraft(template_id, values)

def modal(template_id: str, **values: Any) -> ModalDraft:
    return ModalDraft(template_id, values)

def _add_button(target: Any, spec: ButtonSpec) -> None:
    kwargs: dict[str, Any] = {
        "label": spec.label,
        "style": _STYLE[spec.style],
        "disabled": spec.disabled,
    }
    if spec.row is not None:
        kwargs["row"] = spec.row
    if spec.emoji is not None:
        kwargs["emoji"] = spec.emoji
    active = spec.handler is not None and not spec.disabled
    if active:
        kwargs["custom_id"] = custom_id.encode(spec.handler)  # type: ignore[arg-type]
    button: discord.ui.Button[Any] = discord.ui.Button(**kwargs)
    if active:
        handler = spec.handler

        async def _callback(interaction: discord.Interaction) -> None:
            from bot.app.widgets.dispatch import handle_handler

            await handle_handler(target.bot, interaction, handler)  # type: ignore[arg-type]

        button.callback = _callback  # type: ignore[method-assign]
    target.add_item(button)

def _add_select(target: Any, spec: SelectSpec) -> None:
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
        custom_id=custom_id.encode(spec.handler),
        row=spec.row,
    )
    handler = spec.handler

    async def _callback(interaction: discord.Interaction) -> None:
        from bot.app.widgets.dispatch import handle_handler

        raw = dict(interaction.data) if isinstance(interaction.data, dict) else {}
        values = raw.get("values")
        selected = [str(v) for v in values] if isinstance(values, list) else []
        await handle_handler(
            target.bot,
            interaction,
            handler,
            submitted={"selected_client_ids": selected, "select_values": selected},
        )

    select.callback = _callback  # type: ignore[method-assign]
    target.add_item(select)
