from __future__ import annotations

from dataclasses import dataclass

from bot.domain.errors import NetworkValidationError
from bot.domain.network import Network
from bot.services.view_registry import ViewRegistry


@dataclass(frozen=True)
class CreateNetworkResult:
    success: bool
    network: Network | None = None
    updated_profile_count: int = 0
    relinked_subscription_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class DeleteNetworkResult:
    success: bool
    network_key: str | None = None
    error: str | None = None


async def create_network(
    context,
    bot,
    guild,
    *,
    key: str,
    display_name: str,
    view_registry: ViewRegistry,
) -> CreateNetworkResult:
    from bot.services.client_profile_sync import refresh_all_client_profiles
    from bot.services.client_subscription import resync_subscriptions_for_network

    try:
        existing = await context.network_repo.get_by_key(key)
        if existing is not None:
            return CreateNetworkResult(
                success=False,
                error=f"Network `{existing.key}` already exists.",
            )

        network = await context.network_repo.create(
            guild_id=guild.id,
            key=key,
            display_name=display_name,
        )
        await context.routing_service.load_cache()
        await context.refresh_network_counts()
        relinked = await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name=bot.settings.network_access_role_name,
            view_registry=view_registry,
        )
        from bot.services.hub_announcements import ensure_hub_announcements_subscription

        await ensure_hub_announcements_subscription(guild, bot, context, network)
        updated = await refresh_all_client_profiles(
            bot,
            context,
            guild,
            view_registry=view_registry,
        )
        return CreateNetworkResult(
            success=True,
            network=network,
            updated_profile_count=updated,
            relinked_subscription_count=relinked,
        )
    except NetworkValidationError as exc:
        return CreateNetworkResult(success=False, error=str(exc))
    except Exception as exc:
        return CreateNetworkResult(
            success=False,
            error=f"Unexpected error: {type(exc).__name__}: {exc}",
        )


async def delete_network(
    context,
    bot,
    guild,
    *,
    key: str,
    view_registry: ViewRegistry,
) -> DeleteNetworkResult:
    from bot.services.client_profile_sync import refresh_all_client_profiles

    try:
        network = await context.network_repo.get_by_key(key)
        if network is None:
            raise NetworkValidationError(f"Network `{key.strip().lower()}` was not found.")

        await context.client_repo.detach_subscriptions_from_network(network.id, network.key)
        await context.relay_record_repo.delete_by_network_id(network.id)
        await context.server_request_repo.delete_by_network_id(network.id)
        await context.network_repo.delete(key)
        await context.routing_service.load_cache()
        await context.client_cache.load_cache()
        await context.refresh_network_counts()
        await refresh_all_client_profiles(
            bot,
            context,
            guild,
            view_registry=view_registry,
        )
        return DeleteNetworkResult(success=True, network_key=network.key)
    except NetworkValidationError as exc:
        return DeleteNetworkResult(success=False, error=str(exc))
    except Exception:
        return DeleteNetworkResult(success=False, error="Network delete failed. Check bot logs.")
