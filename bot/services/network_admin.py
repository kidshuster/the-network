from __future__ import annotations

from dataclasses import dataclass

from bot.domain.errors import NetworkValidationError
from bot.domain.network import Network


@dataclass(frozen=True)
class CreateNetworkResult:
    success: bool
    network: Network | None = None
    updated_profile_count: int = 0
    reenabled: bool = False
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
) -> CreateNetworkResult:
    from bot.services.client_profile_sync import refresh_all_client_profiles
    from bot.services.client_subscription import resync_subscriptions_for_network

    try:
        existing = await context.network_repo.get_by_key(key)
        if existing is not None:
            if existing.enabled:
                return CreateNetworkResult(
                    success=False,
                    error=f"Network `{existing.key}` already exists and is active.",
                )
            network = await context.network_repo.set_enabled(key, True)
            await context.routing_service.load_cache()
            await context.refresh_network_counts()
            await resync_subscriptions_for_network(
                guild,
                bot,
                context,
                network,
                access_role_name=bot.settings.network_access_role_name,
            )
            updated = await refresh_all_client_profiles(bot, context, guild)
            return CreateNetworkResult(
                success=True,
                network=network,
                updated_profile_count=updated,
                reenabled=True,
            )

        network = await context.network_repo.create(
            guild_id=guild.id,
            key=key,
            display_name=display_name,
        )
        await context.routing_service.load_cache()
        await context.refresh_network_counts()
        await resync_subscriptions_for_network(
            guild,
            bot,
            context,
            network,
            access_role_name=bot.settings.network_access_role_name,
        )
        updated = await refresh_all_client_profiles(bot, context, guild)
        return CreateNetworkResult(
            success=True,
            network=network,
            updated_profile_count=updated,
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
) -> DeleteNetworkResult:
    from bot.services.client_profile_sync import refresh_all_client_profiles

    try:
        network = await context.network_repo.get_by_key(key)
        if network is None:
            raise NetworkValidationError(f"Network `{key.strip().lower()}` was not found.")

        if not network.enabled:
            return DeleteNetworkResult(success=True, network_key=network.key)

        await context.network_repo.set_enabled(key, False)
        await context.routing_service.load_cache()
        await context.refresh_network_counts()
        await refresh_all_client_profiles(bot, context, guild)
        return DeleteNetworkResult(success=True, network_key=network.key)
    except NetworkValidationError as exc:
        return DeleteNetworkResult(success=False, error=str(exc))
    except Exception:
        return DeleteNetworkResult(success=False, error="Network disable failed. Check bot logs.")
