# Android / iOS 本地记录恢复版验收

2026-09-16，以下两个公网成品登记为 `user_accepted`。验收范围为对应完整发布包；未登记逐功能、逐设备测试明细。既有构建报告保留生成时的状态，不能将登记日期当作重新构建或重新测试日期。

| 平台 | 当前成品 | SHA-256 | 准入号 |
| --- | --- | --- | --- |
| Android | `outputs/r10-public-reopen-fix-20260915/StarPoint-CN-1.8.1-r10-public-reopen-fix-20260915.apk` | `3c365e51762ad115366731fa1fa2bd1ffbdac54cbce4c3e2626010deffc91fd2` | `android-181-r10-20260915` |
| iOS | `outputs/ios-admission-public-reopen-fix-20260915/StarPoint-iOS-1.8.4-admission-public-reopen-fix-20260915-unsigned.ipa` | `90d6757bc45c8562926f7ea53b0455c219b9867bf91cbab4314237cab4ffb3f6` | `ios-184-admission-20260915` |

Android 保留 R8 能力计算、R9 队伍派生缓存与回调修复、R10 完整队伍键和分批预计算、准入及此前累计功能，追加空账号读取恢复和账号/设备文件安全写入。主 ABC 索引 296，共 96,635 个方法体。iOS 保留自身累计功能和准入，仅修复两个账号方法并增加四个写入辅助方法，完整 AOT 共 101,287 个方法；设备存储仍使用原 Application 扩展，没有移植 Android 性能改造。两端均无诊断日志导出入口。

Android 配套内网修复包 `outputs/r10-admission-lan-reopen-fix-20260915/StarPoint-CN-1.8.1-r10-admission-lan-reopen-fix-20260915.apk` 单独登记为 `accepted_offline`，SHA-256 为 `229ccd907f3a9909764032abf7e046e5688573206dc35d2bbc9cb8f67cd44ca9`。其既有验证覆盖本地文件系统与启动恢复，不扩大为本次公网包的逐功能验收。

## 身份与验证边界

- 登记检查回读 APK/SWF/DEX/AIR UUID、IPA 原生程序/SWF/包身份，以及完整 iOS ABC 与原生 AOT 的 SHA-1、SHA-256 和方法数。
- 既有 Android 证据包括 8 项 AIR 文件系统用例、空账号冷启动与模拟器重启；公网/内网修复方法和辅助类对应一致。
- 既有 iOS 证据包括离线成品核验、原生布局/重定位/签名边界与 10 项回归。没有补充自动化真机测试。
- 验收不构成五重共斗长时间变慢问题已解决的结论。
- 本次只更新验收登记与检查入口，不改变安装包、校验号、准入密钥、服务器配置、账号归属或存档格式。云服部署状态独立管理。

后续从 `android-accepted.json`、`ios-accepted.json` 指定的精确成品继续。旧商店登记可从 Git 修订 `20a416027089686f1ec0b03f3a0f778154f3fb30` 的同名注册表读取；旧产物和历史报告保留，不能替代当前输入。

实现见 [Android 本地记录恢复](local-record-recovery/README.md) 和 [iOS 本地记录恢复](ios-local-record-recovery/README.md)。
