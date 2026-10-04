# 救援铃铛 C8016 v3 与 10 分钟缓存清理公网 Android 验收记录

日期：2026-10-04。平台：Android APK。地址：`http://124.222.203.221:8001`。
登记状态：`accepted_offline`（离线身份与血缘校验）。

## 成品身份

- APK：`F:/codex/outputs/starpoint-public-migration-20261004/StarPoint-CN-1.8.1-orochi-rescue-bell-c8016-cache-10m-public-20261004-92f713a5.apk`
- APK SHA-256：`cd840c201cf6436e38b2e92ebe0dad4d66b9bce8eff04a2418e123648b77c508`，170,060,995 字节
- 内嵌 SWF SHA-256：`59802822cd25336e8478ca82a57c3c9d4c225f7f026f0ba805fa39db8a20376d`
- `classes.dex` SHA-256：`3b9757ff2bc5fe55d9e4d5efb4938f6a329b046781fb890d7b88d869506f487e`
- AIR `uniqueappversionid`：`92f713a5-7de2-44b3-8357-56082e4f8a04`（内网前值 `4728fb03-…`）
- 准入号：`android-181-author-1047-public-20261001`（沿用内网版配对，未推进新号）
- 签名证书 SHA-256：`569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894`
- 包名 / 版本：`com.leiting.wf` / 1.8.1 / 1008001

## 输入与转换范围

- 直接输入：2026-10-02 用户内网实机验收的救援铃铛内网版
  `4f62b899a89b0648f79d0dbaf20d8aab9b64ad91959d91706dc71af02cb6c335`
  （`user_accepted`，内网地址 `<LAN_HOST>:8001`）。
- 转换只包含三项：地址替换 `<LAN_HOST>:8001` → `124.222.203.221:8001`（主 SWF 内 3 个 ABC tag、
  9 处字符串）、新的 AIR `uniqueappversionid`、固定证书重签。
- 游戏方法体 96,706 个保持不变；超级+ 内置紧凑排版 payload
  `f9cba755d3c5d63f334989fd0a0a21b7f169f0fbede9e77e3178f4efa5568125`、C8016 v3 helper、
  10 分钟缓存清理、主 ABC 索引 361、包名/版本与准入配对均沿用内网版。

## 静态校验

- 独立回读记录：`F:/codex/outputs/starpoint-public-migration-20261004/android-public-verification.json`
  （`status=verified`，无失败项）。
- 成员：4,178 个；仅 `AndroidManifest.xml`、`classes.dex`、`assets/worldflipper_android_release.swf`
  与三个签名成员变化，其余 4,172 个逐字节一致。
- 主 SWF：仅 3 个 ABC tag 的地址字符串变化且替换后可回环；解压后 9 处 `124.222.203.221:8001`，
  无 LAN 地址、无旧公网地址；方法体 96,706。
- DEX：只改 `cn.startpoint.BuildIdentity` 与 `cn.startpoint.StartupCache` 两个身份类，类清单一致，
  引用新的 AIR UUID；Manifest 内 UUID 唯一且等于登记值。
- ZIP 对齐、V1/V2 签名与固定证书指纹通过。

## 验收状态与边界

- 登记为 `accepted_offline`：验收范围为离线身份、转换范围与血缘校验；Codex 未进行实体设备测试。
- 内容验收继承 2026-10-02 的内网版 `user_accepted`；公网版本身尚未单独真机验收。若需要把公网版
  记为 `user_accepted`，需在实际公网环境完成登录与进副本等设备确认后按实际证据更新。
- 本批未改 CDN、服务端、准入配置与存档结构；未制作云服整合包、未部署。
