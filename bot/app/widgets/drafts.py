from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import discord

from bot.app.widgets import custom_id
from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.loader import load_modal, load_view
from bot.app.widgets.schema import SlotSpec, StaticButtonSpec
from bot.contracts.widgets import ButtonSpec, ButtonStyle, RecipeHandler, SelectSpec

_STYLE: dict[ButtonStyle, discord.ButtonStyle] = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
    "link": discord.ButtonStyle.link,
}
_BUTTON_LABEL_MAX = 80
_SELECT_LABEL_MAX = 100
_SELECT_VALUE_MAX = 100
_SELECT_PLACEHOLDER_MAX = 150
_SELECT_DESC_MAX = 100
_VIEW_CHILD_MAX = 25
_SELECT_OPTIONS_MAX = 25
_MODAL_TITLE_MAX = 45
_MODAL_LABEL_MAX = 45
_MODAL_DESC_MAX = 100
_MODAL_PLACEHOLDER_MAX = 100
_ROW_MAX = 4


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


def _require_len(value: str, *, limit: int, tid: str, element_id: str, field: str) -> str:
    if len(value) > limit:
        raise _err(
            f"{field} length {len(value)} exceeds Discord limit {limit}",
            template_id=tid,
            element_id=element_id,
        )
    return value


def _validate_handler(
    registry: Any, handler: RecipeHandler, *, tid: str, element_id: str
) -> None:
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


def _validate_row(row: int | None, *, tid: str, element_id: str) -> None:
    if row is not None and (row < 0 or row > _ROW_MAX):
        raise _err(
            f"row {row} outside Discord range 0-{_ROW_MAX}",
            template_id=tid,
            element_id=element_id,
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
        static = {c.tag for c in comps if isinstance(c, StaticButtonSpec)}
        slots = {c.slot for c in comps if isinstance(c, SlotSpec)}
        for label, bad in (
            ("unbound tags", static - set(self._bindings)),
            ("unknown tags", set(self._bindings) - static),
            ("missing slots", slots - set(self._slots)),
            ("unknown slots", set(self._slots) - slots),
        ):
            if bad:
                raise _err(f"{label} {sorted(bad)}", template_id=tid)
        for tag, handler in self._bindings.items():
            _validate_handler(reg, handler, tid=tid, element_id=tag)
        for slot, items in self._slots.items():
            for item in items:
                eid = getattr(item, "tag", slot)
                if item.handler is None:
                    raise _err(
                        "dynamic interactable missing handler",
                        template_id=tid,
                        element_id=eid,
                    )
                _validate_handler(reg, item.handler, tid=tid, element_id=eid)

        resolved = _resolve_view_components(
            comps,
            bindings=self._bindings,
            slots=self._slots,
            values=self._values,
            tid=tid,
        )
        laid_out = _assign_and_validate_layout(resolved, tid=tid)

        from bot.app.widgets.dispatch import RenderedView

        rendered = RenderedView(bot, timeout=self._spec.timeout, template_id=tid)
        for row, item in laid_out:
            placed = item if item.row == row else _with_row(item, row)
            if isinstance(placed, SelectSpec):
                _add_select(rendered, placed, tid=tid)
            else:
                _add_button(rendered, placed, tid=tid)
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
        _validate_handler(bot.recipe_registry, self._submit, tid=tid, element_id="submit")
        from bot.app.widgets.dispatch import RenderedModal

        title = _require_len(
            _sub(self._spec.title, self._values, tid=tid, field="title") or "",
            limit=_MODAL_TITLE_MAX,
            tid=tid,
            element_id="title",
            field="title",
        )
        rendered = RenderedModal(
            bot,
            title=title,
            submit=self._submit,
            template_id=tid,
        )
        for field in self._spec.fields:
            label_text = _require_len(
                _sub(field.label, self._values, tid=tid, field=f"{field.id}.label") or "",
                limit=_MODAL_LABEL_MAX,
                tid=tid,
                element_id=field.id,
                field="label",
            )
            description = _sub(
                field.description, self._values, tid=tid, field=f"{field.id}.description"
            )
            if description is not None:
                _require_len(
                    description,
                    limit=_MODAL_DESC_MAX,
                    tid=tid,
                    element_id=field.id,
                    field="description",
                )
            if field.type == "file_upload":
                component: Any = discord.ui.FileUpload(
                    required=field.required, max_values=field.max_values
                )
                rendered.file_fields.add(field.id)
            else:
                placeholder = _sub(
                    field.placeholder, self._values, tid=tid, field=f"{field.id}.placeholder"
                )
                if placeholder is not None:
                    _require_len(
                        placeholder,
                        limit=_MODAL_PLACEHOLDER_MAX,
                        tid=tid,
                        element_id=field.id,
                        field="placeholder",
                    )
                component = discord.ui.TextInput(
                    placeholder=placeholder or discord.utils.MISSING,
                    max_length=field.max_length,
                    required=field.required,
                )
                if (default := self._defaults.get(field.id)) is not None:
                    if len(default) > field.max_length:
                        raise _err(
                            f"default exceeds max_length {field.max_length}",
                            template_id=tid,
                            element_id=field.id,
                        )
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


def _with_row(item: ButtonSpec | SelectSpec, row: int) -> ButtonSpec | SelectSpec:
    if item.row == row:
        return item
    if isinstance(item, SelectSpec):
        return SelectSpec(
            tag=item.tag,
            placeholder=item.placeholder,
            options=item.options,
            handler=item.handler,
            min_values=item.min_values,
            max_values=item.max_values,
            row=row,
        )
    return ButtonSpec(
        tag=item.tag,
        label=item.label,
        style=item.style,
        handler=item.handler,
        disabled=item.disabled,
        row=row,
        emoji=item.emoji,
    )


def _resolve_view_components(
    comps: Sequence[StaticButtonSpec | SlotSpec],
    *,
    bindings: Mapping[str, RecipeHandler],
    slots: Mapping[str, tuple[ButtonSpec | SelectSpec, ...]],
    values: Mapping[str, Any],
    tid: str,
) -> list[ButtonSpec | SelectSpec]:
    resolved: list[ButtonSpec | SelectSpec] = []
    for component in comps:
        if isinstance(component, SlotSpec):
            for item in slots[component.slot]:
                if isinstance(item, SelectSpec):
                    resolved.append(item)
                else:
                    resolved.append(_resolved_button(item, values, tid))
            continue
        bound_tag = component.tag
        label = _require_len(
            _sub(component.label, values, tid=tid, field=f"{bound_tag}.label") or "",
            limit=_BUTTON_LABEL_MAX,
            tid=tid,
            element_id=bound_tag,
            field="label",
        )
        resolved.append(
            ButtonSpec(
                tag=bound_tag,
                label=label,
                style=component.style,
                handler=bindings[bound_tag],
                disabled=component.disabled,
                row=component.row,
                emoji=_sub(component.emoji, values, tid=tid, field=f"{bound_tag}.emoji"),
            )
        )
    return resolved


def _assign_and_validate_layout(
    items: Sequence[ButtonSpec | SelectSpec],
    *,
    tid: str,
) -> list[tuple[int, ButtonSpec | SelectSpec]]:
    """Assign rows (matching Discord fill order) and reject invalid resolved layouts."""
    if len(items) > _VIEW_CHILD_MAX:
        raise _err(
            f"view exceeds Discord component limit {_VIEW_CHILD_MAX}",
            template_id=tid,
        )
    weights = [0] * (_ROW_MAX + 1)
    has_select = [False] * (_ROW_MAX + 1)
    laid_out: list[tuple[int, ButtonSpec | SelectSpec]] = []

    for item in items:
        tag = item.tag
        select = isinstance(item, SelectSpec)
        weight = 5 if select else 1
        _validate_row(item.row, tid=tid, element_id=tag)

        explicit_row = item.row
        chosen_row: int
        if explicit_row is not None:
            chosen_row = explicit_row
            if select and weights[chosen_row] > 0:
                raise _err(
                    f"select cannot share row {chosen_row}",
                    template_id=tid,
                    element_id=tag,
                )
            if not select and has_select[chosen_row]:
                raise _err(
                    f"button cannot share row {chosen_row} with a select",
                    template_id=tid,
                    element_id=tag,
                )
            if weights[chosen_row] + weight > 5:
                raise _err(
                    f"row {chosen_row} exceeds Discord capacity (max 5 button slots)",
                    template_id=tid,
                    element_id=tag,
                )
        else:
            assigned: int | None = None
            for candidate in range(_ROW_MAX + 1):
                if select and weights[candidate] != 0:
                    continue
                if not select and has_select[candidate]:
                    continue
                if weights[candidate] + weight <= 5:
                    assigned = candidate
                    break
            if assigned is None:
                raise _err(
                    "no available Discord row for component",
                    template_id=tid,
                    element_id=tag,
                )
            chosen_row = assigned

        weights[chosen_row] += weight
        has_select[chosen_row] = has_select[chosen_row] or select
        laid_out.append((chosen_row, item))
    return laid_out


def _resolved_button(item: ButtonSpec, values: Mapping[str, Any], tid: str) -> ButtonSpec:
    label = _require_len(
        _sub(item.label, values, tid=tid, field=f"{item.tag}.label") or "",
        limit=_BUTTON_LABEL_MAX,
        tid=tid,
        element_id=item.tag,
        field="label",
    )
    return ButtonSpec(
        tag=item.tag,
        label=label,
        style=item.style,
        handler=item.handler,
        disabled=item.disabled,
        row=item.row,
        emoji=_sub(item.emoji, values, tid=tid, field=f"{item.tag}.emoji"),
    )


def _add_button(target: Any, spec: ButtonSpec, *, tid: str) -> None:
    if spec.handler is None:
        raise _err("button missing handler", template_id=tid, element_id=spec.tag)
    _require_len(
        spec.label, limit=_BUTTON_LABEL_MAX, tid=tid, element_id=spec.tag, field="label"
    )
    _validate_row(spec.row, tid=tid, element_id=spec.tag)
    if spec.style not in _STYLE:
        raise _err(f"invalid button style {spec.style!r}", template_id=tid, element_id=spec.tag)
    kwargs: dict[str, Any] = {
        "label": spec.label,
        "style": _STYLE[spec.style],
        "disabled": spec.disabled,
        "custom_id": custom_id.encode(spec.handler),
    }
    if spec.row is not None:
        kwargs["row"] = spec.row
    if spec.emoji is not None:
        kwargs["emoji"] = spec.emoji
    button: discord.ui.Button[Any] = discord.ui.Button(**kwargs)
    handler = spec.handler

    async def _callback(interaction: discord.Interaction) -> None:
        from bot.app.widgets.dispatch import handle_handler

        await handle_handler(target.bot, interaction, handler)

    button.callback = _callback  # type: ignore[method-assign]
    target.add_item(button)


def _add_select(target: Any, spec: SelectSpec, *, tid: str) -> None:
    if len(spec.options) > _SELECT_OPTIONS_MAX:
        raise _err(
            f"select options {len(spec.options)} exceed Discord limit {_SELECT_OPTIONS_MAX}",
            template_id=tid,
            element_id=spec.tag,
        )
    if len(spec.options) == 0:
        raise _err("select requires at least one option", template_id=tid, element_id=spec.tag)
    _require_len(
        spec.placeholder,
        limit=_SELECT_PLACEHOLDER_MAX,
        tid=tid,
        element_id=spec.tag,
        field="placeholder",
    )
    _validate_row(spec.row, tid=tid, element_id=spec.tag)
    if spec.min_values < 0 or spec.max_values < 1:
        raise _err("invalid select value range", template_id=tid, element_id=spec.tag)
    if spec.min_values > spec.max_values:
        raise _err(
            "select min_values exceeds max_values",
            template_id=tid,
            element_id=spec.tag,
        )
    if spec.max_values > len(spec.options):
        raise _err(
            f"select max_values {spec.max_values} exceeds option count {len(spec.options)}",
            template_id=tid,
            element_id=spec.tag,
        )
    options = []
    for option in spec.options:
        _require_len(
            option.label,
            limit=_SELECT_LABEL_MAX,
            tid=tid,
            element_id=spec.tag,
            field="option.label",
        )
        _require_len(
            option.value,
            limit=_SELECT_VALUE_MAX,
            tid=tid,
            element_id=spec.tag,
            field="option.value",
        )
        if option.description is not None:
            _require_len(
                option.description,
                limit=_SELECT_DESC_MAX,
                tid=tid,
                element_id=spec.tag,
                field="option.description",
            )
        options.append(
            discord.SelectOption(
                label=option.label,
                value=option.value,
                description=option.description,
                emoji=option.emoji,
                default=option.default,
            )
        )
    select: discord.ui.Select[Any] = discord.ui.Select(
        placeholder=spec.placeholder,
        min_values=spec.min_values,
        max_values=spec.max_values,
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
