#!/usr/bin/env python3
"""Resolve rolling third-party firmware inputs and write an auditable manifest."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any


class ResolutionError(RuntimeError):
    pass


def github_json(path: str) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com/{path.lstrip('/')}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "fine3399-firmware-builder",
            **(
                {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}
                if os.environ.get("GITHUB_TOKEN")
                else {}
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (OSError, json.JSONDecodeError) as error:
        raise ResolutionError(f"GitHub API request failed for {path}: {error}") from error


def asset_record(asset: dict[str, Any]) -> dict[str, str]:
    name = asset.get("name")
    url = asset.get("browser_download_url")
    digest = asset.get("digest") or ""
    if not isinstance(name, str) or not isinstance(url, str):
        raise ResolutionError("release asset is missing name or download URL")
    return {"name": name, "url": url, "upstream_digest": digest}


def select_assets(release: dict[str, Any], patterns: list[str]) -> list[dict[str, str]]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ResolutionError("release has no assets list")
    selected: list[dict[str, str]] = []
    for pattern in patterns:
        matches = [asset for asset in assets if re.fullmatch(pattern, asset.get("name", ""))]
        if len(matches) != 1:
            raise ResolutionError(f"expected one asset matching {pattern}, found {len(matches)}")
        selected.append(asset_record(matches[0]))
    return selected


def latest_release_with_assets(repository: str, patterns: list[str]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    releases = github_json(f"repos/{repository}/releases?per_page=20")
    if not isinstance(releases, list):
        raise ResolutionError(f"{repository} releases response is not a list")
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        try:
            return release, select_assets(release, patterns)
        except ResolutionError:
            continue
    raise ResolutionError(
        f"no stable {repository} release contains all required assets: {', '.join(patterns)}"
    )


def resolve(config: dict[str, Any], kernel_version: str | None = None) -> dict[str, Any]:
    rolling = config["rolling"]
    argon = github_json(f"repos/{rolling['argon_repository']}/releases/latest")
    openclash = github_json(f"repos/{rolling['openclash_repository']}/releases/latest")
    nginx_ui, nginx_ui_assets = latest_release_with_assets(
        rolling["nginx_ui_repository"], [r"nginx-ui-linux-arm64-v8a\.tar\.gz"]
    )
    kernel = github_json(
        f"repos/{rolling['kernel_repository']}/releases/tags/{rolling['kernel_release_tag']}"
    )

    series = re.escape(rolling["kernel_series"])
    selected_version = kernel_version or rolling.get("kernel_version")
    kernel_assets = kernel.get("assets", [])
    candidates: list[tuple[tuple[int, ...], dict[str, Any]]] = []
    for asset in kernel_assets:
        match = re.fullmatch(rf"({series}\.(\d+))\.tar\.gz", asset.get("name", ""))
        if match and (selected_version is None or match.group(1) == selected_version):
            candidates.append((tuple(int(part) for part in match.group(1).split(".")), asset))
    if not candidates:
        requested = selected_version or f"latest {rolling['kernel_series']}.x"
        raise ResolutionError(f"no ophub kernel asset found for {requested}")
    _, kernel_asset = max(candidates, key=lambda candidate: candidate[0])

    return {
        "schema": 1,
        "immortalwrt": config["immortalwrt"],
        "argon": {
            "tag": argon["tag_name"],
            "assets": select_assets(
                argon,
                [
                    r"luci-theme-argon-[^-]+-r\d+\.apk",
                    r"luci-app-argon-config-[^-]+-r\d+\.apk",
                    r"luci-i18n-argon-config-zh-cn-[^-]+\.apk",
                ],
            ),
        },
        "openclash": {
            "tag": openclash["tag_name"],
            "assets": select_assets(openclash, [r"luci-app-openclash-[^-]+\.apk"]),
        },
        "nginx_ui": {
            "tag": nginx_ui["tag_name"],
            "assets": nginx_ui_assets,
        },
        "kernel": {
            "release_tag": kernel["tag_name"],
            "series": rolling["kernel_series"],
            "asset": asset_record(kernel_asset),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/releases.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kernel-version")
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        manifest = resolve(config, args.kernel_version)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ResolutionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
