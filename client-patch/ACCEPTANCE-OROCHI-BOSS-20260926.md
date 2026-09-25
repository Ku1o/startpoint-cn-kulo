# 八岐大蛇高难 V2 双端客户端交付验收

日期：2026-09-26。当前客户端成品使用最新 Android APK 与 corrected iOS IPA，登记状态为 `accepted_offline`。本记录覆盖离线结构、准入配对和 Boss 机制静态证据；未声称完成真机战斗测试。

## 当前成品

| 平台 | 文件 | SHA-256 | 准入号 | 状态 |
| --- | --- | --- | --- | --- |
| Android 1.8.1 | `F:\codex\outputs\orochi-boss-public-20260926\android\StarPoint-CN-1.8.1-author-1047-orochi-boss-public-20260926.apk` | `85dbc5728e3dd74fee0989638c77b4f10641ced6e3da3be856db3e5409afb4fc` | `android-181-author-1047-20260925` | `accepted_offline` |
| iOS 1.8.4 / 1.8.46 unsigned | `F:\codex\outputs\orochi-boss-public-20260926\ios\StarPoint-iOS-1.8.4-author-1047-orochi-boss-public-20260926-corrected-unsigned.ipa` | `f7c43c3b6ced56ba2cade636ac818cd7d7dc944aefe50573a05ec942ae6ffe4a` | `ios-184-author-1047-20260925` | `accepted_offline` |

两端公网地址均为 `http://175.178.160.158`。旧的 iOS 仅准入重打包候选不属于当前成品，未登记为 Boss 版本。

## 静态验证

- Android：`96699` 个方法体检查，APK 成员保持、zipalign、v1/v2 签名和准入号校验通过；未做真机测试。
- iOS：完整 ABC/AOT 方法数 `101433`，新增 AOT 入口 `46`，重定向原生入口 `59365`；`BossMechanicsRuntime` 的阶段、血量、弱点和联机同步标签已回读；未做真机测试。
- iOS 校验报告：`F:\codex\outputs\orochi-boss-public-20260926\ios\boss-ios-verification.json`。

## 准入与交付

准入名单只保留 Android `android-181-author-1047-20260925` 和 iOS `ios-184-author-1047-20260925`。旧准入 ID 已从私有配置和密钥文件中移除。云服整合包不包含 APK/IPA，客户端成品单独保留在本机交付目录。
