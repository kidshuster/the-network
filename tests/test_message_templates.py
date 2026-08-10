from __future__ import annotations

from pathlib import Path

import pytest

from bot.messages import (
    MessageTemplateError,
    clear_template_cache,
    modal_spec,
    render_embed,
    render_text,
    validate_all_templates,
)
from bot.services.join_requests_sticky import HOW_TO_JOIN_VERSION
from bot.services.rules_sticky import RULES_STICKY_VERSION

_MESSAGES_DIR = Path(__file__).resolve().parents[1] / "bot" / "messages"


def test_validate_all_templates_passes() -> None:
    clear_template_cache()
    validate_all_templates()


def test_all_yaml_files_load() -> None:
    clear_template_cache()
    for directory in ("embeds", "popups", "modals"):
        folder = _MESSAGES_DIR / directory
        names = [path.stem for path in folder.glob("*.yaml")]
        assert names, f"expected templates in {directory}/"
        for name in names:
            if directory == "embeds" and name == "relay_message":
                continue
            if directory == "modals":
                spec = modal_spec(name)
                assert spec.title
                continue
            if directory == "popups":
                text = render_text(name)
                assert text.strip()
                continue
            embed = render_embed(name, version=1, colour="green")
            assert embed.colour is not None


def test_join_the_network_embed() -> None:
    embed = render_embed("join_the_network", version=HOW_TO_JOIN_VERSION)
    assert embed.title == "Join The Network"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "What happens next"
    assert embed.footer
    assert f"v{HOW_TO_JOIN_VERSION}" in embed.footer.text


def test_publish_setup_instructions_covers_community_and_follow() -> None:
    embed = render_embed("publish_setup_instructions", publish_mention="#publish")
    body = (embed.description or "") + " ".join(field.value or "" for field in embed.fields)
    assert "Enable Community" in body
    assert "announcement channel" in body.lower()
    assert "#publish" in body
    assert "Discord desktop app" in body


def test_subscribe_setup_instructions_suggests_network_channel_name() -> None:
    embed = render_embed(
        "subscribe_setup_instructions",
        subscribe_mention="#subscribe",
        network_channel_name="🌐-Stingers",
    )
    body = " ".join(field.value or "" for field in embed.fields)
    assert "🌐-Stingers" in body
    assert "#subscribe" in body


def test_hub_rules_embed() -> None:
    embed = render_embed("hub_rules", version=RULES_STICKY_VERSION)
    assert "Relay Rules" in (embed.title or "")
    assert len(embed.fields) == 5


def test_network_created_optional_field() -> None:
    without = render_embed(
        "network_created",
        key="a",
        display_name="A",
        updated_count="",
        relinked="",
    )
    assert len(without.fields) == 3

    with_update = render_embed(
        "network_created",
        key="a",
        display_name="A",
        updated_count=2,
        relinked="",
    )
    assert len(with_update.fields) == 4

    relinked = render_embed(
        "network_created",
        key="a",
        display_name="A",
        updated_count="",
        relinked="1",
    )
    assert len(relinked.fields) == 4


def test_join_network_modal_field_descriptions_within_discord_limit() -> None:
    spec = modal_spec("join_network")
    for field in spec.fields:
        if field.description is not None:
            assert len(field.description) <= 100, field.id


def test_unknown_template_raises() -> None:
    clear_template_cache()
    with pytest.raises(MessageTemplateError):
        render_embed("does_not_exist")


def test_placeholder_substitution() -> None:
    text = render_text("network_deleted", key="my-net")
    assert "`my-net`" in text
    assert "deleted" in text.lower()
