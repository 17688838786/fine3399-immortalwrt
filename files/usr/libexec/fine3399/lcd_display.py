#!/usr/bin/python3
"""Rotating status and optional artwork display for the Fine3399 LCD."""

from __future__ import annotations

import mmap
import os
import struct
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageSequence


WIDTH = 160
HEIGHT = 80
FONT_PATH = "/usr/share/fonts/ttf-dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/ttf-dejavu/DejaVuSans-Bold.ttf"
THEME_DIR = Path(os.environ.get("FINE3399_LCD_THEME_DIR", "/mnt/mmcblk2p4/lcd"))
BUILTIN_THEME_DIR = Path("/usr/share/fine3399-lcd")
PAGE_SECONDS = max(float(os.environ.get("FINE3399_LCD_PAGE_SECONDS", "8")), 1.0)
SERVICE_SECONDS = max(float(os.environ.get("FINE3399_LCD_SERVICE_SECONDS", "5")), 1.0)
ANIMATION_SECONDS = max(float(os.environ.get("FINE3399_LCD_ANIMATION_SECONDS", "6")), 0.0)
SAMPLE_SECONDS = 1.0

PANEL = (5, 10, 72, 70)
COLORS = {
    "panel": (43, 38, 91, 218),
    "border": (153, 140, 207, 245),
    "text": (248, 244, 255, 255),
    "muted": (174, 168, 200, 255),
    "ok": (78, 226, 148, 255),
    "warn": (255, 207, 105, 255),
    "error": (255, 105, 135, 255),
    "down": (108, 215, 255, 255),
    "up": (255, 164, 218, 255),
    "cpu": (103, 204, 244, 255),
    "ram": (177, 148, 238, 255),
    "disk": (255, 169, 213, 255),
}


def read_text(path: str | Path, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return default


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError:
        return subprocess.CompletedProcess(command, 127, "", "")


def framebuffer_path(
    graphics_root: Path = Path("/sys/class/graphics"),
    device_root: Path = Path("/dev"),
) -> Path:
    configured = os.environ.get("FINE3399_LCD_FB")
    if configured:
        return Path(configured)
    for entry in sorted(graphics_root.glob("fb[0-9]*")):
        if "st7735" in read_text(entry / "name").lower():
            return device_root / entry.name
    raise FileNotFoundError("ST7735 framebuffer is unavailable")


def default_interface() -> str:
    words = run(["ip", "route", "show", "default"]).stdout.split()
    try:
        return words[words.index("dev") + 1]
    except (ValueError, IndexError):
        return "br-lan"


def interface_ip(interface: str) -> str:
    for word in run(["ip", "-4", "-o", "addr", "show", "dev", interface]).stdout.split():
        if "/" in word and word[0].isdigit():
            return word.split("/", 1)[0]
    return ""


def counters(interface: str) -> tuple[int, int]:
    base = Path("/sys/class/net") / interface / "statistics"
    try:
        return int((base / "rx_bytes").read_text()), int((base / "tx_bytes").read_text())
    except (OSError, ValueError):
        return 0, 0


def speed(value: float) -> str:
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            precision = 1 if unit in ("M", "G") and value < 100 else 0
            return f"{value:.{precision}f}{unit}"
        value /= 1024
    return "0B"


def temperature_value() -> float | None:
    preferred: list[Path] = []
    fallback: list[Path] = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        zone_type = read_text(zone / "type").lower()
        target = preferred if any(word in zone_type for word in ("cpu", "soc", "package")) else fallback
        target.append(zone / "temp")
    for path in preferred + fallback:
        try:
            value = int(path.read_text().strip()) / 1000
            if 0 < value < 150:
                return value
        except (OSError, ValueError):
            pass
    return None


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


def cpu_sample() -> tuple[int, int]:
    fields = read_text("/proc/stat").splitlines()
    if not fields or not fields[0].startswith("cpu "):
        return 0, 0
    values = [int(value) for value in fields[0].split()[1:]]
    idle = sum(values[3:5])
    return sum(values), idle


def cpu_percent(previous: tuple[int, int], current: tuple[int, int]) -> int:
    total = current[0] - previous[0]
    idle = current[1] - previous[1]
    return max(0, min(100, round((total - idle) * 100 / total))) if total > 0 else 0


def storage_percent() -> int:
    mounts: list[tuple[int, Path]] = []
    for line in read_text("/proc/mounts").splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        device, mountpoint = fields[:2]
        priority = 0
        if device.startswith("/dev/nvme"):
            priority = 2
        elif mountpoint.endswith("p4") or "share" in mountpoint.lower():
            priority = 1
        if priority:
            mounts.append((priority, Path(mountpoint.replace("\\040", " "))))
    for _, mountpoint in sorted(mounts, reverse=True):
        try:
            stats = os.statvfs(mountpoint)
            return round((stats.f_blocks - stats.f_bavail) * 100 / stats.f_blocks)
        except (OSError, ZeroDivisionError):
            pass
    return 0


def service_state(name: str) -> str:
    init = Path("/etc/init.d") / name
    if not init.exists():
        return "missing"
    running = run([str(init), "running"]).returncode == 0
    enabled = run([str(init), "enabled"]).returncode == 0
    if running:
        return "running"
    return "error" if enabled else "disabled"


def docker_summary() -> tuple[str, str]:
    state = service_state("dockerd")
    if state != "running":
        return state, "OFF"
    running = [line for line in run(["docker", "ps", "-q"]).stdout.splitlines() if line]
    total = [line for line in run(["docker", "ps", "-aq"]).stdout.splitlines() if line]
    return ("running" if len(running) == len(total) else "error"), f"{len(running)}/{len(total)}"


def status_color(state: str) -> tuple[int, int, int, int]:
    return {
        "running": COLORS["ok"],
        "error": COLORS["error"],
        "disabled": COLORS["muted"],
        "missing": COLORS["muted"],
    }[state]


def default_background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (215, 211, 242))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        color = (221 - y // 5, 216 - y // 7, 244 - y // 9)
        draw.line((0, y, WIDTH, y), fill=color)
    # A copyright-free penguin-like pixel companion when no custom theme exists.
    draw.ellipse((105, 7, 154, 61), fill=(89, 119, 173), outline=(57, 64, 119), width=2)
    draw.ellipse((113, 21, 147, 59), fill=(246, 238, 239))
    draw.rectangle((112, 63, 148, 69), fill=(124, 99, 171))
    draw.ellipse((118, 25, 123, 30), fill=(40, 44, 82))
    draw.ellipse((138, 25, 143, 30), fill=(40, 44, 82))
    draw.polygon(((128, 32), (135, 32), (131, 37)), fill=(246, 177, 115))
    return image


def theme_directories() -> tuple[Path, ...]:
    if THEME_DIR == BUILTIN_THEME_DIR:
        return (THEME_DIR,)
    return THEME_DIR, BUILTIN_THEME_DIR


def load_background() -> Image.Image:
    for directory in theme_directories():
        for name in ("status.png", "status.webp", "background.png", "background.webp"):
            path = directory / name
            try:
                with Image.open(path) as source:
                    return source.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            except OSError:
                pass
    return default_background()


def draw_panel(image: Image.Image) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle(PANEL, radius=4, fill=COLORS["panel"], outline=COLORS["border"], width=1)
    return draw


def draw_right(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
) -> None:
    draw.text((x, y), text, font=font, fill=fill, anchor="ra")


def fitting_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    preferred: ImageFont.FreeTypeFont,
    fallback: ImageFont.FreeTypeFont,
    max_width: int,
) -> ImageFont.FreeTypeFont:
    bounds = draw.textbbox((0, 0), text, font=preferred)
    return preferred if bounds[2] - bounds[0] <= max_width else fallback


def render_network(background: Image.Image, online: bool, rx_rate: float, tx_rate: float, fonts: dict[str, ImageFont.FreeTypeFont]) -> Image.Image:
    image = background.copy()
    draw = draw_panel(image)
    state = "ONLINE" if online else "OFFLINE"
    color = COLORS["ok"] if online else COLORS["error"]
    draw.ellipse((11, 17, 17, 23), fill=color)
    draw.text((21, 14), state, font=fonts["bold"], fill=color)
    down = f"↓ {speed(rx_rate)}"
    up = f"↑ {speed(tx_rate)}"
    draw.text((10, 32), down, font=fitting_font(draw, down, fonts["big"], fonts["bold"], 58), fill=COLORS["down"])
    draw.text((10, 50), up, font=fitting_font(draw, up, fonts["big"], fonts["bold"], 58), fill=COLORS["up"])
    return image


def render_system(background: Image.Image, cpu: int, memory: int, storage: int, temp: float | None, fonts: dict[str, ImageFont.FreeTypeFont]) -> Image.Image:
    image = background.copy()
    draw = draw_panel(image)
    temperature = "--°C" if temp is None else f"{temp:.0f}°C"
    temp_color = COLORS["error"] if temp is not None and temp >= 80 else COLORS["warn"] if temp is not None and temp >= 65 else COLORS["text"]
    draw.text((10, 12), temperature, font=fonts["big"], fill=temp_color)
    for y, label, value, color in (
        (36, "CPU", cpu, COLORS["cpu"]),
        (50, "RAM", memory, COLORS["ram"]),
        (64, "SSD", storage, COLORS["disk"]),
    ):
        draw.text((10, y - 6), label, font=fonts["small"], fill=COLORS["text"])
        value = max(0, min(100, value))
        draw.rectangle((31, y, 48, y + 4), fill=(80, 69, 126, 255))
        draw.rectangle((31, y, 31 + round(17 * value / 100), y + 4), fill=color)
        draw_right(draw, 68, y - 7, f"{value}%", fonts["tiny"], COLORS["text"])
    return image


def service_snapshot() -> list[tuple[str, str, str]]:
    services = [
        ("CLASH", service_state("openclash"), ""),
        ("DDNS", service_state("ddns-go"), ""),
        ("FRPS", service_state("frps"), ""),
    ]
    docker_state, docker_text = docker_summary()
    services.append(("DOCKER", docker_state, docker_text))
    return services


def render_services(
    background: Image.Image,
    services: list[tuple[str, str, str]],
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> Image.Image:
    image = background.copy()
    draw = draw_panel(image)
    draw.text((10, 12), "SERVICES", font=fonts["bold"], fill=COLORS["text"])
    for y, (label, state, suffix) in zip((29, 41, 53, 65), services):
        draw.ellipse((10, y - 1, 15, y + 4), fill=status_color(state))
        visible_label = label
        if suffix:
            suffix_box = draw.textbbox((0, 0), suffix, font=fonts["tiny"])
            label_width = 68 - (suffix_box[2] - suffix_box[0]) - 3 - 19
            while visible_label and draw.textbbox((0, 0), visible_label, font=fonts["tiny"])[2] > label_width:
                visible_label = visible_label[:-1]
        draw.text((19, y - 4), visible_label, font=fonts["tiny"], fill=COLORS["text"])
        if suffix:
            draw_right(draw, 68, y - 4, suffix, fonts["tiny"], status_color(state))
    return image


def load_animation() -> list[tuple[Image.Image, float]]:
    for directory in theme_directories():
        for name in ("animation.gif", "animation.webp"):
            path = directory / name
            try:
                frames: list[tuple[Image.Image, float]] = []
                with Image.open(path) as source:
                    for index, frame in enumerate(ImageSequence.Iterator(source)):
                        if index >= 120:
                            break
                        duration = max(float(frame.info.get("duration", 100)) / 1000, 0.05)
                        frames.append((frame.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS), duration))
                if frames:
                    return frames
            except OSError:
                pass
        for name in ("splash.png", "splash.webp"):
            try:
                with Image.open(directory / name) as source:
                    return [(source.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS), 0.25)]
            except OSError:
                pass
    return []


def rgb565(image: Image.Image) -> bytes:
    output = bytearray(WIDTH * HEIGHT * 2)
    offset = 0
    for red, green, blue in image.convert("RGB").getdata():
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        struct.pack_into("<H", output, offset, value)
        offset += 2
    return bytes(output)


def main() -> None:
    fonts = {
        "tiny": ImageFont.truetype(FONT_PATH, 8),
        "small": ImageFont.truetype(FONT_PATH, 9),
        "bold": ImageFont.truetype(FONT_BOLD_PATH, 10),
        "big": ImageFont.truetype(FONT_BOLD_PATH, 14),
    }
    background = load_background()
    animation = load_animation()
    pages = (("network", PAGE_SECONDS), ("system", PAGE_SECONDS), ("services", SERVICE_SECONDS))
    page_index = 0
    page_started = time.monotonic()
    animation_started: float | None = None
    animation_index = 0
    animation_frame_started = 0.0
    interface = default_interface()
    previous_rx, previous_tx = counters(interface)
    previous_cpu = cpu_sample()
    previous_time = time.monotonic()
    rx_rate = tx_rate = 0.0
    cpu = 0
    services = service_snapshot()
    services_checked = time.monotonic()

    with framebuffer_path().open("r+b", buffering=0) as stream:
        framebuffer = mmap.mmap(stream.fileno(), WIDTH * HEIGHT * 2, access=mmap.ACCESS_WRITE)
        while True:
            now = time.monotonic()
            current_interface = default_interface()
            if current_interface != interface:
                interface = current_interface
                previous_rx, previous_tx = counters(interface)
                previous_time = now
            if now - previous_time >= SAMPLE_SECONDS:
                rx, tx = counters(interface)
                elapsed = max(now - previous_time, 0.1)
                rx_rate = max(rx - previous_rx, 0) / elapsed
                tx_rate = max(tx - previous_tx, 0) / elapsed
                previous_rx, previous_tx, previous_time = rx, tx, now
                current_cpu = cpu_sample()
                cpu = cpu_percent(previous_cpu, current_cpu)
                previous_cpu = current_cpu

            page, duration = pages[page_index]
            if animation_started is not None:
                if not animation or now - animation_started >= ANIMATION_SECONDS:
                    animation_started = None
                    animation_index = 0
                    page_started = now
                    page_index = 0
                    continue
                frame, frame_duration = animation[animation_index]
                if now - animation_frame_started >= frame_duration:
                    animation_index = (animation_index + 1) % len(animation)
                    animation_frame_started = now
                    frame = animation[animation_index][0]
                canvas = frame
            else:
                if now - page_started >= duration:
                    page_index += 1
                    page_started = now
                    if page_index >= len(pages):
                        if animation and ANIMATION_SECONDS > 0:
                            animation_started = now
                            animation_frame_started = now
                            animation_index = 0
                            canvas = animation[0][0]
                        else:
                            page_index = 0
                        if animation_started is not None:
                            framebuffer.seek(0)
                            framebuffer.write(rgb565(canvas))
                            framebuffer.flush()
                            time.sleep(0.05)
                            continue
                    page, _ = pages[page_index]
                online = bool(interface_ip(interface)) and interface != "br-lan"
                if page == "network":
                    canvas = render_network(background, online, rx_rate, tx_rate, fonts)
                elif page == "system":
                    canvas = render_system(background, cpu, memory_percent(), storage_percent(), temperature_value(), fonts)
                else:
                    if now - services_checked >= 10:
                        services = service_snapshot()
                        services_checked = now
                    canvas = render_services(background, services, fonts)

            framebuffer.seek(0)
            framebuffer.write(rgb565(canvas))
            framebuffer.flush()
            time.sleep(0.1 if animation_started is not None else 0.5)


if __name__ == "__main__":
    main()
