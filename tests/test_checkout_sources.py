import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_TOOL = REPOSITORY_ROOT / "tools" / "checkout_sources.py"
SOURCE_NAMES = ("ophub",)


def run_git(*arguments, cwd, env=None):
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


class CheckoutSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.remote = self.root / "remote.git"
        self.author = self.root / "author"
        run_git("init", "--bare", str(self.remote), cwd=self.root)
        run_git("init", str(self.author), cwd=self.root)
        run_git("config", "user.name", "Fixture", cwd=self.author)
        run_git("config", "user.email", "fixture@example.invalid", cwd=self.author)

        tracked_file = self.author / "payload.txt"
        tracked_file.write_text("first\n", encoding="utf-8")
        run_git("add", "payload.txt", cwd=self.author)
        run_git("commit", "-m", "first", cwd=self.author)
        self.first_commit = run_git("rev-parse", "HEAD", cwd=self.author)

        tracked_file.write_text("second\n", encoding="utf-8")
        run_git("commit", "-am", "second", cwd=self.author)
        self.second_commit = run_git("rev-parse", "HEAD", cwd=self.author)
        run_git("push", str(self.remote), "HEAD:main", cwd=self.author)

        self.lock_path = self.root / "versions.lock.json"
        self.fake_url = "https://fixture.invalid/remote.git"
        self.write_lock(self.first_commit)
        self.git_environment = os.environ.copy()
        self.git_environment.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": f"url.{self.remote.as_uri()}.insteadOf",
                "GIT_CONFIG_VALUE_0": self.fake_url,
            }
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_lock(self, commit):
        data = {
            "schema": 1,
            "sources": {
                name: {"url": self.fake_url, "commit": commit}
                for name in SOURCE_NAMES
            },
        }
        self.lock_path.write_text(json.dumps(data), encoding="utf-8")

    def run_checkout(self, destination, *extra_arguments):
        return subprocess.run(
            [
                sys.executable,
                str(CHECKOUT_TOOL),
                "--lock",
                str(self.lock_path),
                "--destination",
                str(destination),
                *extra_arguments,
            ],
            cwd=REPOSITORY_ROOT,
            env=self.git_environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_fresh_checkout_detaches_every_source_at_locked_commit(self):
        destination = self.root / "sources"

        result = self.run_checkout(destination)

        self.assertEqual(0, result.returncode, result.stderr)
        for name in SOURCE_NAMES:
            source_path = destination / name
            self.assertEqual(
                self.first_commit,
                run_git("rev-parse", "HEAD", cwd=source_path),
            )
            self.assertEqual("HEAD", run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=source_path))
        manifest = json.loads(
            (destination / "checkout-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(list(SOURCE_NAMES), [item["name"] for item in manifest["sources"]])
        self.assertTrue(all(item["checked_out_commit"] == self.first_commit for item in manifest["sources"]))

    def test_repeat_checkout_accepts_matching_directories(self):
        destination = self.root / "sources"
        first_result = self.run_checkout(destination)

        second_result = self.run_checkout(destination)

        self.assertEqual(0, first_result.returncode, first_result.stderr)
        self.assertEqual(0, second_result.returncode, second_result.stderr)

    def test_existing_wrong_commit_is_rejected_without_reset(self):
        destination = self.root / "sources"
        first_result = self.run_checkout(destination)
        self.assertEqual(0, first_result.returncode, first_result.stderr)
        ophub_path = destination / "ophub"
        run_git("fetch", "origin", self.second_commit, cwd=ophub_path, env=self.git_environment)
        run_git("checkout", "--detach", self.second_commit, cwd=ophub_path)

        result = self.run_checkout(destination)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("ophub", result.stderr)
        self.assertIn(self.first_commit, result.stderr)
        self.assertIn(self.second_commit, result.stderr)
        self.assertEqual(self.second_commit, run_git("rev-parse", "HEAD", cwd=ophub_path))

    def test_missing_commit_does_not_leave_final_source_directory(self):
        destination = self.root / "sources"
        self.write_lock("f" * 40)

        result = self.run_checkout(destination)

        self.assertNotEqual(0, result.returncode)
        self.assertFalse((destination / "ophub").exists())

    def test_destination_with_spaces_is_supported(self):
        destination = self.root / "build output" / "sources"

        result = self.run_checkout(destination)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((destination / "ophub" / ".git").is_dir())

if __name__ == "__main__":
    unittest.main()
