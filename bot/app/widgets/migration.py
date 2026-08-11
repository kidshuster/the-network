from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import discord

from bot.app.widgets.engine import render_view
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
        lines = []
        for item in plan.ambiguous:
            choices = ", ".join(f"#{name}" for name in item.candidate_names)
            lines.append(f"`{item.resource_key}` ← {choices}")
        embed.add_field(name="Ambiguous maps", value="\n".join(lines)[:1024], inline=False)
    if plan.delete_candidates:
        deletes = ", ".join(f"#{item.name}" for item in plan.delete_candidates)
        embed.add_field(
            name="Obsolete channels to remove",
            value=deletes[:1024],
            inline=False,
        )
    if plan.preserve_client:
        preserved = ", ".join(f"#{item.name}" for item in plan.preserve_client[:20])
        embed.add_field(name="Preserved as client", value=preserved[:1024], inline=False)
    return embed


async def present_migration_review(
    interaction: discord.Interaction,
    plan: MigrationPlan,
) -> MigrationReviewDecision | None:
    ambiguous: list[dict[str, Any]] = []
    for item in plan.ambiguous[:4]:
        options = [
            {
                "label": name[:100],
                "value": str(discord_id),
                "description": f"id {discord_id}"[:100],
            }
            for discord_id, name in zip(
                item.candidate_ids,
                item.candidate_names,
                strict=True,
            )
        ][:25]
        if not options:
            continue
        ambiguous.append(
            {
                "resource_key": item.resource_key,
                "options": options,
            }
        )
    view = render_view(
        "migration_review",
        interaction.client,  # type: ignore[arg-type]
        ambiguous=ambiguous,
        has_deletes=bool(plan.delete_candidates),
    )
    if plan.delete_candidates:
        for child in view.children:
            if getattr(child, "custom_id", None) == "hub_migrate:confirm":
                child.style = discord.ButtonStyle.danger  # type: ignore[attr-defined]
    embed = migration_review_embed(plan)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        message = await interaction.original_response()
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        message = await interaction.original_response()
    await view.wait()
    if view.decision is None:
        try:
            await message.edit(
                content="Migration review timed out. Server init aborted.",
                embed=None,
                view=None,
            )
        except discord.HTTPException:
            pass
        return None
    # decision is resolutions dict from finish:confirm
    resolutions = {
        key: int(value)
        for key, value in dict(view.decision).items()
        if not str(key).startswith("_")
    }
    return MigrationReviewDecision(resolutions=resolutions, confirm_deletes=True)
