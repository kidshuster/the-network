from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_MODERATOR_ROLE_NAME,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: str = Field(min_length=1, alias="DISCORD_TOKEN")
    guild_id: int = Field(alias="GUILD_ID")
    discord_application_id: int | None = Field(default=None, alias="DISCORD_APPLICATION_ID")
    discord_public_key: str | None = Field(default=None, alias="DISCORD_PUBLIC_KEY")
    database_path: Path = Field(default=Path("./data/relay.db"), alias="DATABASE_PATH")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    profile_forum_channel_id: int | None = Field(default=None, alias="PROFILE_FORUM_CHANNEL_ID")
    relay_log_channel_id: int | None = Field(default=None, alias="RELAY_LOG_CHANNEL_ID")
    manual_relay_enabled: bool = Field(default=False, alias="MANUAL_RELAY_ENABLED")
    network_access_role_name: str = Field(
        default=DEFAULT_NETWORK_ACCESS_ROLE_NAME,
        alias="NETWORK_ACCESS_ROLE_NAME",
    )
    network_moderator_role_name: str = Field(
        default=DEFAULT_NETWORK_MODERATOR_ROLE_NAME,
        alias="NETWORK_MODERATOR_ROLE_NAME",
    )
    topgg_token: str | None = Field(default=None, alias="TOPGG_TOKEN")

    @field_validator(
        "discord_application_id",
        "profile_forum_channel_id",
        "relay_log_channel_id",
        mode="before",
    )
    @classmethod
    def empty_optional_int(cls, value: object) -> object | None:
        if value is None or value == "":
            return None
        return value

    @field_validator("topgg_token", mode="before")
    @classmethod
    def empty_optional_str(cls, value: object) -> object | None:
        if value is None or value == "":
            return None
        return str(value).strip()

    @field_validator("guild_id", mode="before")
    @classmethod
    def validate_guild_id(cls, value: object) -> int:
        if value is None or value == "":
            raise ValueError("GUILD_ID is required")
        if isinstance(value, int):
            return value
        return int(str(value))

    @field_validator("discord_token", mode="before")
    @classmethod
    def validate_discord_token(cls, value: object) -> str:
        if value is None or not str(value).strip():
            raise ValueError("DISCORD_TOKEN is required")
        return str(value).strip()
