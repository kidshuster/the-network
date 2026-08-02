from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from bot.messages import render_embed, render_text
from bot.ui.custom_ids import (
    blacklist_button,
    delete_client_button,
    leave_network_button,
    profile_edit_button,
    subscribe_connected_button,
    subscribe_network_button,
)

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot

logger = logging.getLogger(__name__)


MAX_PROFILE_NETWORK_BUTTONS = 23


class NetworkProfileView(discord.ui.View):
    def __init__(
        self,
        bot: NetworkRelayBot,
        client_id: int,
        network_keys: list[str],
        *,
        subscribed_keys: set[str] | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._client_id = client_id
        subscribed = subscribed_keys or set()
        for key in network_keys[:MAX_PROFILE_NETWORK_BUTTONS]:
            already_subscribed = key in subscribed
            button = discord.ui.Button(
                label=f"Join {key}",
                style=discord.ButtonStyle.primary,
                custom_id=subscribe_network_button(client_id, key),
                disabled=already_subscribed,
            )
            button.callback = self._make_subscribe_callback(key)
            self.add_item(button)
        edit = discord.ui.Button(
            label="Edit Profile",
            style=discord.ButtonStyle.secondary,
            custom_id=profile_edit_button(client_id),
            row=4,
        )
        edit.callback = self._edit_callback
        self.add_item(edit)
        delete = discord.ui.Button(
            label="Delete Client",
            style=discord.ButtonStyle.danger,
            custom_id=delete_client_button(client_id),
            row=4,
        )
        delete.callback = self._delete_callback
        self.add_item(delete)

    def _make_subscribe_callback(self, network_key: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self._handle_subscribe(interaction, network_key)

        return callback

    async def _handle_subscribe(
        self,
        interaction: discord.Interaction,
        network_key: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._bot.bot_context
        guild = interaction.guild
        if context is None or guild is None:
            await interaction.followup.send(render_text("bot_not_ready"), ephemeral=True)
            return

        client = await context.client_repo.get_by_id(self._client_id)
        if client is None:
            await interaction.followup.send(render_text("client_not_found"), ephemeral=True)
            return

        member = interaction.user
        if isinstance(member, discord.Member):
            client_role = guild.get_role(client.client_role_id)
            if client_role is None or client_role not in member.roles:
                if not member.guild_permissions.manage_guild:
                    await interaction.followup.send(
                        render_text("client_role_required_subscribe"),
                        ephemeral=True,
                    )
                    return

        network = await context.network_repo.get_by_key(network_key)
        if network is None:
            await interaction.followup.send(
                render_text("network_not_found", network_key=network_key),
                ephemeral=True,
            )
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send(
                render_text("bot_member_unavailable_brief"),
                ephemeral=True,
            )
            return

        from bot.services.client_subscription import ClientSubscriptionService
        from bot.services.subscription_setup_sticky import sync_subscription_setup

        service = ClientSubscriptionService()
        result = await service.subscribe_client(
            guild,
            bot_member,
            client=client,
            network_id=network.id,
            network_key=network_key,
            client_repo=context.client_repo,
            network_repo=context.network_repo,
            access_role_name=self._bot.settings.network_access_role_name,
        )
        if not result.success or result.subscription is None:
            await interaction.followup.send(
                embed=render_embed(
                    "subscribe_failed",
                    description=result.error or "Unknown error",
                ),
                ephemeral=True,
            )
            return

        await context.client_cache.load_cache()
        await context.routing_service.load_cache()

        if result.created:
            await sync_subscription_setup(
                self._bot,
                context,
                guild,
                client=client,
                subscription=result.subscription,
                network=network,
            )
        else:
            from bot.services.client_profile_sync import refresh_client_profile_message

            await refresh_client_profile_message(self._bot, context, guild, client)

        label = "Subscribed" if result.created else "Already subscribed"
        sub = result.subscription
        publish = guild.get_channel(sub.publish_channel_id)
        subscribe = guild.get_channel(sub.subscribe_channel_id)
        description = f"**{label}** to network `{network.key}`."
        if isinstance(publish, discord.TextChannel):
            description += f"\nPublish: {publish.mention}"
        if subscribe is not None:
            description += f"\nSubscribe: {subscribe.mention}"
        await interaction.followup.send(
            embed=render_embed("subscribe_success", description=description),
            ephemeral=True,
        )

    async def _edit_callback(self, interaction: discord.Interaction) -> None:
        from bot.ui.profile_views import EditClientProfileModal

        context = self._bot.bot_context
        if context is None:
            await interaction.response.send_message(render_text("bot_not_ready"), ephemeral=True)
            return
        client = await context.client_repo.get_by_id(self._client_id)
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

        client = await context.client_repo.get_by_id(self._client_id)
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

        client_role = guild.get_role(client.client_role_id)
        if client_role is None or (
            client_role not in member.roles and not member.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                render_text("client_role_required_delete"),
                ephemeral=True,
            )
            return

        from bot.ui.profile_views import DeleteClientConfirmView

        await interaction.response.send_message(
            render_text(
                "delete_client_confirm_prompt",
                server_name=client.server_name,
            ),
            view=DeleteClientConfirmView(self._bot, self._client_id),
            ephemeral=True,
        )


class SubscriptionModerationView(discord.ui.View):
    def __init__(
        self,
        bot: NetworkRelayBot,
        subscription_id: int,
        network_key: str,
        *,
        show_subscribe_connected: bool = False,
        show_moderation_actions: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        self._bot = bot
        self._subscription_id = subscription_id
        self._network_key = network_key

        if show_subscribe_connected:
            connected = discord.ui.Button(
                label="Subscribe connected",
                style=discord.ButtonStyle.success,
                custom_id=subscribe_connected_button(subscription_id),
            )
            connected.callback = self._subscribe_connected_callback
            self.add_item(connected)

        if show_moderation_actions:
            blacklist = discord.ui.Button(
                label="Blacklist",
                style=discord.ButtonStyle.danger,
                custom_id=blacklist_button(subscription_id),
            )
            blacklist.callback = self._blacklist_callback
            self.add_item(blacklist)
            leave = discord.ui.Button(
                label=f"Leave {network_key}",
                style=discord.ButtonStyle.secondary,
                custom_id=leave_network_button(subscription_id),
            )
            leave.callback = self._leave_callback
            self.add_item(leave)

    async def _subscribe_connected_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._bot.bot_context
        guild = interaction.guild
        if context is None or guild is None:
            await interaction.followup.send(render_text("bot_not_ready"), ephemeral=True)
            return

        subscription = await context.client_repo.get_subscription_by_id(
            self._subscription_id,
        )
        if subscription is None:
            await interaction.followup.send(
                render_text("subscription_not_found"),
                ephemeral=True,
            )
            return

        client = await context.client_repo.get_by_id(subscription.client_id)
        if client is None:
            await interaction.followup.send(
                render_text("client_was_not_found"),
                ephemeral=True,
            )
            return

        network = await context.network_repo.get_by_id(subscription.network_id or 0)
        if network is None:
            await interaction.followup.send(
                render_text("network_not_found", network_key=self._network_key),
                ephemeral=True,
            )
            return

        from bot.services.subscription_setup import resolve_setup_state
        from bot.services.subscription_setup_sticky import sync_subscription_setup

        state = await resolve_setup_state(
            guild,
            subscription,
            network_active=network.enabled,
        )
        if not state.publish_configured:
            await interaction.followup.send(
                embed=render_embed(
                    "command_failure",
                    title="Publish not connected",
                    description=(
                        "Connect your announcement channel to the **publish** channel "
                        "via Channel Follow first."
                    ),
                ),
                ephemeral=True,
            )
            return

        subscription = await context.client_repo.set_subscribe_confirmed(
            subscription.id,
            True,
        )
        await sync_subscription_setup(
            self._bot,
            context,
            guild,
            client=client,
            subscription=subscription,
            network=network,
        )
        await interaction.followup.send(
            embed=render_embed(
                "review_success",
                label="Confirmed",
                colour="green",
                description="Subscribe channel marked as connected. Relays can flow once both links are active.",
            ),
            ephemeral=True,
        )

    async def _leave_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        context = self._bot.bot_context
        if context is None:
            await interaction.followup.send(render_text("bot_not_ready"), ephemeral=True)
            return

        subscription = await context.client_repo.get_subscription_by_id(
            self._subscription_id,
        )
        if subscription is None:
            await interaction.followup.send(
                render_text("subscription_not_found"),
                ephemeral=True,
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.followup.send(render_text("invalid_member"), ephemeral=True)
            return

        client = await context.client_repo.get_by_id(subscription.client_id)
        if client is None:
            await interaction.followup.send(
                render_text("client_was_not_found"),
                ephemeral=True,
            )
            return

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(render_text("invalid_guild"), ephemeral=True)
            return

        client_role = guild.get_role(client.client_role_id)
        if client_role is None or (
            client_role not in member.roles and not member.guild_permissions.manage_guild
        ):
            await interaction.followup.send(
                render_text("client_role_required_leave"),
                ephemeral=True,
            )
            return

        network = (
            await context.network_repo.get_by_id(subscription.network_id)
            if subscription.network_id is not None
            else None
        )
        network_key = self._network_key
        if network is not None:
            network_key = network.key

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send(
                render_text("bot_member_unavailable_brief"),
                ephemeral=True,
            )
            return

        from bot.services.client_profile_sync import refresh_client_profile_message
        from bot.services.client_subscription import ClientSubscriptionService

        service = ClientSubscriptionService()
        result = await service.unsubscribe_client(
            guild,
            bot_member,
            client=client,
            subscription=subscription,
            network_key=network_key,
            client_repo=context.client_repo,
            network_repo=context.network_repo,
        )
        if not result.success:
            await interaction.followup.send(
                embed=render_embed(
                    "leave_network_failed",
                    description=result.error or "Unknown error",
                ),
                ephemeral=True,
            )
            return

        await context.client_cache.load_cache()
        await context.routing_service.load_cache()
        await refresh_client_profile_message(self._bot, context, guild, client)

        await interaction.followup.send(
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

        subscription = await context.client_repo.get_subscription_by_id(
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

        client = await context.client_repo.get_by_id(subscription.client_id)
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

        client_role = guild.get_role(client.client_role_id)
        if client_role is None or (
            client_role not in member.roles and not member.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                render_text("client_role_required_blacklist"),
                ephemeral=True,
            )
            return

        if subscription.network_id is None:
            await interaction.response.send_message(
                render_text("network_not_found", network_key=self._network_key),
                ephemeral=True,
            )
            return

        network_subs = await context.client_repo.list_subscriptions_by_network(
            subscription.network_id,
        )
        other_client_ids = [
            sub.client_id
            for sub in network_subs
            if sub.client_id != subscription.client_id
        ]
        if not other_client_ids:
            await interaction.response.send_message(
                render_text("no_blacklist_targets"),
                ephemeral=True,
            )
            return

        options: list[discord.SelectOption] = []
        blocked = set(
            await context.client_repo.list_blacklisted_client_ids(subscription.id)
        )
        for other_id in other_client_ids[:25]:
            other = await context.client_repo.get_by_id(other_id)
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
        select = discord.ui.Select(
            placeholder="Clients to blacklist",
            min_values=0,
            max_values=max(len(options), 1),
            options=options,
        )
        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction) -> None:
        context = self._bot.bot_context
        if context is None:
            await interaction.response.send_message(render_text("bot_not_ready"), ephemeral=True)
            return

        select = self.children[0]
        assert isinstance(select, discord.ui.Select)
        selected = {int(value) for value in select.values}

        subscription = await context.client_repo.get_subscription_by_id(self._subscription_id)
        if subscription is None:
            await interaction.response.send_message(
                render_text("subscription_not_found"),
                ephemeral=True,
            )
            return

        other_ids = {
            sub.client_id
            for sub in await context.client_repo.list_subscriptions_by_network(
                subscription.network_id,
            )
            if sub.client_id != subscription.client_id
        }

        for other_id in other_ids:
            if other_id in selected:
                await context.client_repo.add_blacklist(subscription.id, other_id)
            else:
                await context.client_repo.remove_blacklist(subscription.id, other_id)

        await interaction.response.send_message(
            render_text("blacklist_updated", count=len(selected)),
            ephemeral=True,
        )
