#!/usr/bin/env python3
"""Copy the locked ophub tree and apply the local-bundle patch."""

from __future__ import annotations
import argparse, shutil, subprocess, sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--tree", required=True, type=Path)
    args = parser.parse_args(argv)
    source, tree = args.source.resolve(), args.tree.resolve()
    try:
        if tree.exists():
            if not (tree / ".fine3399-ophub-tree").is_file():
                raise RuntimeError(f"refusing to replace unmarked tree: {tree}")
            shutil.rmtree(tree)
        shutil.copytree(source, tree, symlinks=True)
        (tree / ".fine3399-ophub-tree").write_text("disposable\n", encoding="utf-8")
        patch_dir = Path(__file__).resolve().parents[1] / "patches" / "ophub"
        for patch in sorted(patch_dir.glob("*.patch")):
            subprocess.run(["git", "apply", "--check", str(patch)], cwd=tree, check=True)
            subprocess.run(["git", "apply", str(patch)], cwd=tree, check=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

