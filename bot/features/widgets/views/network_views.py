from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import discord

from bot.app.discord.errors import respond_with_error
from bot.app.discord.responses import defer_ephemeral
from bot.app.templates import render_embed, render_text
from bot.features.widgets.views._auth import MembershipPolicy, ensure_client_access
from bot.features.widgets.views._view_helpers import bind_item_callback
from bot.features.widgets.views.custom_ids import (
    blacklist_button,
    delete_client_button,
    leave_network_button,
    profile_edit_button,
    subscribe_connected_button,
    subscribe_network_button,
    timecode_toggle_button,
)
from bot.features.widgets.views.persistent_views import PersistentViewRegistry

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot

logger = logging.getLogger(__name__)

SUBSCRIBED_CHANNEL_CONNECTED_LABEL = "Subscribed channel connected"


MAX_PROFILE_NETWORK_BUTTONS = 22


class NetworkProfileView(discord.ui.View):
    def __init__(
        self,
        bot: NetworkRelayBot,
        client_id: int,
        network_keys: list[str],
        *,
        subscribed_keys: set[str] | None = None,
        timecode_enabled: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._client_id = client_id
        subscribed = subscribed_keys or set()
        for key in network_keys[:MAX_PROFILE_NETWORK_BUTTONS]:
            already_subscribed = key in subscribed
            button: discord.ui.Button[Any] = discord.ui.Button(
                label=f"Join {key}",
                style=discord.ButtonStyle.primary,
                custom_id=subscribe_network_button(client_id, key),
                disabled=already_subscribed,
            )
            bind_item_callback(button, self._make_subscribe_callback(key))
            self.add_item(button)
        timecode_style = (
            discord.ButtonStyle.success if timecode_enabled else discord.ButtonStyle.secondary
        )
        timecode: discord.ui.Button[Any] = discord.ui.Button(
            label="Timecodes: On" if timecode_enabled else "Timecodes: Off",
            style=timecode_style,
            custom_id=timecode_toggle_button(client_id),
            row=4,
        )
        bind_item_callback(timecode, self._timecode_toggle_callback)
        self.add_item(timecode)
        edit: discord.ui.Button[Any] = discord.ui.Button(
            label="Edit Profile",
            style=discord.ButtonStyle.secondary,
            custom_id=profile_edit_button(client_id),
            row=4,
        )
        bind_item_callback(edit, self._edit_callback)
        self.add_item(edit)
        delete: discord.ui.Button[Any] = discord.ui.Button(
            label="Delete Client",
            style=discord.ButtonStyle.danger,
            custom_id=delete_client_button(client_id),
            row=4,
        )
        bind_item_callback(delete, self._delete_callback)
        self.add_item(delete)

    def _make_subscribe_callback(
        self, network_key: str
    ) -> Callable[[discord.Interaction], Coroutine[Any, Any, None]]:
        async def callback(interaction: discord.Interaction) -> None:
            await self._handle_subscribe(interaction, network_key)

        return callback

    async def _handle_subscribe(
        self,
        interaction: discord.Interaction,
        network_key: str,
    ) -> None:
        response = await defer_ephemeral(interaction)
        context = self._bot.bot_context
        guild = interaction.guild
        if context is None or guild is None:
            await response.send_text("bot_not_ready")
            return

        client = await context.store.clients.get_by_id(self._client_id)
        if client is None:
            await response.send_text("client_not_found")
            return

        if not await ensure_client_access(
            interaction,
            guild,
            client,
            popup_key="client_role_required_subscribe",
            membership_policy=MembershipPolicy.ALLOW_NON_MEMBER,
            via="followup",
        ):
            return

        network = await context.store.networks.get_by_key(network_key)
        if network is None:
            await response.send_text("network_not_found", network_key=network_key)
            return

        bot_member = guild.me
        if bot_member is None:
            await response.send_text("bot_member_unavailable_brief")
            return

        from bot.features.channels.stickies.subscription import sync_subscription_setup
        from bot.features.clients.subscription import ClientSubscriptionService

        service = ClientSubscriptionService()
        result = await service.subscribe_client(
            guild,
            bot_member,
            client=client,
            network_id=network.id,
            network_key=network_key,
            client_repo=context.store.clients,
            network_repo=context.store.networks,
            access_role_name=self._bot.settings.network_access_role_name,
        )
        if not result.success or result.subscription is None:
            await respond_with_error(
                self._bot,
                interaction,
                response,
                result.error or "Unknown error",
                operation="subscription.create",
                title="Subscribe Failed",
            )
            return

        await context.refresh_projections()

        view_registry = PersistentViewRegistry(self._bot)
        if result.created:
            await sync_subscription_setup(
                self._bot,
                context,
                guild,
                client=client,
                subscription=result.subscription,
                network=network,
                view_registry=view_registry,
            )
        else:
            from bot.features.clients.profile_sync import refresh_client_profile_message

            await refresh_client_profile_message(
                self._bot,
                context,
                guild,
                client,
                view_registry=view_registry,
            )

        label = "Subscribed" if result.created else "Already subscribed"
        sub = result.subscription
        publish = guild.get_channel(sub.publish_channel_id)
        subscribe = guild.get_channel(sub.subscribe_channel_id)
        description = f"**{label}** to network `{network.key}`."
        if isinstance(publish, discord.TextChannel):
            description += f"\nPublish: {publish.mention}"
        if subscribe is not None:
            description += f"\nSubscribe: {subscribe.mention}"
        await response.send(
            embed=render_embed("subscribe_success", description=description),
            ephemeral=True,
        )

    async def _timecode_toggle_callback(self, interaction: discord.Interaction) -> None:
        response = await defer_ephemeral(interaction)
        context = self._bot.bot_context
        guild = interaction.guild
        if context is None or guild is None:
            await response.send_text("bot_not_ready")
            return

        client = await context.store.clients.get_by_id(self._client_id)
        if client is None:
            await response.send_text("client_not_found")
            return

        if not await ensure_client_access(
            interaction,
            guild,
            client,
            popup_key="client_role_required_edit",
            membership_policy=MembershipPolicy.ALLOW_NON_MEMBER,
            via="followup",
            ephemeral=None,
        ):
            return

        updated = await context.store.clients.set_timecode_enabled(
            client.id,
            not client.timecode_enabled,
        )
        await context.refresh_client_counts()

        from bot.features.clients.profile_sync import refresh_client_profile_message

        await refresh_client_profile_message(
            self._bot,
            context,
            guild,
            updated,
            view_registry=PersistentViewRegistry(self._bot),
        )

        state = "enabled" if updated.timecode_enabled else "disabled"
        await response.send(
            render_text("timecode_toggle_updated", state=state),
            ephemeral=True,
        )

    async def _edit_callback(self, interaction: discord.Interaction) -> None:
        from bot.features.widgets.views.profile_views import EditClientProfileModal

        context = self._bot.bot_context
        if context is None:
            await interaction.response.send_message(render_text("bot_not_ready"), ephemeral=True)
            return
        client = await context.store.clients.get_by_id(self._client_id)
        if client is None:
            await interaction.response.send_message(
                render_text("client_not_found"),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            EditClientProfileModal(self._bot, self._client_id, client.display_name),
        )

    async def _delete_callback(self, interaction: discord.Interaction) -> None:
        context = self._bot.bot_context
        if context is None:
            await interaction.response.send_message(render_text("bot_not_ready"), ephemeral=True)
            return

        client = await context.store.clients.get_by_id(self._client_id)
        if client is None:
            await interaction.response.send_message(
                render_text("client_not_found"),
                ephemeral=True,
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(render_text("invalid_member"), ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(render_text("invalid_guild"), ephemeral=True)
            return

        if not await ensure_client_access(
            interaction,
            guild,
            client,
            popup_key="client_role_required_delete",
            membership_policy=MembershipPolicy.REQUIRED,
            via="response",
        ):
            return

        from bot.features.widgets.views.profile_views import DeleteClientConfirmView

        await interaction.response.send_message(
            render_text(
                "delete_client_confirm_prompt",
                server_name=client.server_name,
            ),
            view=DeleteClientConfirmView(self._bot, self._client_id),
            ephemeral=True,
        )


async def handle_subscribe_connected(
    bot: NetworkRelayBot,
    interaction: discord.Interaction,
    subscription_id: int,
    network_key: str,
) -> None:
    """Mark subscribe channel connected and refresh setup UI."""
    response = await defer_ephemeral(interaction)
    context = bot.bot_context
    guild = interaction.guild
    if context is None or guild is None:
        await response.send_text("bot_not_ready")
        return

    subscription = await context.store.clients.get_subscription_by_id(subscription_id)
    if subscription is None:
        await response.send_text("subscription_not_found")
        return

    client = await context.store.clients.get_by_id(subscription.client_id)
    if client is None:
        await response.send_text("client_was_not_found")
        return

    network = await context.store.networks.get_by_id(subscription.network_id or 0)
    if network is None:
        await response.send_text("network_not_found", network_key=network_key)
        return

    from bot.features.channels.stickies.subscription import sync_subscription_setup

    view_registry = PersistentViewRegistry(bot)
    subscription = await context.store.clients.set_subscribe_confirmed(
        subscription.id,
        True,
    )
    await sync_subscription_setup(
        bot,
        context,
        guild,
        client=client,
        subscription=subscription,
        network=network,
        view_registry=view_registry,
    )
    await response.send(
        embed=render_embed(
            "review_success",
            label="Confirmed",
            colour="green",
            description=(
                "Subscribe channel marked as connected. Relays can flow once both links are active."
            ),
        ),
        ephemeral=True,
    )


class SubscribeSetupView(discord.ui.View):
    def __init__(
        self,
        bot: NetworkRelayBot,
        subscription_id: int,
        network_key: str,
    ) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._subscription_id = subscription_id
        self._network_key = network_key

        connected: discord.ui.Button[Any] = discord.ui.Button(
            label=SUBSCRIBED_CHANNEL_CONNECTED_LABEL,
            style=discord.ButtonStyle.success,
            custom_id=subscribe_connected_button(subscription_id),
        )
        bind_item_callback(connected, self._subscribe_connected_callback)
        self.add_item(connected)

    async def _subscribe_connected_callback(self, interaction: discord.Interaction) -> None:
        await handle_subscribe_connected(
            self._bot,
            interaction,
            self._subscription_id,
            self._network_key,
        )


class SubscriptionModerationView(discord.ui.View):
    def __init__(
        self,
        bot: NetworkRelayBot,
        subscription_id: int,
        network_key: str,
        *,
        show_subscribe_connected: bool = False,
        show_blacklist: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._subscription_id = subscription_id
        self._network_key = network_key

        if show_subscribe_connected:
            connected: discord.ui.Button[Any] = discord.ui.Button(
                label=SUBSCRIBED_CHANNEL_CONNECTED_LABEL,
                style=discord.ButtonStyle.success,
                custom_id=subscribe_connected_button(subscription_id),
            )
            bind_item_callback(connected, self._subscribe_connected_callback)
            self.add_item(connected)

        if show_blacklist:
            blacklist: discord.ui.Button[Any] = discord.ui.Button(
                label="Blacklist",
                style=discord.ButtonStyle.danger,
                custom_id=blacklist_button(subscription_id),
            )
            bind_item_callback(blacklist, self._blacklist_callback)
            self.add_item(blacklist)

        leave: discord.ui.Button[Any] = discord.ui.Button(
            label=f"Leave {network_key}",
            style=discord.ButtonStyle.secondary,
            custom_id=leave_network_button(subscription_id),
        )
        bind_item_callback(leave, self._leave_callback)
        self.add_item(leave)

    async def _subscribe_connected_callback(self, interaction: discord.Interaction) -> None:
        await handle_subscribe_connected(
            self._bot,
            interaction,
            self._subscription_id,
            self._network_key,
        )

    async def _leave_callback(self, interaction: discord.Interaction) -> None:
        response = await defer_ephemeral(interaction)
        context = self._bot.bot_context
        if context is None:
            await response.send_text("bot_not_ready")
            return

        subscription = await context.store.clients.get_subscription_by_id(
            self._subscription_id,
        )
        if subscription is None:
            await response.send_text("subscription_not_found")
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await response.send_text("invalid_member")
            return

        client = await context.store.clients.get_by_id(subscription.client_id)
        if client is None:
            await response.send_text("client_was_not_found")
            return

        guild = interaction.guild
        if guild is None:
            await response.send_text("invalid_guild")
            return

        if not await ensure_client_access(
            interaction,
            guild,
            client,
            popup_key="client_role_required_leave",
            membership_policy=MembershipPolicy.REQUIRED,
            via="followup",
        ):
            return

        network = (
            await context.store.networks.get_by_id(subscription.network_id)
            if subscription.network_id is not None
            else None
        )
        network_key = self._network_key
        if network is not None:
            network_key = network.key

        bot_member = guild.me
        if bot_member is None:
            await response.send_text("bot_member_unavailable_brief")
            return

        from bot.features.clients.profile_sync import refresh_client_profile_message
        from bot.features.clients.subscription import ClientSubscriptionService

        service = ClientSubscriptionService()
        result = await service.unsubscribe_client(
            guild,
            bot_member,
            client=client,
            subscription=subscription,
            network_key=network_key,
            client_repo=context.store.clients,
            network_repo=context.store.networks,
        )
        if not result.success:
            await respond_with_error(
                self._bot,
                interaction,
                response,
                result.error or "Unknown error",
                operation="subscription.delete",
                title="Could not leave network",
            )
            return

        await context.refresh_projections()
        await refresh_client_profile_message(
            self._bot,
            context,
            guild,
            client,
            view_registry=PersistentViewRegistry(self._bot),
        )

        await response.send(
            embed=render_embed(
                "leave_network_success",
                network_key=network_key,
            ),
            ephemeral=True,
        )

    async def _blacklist_callback(self, interaction: discord.Interaction) -> None:
        context = self._bot.bot_context
        if context is None:
            await interaction.response.send_message(render_text("bot_not_ready"), ephemeral=True)
            return

        subscription = await context.store.clients.get_subscription_by_id(
            self._subscription_id,
        )
        if subscription is None:
            await interaction.response.send_message(
                render_text("subscription_not_found"),
                ephemeral=True,
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(render_text("invalid_member"), ephemeral=True)
            return

        client = await context.store.clients.get_by_id(subscription.client_id)
        if client is None:
            await interaction.response.send_message(
                render_text("client_was_not_found"),
                ephemeral=True,
            )
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(render_text("invalid_guild"), ephemeral=True)
            return

        if not await ensure_client_access(
            interaction,
            guild,
            client,
            popup_key="client_role_required_blacklist",
            membership_policy=MembershipPolicy.REQUIRED,
            via="response",
        ):
            return

        if subscription.network_id is None:
            await interaction.response.send_message(
                render_text("network_not_found", network_key=self._network_key),
                ephemeral=True,
            )
            return

        network_subs = await context.store.clients.list_subscriptions_by_network(
            subscription.network_id,
        )
        other_client_ids = [
            sub.client_id for sub in network_subs if sub.client_id != subscription.client_id
        ]
        if not other_client_ids:
            await interaction.response.send_message(
                render_text("no_blacklist_targets"),
                ephemeral=True,
            )
            return

        options: list[discord.SelectOption] = []
        blocked = set(await context.store.clients.list_blacklisted_client_ids(subscription.id))
        for other_id in other_client_ids[:25]:
            other = await context.store.clients.get_by_id(other_id)
            if other is None:
                continue
            options.append(
                discord.SelectOption(
                    label=other.display_name[:100],
                    value=str(other.id),
                    description=other.server_name[:100],
                    default=other.id in blocked,
                )
            )

        view = BlacklistSelectView(
            self._bot,
            subscription.id,
            options,
        )
        await interaction.response.send_message(
            render_text("blacklist_select_prompt"),
            view=view,
            ephemeral=True,
        )


class BlacklistSelectView(discord.ui.View):
    def __init__(
        self,
        bot: NetworkRelayBot,
        subscription_id: int,
        options: list[discord.SelectOption],
    ) -> None:
        super().__init__(timeout=120)
        self._bot = bot
        self._subscription_id = subscription_id
        select: discord.ui.Select[Any] = discord.ui.Select(
            placeholder="Clients to blacklist",
            min_values=0,
            max_values=max(len(options), 1),
            options=options,
        )
        bind_item_callback(select, self._select_callback)
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction) -> None:
        if self._bot.bot_context is None:
            await interaction.response.send_message(render_text("bot_not_ready"), ephemeral=True)
            return

        select = self.children[0]
        assert isinstance(select, discord.ui.Select)
        count = await self._bot.recipe_registry.run(
            "blacklist.replace",
            subscription_id=self._subscription_id,
            selected_client_ids=list(select.values),
        )

        await interaction.response.send_message(
            render_text("blacklist_updated", count=count),
            ephemeral=True,
        )
