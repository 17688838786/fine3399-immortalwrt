#!/usr/bin/env python3
"""Validate immutable upstream source locks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REQUIRED_SOURCES = frozenset({"ophub"})
ROOT_FIELDS = frozenset({"schema", "sources"})
SOURCE_FIELDS = frozenset({"url", "commit"})
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


class LockfileError(ValueError):
    """Raised when a source lock violates the repository schema."""


def _require_exact_fields(
    value: dict[str, Any], expected: frozenset[str], context: str
) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise LockfileError(f"{context} has unknown fields: {', '.join(unknown)}")
    if missing:
        raise LockfileError(f"{context} is missing fields: {', '.join(missing)}")


def _validate_source(name: str, source: Any) -> None:
    if not isinstance(source, dict):
        raise LockfileError(f"source {name} must be an object")
    _require_exact_fields(source, SOURCE_FIELDS, f"source {name}")

    url = source["url"]
    if not isinstance(url, str):
        raise LockfileError(f"source {name} URL must be a string")
    parsed_url = urlparse(url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.netloc
        or not parsed_url.path.endswith(".git")
        or parsed_url.params
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise LockfileError(f"source {name} URL must be an HTTPS Git URL")

    commit = source["commit"]
    if not isinstance(commit, str) or COMMIT_PATTERN.fullmatch(commit) is None:
        raise LockfileError(
            f"source {name} commit must be a lowercase 40-character SHA-1"
        )


def validate_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LockfileError("lockfile root must be an object")
    _require_exact_fields(data, ROOT_FIELDS, "lockfile root")
    if data["schema"] != 1 or isinstance(data["schema"], bool):
        raise LockfileError("lockfile schema must be integer 1")
    if not isinstance(data["sources"], dict):
        raise LockfileError("lockfile sources must be an object")

    source_names = set(data["sources"])
    missing = sorted(REQUIRED_SOURCES - source_names)
    unknown = sorted(source_names - REQUIRED_SOURCES)
    if missing:
        raise LockfileError(f"missing required sources: {', '.join(missing)}")
    if unknown:
        raise LockfileError(f"unknown sources: {', '.join(unknown)}")

    for name in sorted(source_names):
        _validate_source(name, data["sources"][name])
    return data


def load_and_validate(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise LockfileError(f"cannot read {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise LockfileError(
            f"invalid JSON in {path}: line {error.lineno} column {error.colno}"
        ) from error
    return validate_data(data)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("lockfile", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = create_parser().parse_args(argv)
    try:
        load_and_validate(arguments.lockfile)
    except LockfileError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
