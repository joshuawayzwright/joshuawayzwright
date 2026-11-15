"""Screen vision: let Jarvis look at what's on your screen (an error dialog, a broken page, a stack trace)."""

from __future__ import annotations

import base64
import io
from typing import Any

MAX_EDGE = 1568  # the long edge Claude's vision works best at; bigger images are downscaled anyway
MAX_BYTES = 3_500_000  # stay well under the API's per-image limit after base64 encoding


class ScreenUnavailable(Exception):
    """A screenshot can't be taken; the message says why."""


def _grab(monitor: int) -> Any:
    try:
        import mss
        from PIL import Image
    except ImportError as err:
        raise ScreenUnavailable('Screen vision needs extra packages: pip install ".[screen]"') from err
    factory = getattr(mss, "MSS", None) or mss.mss  # mss 10 renamed the class
    try:
        with factory() as sct:
            monitors = sct.monitors  # [0] is all screens together, [1:] are individual screens
            if not 0 <= monitor < len(monitors):
                raise ScreenUnavailable(f"Monitor {monitor} doesn't exist; there are {len(monitors) - 1} screen(s).")
            shot = sct.grab(monitors[monitor])
            return Image.frombytes("RGB", shot.size, shot.rgb)
    except ScreenUnavailable:
        raise
    except Exception as err:  # noqa: BLE001 - no display, permissions (macOS Screen Recording), etc.
        raise ScreenUnavailable(
            f"Couldn't capture the screen: {err}. On macOS, allow your terminal under "
            "System Settings > Privacy & Security > Screen Recording."
        ) from err


def encode(image: Any) -> tuple[str, str, tuple[int, int]]:
    """Downscale and encode an image. Returns (base64 data, media type, final size)."""
    from PIL import Image

    scale = MAX_EDGE / max(image.size)
    if scale < 1:
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    media_type = "image/png"
    if buffer.tell() > MAX_BYTES:  # photos and busy screens: JPEG is far smaller
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=85)
        media_type = "image/jpeg"
    return base64.b64encode(buffer.getvalue()).decode("ascii"), media_type, image.size


def screenshot_blocks(monitor: int = 1) -> list[dict[str, Any]]:
    """Tool-result content: the screenshot as an image block plus a short caption."""
    data, media_type, (width, height) = encode(_grab(monitor))
    return [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
        {"type": "text", "text": f"Screenshot of monitor {monitor}, shown at {width}x{height}."},
    ]
