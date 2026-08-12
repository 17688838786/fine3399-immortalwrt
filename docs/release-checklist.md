# 发布检查表

- GitHub Actions 的 test 与 build 均为绿色；
- 下载 artifact 并校验 `SHA256SUMS`；其中不再包含仅供构建使用的 rootfs；
- 检查 `build-manifest.json` 中 ImmortalWrt、OpenClash、Argon 和内核版本；
- 写盘前保留当前可启动固件和配置备份；
- 按 [硬件验收](hardware-smoke-test.md) 完成 LAN/WAN、PPPoE、LCD、存储与服务测试；
- 只有硬件验收完成后再创建正式 `v*` 标签；标签构建会自动创建 GitHub Release，
  镜像、manifest 和校验和可作为独立 assets 下载。
