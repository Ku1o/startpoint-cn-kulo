# Android 内容运营与主城主题 R11 内网基线登记

2026-10-24 将已保留的最终 R11 APK 登记为 Android 后续开发默认输入，层级为 `accepted_offline`。该层级允许继续制作，证据覆盖离线成品身份、累计改动保全和受控原生执行，不表示新增完整设备、实际资源下载或公网验收。

## 精确身份

| 项目 | 登记值 |
| --- | --- |
| APK | `F:/codex/outputs/server-time-july-ops-20261021/isolated-r11/StarPoint-CN-1.8.1-主城外观管理-isolated-lan-r11-20261023.apk` |
| 字节数 | 214212284 |
| APK SHA-256 | `e9b9bbd8a0557a4cfaf6534b0e952caf20d142f5e6702fb2d35a0977f9a871b8` |
| 内嵌 SWF SHA-256 | `9c672e56e5911679848047daece874e139255b2d128f67ab11e605c5db2bb951` |
| DEX SHA-256 | `5859dccb9af162a760874db0d523c222d632cef3146f750242bd4570dec2cd18` |
| AIR / DEX 缓存 UUID | `2345e786-411e-4f03-870e-8f3100737da9` |
| 包名 / 版本 | `com.leiting.wf` / `1.8.1` / `1008001` |
| 架构 | `arm64-v8a`、`x86_64`，各 15 个原生库 |
| 内网地址 | `http://<LAN_HOST>:18001`；原地址摘要保存在登记中 |
| 沿用准入 ID | `android-181-author-1047-public-20261001`；编号中的 public 是原编号的一部分，本包实际指向内网 |
| 证书 SHA-256 | `569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894` |

SWF 有 305 个 DoABC，主 `boot_ffc6` 的零基 ordinal 为 304、原始 tag index 为 367；主 ABC 有 92601 个方法体，全容器共有 96836 个方法体。

## 累计范围

- 原生页面读取管理员控制的活动和卡池状态，重新登录后应用；接入真实服务器时间及重新登录通知。
- 历史活动、通行证及奖励箱入口沿用原生页面。只在原有时间字段中显示常驻或结束时间，保留日/周任务等独立计时；包含通行证文字位置修复。
- 修复兑换与浏览错误使用活动原时间的问题，星之碎片列表读取服务端保留的商品范围；账号专属资格不由客户端伪造。
- 个人资料“一览”常驻，兼容旧存档缺少完成日期的显示。每日任务、救援计次、关卡次数等服务端规则不由本 APK 登记替代。
- 完整登录响应捕获主城外观设置，原生主题选择器在下次进入时读取；无效或缺少设置时回退原算法。保留玩家自选音乐优先、主题默认音乐其次，未清空或批量改写自选音乐。

累计源码已在提交 `6283a9229cad4bdce7537d99e7290d92d5856845` 中保存。入口为 [内容运营实现](content-operations/README.md)与[主城主题实现](town-theme/README.md)。这些固定历史配方说明每一步的输入与差异；后续开发直接从本次登记的最终 R11 接续，避免重复套补丁或遗漏累计修复。

## 验证与保留证据

本次回读实际 APK、内嵌 SWF、DEX、Manifest UUID、包大小及 ABC 结构数量；与未变成品对应的原封包证据复用：原证书 V1/V2、zipalign、CRC、6125 个非目标成员保留、70 个既有网络常量及准入 DoABC 字节保留。

R11 相对 R10 仅接入两个原生方法体和独立 `town_theme_login` helper。原 85 个运营 helper 方法、7 个个人资料 helper 方法和此前 7 个原生资料补丁保持。原受控 AIR 回执包含主城 122 项断言和资料回归 153 项断言；夹具未覆盖完整 GPU、实际资源下载及全游戏操作，不能外推为完整设备验收。

原始构建报告保持生成时状态，不将其中 `deviceTested=false`、`acceptedRegistryChanged=false` 等历史事实改写成后续登记结果。本地原封包证据为 APK 同目录 `verification.json`，功能证据位于 `work/server-time-july-ops-20261021/continuation/town-theme-admin-20261023/`；本次登记回读位于同一工程 `continuation/android-r11-baseline-20261024/`。

```powershell
python -B client-patch/verify_android_baseline.py --variant lan
```

## 公网与 iOS 边界

[android-accepted.json](android-accepted.json) 的默认入口改为 `variants.lan`。现存 `variants.public` 的身份、日期及原验收层级完整保留，但它没有本批 R11 累计改动；未来同功能公网 APK 应直接从 R11 转换。现有 iOS 登记保持原样，本批功能尚未移植到 iOS。

本次未重新打包或签名、未变更准入材料或服务器允许名单、未安装设备、未更改玩家数据或服务运行状态。源码提交、推送、制作公网包与部署分别按后续明确范围执行。
