from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

import discord

from bot.domain.errors import NetworkValidationError
from bot.services.guild_permissions import build_network_access_overwrite
from bot.smoke.resource_guard import (
    PROBE_PREFIX,
    GuildTestResourceGuard,
    cleanup_stale_probe_resources,  # noqa: F401
    guild_test_resource_guard,
)
from bot.testing.png_fixtures import probe_png_bytes

logger = logging.getLogger(__name__)

_PROBE_REASON = "The Network permission probe (auto-deleted)"

PROBE_PNG = probe_png_bytes()
_PROBE_PNG = PROBE_PNG


async def verify_operator_permissions_live(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    *,
    operator_role_name: str,
) -> list[str]:
    """Create and delete probe resources to confirm Discord API permissions work.

    Raises NetworkValidationError when a probe step fails. Returns a list of
    successful probe step labels on success.
    """
    _ = (bot_member, operator_role_name)
    suffix = secrets.token_hex(3)

    async with guild_test_resource_guard(guild) as guard:
        step = "starting"
        try:
            step = "create category"
            category = await _run_probe_step(
                step,
                guild.create_category(
                    name=f"{PROBE_PREFIX}-cat-{suffix}",
                    reason=_PROBE_REASON,
                ),
                guard,
            )
            guard.track_category(category)

            step = "create text channel"
            channel = await _run_probe_step(
                step,
                guild.create_text_channel(
                    name=f"{PROBE_PREFIX}-ch-{suffix}",
                    category=category,
                    reason=_PROBE_REASON,
                ),
                guard,
            )
            guard.track_channel(channel)

            step = f"set channel overwrite for {access_role.name}"
            await _run_probe_step(
                step,
                channel.set_permissions(
                    access_role,
                    overwrite=build_network_access_overwrite(),
                    reason=_PROBE_REASON,
                ),
                guard,
            )

            step = "create role"
            role = await _run_probe_step(
                step,
                guild.create_role(
                    name=f"{PROBE_PREFIX}-role-{suffix}"[:100],
                    reason=_PROBE_REASON,
                ),
                guard,
            )
            guard.track_role(role)

            step = "create webhook"
            webhook = await _run_probe_step(
                step,
                channel.create_webhook(
                    name=f"{PROBE_PREFIX}-{suffix}"[:32],
                    reason=_PROBE_REASON,
                ),
                guard,
            )
            guard.track_webhook(webhook)

            step = "send message"
            await _run_probe_step(
                step,
                channel.send("The Network permission probe."),
                guard,
            )

            step = "create emoji"
            emoji_name = f"tnprobe{suffix}"[:32]
            emoji = await _run_probe_step(
                step,
                guild.create_custom_emoji(
                    name=emoji_name,
                    image=_PROBE_PNG,
                    reason=_PROBE_REASON,
                ),
                guard,
            )
            guard.track_emoji(emoji)
        except NetworkValidationError:
            raise
        except discord.HTTPException as exc:
            raise _probe_failure_for_step(step, guard.completed_steps, exc) from exc
        except Exception as exc:
            raise _probe_failure_for_step(step, guard.completed_steps, exc) from exc

        return list(guard.completed_steps)


async def verify_provision_permissions_live(
    guild: discord.Guild,
    bot_member: discord.Member,
    access_role: discord.Role,
    *,
    access_role_name: str,
    operator_role_name: str,
) -> list[str]:
    """Probe client onboarding provisioning (Accept button / join-approval path).

    Creates a client category, client role, profile channel, and publish channel
    with production overwrites, assigns the client role, verifies webhook creation
    on the publish channel, then deletes everything via RAII cleanup.
    """
    from bot.services.guild_layout import resolve_human_moderator_role
    from bot.services.guild_permissions import (
        build_client_category_overwrites,
        build_client_profile_channel_overwrites,
        build_client_publish_channel_overwrites,
        build_client_role_name,
        create_text_channel_with_overwrites,
        filter_configurable_overwrites,
    )
    from bot.services.network_provision import (
        resolve_operator_role_by_name,
        validate_provision_permissions,
    )

    _ = access_role_name
    suffix = secrets.token_hex(3)
    human_moderator_role = resolve_human_moderator_role(guild)
    operator_role = resolve_operator_role_by_name(guild, role_name=operator_role_name)
    validate_provision_permissions(
        bot_member,
        access_role,
        operator_role=operator_role,
        operator_role_name=operator_role_name,
    )

    async with guild_test_resource_guard(guild, bot_member=bot_member) as guard:
        step = "starting"
        try:
            step = "create client role"
            client_role = await _run_probe_step(
                step,
                guild.create_role(
                    name=f"{PROBE_PREFIX}-client-{suffix}"[:100],
                    mentionable=False,
                    hoist=False,
                    reason=_PROBE_REASON,
                ),
                guard,
                failure_for_step=_provision_probe_failure,
            )
            guard.track_role(client_role)

            step = "create client category with hub overwrites"
            category_overwrites = filter_configurable_overwrites(
                bot_member,
                build_client_category_overwrites(
                    guild,
                    bot_member,
                    client_role,
                    access_role,
                    human_moderator_role,
                ),
            )
            category = await _run_probe_step(
                step,
                guild.create_category(
                    name=f"{PROBE_PREFIX}-client-cat-{suffix}",
                    overwrites=category_overwrites,
                    reason=_PROBE_REASON,
                ),
                guard,
                failure_for_step=_provision_probe_failure,
            )
            guard.track_category(category)

            profile_overwrites = filter_configurable_overwrites(
                bot_member,
                build_client_profile_channel_overwrites(
                    guild,
                    bot_member,
                    client_role,
                    access_role,
                    human_moderator_role,
                ),
                for_channel=True,
            )
            step = "create network-profile channel"
            profile_channel = await _run_probe_step(
                step,
                create_text_channel_with_overwrites(
                    guild,
                    bot_member,
                    name=f"{PROBE_PREFIX}-profile-{suffix}",
                    category=category,
                    overwrites=profile_overwrites,
                    reason=_PROBE_REASON,
                ),
                guard,
                failure_for_step=_provision_probe_failure,
            )
            guard.track_channel(profile_channel)

            publish_overwrites = filter_configurable_overwrites(
                bot_member,
                build_client_publish_channel_overwrites(
                    guild,
                    bot_member,
                    client_role,
                    access_role,
                    human_moderator_role,
                ),
                for_channel=True,
            )
            step = "create client publish channel with webhook overwrites"
            publish_channel = await _run_probe_step(
                step,
                create_text_channel_with_overwrites(
                    guild,
                    bot_member,
                    name=f"{PROBE_PREFIX}-publish-{suffix}",
                    category=category,
                    overwrites=publish_overwrites,
                    reason=_PROBE_REASON,
                ),
                guard,
                failure_for_step=_provision_probe_failure,
            )
            guard.track_channel(publish_channel)

            step = "send profile starter message"
            await _run_probe_step(
                step,
                profile_channel.send(
                    embed=discord.Embed(
                        title="Provision probe",
                        description="The Network client onboarding probe.",
                    ),
                ),
                guard,
                failure_for_step=_provision_probe_failure,
            )

            step = "assign client role to member"
            await _run_probe_step(
                step,
                bot_member.add_roles(client_role, reason=_PROBE_REASON),
                guard,
                failure_for_step=_provision_probe_failure,
            )
            guard.track_role_assignment(client_role)

            step = (
                f"create webhook on publish channel as "
                f"{build_client_role_name('probe').split(':')[0]}"
            )
            webhook = await _run_probe_step(
                step,
                publish_channel.create_webhook(
                    name=f"{PROBE_PREFIX}-{suffix}"[:32],
                    reason=_PROBE_REASON,
                ),
                guard,
                failure_for_step=_provision_probe_failure,
            )
            guard.track_webhook(webhook)
        except NetworkValidationError:
            raise
        except discord.HTTPException as exc:
            raise _provision_probe_failure(step, guard.completed_steps, exc) from exc
        except Exception as exc:
            raise _provision_probe_failure(step, guard.completed_steps, exc) from exc

        return list(guard.completed_steps)


async def _run_probe_step[T](
    label: str,
    coro,
    guard: GuildTestResourceGuard,
    *,
    failure_for_step: Callable[[str, list[str], BaseException], NetworkValidationError]
    | None = None,
) -> T:
    report = failure_for_step or _probe_failure_for_step
    try:
        result = await coro
    except discord.HTTPException as exc:
        raise report(label, guard.completed_steps, exc) from exc
    except Exception as exc:
        raise report(label, guard.completed_steps, exc) from exc
    guard.record_step(label)
    return result


def _probe_failure_for_step(
    step: str,
    completed: list[str],
    exc: BaseException,
) -> NetworkValidationError:
    if isinstance(exc, discord.HTTPException):
        code = getattr(exc, "code", None)
        detail = f" ({code})" if code is not None else ""
        failure = f"{exc.text}{detail}"
    else:
        failure = f"{type(exc).__name__}: {exc}"

    progress = (
        f"Completed before failure: {', '.join(completed)}."
        if completed
        else "No probe steps completed before failure."
    )
    return NetworkValidationError(
        "Permission probe failed before guild init could start:\n"
        f"• Failed at **{step}**: {failure}\n"
        f"• {progress}\n\n"
        "Fix **The Network+** permissions and role order, then run `/server init` again."
    )


def _provision_probe_failure(
    step: str,
    completed: list[str],
    exc: BaseException,
) -> NetworkValidationError:
    if isinstance(exc, discord.HTTPException):
        code = getattr(exc, "code", None)
        detail = f" ({code})" if code is not None else ""
        failure = f"{exc.text}{detail}"
    else:
        failure = f"{type(exc).__name__}: {exc}"

    progress = (
        f"Completed before failure: {', '.join(completed)}."
        if completed
        else "No probe steps completed before failure."
    )
    return NetworkValidationError(
        "Join-approval provisioning probe failed — Accept and client onboarding would fail:\n"
        f"• Failed at **{step}**: {failure}\n"
        f"• {progress}\n\n"
        "Fix **The Network+** permissions and role order before running `/server init` "
        "or approving join requests."
    )
