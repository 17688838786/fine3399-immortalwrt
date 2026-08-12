#!/usr/bin/env sh
set -eu

[ "$(id -u)" -ne 0 ] || { echo "Do not build the DTB as root." >&2; exit 2; }
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_tree=${1:?usage: check-fine3399-dtb.sh IMMORTALWRT_SOURCE_TREE}
details="$source_tree/target/linux/generic/kernel-6.12"
[ -f "$details" ] || { echo "Missing locked 6.12 kernel details: $details" >&2; exit 2; }
version=$(sed -n 's/^LINUX_VERSION-6\.12 = //p' "$details")
expected=$(sed -n 's/^LINUX_KERNEL_HASH-6\.12\.[0-9][0-9]* = //p' "$details")
[ -n "$version" ] && [ -n "$expected" ] || { echo "Invalid 6.12 kernel details." >&2; exit 2; }

cd "$repo_dir"
mkdir -p dl build
archive="dl/linux-6.12${version}.tar.xz"
if [ ! -f "$archive" ]; then
    wget -O "$archive.tmp" "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12${version}.tar.xz"
    mv "$archive.tmp" "$archive"
fi
echo "$expected  $archive" | sha256sum -c -
work=build/dtb-contract
rm -rf "$work"
mkdir -p "$work"
tar -xJf "$archive" --strip-components=1 -C "$work"
cp kernel/dts/rk3399-fine3399.dts "$work/arch/arm64/boot/dts/rockchip/"
make -C "$work" ARCH=arm64 defconfig
make -C "$work" -j"$(nproc)" ARCH=arm64 rockchip/rk3399-fine3399.dtb
test -s "$work/arch/arm64/boot/dts/rockchip/rk3399-fine3399.dtb"
