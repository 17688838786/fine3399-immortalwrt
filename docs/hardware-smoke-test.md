# Fine3399 硬件验收

1. 从可移除介质启动，确认串口、LuCI `192.168.1.1` 和 SSH 可达。
2. 确认两个网口名称/MAC，先保持一个 LAN，再设置另一个为 PPPoE WAN。
3. PPPoE 连通后测速并检查 nftables、IPv6 和千兆链路。
4. `iw reg get` 显示 `country CN`，板载 Wi-Fi 可扫描；主无线仍交给独立 AP。
5. `lsmod`/`modinfo` 检查 tun、nft_fullcone、nft_tproxy、veth、br_netfilter、brcmfmac 和 rockchipdrm。
6. ST7735S 亮屏，`/dev/fb0` 存在，LCD 显示 IP、温度和流量。
7. 确认 ophub 已创建并挂载 p3、p4，Docker 的 `data_root` 指向预期的 p4 或 NVMe。
8. 在 LuCI 中逐项配置并启动 OpenClash、DDNS-Go、FRPS、Samba/SFTP、Docker；
   验证 FRPS 端口范围和防火墙规则仅按实际需求开放。
9. 备份 `/etc/config`、OpenClash 配置和服务密钥，再考虑写入 eMMC。
