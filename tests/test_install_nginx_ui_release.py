import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.install_nginx_ui_release import InstallError, install


class InstallNginxUiReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.downloads = self.root / "downloads"
        self.downloads.mkdir()
        self.overlay = self.root / "overlay"
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "nginx_ui": {
                        "tag": "v2.5.6",
                        "assets": [{"name": "nginx-ui-linux-arm64-v8a.tar.gz"}],
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def arm64_elf():
        data = bytearray(64)
        data[:6] = b"\x7fELF\x02\x01"
        data[18:20] = (183).to_bytes(2, "little")
        return bytes(data)

    def make_archive(self, payload=None):
        archive = self.downloads / "nginx-ui-linux-arm64-v8a.tar.gz"
        data = self.arm64_elf() if payload is None else payload
        with tarfile.open(archive, "w:gz") as stream:
            info = tarfile.TarInfo("nginx-ui")
            info.size = len(data)
            stream.addfile(info, io.BytesIO(data))
        return data

    def test_installs_aarch64_binary_and_release_marker(self):
        expected = self.make_archive()

        destination = install(self.manifest, self.downloads, self.overlay)

        self.assertEqual(expected, destination.read_bytes())
        marker = json.loads(
            (self.overlay / "etc/fine3399-nginx-ui-release.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("v2.5.6", marker["tag"])
        self.assertEqual("https://github.com/0xJacky/nginx-ui", marker["project"])

    def test_rejects_non_aarch64_payload(self):
        self.make_archive(b"\x7fELFnot-arm64")

        with self.assertRaisesRegex(InstallError, "AArch64"):
            install(self.manifest, self.downloads, self.overlay)


if __name__ == "__main__":
    unittest.main()
