from __future__ import annotations

import gzip
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

_SECRET_PATTERNS = (
    re.compile(r"(?i)(discord_token|bot_token|authorization|webhook)\s*[:=]\s*\S+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)Bot\s+[A-Za-z0-9._\-]+"),
)


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


@dataclass
class SmokeRunLogger:
    path: Path
    _handle: TextIO = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def write(self, message: str) -> None:
        line = redact_secrets(message.rstrip("\n"))
        self._handle.write(line + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def as_logging_handler(self) -> logging.Handler:
        logger = self

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                logger.write(self.format(record))

        handler = _Handler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        return handler


def make_run_log_path(log_dir: Path, recipe_name: str, run_id: str) -> Path:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_recipe = re.sub(r"[^a-zA-Z0-9._-]+", "-", recipe_name).strip("-") or "recipe"
    safe_run = re.sub(r"[^a-zA-Z0-9._-]+", "-", run_id).strip("-") or secrets.token_hex(4)
    return log_dir / f"{stamp}-{safe_recipe}-{safe_run}.log"


async def attach_log_file(
    interaction_followup_send: Any,
    log_path: Path,
    *,
    max_bytes: int = 8 * 1024 * 1024,
) -> str:
    """Upload log if possible. Returns status note; never raises for size/upload issues."""
    try:
        size = log_path.stat().st_size
        upload = log_path
        if size > max_bytes:
            gz_path = log_path.with_suffix(log_path.suffix + ".gz")
            with log_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                dst.writelines(src)
            upload = gz_path
            size = gz_path.stat().st_size
        if size > max_bytes:
            return f"Log too large to upload; saved at `{log_path}`"
        import discord

        await interaction_followup_send(
            file=discord.File(upload),
            ephemeral=True,
        )
        return f"Log attached (`{upload.name}`)."
    except Exception:
        return f"Log upload failed; preserved at `{log_path}`"
