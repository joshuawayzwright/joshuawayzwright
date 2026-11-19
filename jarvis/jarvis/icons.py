"""App icons for adding the web interface to a phone's home screen, drawn in code so no image files ship.

The icon is a blue rounded square with a white ring (Jarvis's "arc"). PNG is needed because iOS ignores SVG
home-screen icons; the encoder is the minimal one PNG allows: 8-bit RGBA, one zlib-compressed IDAT chunk.
"""

from __future__ import annotations

import struct
import zlib
from functools import lru_cache

BACKGROUND = (11, 107, 203, 255)  # the interface's accent blue
RING = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
<rect width="100" height="100" rx="22" fill="#0b6bcb"/>
<circle cx="50" cy="50" r="26" fill="none" stroke="#fff" stroke-width="9"/>
<circle cx="50" cy="50" r="7" fill="#fff"/>
</svg>"""


def _pixel(x: float, y: float, size: int, rounded: bool) -> tuple[int, int, int, int]:
    u, v = x / size * 100, y / size * 100  # same 0-100 coordinates as the SVG
    if rounded:
        r = 22
        cx, cy = min(max(u, r), 100 - r), min(max(v, r), 100 - r)
        if (u - cx) ** 2 + (v - cy) ** 2 > r * r:
            return CLEAR
    d = ((u - 50) ** 2 + (v - 50) ** 2) ** 0.5
    if abs(d - 26) <= 4.5 or d <= 7:
        return RING
    return BACKGROUND


@lru_cache(maxsize=4)
def png(size: int, rounded: bool = True) -> bytes:
    """The icon as a PNG of size x size pixels. iOS rounds corners itself, so it gets a square one."""
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # filter type: none
        for x in range(size):
            rows.extend(_pixel(x + 0.5, y + 0.5, size, rounded))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))
