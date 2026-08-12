.PHONY: test resolve fetch checkout rootfs dtb bundle package verify image clean

test:
	./scripts/test.sh

resolve:
	python3 tools/resolve_releases.py --config configs/releases.json --output build/resolved-releases.json $(if $(KERNEL_VERSION),--kernel-version $(KERNEL_VERSION),)

fetch: resolve
	python3 tools/fetch_artifacts.py --manifest build/resolved-releases.json --destination dl/releases

checkout:
	python3 tools/checkout_sources.py --lock versions.lock.json --destination build/sources

rootfs: fetch
	./scripts/build-rootfs.sh build/resolved-releases.json

dtb: fetch
	./scripts/build-fine3399-dtb.sh build/resolved-releases.json

bundle: dtb
	python3 tools/import_ophub_kernel.py \
		--kernel dl/releases/$$(python3 -c 'import json; print(json.load(open("build/resolved-releases.json"))["kernel"]["asset"]["name"])') \
		--dtb build/dtb-contract/arch/arm64/boot/dts/rockchip/rk3399-fine3399.dtb \
		--resolved build/resolved-releases.json \
		--output dist/kernel-bundle

package: checkout rootfs bundle
	sudo ./scripts/package-fine3399.sh build/resolved-releases.json

verify:
	python3 tools/verify_fast_artifacts.py \
		--rootfs dist/staging/immortalwrt-armsr-armv8-rootfs.tar.gz \
		--bundle dist/kernel-bundle \
		--image dist/staging/fine3399.img.gz

image: test package verify

clean:
	python3 -c "import pathlib,shutil; root=pathlib.Path.cwd().resolve(); [shutil.rmtree(p) for p in (root/'build',root/'dist') if p.is_dir() and root in p.resolve().parents]"
