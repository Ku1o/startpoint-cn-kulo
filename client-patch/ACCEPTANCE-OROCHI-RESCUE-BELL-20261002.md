# 救援铃铛“超级+”内网客户端验收

## 范围

- 平台：Android APK，内网环境
- 地址：`http://<LAN_HOST>:8001`
- 仅验收紧凑居中的“超级+”窄难度条排版
- 本批不制作公网 APK，也不制作公网 IPA

## 成品身份

- APK：`F:\codex\outputs\orochi-rescue-bell-client-20261002-layout-compact\StarPoint-CN-1.8.1-orochi-rescue-bell-superplus-layout-compact-lan-20261002-08f205a0.apk`
- APK SHA-256：`8ab2533469bb88d1292db9c2406b7ff696cb1d1064c027bd83b4985f5e19dcc1`
- 内嵌 SWF SHA-256：`457d148d55f8cf6b85d8d144e14a12ab12feff1e5561018a9de1fa08c05fc836`
- AIR `uniqueappversionid`：`08f205a0-4fdc-4faf-9201-16aade2e174f`
- 签名证书 SHA-256：`569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894`

## 内置资源

- 资源来源：APK 内置 bundle；本批未使用 CDN 增量
- 目标成员：`production/android_bundle/dc/bcccb129122c0189c8eab004ecc4516a077f3e`
- 紧凑排版 payload SHA-256：`f9cba755d3c5d63f334989fd0a0a21b7f169f0fbede9e77e3178f4efa5568125`
- payload 大小：480 字节
- bundle SHA-1 标记：`8c1ac688d7d83d58e27e41c640ef2f46655c74de`

## 验收状态

静态构建检查通过：APK ZIP、V1/V2 签名和 zipalign 均通过，bundle 标记与实际 bundle 一致。用户已在内网设备完成实机验收；Codex 未连接设备。公网 Android 和 iOS 继续保留为后续工作，不作为本次成品范围。
