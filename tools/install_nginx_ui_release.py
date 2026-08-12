#!/usr/bin/env python3
"""Install the resolved official Nginx UI ARM64 binary into an overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path, PurePosixPath


class InstallError(RuntimeError):
    pass


def install(manifest_path: Path, downloads: Path, root: Path) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = manifest["nginx_ui"]["assets"]
    if len(assets) != 1:
        raise InstallError(f"expected one Nginx UI release asset, found {len(assets)}")

    archive_path = downloads / assets[0]["name"]
    if not archive_path.is_file():
        raise InstallError(f"missing downloaded Nginx UI release: {archive_path}")

    with tarfile.open(archive_path, "r:gz") as archive:
        matches = []
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.isdev():
                raise InstallError(f"unsafe Nginx UI archive member: {member.name}")
            if member.isfile() and path.name == "nginx-ui":
                matches.append(member)
        if len(matches) != 1:
            raise InstallError(f"expected one nginx-ui binary, found {len(matches)}")
        stream = archive.extractfile(matches[0])
        if stream is None:
            raise InstallError("unable to read nginx-ui binary")
        data = stream.read()

    if (
        data[:6] != b"\x7fELF\x02\x01"
        or len(data) < 20
        or int.from_bytes(data[18:20], "little") != 183
    ):
        raise InstallError("Nginx UI release payload is not AArch64 ELF64")

    destination = root / "usr/bin/nginx-ui"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    os.chmod(destination, 0o755)

    marker = root / "etc/fine3399-nginx-ui-release.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "asset": assets[0]["name"],
                "binary_sha256": hashlib.sha256(data).hexdigest(),
                "project": "https://github.com/0xJacky/nginx-ui",
                "tag": manifest["nginx_ui"]["tag"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        install(args.manifest, args.downloads, args.root)
    except (InstallError, OSError, KeyError, ValueError, json.JSONDecodeError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
