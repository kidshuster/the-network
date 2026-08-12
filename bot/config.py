from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.constants import (
    DEFAULT_NETWORK_ACCESS_ROLE_NAME,
    DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
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
        validation_alias=AliasChoices("NETWORK_ACCESS_ROLE_NAME", "NETWORK_BOT_ROLE_NAME"),
    )
    network_operator_role_name: str = Field(
        default=DEFAULT_NETWORK_OPERATOR_ROLE_NAME,
        alias="NETWORK_OPERATOR_ROLE_NAME",
    )
    enable_test_commands: bool = Field(default=False, alias="ENABLE_TEST_COMMANDS")
    test_guild_id: int | None = Field(default=None, alias="TEST_GUILD_ID")
    test_command_log_dir: Path = Field(
        default=Path("./data/smoke-runs"),
        alias="TEST_COMMAND_LOG_DIR",
    )
    test_max_rate_limit_wait_seconds: float = Field(
        default=300.0,
        alias="TEST_MAX_RATE_LIMIT_WAIT_SECONDS",
    )

    @property
    def network_bot_role_name(self) -> str:
        """Backwards-compatible alias for the hub access role."""
        return self.network_access_role_name

    @field_validator(
        "discord_application_id",
        "profile_forum_channel_id",
        "relay_log_channel_id",
        "test_guild_id",
        mode="before",
    )
    @classmethod
    def empty_optional_int(cls, value: object) -> object | None:
        if value is None or value == "":
            return None
        return value

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

    @field_validator("enable_test_commands", mode="before")
    @classmethod
    def coerce_enable_test_commands(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None or value == "":
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @model_validator(mode="after")
    def validate_test_command_mode(self) -> Settings:
        if not self.enable_test_commands:
            return self
        if self.test_guild_id is None:
            raise ValueError("TEST_GUILD_ID is required when ENABLE_TEST_COMMANDS=true")
        if self.guild_id != self.test_guild_id:
            raise ValueError(
                "GUILD_ID must equal TEST_GUILD_ID when ENABLE_TEST_COMMANDS=true"
            )
        return self
