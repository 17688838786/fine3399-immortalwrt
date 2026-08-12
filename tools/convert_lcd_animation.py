#!/usr/bin/env python3
"""Convert an animated image into Fine3399's directly writable RGB565 frame pack."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PIL import Image, ImageSequence


WIDTH = 160
HEIGHT = 80
MAGIC = b"F339LCD1"
HEADER = struct.Struct("<8sHHHH")


def rgb565(image: Image.Image) -> bytes:
    output = bytearray(WIDTH * HEIGHT * 2)
    offset = 0
    for red, green, blue in image.convert("RGB").getdata():
        value = ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)
        struct.pack_into("<H", output, offset, value)
        offset += 2
    return bytes(output)


def convert(source_path: Path, output_path: Path, limit: int) -> tuple[int, int]:
    frames: list[bytes] = []
    durations: list[int] = []
    with Image.open(source_path) as source:
        for index, frame in enumerate(ImageSequence.Iterator(source)):
            if index >= limit:
                break
            image = frame.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            frames.append(rgb565(image))
            durations.append(max(int(frame.info.get("duration", 100)), 50))
    if not frames:
        raise ValueError(f"No frames found in {source_path}")
    delay_ms = round(sum(durations) / len(durations))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(
        HEADER.pack(MAGIC, WIDTH, HEIGHT, len(frames), delay_ms) + b"".join(frames)
    )
    return len(frames), delay_ms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 65535:
        parser.error("--limit must be between 1 and 65535")
    frame_count, delay_ms = convert(args.source, args.output, args.limit)
    print(f"wrote {frame_count} frames at {delay_ms} ms to {args.output}")


if __name__ == "__main__":
    main()
