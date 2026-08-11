from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from bot.app.discord.errors import respond_to_error, respond_with_error
from bot.app.discord.responses import defer_ephemeral
from bot.app.templates import modal_spec, render_embed, render_text
from bot.app.widgets.fields import add_modal_fields, collect_modal_values
from bot.app.widgets.ids import encode_component, format_custom_id
from bot.app.widgets.loader import (
    load_modal_meta,
    load_view_spec,
    map_context,
    resolve_path,
    substitute,
    truthy,
)
from bot.app.widgets.policies import check_requires
from bot.app.widgets.schema import ActionSpec, ComponentSpec, ReplySpec, ViewTemplateSpec

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot

logger = logging.getLogger(__name__)

_STYLE_MAP = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}


def _bind(item: discord.ui.Item[Any], callback: Any) -> None:
    item.callback = callback  # type: ignore[method-assign]


def _view_registry(bot: NetworkRelayBot) -> Any:
    from bot.app.widgets.registry import PersistentViewRegistry

    return PersistentViewRegistry(bot)


async def _apply_reply(
    interaction: discord.Interaction,
    reply: ReplySpec,
    *,
    result: Any,
    params: dict[str, Any],
    response: Any | None = None,
) -> None:
    ctx = map_context(reply.map, result=result, params=params)
    # Allow bare result attributes in map defaults
    if not reply.map and result is not None:
        for key in ("server_name", "message", "display_name", "key"):
            if hasattr(result, key):
                ctx.setdefault(key, getattr(result, key))
    kwargs: dict[str, Any] = {}
    if reply.embed:
        kwargs["embed"] = render_embed(reply.embed, **ctx)
    content = render_text(reply.popup, **ctx) if reply.popup else None
    if content is not None:
        kwargs["content"] = content
    if reply.clear_view:
        kwargs["view"] = None
    if reply.edit_message:
        await interaction.response.edit_message(**kwargs)
        return
    if response is not None:
        await response.send(**kwargs, ephemeral=reply.ephemeral)
    elif interaction.response.is_done():
        await interaction.followup.send(**kwargs, ephemeral=reply.ephemeral)
    else:
        await interaction.response.send_message(**kwargs, ephemeral=reply.ephemeral)


def _coerce_params(raw: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            out[key] = int(value)
        else:
            out[key] = value
    return out


def _eval_params(
    templates: dict[str, str],
    *,
    context: dict[str, Any],
    item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ctx = {**context, "context": context, "item": item or {}}
    out: dict[str, Any] = {}
    for key, expr in templates.items():
        if expr.startswith("item.") or expr.startswith("context.") or expr.startswith("params."):
            value = resolve_path(ctx, expr)
        elif expr.startswith("{") and expr.endswith("}"):
            value = resolve_path(ctx, expr[1:-1])
        else:
            # Treat as literal with optional substitution
            value = substitute(expr, {**context, **(item or {})})
            if value == expr and expr in context:
                value = context[expr]
        if value is not None:
            out[key] = value
    return out


async def _inject_payload(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    inject: list[str],
    payload: dict[str, Any],
) -> dict[str, Any] | str:
    guild = interaction.guild
    for name in inject:
        if name == "guild":
            if guild is None:
                return render_text("invalid_guild")
            payload["guild"] = guild
        elif name in ("member", "moderator", "requester"):
            payload[name] = interaction.user
        elif name == "bot_member":
            if guild is None or guild.me is None:
                return render_text("bot_member_unavailable_brief")
            payload["bot_member"] = guild.me
        elif name == "view_registry":
            payload["view_registry"] = _view_registry(bot)
        elif name == "interaction":
            payload["interaction"] = interaction
        else:
            raise ValueError(f"Unknown inject {name!r}")
    return payload


async def _resolve_entities(
    bot: NetworkRelayBot,
    payload: dict[str, Any],
) -> dict[str, Any] | str:
    """Load store entities from ids when recipes need objects."""
    context = bot.bot_context
    if context is None:
        return render_text("bot_not_ready")

    if "subscription" not in payload and "subscription_id" in payload:
        get_sub = context.store.clients.get_subscription_by_id
        subscription = await get_sub(int(payload["subscription_id"]))
        if subscription is None:
            return render_text("subscription_not_found")
        payload["subscription"] = subscription
        if "client" not in payload:
            client = await context.store.clients.get_by_id(subscription.client_id)
            if client is None:
                return render_text("client_was_not_found")
            payload["client"] = client
        if "network" not in payload and subscription.network_id is not None:
            network = await context.store.networks.get_by_id(subscription.network_id)
            if network is not None:
                payload["network"] = network
                payload.setdefault("network_key", network.key)

    if "client" not in payload and "client_id" in payload:
        client = await context.store.clients.get_by_id(int(payload["client_id"]))
        if client is None:
            return render_text("client_not_found")
        payload["client"] = client

    # Resolve network by key only for subscribe-style actions (client_id present).
    if (
        "network" not in payload
        and "network_key" in payload
        and "client_id" in payload
    ):
        get_network = context.store.networks.get_by_key
        network = await get_network(str(payload["network_key"]))
        if network is None:
            return render_text(
                "network_not_found",
                network_key=str(payload["network_key"]),
            )
        payload["network"] = network
    return payload


async def run_action(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    action: ActionSpec,
    *,
    params: dict[str, Any],
    view: DeclarativeView | None = None,
    select_values: list[str] | None = None,
) -> None:
    payload = dict(params)
    if select_values is not None:
        payload["selected_values"] = select_values
        payload["selected_client_ids"] = select_values

    if action.store and view is not None:
        for key_expr, value_expr in action.store.items():
            key = substitute(key_expr, payload)
            if value_expr == "select.values.0" and select_values:
                view.state[key] = int(select_values[0])
            else:
                view.state[key] = resolve_path(
                    {"params": payload, "select": {"values": select_values or []}},
                    value_expr,
                )
        if not interaction.response.is_done():
            await interaction.response.defer()
        return

    if action.finish and view is not None:
        if action.finish == "cancel":
            view.decision = None
            await interaction.response.edit_message(
                content="Cancelled.",
                embed=None,
                view=None,
            )
            view.stop()
            return
        view.decision = dict(view.state)
        await interaction.response.edit_message(
            content="Confirmed.",
            embed=None,
            view=None,
        )
        view.stop()
        return

    response = None

    # Auth/gates before defer so Discord can still use interaction.response.
    checked = await check_requires(
        bot,
        interaction,
        action.require,
        params=payload,
        via="response",
    )
    if checked == "__abort__":
        return
    if isinstance(checked, str):
        if interaction.response.is_done():
            await interaction.followup.send(checked, ephemeral=True)
        else:
            await interaction.response.send_message(checked, ephemeral=True)
        return

    if action.trigger and action.defer:
        response = await defer_ephemeral(interaction)

    if action.open_modal:
        meta_defaults = load_modal_meta(action.open_modal).get("field_defaults") or {}
        defaults = {
            key: str(resolve_path({"params": payload, **payload}, expr) or "")
            for key, expr in meta_defaults.items()
        }
        # Allow context defaults like display_name from client
        if "client" in payload and hasattr(payload["client"], "display_name"):
            defaults.setdefault("display_name", payload["client"].display_name)
        modal = render_modal(
            action.open_modal,
            bot,
            params=payload,
            field_defaults=defaults,
        )
        if interaction.response.is_done():
            # Cannot open modal after defer — should not defer open_modal actions
            await interaction.followup.send(
                "Unable to open form after defer.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(modal)
        return

    if action.open_view:
        # Special-case blacklist: build options then open
        if action.open_view == "blacklist_select":
            built = await _build_blacklist_context(bot, payload)
            if isinstance(built, str):
                if interaction.response.is_done():
                    await interaction.followup.send(built, ephemeral=True)
                else:
                    await interaction.response.send_message(built, ephemeral=True)
                return
            child = render_view("blacklist_select", bot, **built)
            prompt = render_text("blacklist_select_prompt")
            if interaction.response.is_done():
                await interaction.followup.send(prompt, view=child, ephemeral=True)
            else:
                await interaction.response.send_message(prompt, view=child, ephemeral=True)
            return
        if action.open_view == "delete_client_confirm":
            client = payload.get("client")
            server_name = getattr(client, "server_name", "")
            child = render_view(
                "delete_client_confirm",
                bot,
                client_id=payload.get("client_id"),
                client=client,
            )
            text = render_text("delete_client_confirm_prompt", server_name=server_name)
            if interaction.response.is_done():
                await interaction.followup.send(text, view=child, ephemeral=True)
            else:
                await interaction.response.send_message(text, view=child, ephemeral=True)
            return
        child = render_view(action.open_view, bot, **payload)
        if interaction.response.is_done():
            await interaction.followup.send(view=child, ephemeral=True)
        else:
            await interaction.response.send_message(view=child, ephemeral=True)
        return

    if action.reply and not action.trigger:
        await _apply_reply(interaction, action.reply, result=None, params=payload)
        return

    if not action.trigger:
        return

    injected = await _inject_payload(bot, interaction, action.inject, payload)
    if isinstance(injected, str):
        if response is not None:
            await response.send(injected)
        else:
            await interaction.response.send_message(injected, ephemeral=True)
        return
    payload = injected

    resolved = await _resolve_entities(bot, payload)
    if isinstance(resolved, str):
        if response is not None:
            await response.send(resolved)
        else:
            await interaction.response.send_message(resolved, ephemeral=True)
        return
    payload = resolved

    trigger_payload = dict(payload)
    try:
        result = await bot.dispatch_trigger(
            action.trigger,
            **_filter_trigger_kwargs(bot, action.trigger, trigger_payload),
        )
    except Exception as error:
        if action.on_error is not None and response is not None:
            await _apply_reply(
                interaction,
                action.on_error,
                result=error,
                params=payload,
                response=response,
            )
            return
        if response is not None:
            await respond_to_error(
                bot,
                interaction,
                response,
                error,
                operation=action.trigger,
            )
        return

    if getattr(result, "success", None) is False:
        if response is not None:
            await respond_with_error(
                bot,
                interaction,
                response,
                getattr(result, "error", None) or "Unknown error",
                operation=action.trigger,
                title="Request Failed",
            )
        return

    success_reply = action.on_success or action.reply
    if success_reply is not None and action.trigger is not None:
        await _deliver_success(
            bot,
            interaction,
            action.trigger,
            success_reply,
            result=result,
            payload=payload,
            response=response,
        )


async def _deliver_success(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    trigger: str,
    success_reply: ReplySpec,
    *,
    result: Any,
    payload: dict[str, Any],
    response: Any | None,
) -> None:
    if trigger in {"request.approve", "request.deny"}:
        approved = trigger.endswith("approve")
        label = "approved" if approved else "denied"
        params = {
            **payload,
            "label": label.title(),
            "colour": "green" if approved else "orange",
            "description": getattr(result, "message", None) or f"The request was {label}.",
        }
        await _apply_reply(
            interaction, success_reply, result=result, params=params, response=response
        )
        return
    if trigger == "request.submit":
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={
                **payload,
                "client_name": getattr(result, "server_name", None) or "—",
            },
            response=response,
        )
        return
    if trigger == "subscription.confirm_connected":
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={
                **payload,
                "label": "Confirmed",
                "colour": "green",
                "description": (
                    "Subscribe channel marked as connected. "
                    "Relays can flow once both links are active."
                ),
            },
            response=response,
        )
        return
    if trigger == "subscription.create" and result is not None:
        label = "Subscribed" if getattr(result, "created", False) else "Already subscribed"
        network = payload.get("network")
        guild = payload.get("guild") or interaction.guild
        description = f"**{label}** to network `{getattr(network, 'key', '')}`."
        sub = getattr(result, "subscription", None)
        if guild is not None and sub is not None:
            publish = guild.get_channel(sub.publish_channel_id)
            subscribe_ch = guild.get_channel(sub.subscribe_channel_id)
            if isinstance(publish, discord.TextChannel):
                description += f"\nPublish: {publish.mention}"
            if subscribe_ch is not None:
                description += f"\nSubscribe: {subscribe_ch.mention}"
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={**payload, "description": description},
            response=response,
        )
        return
    if trigger == "client.toggle_timecode" and result is not None:
        state = "enabled" if getattr(result, "timecode_enabled", False) else "disabled"
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={**payload, "state": state},
            response=response,
        )
        return
    if trigger == "client.edit_profile" and result is not None:
        warnings = ""
        if getattr(result, "warnings", None):
            warnings = "\n".join(f"• {warning}" for warning in result.warnings)
        display_name = getattr(getattr(result, "client", None), "display_name", "")
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={**payload, "display_name": display_name, "warnings": warnings},
            response=response,
        )
        return
    if trigger == "client.delete":
        client = payload.get("client")
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={
                **payload,
                "server_name": getattr(client, "server_name", ""),
            },
            response=response,
        )
        return
    if trigger == "network.create" and isinstance(result, tuple):
        network, updated_count, relinked_count = result
        await _apply_reply(
            interaction,
            success_reply,
            result=network,
            params={
                **payload,
                "key": network.key,
                "display_name": network.display_name,
                "updated_count": updated_count if updated_count else "",
                "relinked": "1" if relinked_count else "",
            },
            response=response,
        )
        return
    if trigger == "network.delete":
        key = getattr(result, "key", payload.get("key", ""))
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={**payload, "key": key},
            response=response,
        )
        return
    if trigger == "blacklist.replace":
        await _apply_reply(
            interaction,
            success_reply,
            result=result,
            params={**payload, "count": result},
            response=response,
        )
        return
    await _apply_reply(
        interaction,
        success_reply,
        result=result,
        params=payload,
        response=response,
    )


def _filter_trigger_kwargs(
    bot: NetworkRelayBot,
    trigger_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Pass only kwargs accepted by the bound recipe."""
    import inspect

    try:
        spec = bot.trigger_catalog.get(trigger_id)
        recipe_name = spec.recipe
        function = bot.recipe_registry._recipes[recipe_name]  # noqa: SLF001
    except Exception:
        return payload
    signature = inspect.signature(function)
    accepted = {
        name
        for name, param in signature.parameters.items()
        if name != "recipe_context" and param.kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    }
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
        return payload
    return {key: value for key, value in payload.items() if key in accepted}


async def _build_blacklist_context(
    bot: NetworkRelayBot,
    payload: dict[str, Any],
) -> dict[str, Any] | str:
    context = bot.bot_context
    if context is None:
        return render_text("bot_not_ready")
    subscription = payload.get("subscription")
    if subscription is None and "subscription_id" in payload:
        subscription = await context.store.clients.get_subscription_by_id(
            int(payload["subscription_id"])
        )
    if subscription is None:
        return render_text("subscription_not_found")
    if subscription.network_id is None:
        return render_text(
            "network_not_found",
            network_key=str(payload.get("network_key", "")),
        )
    network_subs = await context.store.clients.list_subscriptions_by_network(
        subscription.network_id,
    )
    other_client_ids = [
        sub.client_id for sub in network_subs if sub.client_id != subscription.client_id
    ]
    if not other_client_ids:
        return render_text("no_blacklist_targets")
    blocked = set(await context.store.clients.list_blacklisted_client_ids(subscription.id))
    options: list[dict[str, Any]] = []
    for other_id in other_client_ids[:25]:
        other = await context.store.clients.get_by_id(other_id)
        if other is None:
            continue
        options.append(
            {
                "label": other.display_name[:100],
                "value": str(other.id),
                "description": other.server_name[:100],
                "default": other.id in blocked,
            }
        )
    return {
        "subscription_id": subscription.id,
        "select_options": options,
    }


class DeclarativeModal(discord.ui.Modal):
    def __init__(
        self,
        bot: NetworkRelayBot,
        name: str,
        *,
        params: dict[str, Any] | None = None,
        field_defaults: dict[str, str] | None = None,
    ) -> None:
        self._spec = modal_spec(name)
        self._meta = load_modal_meta(name)
        super().__init__(title=self._spec.title)
        self._bot = bot
        self._name = name
        self._params = dict(params or {})
        defaults = dict(self._meta.get("field_defaults") or {})
        defaults.update(field_defaults or {})
        # Resolve default templates against params
        resolved_defaults = {
            key: substitute(str(value), self._params) for key, value in defaults.items()
        }
        self._fields = add_modal_fields(self, self._spec, defaults=resolved_defaults)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        meta = self._meta
        require = list(meta.get("require") or [])
        inject = list(meta.get("inject") or [])
        trigger = self._spec.trigger
        if not trigger:
            await interaction.response.send_message(
                "Modal is misconfigured (missing trigger).",
                ephemeral=True,
            )
            return

        response = await defer_ephemeral(interaction)
        checked = await check_requires(
            self._bot,
            interaction,
            require,
            params=self._params,
            via="followup",
        )
        if checked == "__abort__":
            return
        if isinstance(checked, str):
            await response.send(checked)
            return

        values = collect_modal_values(self._fields, self._spec)
        field_map: dict[str, str] = meta.get("field_map") or {}
        payload = dict(self._params)
        for field_id, value in values.items():
            if field_id.endswith("_attachments"):
                continue
            target = field_map.get(field_id, field_id)
            # Common aliases used by recipes
            if field_id == "name" and "server_name" not in payload:
                payload["server_name"] = value
            if field_id == "profile_image":
                payload["profile_image"] = value
            payload[target] = value

        if "profile_image" in values and values["profile_image"] is None:
            # required file missing
            field = next((f for f in self._spec.fields if f.id == "profile_image"), None)
            if field is not None and field.required:
                await respond_with_error(
                    self._bot,
                    interaction,
                    response,
                    "A profile image upload is required.",
                    operation=trigger,
                    title="Request Failed",
                )
                return

        injected = await _inject_payload(self._bot, interaction, inject, payload)
        if isinstance(injected, str):
            await response.send(injected)
            return
        payload = injected

        try:
            result = await self._bot.dispatch_trigger(
                trigger,
                **_filter_trigger_kwargs(self._bot, trigger, payload),
            )
        except Exception as error:
            await respond_to_error(
                self._bot,
                interaction,
                response,
                error,
                operation=trigger,
            )
            return

        if getattr(result, "success", None) is False:
            await respond_with_error(
                self._bot,
                interaction,
                response,
                getattr(result, "error", None) or "Unknown error",
                operation=trigger,
                title="Request Failed",
            )
            return

        success_reply = _reply_from_raw(meta.get("on_success"))
        if success_reply is None:
            await response.send(content="Done.", ephemeral=True)
            return
        await _deliver_success(
            self._bot,
            interaction,
            trigger,
            success_reply,
            result=result,
            payload=payload,
            response=response,
        )


def _reply_from_raw(raw: Any) -> ReplySpec | None:
    if raw is None:
        return None
    if isinstance(raw, dict) and "reply" in raw:
        return ReplySpec.model_validate(raw["reply"])
    if isinstance(raw, dict):
        return ReplySpec.model_validate(raw)
    return None


class DeclarativeView(discord.ui.View):
    def __init__(
        self,
        bot: NetworkRelayBot,
        spec: ViewTemplateSpec,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        timeout = spec.timeout
        super().__init__(timeout=timeout)
        self._bot = bot
        self.spec = spec
        self.context: dict[str, Any] = dict(context or {})
        self.state: dict[str, Any] = {}
        self.decision: Any = None
        self._actions: dict[str, tuple[ComponentSpec, dict[str, Any]]] = {}
        self._build()

    def _build(self) -> None:
        for component in self.spec.components:
            if component.foreach:
                items = self.context.get(component.foreach) or []
                for index, item in enumerate(items):
                    item_ctx = item if isinstance(item, dict) else {"value": item, "key": item}
                    when_ctx = {**self.context, "item": item_ctx}
                    if component.when and not truthy(component.when, when_ctx):
                        continue
                    self._add_component(component, item=item_ctx, index=index)
            else:
                if component.when and not truthy(component.when, self.context):
                    continue
                self._add_component(component, item=None, index=None)

    def _add_component(
        self,
        component: ComponentSpec,
        *,
        item: dict[str, Any] | None,
        index: int | None,
    ) -> None:
        params = dict(self.context)
        # Flatten common scalar context into params for custom_id
        for key in ("client_id", "request_id", "subscription_id", "network_key"):
            if key in self.context:
                params[key] = self.context[key]
        evaled = _eval_params(component.params, context=self.context, item=item)
        params.update(evaled)
        # Coerce ints
        for key, value in list(params.items()):
            if isinstance(value, str) and value.isdigit():
                params[key] = int(value)

        label_ctx = {**self.context, **params, **(item or {})}
        if item and "key" in item:
            label_ctx.setdefault("key", item["key"])

        if component.custom_id:
            custom_id = format_custom_id(component.custom_id, params)
        else:
            encode_params: dict[str, str | int] = {}
            for key in ("client_id", "request_id", "subscription_id", "network_key"):
                if key in params:
                    encode_params[key] = params[key]
            if item and "key" in item:
                encode_params["network_key"] = str(item["key"])
            suffix = component.id if index is None else f"{component.id}_{index}"
            custom_id = encode_component(self.spec.id, suffix, encode_params)

        disabled = component.disabled
        if component.disabled_when:
            disabled = truthy(
                component.disabled_when,
                {**self.context, "item": item or {}, **params},
            )

        if component.type == "select":
            options_source = component.options_from or "select_options"
            if options_source.startswith("item.") and item is not None:
                options_data = resolve_path({"item": item}, options_source) or []
            else:
                options_data = self.context.get(options_source) or []
            options = [
                discord.SelectOption(
                    label=str(opt.get("label", opt.get("value", "")))[:100],
                    value=str(opt["value"]),
                    description=(str(opt["description"])[:100] if opt.get("description") else None),
                    default=bool(opt.get("default", False)),
                )
                for opt in options_data
                if isinstance(opt, dict) and "value" in opt
            ]
            if not options:
                return
            select_kwargs: dict[str, Any] = {
                "placeholder": component.placeholder or "Select…",
                "min_values": component.min_values,
                "max_values": min(max(component.max_values, 1), len(options)),
                "options": options,
            }
            if self.timeout is None:
                select_kwargs["custom_id"] = custom_id
            elif component.custom_id:
                select_kwargs["custom_id"] = custom_id
            if component.row is not None:
                select_kwargs["row"] = component.row
            select: discord.ui.Select[Any] = discord.ui.Select(**select_kwargs)
            self._actions[custom_id] = (component, params)
            _bind(select, self._make_callback(custom_id))
            self.add_item(select)
            return

        label = substitute(component.label or component.id, label_ctx)
        style = _STYLE_MAP.get(component.style, discord.ButtonStyle.secondary)
        # Support style_when via context key style
        if component.id == "timecode" and "timecode_enabled" in self.context:
            style = (
                discord.ButtonStyle.success
                if self.context["timecode_enabled"]
                else discord.ButtonStyle.secondary
            )
            label = (
                "Timecodes: On"
                if self.context["timecode_enabled"]
                else "Timecodes: Off"
            )
        button_kwargs: dict[str, Any] = {
            "label": label[:80],
            "style": style,
            "disabled": disabled,
        }
        if self.timeout is None or component.custom_id:
            button_kwargs["custom_id"] = custom_id
        if component.row is not None:
            button_kwargs["row"] = component.row
        button: discord.ui.Button[Any] = discord.ui.Button(**button_kwargs)
        self._actions[getattr(button, "custom_id", None) or custom_id] = (component, params)

        async def callback(
            interaction: discord.Interaction,
            *,
            key: str = custom_id,
        ) -> None:
            await self._handle(interaction, key)

        _bind(button, callback)
        self.add_item(button)

    def _make_callback(self, custom_id: str) -> Any:
        async def callback(interaction: discord.Interaction) -> None:
            await self._handle(interaction, custom_id)

        return callback

    async def _handle(self, interaction: discord.Interaction, custom_id: str) -> None:
        # Match by custom_id; for ephemeral buttons without custom_id, match first action
        entry = self._actions.get(custom_id)
        if entry is None and len(self._actions) == 1:
            entry = next(iter(self._actions.values()))
        if entry is None:
            # Try matching interaction data custom_id
            data_id = getattr(interaction.data, "get", lambda *_: None)("custom_id")
            if isinstance(interaction.data, dict):
                data_id = interaction.data.get("custom_id")
            if isinstance(data_id, str):
                entry = self._actions.get(data_id)
        if entry is None:
            await interaction.response.send_message(
                "This control is no longer available.",
                ephemeral=True,
            )
            return
        component, params = entry
        action = component.action
        # open_modal must not defer
        if action.open_modal:
            action = action.model_copy(update={"defer": False})
        if action.open_view and action.open_view in {
            "blacklist_select",
            "delete_client_confirm",
        }:
            action = action.model_copy(update={"defer": False})
        if action.finish or action.store:
            action = action.model_copy(update={"defer": False})

        select_values: list[str] | None = None
        if component.type == "select":
            raw_data = interaction.data
            values: Any = None
            if isinstance(raw_data, dict):
                values = raw_data.get("values")
            if isinstance(values, list):
                select_values = [str(v) for v in values]
            else:
                for child in self.children:
                    if isinstance(child, discord.ui.Select) and child.custom_id == custom_id:
                        select_values = list(child.values)
                        break

        # Resolve client for open_modal edit profile
        if action.open_modal == "edit_client_profile" and "client_id" in params:
            resolved = await _resolve_entities(self._bot, dict(params))
            if isinstance(resolved, str):
                await interaction.response.send_message(resolved, ephemeral=True)
                return
            params = resolved

        if action.open_view == "delete_client_confirm":
            resolved = await _resolve_entities(self._bot, dict(params))
            if isinstance(resolved, str):
                await interaction.response.send_message(resolved, ephemeral=True)
                return
            params = resolved
            checked = await check_requires(
                self._bot,
                interaction,
                action.require,
                params=params,
                via="response",
            )
            if checked == "__abort__":
                return
            if isinstance(checked, str):
                await interaction.response.send_message(checked, ephemeral=True)
                return
            action = action.model_copy(update={"require": []})

        await run_action(
            self._bot,
            interaction,
            action,
            params=params,
            view=self,
            select_values=select_values,
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True


def render_view(name: str, bot: NetworkRelayBot, **context: Any) -> DeclarativeView:
    spec = load_view_spec(name)
    # Normalize networks foreach input
    if "network_keys" in context and "networks" not in context:
        keys = context["network_keys"]
        subscribed = context.get("subscribed_keys") or set()
        context["networks"] = [
            {"key": key, "subscribed": key in subscribed}
            for key in list(keys)[:22]
        ]
    return DeclarativeView(bot, spec, context=context)


def render_modal(
    name: str,
    bot: NetworkRelayBot,
    *,
    params: dict[str, Any] | None = None,
    field_defaults: dict[str, str] | None = None,
) -> DeclarativeModal:
    return DeclarativeModal(bot, name, params=params, field_defaults=field_defaults)
