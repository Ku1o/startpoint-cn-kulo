# 救援铃铛 iOS 静态槽修复与新公网迁移验收记录

日期：2026-10-04。平台：iOS unsigned IPA（TrollStore 安装流程）。地址：`http://124.222.203.221`。
登记状态：`accepted_offline`（离线身份与血缘校验；用户已批准该版本作为后续基线）。

## 成品身份

- IPA：`F:/codex/outputs/orochi-rescue-bell-ios-fix-20261004/public-migration/StarPoint-iOS-1.8.4-orochi-rescue-bell-cache-10m-fix-public-124.222.203.221-20261004-unsigned.ipa`
- IPA SHA-256：`66b1057cc7cd9e66da7a38aa9e4963d7effe2220f0889a9fcff4cfa1eeac77e0`，167,038,327 字节
- 原生可执行文件 SHA-256：`bde4cb2273d9b2f7df4aa06c3b3152edd32be56586974b8bb696767df97e176a`
- 主 SWF SHA-256：`1d986e575b5948865a1b1eb733bee964207f71c9fe881bcff2be0204d089d3ea`
- 完整 ABC：`F:/codex/outputs/orochi-rescue-bell-ios-fix-20261004/public-migration/ios-full-fix-public-124.222.203.221.abc`
  （SHA-256 `a3a7e2b465f14472164a2b7cb61fcdd7b57c3987cb76bf2e8cfa095620270ab8`，SHA-1
  `42b71efd1b0fb201485b093dbb1c94e08ebfedbd`，101,466 方法）
- 包身份 / 签名：`com.kulo.wf` / 1.8.4 / 1.8.46；unsigned
- 准入号：`ios-184-author-1047-public-20261001`（沿用原配对，未推进新号）

## 范围

本成品在 2026-10-02 用户验收载体 `4ce93ffe…` 上包含三部分内容：

1. 救援铃铛内置排版：超级+ 紧凑居中 payload（480 字节
   `f9cba755d3c5d63f334989fd0a0a21b7f169f0fbede9e77e3178f4efa5568125`，与 Android 内网同一逻辑资源）。
2. iOS 等效 10 分钟缓存清理：`cn.mod::CacheCleanupState` 承载 `periodicStarted`/`periodicTimer` 与 5 个静态方法，
   每 600,000 毫秒仅删除 `File.cacheDirectory/app` 与 `File.cacheDirectory/.AIR`，失败容错并写有界诊断
   `sp-cache-periodic.diag`；启动钩子位于 `GlobalLoading/applyLoad` 原生入口包装器，桥接方法 101460。
3. F1009 静态槽修复：状态字段不落在既有类上，`cn.mod::AuthorState` 的 class/instance trait 与载体逐字节一致，
   四个既有访问器（101323–101326）继续使用 `0x30/0x30/0x38/0x38` 槽偏移；详见
   [类静态槽 F1009 记录](./IOS-STATIC-SLOT-F1009-20261004.md)。

之后按新公网规则迁移：`http://175.178.160.158` → `http://124.222.203.221`（native 354 处、完整 ABC 17 处，
长度不变），重算 AOT 摘要并同步主 SWF 摘要槽；转换只改原生可执行文件与主 SWF，游戏内容、准入配对、
包名/版本与签名布局不变。

## 静态校验

- 修复包（迁移前）：`F:/codex/outputs/orochi-rescue-bell-ios-fix-20261004/ios-verification-report.json`
  （`status=verified`，无失败项）：`authorstate_untouched`、`accessor_slot_guard_matches`
  （冻结与重编译均为 `0x30/0x30/0x38/0x38`）、新类槽与方法名、101,466 方法、旧方法与旧方法体不变、
  仅 3 个成员变化、签名布局保持。
- 公网迁移包：`F:/codex/outputs/orochi-rescue-bell-ios-fix-20261004/public-migration/ios-public-verification.json`
  （`status=verified`，无失败项）：仅原生可执行文件与主 SWF 变化、全包无旧地址、354 处替换点全部落到新地址、
  构造器 origin 解析为 `http://124.222.203.221`、AOT 摘要等于新完整 ABC 的 SHA-1、SWF 仅摘要槽变化、
  签名布局与输入一致。
- 身份回读：`python client-patch/verify_ios_baseline.py` 通过（IPA/原生/SWF/完整 ABC/AOT 摘要/包身份）。

## 验收状态与边界

- 登记为 `accepted_offline`，并记录该版本已获批准作为后续基线；Codex 未进行实体设备测试。
- 内容范围与 2026-10-02 载体及救援铃铛批次一致；本记录不把离线校验写成真机验收。
- 本批未改 CDN、服务端、准入配置与存档结构；未部署云服、未制作覆盖包。
