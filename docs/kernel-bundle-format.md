# Kernel bundle format

`dist/kernel-bundle/` uses manifest schema 2 and contains the three archives from one
resolved ophub kernel Release:

- `boot-<release>.tar.gz`;
- `modules-<release>.tar.gz`;
- `dtb-rockchip-<release>.tar.gz`, with only `rk3399-fine3399.dtb` replaced by the
  display-enabled DTB compiled by this repository;
- `manifest.json` and `sha256sums`.

The importer rejects unsafe archive paths, verifies the downloaded asset digest when
GitHub publishes one, checks routing/container/display modules, and records the custom
DTB digest. The patched ophub packager refuses network kernel fallback whenever
`FINE3399_KERNEL_BUNDLE` is set.
