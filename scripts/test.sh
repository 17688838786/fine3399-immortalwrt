#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
python3 -m unittest discover -s tests -v
python3 tools/lockfile.py validate versions.lock.json
git diff --check
