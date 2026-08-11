from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable

import discord

from bot.core.models.errors import NetworkValidationError
from bot.testing.png_fixtures import probe_png_bytes
from tests.core.resource_guard import (
    PROBE_PREFIX,
    GuildTestResourceGuard,
    cleanup_stale_probe_resources,  # noqa: F401
    guild_test_resource_guard,
)

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
            category: discord.CategoryChannel = await _run_probe_step(
                step,
                guild.create_category(
                    name=f"{PROBE_PREFIX}-cat-{suffix}",
                    reason=_PROBE_REASON,
                ),
                guard,
            )
            guard.track_category(category)

            step = "create text channel"
            channel: discord.TextChannel = await _run_probe_step(
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
                    overwrite=discord.PermissionOverwrite(
                        view_channel=True,
                        read_message_history=True,
                        manage_webhooks=True,
                        send_messages=True,
                        embed_links=True,
                        attach_files=True,
                    ),
                    reason=_PROBE_REASON,
                ),
                guard,
            )

            step = "create role"
            from tests.core.pacing import pause_before_role_create

            await pause_before_role_create()
            role: discord.Role = await _run_probe_step(
                step,
                guild.create_role(
                    name=f"{PROBE_PREFIX}-role-{suffix}"[:100],
                    reason=_PROBE_REASON,
                ),
                guard,
            )
            guard.track_role(role)

            step = "create webhook"
            webhook: discord.Webhook = await _run_probe_step(
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
            emoji: discord.Emoji = await _run_probe_step(
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
    from dataclasses import replace

    from bot.channels.layout import ApplyMode, LayoutContext, apply_layout, compile_client
    from bot.channels.resolve import resolve_human_moderator_role
    from bot.core.clients.names import build_client_role_name
    from bot.core.networks.roles import (
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
            from tests.core.pacing import pause_before_role_create

            await pause_before_role_create()
            client_role: discord.Role = await _run_probe_step(
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

            layout_ctx = LayoutContext(
                guild=guild,
                bot_member=bot_member,
                access_role=access_role,
                moderator_role=human_moderator_role,
                operator_role=operator_role,
                client_role=client_role,
                server_name=f"probe-{suffix}",
                slug=f"probe-{suffix}",
                network_key="probe",
                reason=_PROBE_REASON,
            )
            cat_name = f"{PROBE_PREFIX}-client-cat-{suffix}"
            profile_name = f"{PROBE_PREFIX}-profile-{suffix}"
            publish_name = f"{PROBE_PREFIX}-publish-{suffix}"
            resources = []
            for resource in compile_client(
                layout_ctx,
                include_subscribed=True,
                channel_ids={"profile", "publish"},
            ):
                if resource.id == "client":
                    resources.append(replace(resource, name=cat_name))
                elif resource.id == "profile":
                    resources.append(
                        replace(
                            resource,
                            name=profile_name,
                            topic=("The Network client onboarding probe profile channel."),
                        )
                    )
                elif resource.id == "publish":
                    resources.append(
                        replace(
                            resource,
                            name=publish_name,
                            topic=("The Network client onboarding probe publish channel."),
                        )
                    )

            step = "create client category with hub overwrites"
            batch = await _run_probe_step(
                step,
                apply_layout(layout_ctx, resources, mode=ApplyMode.ENSURE),
                guard,
                failure_for_step=_provision_probe_failure,
            )
            category = batch.resource("client")
            if not isinstance(category, discord.CategoryChannel):
                raise _provision_probe_failure(
                    step,
                    guard.completed_steps,
                    RuntimeError("; ".join(batch.failures) or "category create failed"),
                )
            guard.track_category(category)

            step = "create network-profile channel"
            profile_channel = batch.resource("profile")
            if not isinstance(profile_channel, discord.TextChannel):
                raise _provision_probe_failure(
                    step,
                    guard.completed_steps,
                    RuntimeError("; ".join(batch.failures) or "profile create failed"),
                )
            guard.track_channel(profile_channel)
            guard.completed_steps.append(step)

            step = "create client publish channel with webhook overwrites"
            publish_channel = batch.resource("publish")
            if not isinstance(publish_channel, discord.TextChannel):
                raise _provision_probe_failure(
                    step,
                    guard.completed_steps,
                    RuntimeError("; ".join(batch.failures) or "publish create failed"),
                )
            guard.track_channel(publish_channel)
            guard.completed_steps.append(step)

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
            webhook: discord.Webhook = await _run_probe_step(
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
    coro: Awaitable[T],
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


def _probe_failure_detail(exc: BaseException) -> tuple[str, str]:
    """Return (failure line, guidance paragraph)."""
    from bot.core.hub.changelog import installed_version

    version = installed_version()
    if isinstance(exc, discord.RateLimited):
        retry = getattr(exc, "retry_after", None)
        wait_hint = f" Retry in **{retry:.0f}s**." if retry is not None else ""
        failure = f"Discord rate limit.{wait_hint}"
        guidance = (
            "Too many smoke/probe runs hit the guild **role-creation** bucket. "
            "Wait for the retry window, then rerun — or run "
            "`tests/live/smoke_cleanup_artifacts.sh` and avoid back-to-back full suites."
        )
        return failure, guidance
    if isinstance(exc, discord.HTTPException):
        code = getattr(exc, "code", None)
        detail = f" ({code})" if code is not None else ""
        failure = f"{exc.text}{detail}"
        guidance = (
            "Fix **The Network+** permissions and role order before running `/server init` "
            "or approving join requests."
        )
        return failure, guidance

    failure = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, TypeError) and "sync_permissions" in str(exc):
        guidance = (
            f"This is **not** a Discord permissions issue — the running bot (**v{version}**) "
            "is outdated and still contains a known bug fixed in **v1.2.9**.\n\n"
            "On the host:\n"
            "```\n"
            "cd ~/the-network-install\n"
            "git pull\n"
            "cat VERSION    # must show 1.2.9 or newer\n"
            "./scripts/update.sh\n"
            "```\n"
            'Then confirm logs show `"bot_version": "1.2.10"` (or newer) before running '
            "`/server init` again."
        )
        return failure, guidance

    guidance = (
        f"Running bot version: **{version}**. If this persists after `./scripts/update.sh`, "
        "check `./scripts/logs.sh` for the `bot_version` field on startup."
    )
    return failure, guidance


def _probe_failure_for_step(
    step: str,
    completed: list[str],
    exc: BaseException,
) -> NetworkValidationError:
    failure, guidance = _probe_failure_detail(exc)
    progress = (
        f"Completed before failure: {', '.join(completed)}."
        if completed
        else "No probe steps completed before failure."
    )
    return NetworkValidationError(
        "Permission probe failed before guild init could start:\n"
        f"• Failed at **{step}**: {failure}\n"
        f"• {progress}\n\n"
        f"{guidance}"
    )


def _provision_probe_failure(
    step: str,
    completed: list[str],
    exc: BaseException,
) -> NetworkValidationError:
    failure, guidance = _probe_failure_detail(exc)
    progress = (
        f"Completed before failure: {', '.join(completed)}."
        if completed
        else "No probe steps completed before failure."
    )
    return NetworkValidationError(
        "Join-approval provisioning probe failed — Accept and client onboarding would fail:\n"
        f"• Failed at **{step}**: {failure}\n"
        f"• {progress}\n\n"
        f"{guidance}"
    )
