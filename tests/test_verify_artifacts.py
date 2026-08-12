import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools.verify_fast_artifacts import (
    EXPECTED_PACKAGES,
    VerificationError,
    verify_bundle,
    verify_rootfs,
)


class VerifyArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_rootfs(self, packages=EXPECTED_PACKAGES):
        rootfs = self.root / "rootfs.tar.gz"
        frps = b"\x7fELFfrps"
        lcd = bytearray(64)
        lcd[:6] = b"\x7fELF\x02\x01"
        lcd[18:20] = (183).to_bytes(2, "little")
        lcd = bytes(lcd)
        nginx_ui = bytearray(64)
        nginx_ui[:6] = b"\x7fELF\x02\x01"
        nginx_ui[18:20] = (183).to_bytes(2, "little")
        nginx_ui = bytes(nginx_ui)
        files = {
            "lib/apk/db/installed": "".join(f"P:{name}\n" for name in packages).encode(),
            "etc/fine3399-build.json": b"{}\n",
            "etc/uci-defaults/90-fine3399-baseline": b"#!/bin/sh\n",
            "etc/init.d/lcd_display": b"#!/bin/sh\n",
            "etc/modules.d/drm-rockchip": b"rockchipdrm\n",
            "etc/modules.d/30-brcmfmac": b"brcmfmac feature_disable=0x282000\n",
            "usr/bin/fine3399-lcd": lcd,
            "usr/share/fine3399-lcd/status.rgb565": b"\0" * (160 * 80 * 2),
            "usr/share/fine3399-lcd/animation.rgb565": b"F339LCD1" + b"\0" * 32,
            "lib/firmware/brcm/brcmfmac43362-sdio.txt": b"boardtype=0x0598\n",
            "lib/firmware/rtl_nic/rtl8153b-2.fw": b"rtl8153b firmware\n",
            "usr/bin/frps": frps,
            "usr/bin/nginx-ui": nginx_ui,
            "etc/fine3399-nginx-ui-release.json": json.dumps(
                {
                    "binary_sha256": hashlib.sha256(nginx_ui).hexdigest(),
                    "tag": "v2.5.6",
                }
            ).encode(),
            "etc/init.d/nginx-ui": b"#!/bin/sh /etc/rc.common\n",
            "etc/config/nginx": b"config main 'global'\n",
            "etc/config/nginx-ui": b"config main 'main'\n",
            "etc/config/samba4": b"config samba\n",
            "etc/avahi/avahi-daemon.conf": b"[server]\nallow-interfaces=br-lan\n",
            "etc/nginx-ui/app.ini": b"[server]\nPort = 9000\n",
            "etc/nginx/nginx.conf": b"events {}\nhttp {}\n",
            "lib/upgrade/keep.d/nginx-ui": b"/etc/nginx/\n",
            "usr/share/luci/menu.d/zz-fine3399-docker.json": b"{}\n",
            "usr/share/luci/menu.d/fine3399-nginx-ui.json": b"{}\n",
            "www/luci-static/resources/view/fine3399/nginx-ui.js": b"return view.extend({});\n",
        }
        with tarfile.open(rootfs, "w:gz") as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return rootfs

    def make_bundle(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        dtb_data = b"fine3399-dtb"
        dtb_name = "dtb-rockchip-6.18.43-ophub.tar.gz"
        module = bytearray(64)
        module[:6] = b"\x7fELF\x02\x01"
        module[18:20] = (183).to_bytes(2, "little")
        module = bytes(module)
        module_name = "modules-6.18.43-ophub.tar.gz"
        module_path = "6.18.43-ophub/kernel/drivers/staging/fbtft/fb_fine3399_st7735s.ko"
        with tarfile.open(bundle / dtb_name, "w:gz") as archive:
            info = tarfile.TarInfo("dtb/rockchip/rk3399-fine3399.dtb")
            info.size = len(dtb_data)
            archive.addfile(info, io.BytesIO(dtb_data))
        with tarfile.open(bundle / module_name, "w:gz") as archive:
            info = tarfile.TarInfo(module_path)
            info.size = len(module)
            archive.addfile(info, io.BytesIO(module))
        manifest = {
            "schema": 3,
            "custom_dtb_sha256": hashlib.sha256(dtb_data).hexdigest(),
            "custom_module": {
                "path": module_path,
                "sha256": hashlib.sha256(module).hexdigest(),
            },
            "archives": {"dtb": dtb_name, "modules": module_name},
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        names = (dtb_name, module_name, "manifest.json")
        (bundle / "sha256sums").write_text(
            "".join(
                f"{hashlib.sha256((bundle / name).read_bytes()).hexdigest()}  {name}\n"
                for name in names
            ),
            encoding="utf-8",
        )
        return bundle

    def test_valid_rootfs_and_bundle_pass(self):
        verify_rootfs(self.make_rootfs())
        verify_bundle(self.make_bundle())

    def test_missing_required_package_is_rejected(self):
        packages = EXPECTED_PACKAGES - {"luci-app-openclash"}
        with self.assertRaisesRegex(VerificationError, "luci-app-openclash"):
            verify_rootfs(self.make_rootfs(packages))

    def test_modified_dtb_archive_is_rejected(self):
        bundle = self.make_bundle()
        dtb_archive = bundle / "dtb-rockchip-6.18.43-ophub.tar.gz"
        dtb_archive.write_bytes(dtb_archive.read_bytes() + b"modified")
        with self.assertRaisesRegex(VerificationError, "checksum mismatch"):
            verify_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
