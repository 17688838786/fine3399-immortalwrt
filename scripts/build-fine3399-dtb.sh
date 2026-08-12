#!/usr/bin/env sh
set -eu

[ "$(id -u)" -ne 0 ] || { echo "Do not build the DTB as root." >&2; exit 2; }
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
manifest=${1:-build/resolved-releases.json}
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["kernel"]["asset"]["name"].removesuffix(".tar.gz"))' "$manifest")
case "$version" in
	6.12.*) ;;
	*) echo "Unsupported DTB kernel version: $version" >&2; exit 2 ;;
esac

archive="dl/linux-${version}.tar.xz"
url="https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-${version}.tar.xz"
mkdir -p dl build
if [ ! -s "$archive" ]; then
	curl -fL --retry 4 --retry-delay 3 -o "${archive}.part" "$url"
	mv "${archive}.part" "$archive"
fi
source_sha256=$(sha256sum "$archive" | awk '{print $1}')
python3 - "$manifest" "$url" "$source_sha256" <<'PY'
import json, sys
path, url, digest = sys.argv[1:]
data = json.load(open(path, encoding="utf-8"))
data["kernel"]["linux_source"] = {"url": url, "sha256": digest}
open(path, "w", encoding="utf-8").write(json.dumps(data, indent=2, sort_keys=True) + "\n")
PY

tree=build/dtb-contract
if [ -e "$tree" ]; then
	[ -f "$tree/.fine3399-dtb-tree" ] || { echo "Refusing to replace unmarked $tree" >&2; exit 2; }
	rm -rf "$tree"
fi
mkdir -p "$tree"
tar -xJf "$archive" --strip-components=1 -C "$tree"
touch "$tree/.fine3399-dtb-tree"
cp kernel/dts/rk3399-fine3399.dts "$tree/arch/arm64/boot/dts/rockchip/"
make -C "$tree" ARCH=arm64 defconfig
make -C "$tree" -j"$(nproc)" ARCH=arm64 rockchip/rk3399-fine3399.dtb
test -s "$tree/arch/arm64/boot/dts/rockchip/rk3399-fine3399.dtb"

kernel_asset="dl/releases/${version}.tar.gz"
headers=build/ophub-headers
python3 tools/extract_ophub_headers.py --kernel "$kernel_asset" --output "$headers"

# ophub builds and packages these host utilities on arm64. GitHub Actions
# runs on x86_64, so rebuild only the two helpers required by an external
# module instead of executing the packaged arm64 binaries.
host_cc=${HOSTCC:-cc}
"$host_cc" -Wall -Wmissing-prototypes -Wstrict-prototypes -O2 \
	-fomit-frame-pointer -std=gnu11 -I"$headers/scripts/include" \
	-o "$headers/scripts/basic/fixdep" "$headers/scripts/basic/fixdep.c"
modpost_objects=""
for source in modpost file2alias sumversion symsearch; do
	object="$headers/scripts/mod/$source.host.o"
	"$host_cc" -Wall -Wmissing-prototypes -Wstrict-prototypes -O2 \
		-fomit-frame-pointer -std=gnu11 -I"$headers/scripts/include" \
		-I"$headers/scripts/mod" -c \
		-o "$object" "$headers/scripts/mod/$source.c"
	modpost_objects="$modpost_objects $object"
done
# The object list is generated above from fixed repository-owned names.
# shellcheck disable=SC2086
"$host_cc" -o "$headers/scripts/mod/modpost" $modpost_objects

module_tree=build/fine3399-st7735s-module
module_marker=build/.fine3399-st7735s-module
if [ -e "$module_tree" ]; then
	[ -f "$module_marker" ] || { echo "Refusing to replace unmarked $module_tree" >&2; exit 2; }
	rm -rf "$module_tree"
fi
mkdir -p "$module_tree"
cp kernel/modules/fine3399-st7735s/Makefile "$module_tree/"
cp kernel/modules/fine3399-st7735s/fb_fine3399_st7735s.c "$module_tree/"
cp "$tree/drivers/staging/fbtft/fbtft.h" "$module_tree/"
touch "$module_marker"
make -C "$headers" -j"$(nproc)" \
	ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CC=aarch64-linux-gnu-gcc-14 \
	M="$repo_dir/$module_tree" modules
test -s "$module_tree/fb_fine3399_st7735s.ko"
test "$(modinfo -F name "$module_tree/fb_fine3399_st7735s.ko")" = "fb_fine3399_st7735s"
case "$(modinfo -F vermagic "$module_tree/fb_fine3399_st7735s.ko")" in
	"${version}-ophub "*) ;;
	*) echo "Custom LCD module vermagic does not match ${version}-ophub" >&2; exit 2 ;;
esac
test "$(modinfo -F depends "$module_tree/fb_fine3399_st7735s.ko")" = "fbtft"
