#!/usr/bin/env python3
"""Download resolved release assets and append actual SHA256 values to a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path


class FetchError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "fine3399-firmware-builder"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def fetch(manifest_path: Path, destination: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = []
    for component in ("argon", "openclash", "nginx_ui"):
        assets.extend(manifest[component]["assets"])
    assets.append(manifest["kernel"]["asset"])
    destination.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        target = destination / asset["name"]
        upstream = asset.get("upstream_digest", "")
        if (
            target.is_file()
            and upstream.startswith("sha256:")
            and sha256(target) != upstream.removeprefix("sha256:")
        ):
            target.unlink()
        if not target.is_file():
            download(asset["url"], target)
        actual = sha256(target)
        if upstream.startswith("sha256:") and actual != upstream.removeprefix("sha256:"):
            raise FetchError(f"checksum mismatch for {asset['name']}")
        asset["sha256"] = actual
        asset["size"] = target.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        fetch(args.manifest, args.destination)
    except (FetchError, OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
