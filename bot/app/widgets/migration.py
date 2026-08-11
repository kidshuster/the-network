from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord

from bot.app.widgets import custom_id as codec
from bot.app.widgets.dispatch import RenderedView
from bot.app.widgets.models import ActionBinding, ButtonSpec, SelectOptionSpec, SelectSpec
from bot.app.widgets.renderer import view as render_view
from bot.core.channels.migration import MigrationPlan


@dataclass
class MigrationReviewDecision:
    resolutions: dict[str, int] = field(default_factory=dict)
    confirm_deletes: bool = False


def migration_review_embed(plan: MigrationPlan) -> discord.Embed:
    embed = discord.Embed(
        title="Hub migration review",
        description=(
            "Confirm how to map ambiguous channels and whether to remove obsolete "
            "hub leftovers. Client resources are preserved automatically."
        ),
        color=discord.Color.orange(),
    )
    if plan.ambiguous:
        lines = [
            f"`{item.resource_key}` ← {', '.join(f'#{name}' for name in item.candidate_names)}"
            for item in plan.ambiguous
        ]
        embed.add_field(name="Ambiguous maps", value="\n".join(lines)[:1024], inline=False)
    if plan.delete_candidates:
        deletes = ", ".join(f"#{item.name}" for item in plan.delete_candidates)
        embed.add_field(
            name="Obsolete channels to remove",
            value=deletes[:1024],
            inline=False,
        )
    return embed


async def present_migration_review(
    interaction: discord.Interaction,
    plan: MigrationPlan,
) -> MigrationReviewDecision | None:
    selects: list[SelectSpec] = []
    for item in plan.ambiguous[:4]:
        options = tuple(
            SelectOptionSpec(
                label=name[:100],
                value=str(discord_id),
                description=f"id {discord_id}"[:100],
            )
            for discord_id, name in zip(
                item.candidate_ids,
                item.candidate_names,
                strict=True,
            )
        )[:25]
        if not options:
            continue
        selects.append(
            SelectSpec(
                id=item.resource_key,
                placeholder=item.resource_key,
                options=options,
                action=ActionBinding(
                    action="ui.migrate.store",
                    arguments={"resource_key": item.resource_key},
                ),
            )
        )
    actions = (
        ButtonSpec(
            id="confirm",
            label="Confirm",
            style="danger" if plan.delete_candidates else "primary",
            action=ActionBinding(action="ui.migrate.confirm"),
        ),
        ButtonSpec(
            id="cancel",
            label="Cancel",
            style="secondary",
            action=ActionBinding(action="ui.migrate.cancel"),
        ),
    )
    built = render_view(
        interaction.client,
        "migration_review",
        slots={"ambiguous": tuple(selects), "actions": actions},
    )
    assert isinstance(built, RenderedView)
    built.decision = {}
    resolutions: dict[str, int] = {}

    for child in built.children:
        if not isinstance(child, discord.ui.Select):
            continue

        async def _on_select(
            interaction: discord.Interaction,
            *,
            select: discord.ui.Select[Any] = child,
        ) -> None:
            binding = codec.decode(select.custom_id or "")
            key = str(binding.arguments.get("resource_key") or "")
            raw: dict[str, Any] = (
                dict(interaction.data) if isinstance(interaction.data, dict) else {}
            )
            selected = raw.get("values")
            values = [str(v) for v in selected] if isinstance(selected, list) else []
            if key and values:
                resolutions[key] = int(values[0])
            if not interaction.response.is_done():
                await interaction.response.defer()

        child.callback = _on_select  # type: ignore[method-assign]

    embed = migration_review_embed(plan)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=built, ephemeral=True)
        message = await interaction.original_response()
    else:
        await interaction.response.send_message(embed=embed, view=built, ephemeral=True)
        message = await interaction.original_response()
    await built.wait()
    if built.decision is None:
        try:
            await message.edit(
                content="Migration review cancelled or timed out.",
                embed=None,
                view=None,
            )
        except discord.HTTPException:
            pass
        return None
    return MigrationReviewDecision(resolutions=resolutions, confirm_deletes=True)
