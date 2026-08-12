import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCKFILE_TOOL = REPOSITORY_ROOT / "tools" / "lockfile.py"

VALID_LOCK = {
    "schema": 1,
    "sources": {
        "ophub": {
            "url": "https://github.com/ophub/amlogic-s9xxx-openwrt.git",
            "commit": "75dd68045f59011667c356fcda5bff84940c1c2f",
        },
    },
}


class LockfileCliTests(unittest.TestCase):
    def run_tool(self, data, *arguments):
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock_path = Path(temporary_directory) / "versions.lock.json"
            lock_path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(LOCKFILE_TOOL),
                    arguments[0],
                    str(lock_path),
                    *arguments[1:],
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_validate_accepts_complete_immutable_lock(self):
        result = self.run_tool(VALID_LOCK, "validate")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_validate_rejects_invalid_source_values(self):
        mutations = {
            "branch instead of commit": ("commit", "openwrt-25.12"),
            "short commit": ("commit", "3dacd2f"),
            "uppercase commit": (
                "commit",
                "3DACD2FB6A48C5963B1026C6A343EC7E67CBF810",
            ),
            "non-https URL": (
                "url",
                "git@github.com:immortalwrt/immortalwrt.git",
            ),
        }

        for label, (field, value) in mutations.items():
            with self.subTest(label=label):
                invalid_lock = copy.deepcopy(VALID_LOCK)
                invalid_lock["sources"]["ophub"][field] = value

                result = self.run_tool(invalid_lock, "validate")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("ophub", result.stderr)

    def test_validate_rejects_missing_required_source(self):
        invalid_lock = copy.deepcopy(VALID_LOCK)
        del invalid_lock["sources"]["ophub"]

        result = self.run_tool(invalid_lock, "validate")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing required sources: ophub", result.stderr)

    def test_validate_rejects_unknown_fields(self):
        root_field_lock = copy.deepcopy(VALID_LOCK)
        root_field_lock["unexpected"] = True
        source_field_lock = copy.deepcopy(VALID_LOCK)
        source_field_lock["sources"]["ophub"]["branch"] = "main"

        for label, invalid_lock in (
            ("root", root_field_lock),
            ("source", source_field_lock),
        ):
            with self.subTest(label=label):
                result = self.run_tool(invalid_lock, "validate")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("unknown", result.stderr.lower())

if __name__ == "__main__":
    unittest.main()
