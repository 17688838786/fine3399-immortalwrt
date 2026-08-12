import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DTS_PATH = REPOSITORY_ROOT / "kernel" / "dts" / "rk3399-fine3399.dts"
LCD_INIT_PATH = REPOSITORY_ROOT / "files" / "etc" / "init.d" / "lcd_display"
LCD_PROGRAM_PATH = (
    REPOSITORY_ROOT / "src" / "fine3399-lcd.c"
)
LCD_BUILD_PATH = REPOSITORY_ROOT / "scripts" / "build-fine3399-dtb.sh"
DOCKER_MENU_PATH = (
    REPOSITORY_ROOT
    / "files"
    / "usr"
    / "share"
    / "luci"
    / "menu.d"
    / "zz-fine3399-docker.json"
)
NGINX_UI_INIT_PATH = REPOSITORY_ROOT / "files" / "etc" / "init.d" / "nginx-ui"
NGINX_UI_CONFIG_PATH = REPOSITORY_ROOT / "files" / "etc" / "nginx-ui" / "app.ini"
NGINX_CONFIG_PATH = REPOSITORY_ROOT / "files" / "etc" / "nginx" / "nginx.conf"
NGINX_UI_MENU_PATH = (
    REPOSITORY_ROOT
    / "files"
    / "usr"
    / "share"
    / "luci"
    / "menu.d"
    / "fine3399-nginx-ui.json"
)
NGINX_UI_VIEW_PATH = (
    REPOSITORY_ROOT
    / "files"
    / "www"
    / "luci-static"
    / "resources"
    / "view"
    / "fine3399"
    / "nginx-ui.js"
)
SAMBA_CONFIG_PATH = REPOSITORY_ROOT / "files" / "etc" / "config" / "samba4"
AVAHI_CONFIG_PATH = (
    REPOSITORY_ROOT / "files" / "etc" / "avahi" / "avahi-daemon.conf"
)


class BoardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dts = DTS_PATH.read_text(encoding="utf-8")

    def test_dts_identifies_fine3399_and_locked_origin(self):
        self.assertIn('model = "Fine3399";', self.dts)
        self.assertIn(
            'compatible = "rockchip,fine3399", "rockchip,rk3399";',
            self.dts,
        )
        self.assertIn("cb212f6d3ed5ea73d946f505dd42fac8ac954cbc", self.dts)
        self.assertTrue(self.dts.startswith("// SPDX-License-Identifier:"))

    def test_dts_enables_router_hardware_paths(self):
        for node in (
            "&gmac",
            "&sdio0",
            "brcmf: wifi@1",
            "&sdhci",
            "&usb_host0_ehci",
            "&usb_host1_ehci",
            "&usbdrd_dwc3_0",
            "&usbdrd_dwc3_1",
            "&spi2",
        ):
            with self.subTest(node=node):
                self.assertIn(node, self.dts)

    def test_st7735s_wiring_uses_the_offset_aware_module(self):
        panel_match = re.search(r"panel@0\s*\{(?P<body>.*?)\n\t\};", self.dts, re.S)
        self.assertIsNotNone(panel_match)
        panel = panel_match.group("body")
        for expected in (
            'status = "okay";',
            'compatible = "fine3399,st7735s"',
            "width = <80>;",
            "height = <160>;",
            "rotate = <90>;",
            "bgr;",
            "dc-gpios = <&gpio4 RK_PD5 GPIO_ACTIVE_HIGH>;",
            "reset-gpios = <&gpio4 RK_PD1 GPIO_ACTIVE_LOW>;",
            "led-gpios = <&gpio4 RK_PC2 GPIO_ACTIVE_LOW>;",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, panel)
        self.assertNotIn("spi-cpol;", panel)
        self.assertNotIn("spi-cpha;", panel)
        driver = (
            REPOSITORY_ROOT
            / "kernel"
            / "modules"
            / "fine3399-st7735s"
            / "fb_fine3399_st7735s.c"
        ).read_text(encoding="utf-8")
        self.assertIn("#define Y_OFFSET 24", driver)
        self.assertIn('FBTFT_REGISTER_DRIVER(DRVNAME, "fine3399,st7735s"', driver)

    def test_bcm43362_is_explicitly_loaded_before_wifi_detection(self):
        modules = (REPOSITORY_ROOT / "files" / "etc" / "modules.d" / "30-brcmfmac")
        baseline = (
            REPOSITORY_ROOT
            / "files"
            / "etc"
            / "uci-defaults"
            / "90-fine3399-baseline"
        ).read_text(encoding="utf-8")

        self.assertIn("brcmfmac", modules.read_text(encoding="utf-8"))
        self.assertIn("modprobe brcmfmac", baseline)
        self.assertIn("wifi config", baseline)
        self.assertIn("country=CN", baseline)
        self.assertIn("disabled=1", baseline)

    def test_lcd_service_selects_st7735_instead_of_hdmi_framebuffer(self):
        init_script = LCD_INIT_PATH.read_text(encoding="utf-8")
        program = LCD_PROGRAM_PATH.read_text(encoding="utf-8")

        self.assertIn("/sys/class/graphics/fb*/name", init_script)
        self.assertIn("*st7735*", init_script)
        self.assertIn("FINE3399_LCD_FB", init_script)
        self.assertIn("modprobe fb_fine3399_st7735s", init_script)
        self.assertIn('getenv("FINE3399_LCD_FB")', program)
        self.assertNotIn('open("/dev/fb0"', program)
        self.assertIn("/usr/bin/fine3399-lcd", init_script)
        self.assertNotIn("python", init_script)

    def test_lcd_rotates_concise_pages_and_loads_external_artwork(self):
        init_script = LCD_INIT_PATH.read_text(encoding="utf-8")
        program = LCD_PROGRAM_PATH.read_text(encoding="utf-8")
        config = (
            REPOSITORY_ROOT / "files" / "etc" / "config" / "lcd_display"
        ).read_text(encoding="utf-8")

        for page in ("render_network", "render_system", "render_services"):
            self.assertIn(page, program)
        for service in ("openclash", "ddns-go", "frps", "dockerd"):
            self.assertIn(service, program)
        self.assertIn('"CLASH"', program)
        self.assertIn("docker_icon", program)
        self.assertIn("startup.rgb565", program)
        self.assertIn("animation.rgb565", program)
        self.assertIn("status.rgb565", program)
        self.assertIn("option theme_dir '/mnt/mmcblk2p4/lcd'", config)
        self.assertIn('FINE3399_LCD_THEME_DIR="$theme_dir"', init_script)
        self.assertIn("option startup_seconds '6'", config)
        self.assertIn("option transition_seconds '0.6'", config)
        self.assertIn("option animation_every '3'", config)
        self.assertIn('FINE3399_LCD_STARTUP_SECONDS="$startup_seconds"', init_script)
        self.assertIn('FINE3399_LCD_TRANSITION_SECONDS="$transition_seconds"', init_script)
        self.assertIn('FINE3399_LCD_ANIMATION_EVERY="$animation_every"', init_script)
        self.assertIn('procd_add_reload_trigger "lcd_display"', init_script)

        built_in_theme = REPOSITORY_ROOT / "files" / "usr" / "share" / "fine3399-lcd"
        self.assertEqual((built_in_theme / "status.rgb565").stat().st_size, 160 * 80 * 2)
        animation = (built_in_theme / "animation.rgb565").read_bytes()
        self.assertEqual(animation[:8], b"F339LCD1")
        self.assertGreater(len(animation), 160 * 80 * 2)
        startup = (built_in_theme / "startup.rgb565").read_bytes()
        self.assertEqual(startup[:8], b"F339LCD1")
        self.assertGreater(len(startup), 160 * 80 * 2)
        self.assertIn("load_animation_file", program)
        self.assertIn("play_animation(framebuffer, &startup, startup_seconds)", program)
        self.assertIn("play_transition", program)

        packages = (
            REPOSITORY_ROOT / "configs" / "imagebuilder" / "packages.txt"
        ).read_text(encoding="utf-8")
        self.assertNotIn("python3", packages)
        self.assertNotIn("pillow", packages.lower())
        self.assertNotIn("dejavu-fonts", packages)

        build_script = (REPOSITORY_ROOT / "scripts" / "build-rootfs.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("src/fine3399-lcd.c", build_script)
        self.assertIn('overlay/usr/bin/fine3399-lcd', build_script)

    def test_lcd_module_rebuilds_ophub_host_tools_for_the_ci_architecture(self):
        build_script = LCD_BUILD_PATH.read_text(encoding="utf-8")

        self.assertIn("scripts/basic/fixdep.c", build_script)
        self.assertIn('scripts/mod/$source.host.o', build_script)
        self.assertIn('scripts/mod/modpost" $modpost_objects', build_script)

    def test_dockerman_menu_is_presented_as_docker(self):
        menu = DOCKER_MENU_PATH.read_text(encoding="utf-8")

        self.assertIn('"admin/docker"', menu)
        self.assertIn('"title": "Docker"', menu)
        self.assertIn('"type": "alias"', menu)
        self.assertIn('"path": "admin/services/dockerman"', menu)
        self.assertIn('"admin/services/dockerman"', menu)
        self.assertIn('"title": ""', menu)
        self.assertFalse(
            (
                REPOSITORY_ROOT
                / "files"
                / "etc"
                / "uci-defaults"
                / "92-fine3399-docker-menu"
            ).exists()
        )

    def test_nas_discovery_and_legacy_smb_stay_on_lan(self):
        samba = SAMBA_CONFIG_PATH.read_text(encoding="utf-8")
        avahi = AVAHI_CONFIG_PATH.read_text(encoding="utf-8")

        self.assertIn("option interface 'lan'", samba)
        self.assertIn("option allow_legacy_protocols '1'", samba)
        self.assertIn("option macos '1'", samba)
        self.assertNotIn("config sambashare", samba)
        self.assertIn("allow-interfaces=br-lan", avahi)
        self.assertIn("enable-reflector=no", avahi)

    def test_nginx_ui_is_native_persistent_and_luci_integrated(self):
        init_script = NGINX_UI_INIT_PATH.read_text(encoding="utf-8")
        app_config = NGINX_UI_CONFIG_PATH.read_text(encoding="utf-8")
        nginx_config = NGINX_CONFIG_PATH.read_text(encoding="utf-8")
        menu = NGINX_UI_MENU_PATH.read_text(encoding="utf-8")
        view = NGINX_UI_VIEW_PATH.read_text(encoding="utf-8")

        self.assertIn("/usr/bin/nginx-ui", init_script)
        self.assertIn("config_get CONFIG main config_path", init_script)
        self.assertIn('procd_add_reload_trigger "nginx-ui"', init_script)
        self.assertIn("configured storage is not mounted", init_script)
        self.assertIn('cp "$DEFAULT_CONFIG" "$CONFIG"', init_script)
        self.assertNotIn("/mnt/mmcblk2p4/nginx-ui", init_script)
        self.assertIn("Port = 9000", app_config)
        self.assertIn("StartCmd = /bin/login", app_config)
        self.assertIn("SbinPath = /usr/sbin/nginx", app_config)
        self.assertIn("user root;", nginx_config)
        self.assertIn("include /etc/nginx/sites-enabled/*;", nginx_config)
        self.assertIn("include /etc/nginx/streams-enabled/*;", nginx_config)
        self.assertNotIn("listen 80", nginx_config)
        self.assertNotIn("listen 443", nginx_config)
        self.assertIn('"admin/nginx-ui"', menu)
        self.assertIn("':9000/'", view)
        self.assertIn("iframe", view)

if __name__ == "__main__":
    unittest.main()
