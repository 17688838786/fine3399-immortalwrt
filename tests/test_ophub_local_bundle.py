import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "prepare_ophub.py"


class OphubLocalBundleTests(unittest.TestCase):
    def test_repository_patch_applies_to_locked_ophub_and_disables_download(self):
        source = ROOT / "build" / "sources" / "ophub"
        if not source.is_dir():
            self.skipTest("locked ophub checkout is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            tree = Path(temporary) / "ophub"
            result = subprocess.run([sys.executable, str(TOOL), "--source", str(source), "--tree", str(tree)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            remake = (tree / "remake").read_text(encoding="utf-8")
            self.assertIn("FINE3399_KERNEL_BUNDLE", remake)
            self.assertIn('if [[ -n "${local_kernel_bundle}" ]]', remake)
            self.assertIn('check_kernel "${local_kernel_bundle}"', remake)
            self.assertIn('build_kernel=("${latest_kernel[@]}")', remake)
        self.assertIn("Installed checked local kernel bundle", remake)
        self.assertIn('tar -mxzf "${local_kernel_bundle}/${kernel_modules}" -C "${tag_rootfs}/lib/modules"', remake)


if __name__ == "__main__":
    unittest.main()
