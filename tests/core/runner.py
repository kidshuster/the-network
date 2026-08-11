from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any, cast

import discord

from bot.config import Settings
from tests.core.client_guard import snapshot_protected_clients
from tests.core.discord_client import create_smoke_discord_client
from tests.core.mock_backend import SCENARIO_DIR, load_mock_context
from tests.core.probes import PROBES, LiveContext
from tests.core.provision_flow import create_smoke_context
from tests.core.recipes import RecipeRunner, load_recipes

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext


class LiveBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bot_context: BotContext | None = None
        self.user: discord.ClientUser | None = None
        self._guild: discord.Guild | None = None

    def get_guild(self, guild_id: int) -> Any:
        if self._guild is not None and self._guild.id == guild_id:
            return self._guild
        return None

    def add_view(self, _view: object) -> None:
        return None


def build_parser() -> argparse.ArgumentParser:
    recipes = load_recipes()
    parser = argparse.ArgumentParser(description="Run targeted Discord probes or smoke recipes")
    subparsers = parser.add_subparsers(dest="command", required=True)
    recipe = subparsers.add_parser("recipe", help="run a YAML smoke recipe")
    recipe.add_argument("name", choices=sorted(recipes))
    recipe.add_argument("--backend", choices=("mock", "live"), default="live")
    recipe.add_argument("--scenario", default="healthy")
    probe = subparsers.add_parser("probe", help="run one probe directly")
    probe.add_argument("name", choices=sorted(PROBES))
    probe.add_argument("--backend", choices=("mock", "live"), default="live")
    probe.add_argument("--scenario", default="healthy")
    subparsers.add_parser("list", help="list probes and recipes")
    return parser


async def run_live(command: str, name: str) -> None:
    settings = Settings()
    client = create_smoke_discord_client(members=True)
    bot = LiveBot(settings)
    completed = asyncio.Event()
    failures: list[BaseException] = []

    @client.event
    async def on_ready() -> None:
        try:
            guild = client.get_guild(settings.guild_id)
            if guild is None or guild.me is None:
                raise RuntimeError("Configured live-test guild or bot member was not found.")
            bot.user = client.user
            bot._guild = guild
            database, runtime = await create_smoke_context(settings)
            bot.bot_context = runtime
            context = LiveContext(
                guild=guild,
                bot_member=guild.me,
                bot=cast("NetworkRelayBot", bot),
                settings=settings,
                database=database,
                runtime=runtime,
                protected_clients=await snapshot_protected_clients(runtime, guild.id),
            )
            try:
                runner = RecipeRunner(context, load_recipes())
                if command == "recipe":
                    await runner.run(name)
                else:
                    await runner.run_probe(name)
            finally:
                await database.close()
        except BaseException as exc:
            failures.append(exc)
        finally:
            completed.set()
            await client.close()

    task = asyncio.create_task(client.start(settings.discord_token))
    try:
        await asyncio.wait_for(completed.wait(), timeout=1800.0)
    except TimeoutError as exc:
        task.cancel()
        raise RuntimeError("Live test timed out after 30 minutes.") from exc
    await task
    if failures:
        raise failures[0]


async def run_mock(command: str, name: str, scenario: str) -> None:
    context = load_mock_context(scenario)
    runner = RecipeRunner(context, load_recipes(), backend="mock")
    if command == "recipe":
        await runner.run(name)
    else:
        await runner.run_probe(name)


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "list":
        print("Probes:")
        for name in sorted(PROBES):
            print(f"  {name}")
        print("Recipes:")
        for recipe in load_recipes().values():
            print(f"  {recipe.name}: {recipe.description}")
        print("Mock scenarios:")
        for path in sorted(SCENARIO_DIR.glob("*.yaml")):
            print(f"  {path.stem}")
        return
    try:
        if args.backend == "mock":
            asyncio.run(run_mock(args.command, args.name, args.scenario))
        else:
            asyncio.run(run_live(args.command, args.name))
    except BaseException as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
