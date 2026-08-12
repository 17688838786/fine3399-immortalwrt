#!/usr/bin/env python3
"""Check out every locked source at an exact detached commit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from lockfile import LockfileError, load_and_validate


class CheckoutError(RuntimeError):
    """Raised when a checkout cannot safely satisfy its source lock."""


def run_git(arguments: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "git failed"
        raise CheckoutError(detail) from error
    return result.stdout.strip()


def validate_existing_checkout(path: Path, name: str, url: str, commit: str) -> None:
    if not (path / ".git").is_dir():
        raise CheckoutError(f"source {name} exists but is not a Git checkout: {path}")
    actual_commit = run_git(["rev-parse", "HEAD"], path)
    if actual_commit != commit:
        raise CheckoutError(
            f"source {name} commit mismatch: expected {commit}, actual {actual_commit}"
        )
    actual_url = run_git(["config", "--get", "remote.origin.url"], path)
    if actual_url != url:
        raise CheckoutError(
            f"source {name} origin mismatch: expected {url}, actual {actual_url}"
        )


def create_checkout(destination: Path, name: str, url: str, commit: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=destination) as temporary:
        staging = Path(temporary)
        run_git(["init", "--quiet"], staging)
        run_git(["remote", "add", "origin", url], staging)
        run_git(["fetch", "--depth=1", "origin", commit], staging)
        run_git(["checkout", "--quiet", "--detach", "FETCH_HEAD"], staging)
        actual_commit = run_git(["rev-parse", "HEAD"], staging)
        if actual_commit != commit:
            raise CheckoutError(
                f"source {name} fetched wrong commit: expected {commit}, actual {actual_commit}"
            )
        final_path = destination / name
        if final_path.exists():
            raise CheckoutError(f"source {name} appeared during checkout: {final_path}")
        staging.rename(final_path)


def checkout_sources(lock_path: Path, destination: Path) -> None:
    lock = load_and_validate(lock_path)
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise CheckoutError(f"destination is not a directory: {destination}")

    manifest_sources = []
    for name in sorted(lock["sources"]):
        source = lock["sources"][name]
        source_path = destination / name
        if source_path.exists():
            validate_existing_checkout(
                source_path,
                name,
                source["url"],
                source["commit"],
            )
        else:
            create_checkout(
                destination,
                name,
                source["url"],
                source["commit"],
            )
        checked_out_commit = run_git(["rev-parse", "HEAD"], source_path)
        manifest_sources.append(
            {
                "name": name,
                "url": source["url"],
                "locked_commit": source["commit"],
                "checked_out_commit": checked_out_commit,
            }
        )

    manifest_path = destination / "checkout-manifest.json"
    manifest_path.write_text(
        json.dumps({"schema": 1, "sources": manifest_sources}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = create_parser().parse_args(argv)
    try:
        checkout_sources(arguments.lock, arguments.destination)
    except (CheckoutError, LockfileError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
