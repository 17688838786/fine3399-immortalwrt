#!/usr/bin/python3
"""Small status display for the Fine3399 ST7735S framebuffer."""

from __future__ import annotations

import mmap
import os
import socket
import struct
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 160
HEIGHT = 80
FONT_PATH = "/usr/share/fonts/ttf-dejavu/DejaVuSans.ttf"


def read_text(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return default


def framebuffer_path(
    graphics_root: Path = Path("/sys/class/graphics"),
    device_root: Path = Path("/dev"),
) -> Path:
    configured = os.environ.get("FINE3399_LCD_FB")
    if configured:
        return Path(configured)
    for entry in sorted(graphics_root.glob("fb[0-9]*")):
        if "st7735" in read_text(str(entry / "name")).lower():
            return device_root / entry.name
    raise FileNotFoundError("ST7735 framebuffer is unavailable")


def temperature() -> str:
    for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        try:
            value = int(path.read_text().strip()) / 1000
            if 0 < value < 150:
                return f"{value:.0f}C"
        except (OSError, ValueError):
            pass
    return "--C"


def memory_percent() -> int:
    fields: dict[str, int] = {}
    for line in read_text("/proc/meminfo").splitlines():
        name, _, value = line.partition(":")
        try:
            fields[name] = int(value.split()[0])
        except (IndexError, ValueError):
            continue
    total = fields.get("MemTotal", 0)
    available = fields.get("MemAvailable", 0)
    return round((total - available) * 100 / total) if total else 0


def default_interface() -> str:
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            check=False,
            capture_output=True,
            text=True,
        )
        words = result.stdout.split()
        return words[words.index("dev") + 1] if "dev" in words else "br-lan"
    except (OSError, ValueError, IndexError):
        return "br-lan"


def interface_ip(interface: str) -> str:
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "dev", interface],
            check=False,
            capture_output=True,
            text=True,
        )
        for word in result.stdout.split():
            if "/" in word and word[0].isdigit():
                return word.split("/", 1)[0]
    except OSError:
        pass
    return "no IPv4"


def counters(interface: str) -> tuple[int, int]:
    base = Path("/sys/class/net") / interface / "statistics"
    try:
        return int((base / "rx_bytes").read_text()), int((base / "tx_bytes").read_text())
    except (OSError, ValueError):
        return 0, 0


def speed(value: float) -> str:
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}/s"
        value /= 1024
    return "0B/s"


def rgb565(image: Image.Image) -> bytes:
    output = bytearray(WIDTH * HEIGHT * 2)
    offset = 0
    for red, green, blue in image.convert("RGB").getdata():
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        struct.pack_into("<H", output, offset, value)
        offset += 2
    return bytes(output)


def main() -> None:
    font = ImageFont.truetype(FONT_PATH, 12)
    small = ImageFont.truetype(FONT_PATH, 10)
    interface = default_interface()
    previous_rx, previous_tx = counters(interface)
    previous_time = time.monotonic()

    with framebuffer_path().open("r+b", buffering=0) as stream:
        framebuffer = mmap.mmap(stream.fileno(), WIDTH * HEIGHT * 2, access=mmap.ACCESS_WRITE)
        while True:
            now = time.monotonic()
            rx, tx = counters(interface)
            elapsed = max(now - previous_time, 0.1)
            rx_rate = max(rx - previous_rx, 0) / elapsed
            tx_rate = max(tx - previous_tx, 0) / elapsed
            previous_rx, previous_tx, previous_time = rx, tx, now

            canvas = Image.new("RGB", (WIDTH, HEIGHT), "black")
            draw = ImageDraw.Draw(canvas)
            draw.text((3, 2), socket.gethostname()[:16], font=font, fill="#52d273")
            draw.text((3, 19), f"{interface}: {interface_ip(interface)}", font=small, fill="white")
            draw.text((3, 34), f"DOWN {speed(rx_rate)}", font=small, fill="#5ab0ff")
            draw.text((84, 34), f"UP {speed(tx_rate)}", font=small, fill="#ffb35a")
            uptime = int(float(read_text("/proc/uptime", "0").split()[0]) // 60)
            draw.text((3, 50), f"TEMP {temperature()}  RAM {memory_percent()}%", font=small, fill="white")
            draw.text((3, 65), f"UP {uptime // 60}h{uptime % 60:02d}m", font=small, fill="#bbbbbb")

            framebuffer.seek(0)
            framebuffer.write(rgb565(canvas))
            framebuffer.flush()
            time.sleep(1)


if __name__ == "__main__":
    main()
