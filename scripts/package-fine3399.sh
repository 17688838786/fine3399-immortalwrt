#!/usr/bin/env sh
set -eu

[ "$(id -u)" -eq 0 ] || { echo "ophub packaging requires root." >&2; exit 2; }
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"
manifest=${1:-build/resolved-releases.json}
[ -s "$manifest" ] || { echo "Missing resolved release manifest." >&2; exit 2; }
[ -s dist/staging/immortalwrt-armsr-armv8-rootfs.tar.gz ] || { echo "Missing ImageBuilder rootfs." >&2; exit 2; }
[ -s dist/kernel-bundle/manifest.json ] || { echo "Missing checked kernel bundle." >&2; exit 2; }

python3 tools/prepare_ophub.py --source build/sources/ophub --tree build/ophub
mkdir -p build/ophub/openwrt-armsr dist/staging
cp dist/staging/immortalwrt-armsr-armv8-rootfs.tar.gz build/ophub/openwrt-armsr/
kernel_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["kernel"]["asset"]["name"].removesuffix(".tar.gz"))' "$manifest")
(
	cd build/ophub
	FINE3399_KERNEL_BUNDLE="$repo_dir/dist/kernel-bundle" ./remake \
		-b fine3399 -a false -k "$kernel_version" -s 512/2048 -n Fine3399-ImmortalWrt
)
set -- build/ophub/openwrt/out/*.img.gz
[ "$#" -eq 1 ] && [ -s "$1" ] || { echo "Expected exactly one packaged Fine3399 image." >&2; exit 2; }
cp "$1" dist/staging/fine3399.img.gz

release_tmp=dist/release.tmp
rm -rf "$release_tmp"
mkdir -p "$release_tmp"
release_version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["immortalwrt"]["version"])' "$manifest")
kernel_release=$(python3 -c 'import json; print(json.load(open("dist/kernel-bundle/manifest.json"))["kernel_release"])')
image_name="fine3399-immortalwrt-${release_version}-${kernel_release}.img.gz"
cp dist/staging/fine3399.img.gz "$release_tmp/$image_name"
cp "$manifest" "$release_tmp/build-manifest.json"
cp dist/kernel-bundle/manifest.json "$release_tmp/kernel-bundle-manifest.json"
(
	cd "$release_tmp"
	sha256sum "$image_name" \
		build-manifest.json kernel-bundle-manifest.json >SHA256SUMS
)
rm -rf dist/release
mv "$release_tmp" dist/release
