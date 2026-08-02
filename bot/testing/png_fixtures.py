from __future__ import annotations

import io

from PIL import Image

_PROBE_PNG: bytes | None = None


def probe_png_bytes() -> bytes:
    """Return a valid 1×1 RGBA PNG suitable for probes and smoke tests."""
    global _PROBE_PNG
    if _PROBE_PNG is None:
        buffer = io.BytesIO()
        Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buffer, format="PNG")
        _PROBE_PNG = buffer.getvalue()
    return _PROBE_PNG
