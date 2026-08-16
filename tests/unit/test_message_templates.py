from __future__ import annotations

from pathlib import Path

import pytest

from bot.core.templates import (
    MessageTemplateError,
    clear_template_cache,
    load_template,
    modal_spec,
    render_embed,
    render_text,
    validate_all_templates,
)
from bot.core.templates.schema import EmbedTemplateSpec, TextTemplateSpec
from bot.features.channels.stickies.join import HOW_TO_JOIN_VERSION
from bot.features.channels.stickies.rules import RULES_STICKY_VERSION

_BOT_DIR = Path(__file__).resolve().parents[2] / "bot"
_WIDGET_TEMPLATES_DIR = _BOT_DIR / "features" / "widgets" / "templates"
_CHANNEL_TEMPLATES_DIR = _BOT_DIR / "features" / "channels" / "templates"


def test_validate_all_templates_passes() -> None:
    clear_template_cache()
    validate_all_templates()


def test_all_yaml_files_load() -> None:
    clear_template_cache()
    for directory in ("embeds", "popups", "modals"):
        folder = _WIDGET_TEMPLATES_DIR / directory
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

    channel_names = [path.stem for path in _CHANNEL_TEMPLATES_DIR.glob("*.yaml")]
    assert channel_names
    for name in channel_names:
        spec = load_template(name)
        if isinstance(spec, TextTemplateSpec):
            text = render_text(
                name,
                network_key="x",
                network_display_name="X",
                client_server_name="y",
            )
            assert text.strip()
            continue
        assert isinstance(spec, EmbedTemplateSpec)
        embed = render_embed(name, version=1, colour="green")
        assert embed.colour is not None


def test_join_the_network_embed() -> None:
    embed = render_embed("join_the_network", version=HOW_TO_JOIN_VERSION)
    assert embed.title == "Join The Network"
    assert len(embed.fields) == 2
    assert embed.fields[0].name == "What happens next"
    assert embed.fields[1].name == "Profile toggles"
    body = " ".join(field.value or "" for field in embed.fields)
    assert "Timecodes" in body
    assert "Read-only" in body
    assert embed.footer
    assert f"v{HOW_TO_JOIN_VERSION}" in embed.footer.text
    assert HOW_TO_JOIN_VERSION == 11


def test_publish_setup_instructions_covers_community_follow_and_timecodes() -> None:
    embed = render_embed("publish_setup_instructions", publish_mention="#publish")
    body = (embed.description or "") + " ".join(field.value or "" for field in embed.fields)
    assert "Enable Community" in body
    assert "announcement channel" in body.lower()
    assert "#publish" in body
    assert "Discord desktop app" in body
    assert "write" in body.casefold()
    assert "Timecodes" in body
    assert "5:30 pst" in body


def test_subscribe_setup_instructions_write_mode_mentions_publish_and_timecodes() -> None:
    embed = render_embed(
        "subscribe_setup_instructions",
        subscribe_mention="#subscribe",
        network_channel_name="🌐-Stingers",
    )
    body = (embed.description or "") + " ".join(field.value or "" for field in embed.fields)
    assert "🌐-Stingers" in body
    assert "#subscribe" in body
    assert "publish" in body.casefold()
    assert "Timecodes" in body
    assert "write" in body.casefold()


def test_subscribe_setup_instructions_readonly_omits_publish_step() -> None:
    embed = render_embed(
        "subscribe_setup_instructions_readonly",
        subscribe_mention="#subscribe",
        network_channel_name="🌐-Stingers",
    )
    body = (embed.description or "") + " ".join(field.value or "" for field in embed.fields)
    assert "read-only" in body.casefold()
    assert "no publish" in body.casefold()
    assert "#subscribe" in body
    assert "Timecodes" in body
    assert "complete the **publish**" not in body.casefold()


def test_subscription_moderation_templates_split_by_mode() -> None:
    write = render_embed(
        "subscription_moderation",
        network_display_name="Stingers",
        network_key="stingers",
        client_slug="acme",
    )
    readonly = render_embed(
        "subscription_moderation_readonly",
        network_display_name="Stingers",
        network_key="stingers",
        client_slug="acme",
    )
    assert "Write mode" in (write.description or "")
    assert "publish" in (write.description or "").casefold()
    assert "Read-only mode" in (readonly.description or "")
    assert "no publish channel" in (readonly.description or "").casefold()
    assert "Timecodes" in (write.description or "")
    assert "Timecodes" in (readonly.description or "")


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
        updated_count="Refreshed buttons on **2** client profile(s).",
        relinked="",
    )
    assert len(with_update.fields) == 4

    relinked = render_embed(
        "network_created",
        key="a",
        display_name="A",
        updated_count="",
        relinked="Existing client subscriptions were relinked and forwarding resumed.",
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
