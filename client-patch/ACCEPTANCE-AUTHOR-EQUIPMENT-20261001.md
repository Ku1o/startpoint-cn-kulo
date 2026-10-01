# 作者装备规则公网 iOS 验收记录（2026-10-01）

本记录登记作者装备规则移植到公网 iOS 后的最终 unsigned IPA。该成品接续已验收的 startup-download r2 iOS 载体，未替换 Android 成品，也未改变服务端资源链。

## 成品身份

- IPA：`F:/codex/outputs/author-equipment-ios-public-20261001/ios/StarPoint-iOS-1.8.4-author-equipment-public-20261001-unsigned.ipa`
- IPA SHA-256：`1ebe19e1d70dee51f1d6933d2c93cecca7380df4b5504cdf0019addb3e0fd850`
- 原生载体 SHA-256：`183636a9c9241f8cf085208c652daac1576cd212c75f7756f959fe0a32b26abf`
- 主 SWF SHA-256：`62c569f526e801ddf350140c78089049fd4b4c7f00cca0d1e7b28309f5ef228c`
- 完整 ABC SHA-256：`efc8e337f0bd74df73d847f1b8dc8e2533bd1d9181d6a6214627cc48298aad04`
- 包身份：`com.kulo.wf` / `1.8.4` / `1.8.46`
- 公网地址：`http://175.178.160.158`
- 新 iOS 准入号：`ios-184-author-1047-public-20261001`
- 旧 iOS 准入号未嵌入新 IPA；服务端配对仍保留旧安卓和旧 iOS 校验项。

## 变更范围

- 14 个既有装备规则方法，其中 13 个按相同 activation 布局替换，`resolvePathCollection` 使用安全重定向。
- 6 个 `BattleCharacterLogic` 辅助方法。
- 2 个闭包方法。
- AOT 方法表从 `101436` 扩展到 `101464`，新增 28 个入口。
- IPA 中仅 `worldflipper` 和 `worldflipper_ios_release.swf` 两个成员发生变化，包清单、Info.plist、版本身份和签名状态保持不变。
- 未改变存档结构、持久化 ID 或资源 CDN；不需要存档迁移。

## 验收结论

登记状态为 `accepted_offline`，用户已确认使用该成品；Codex 未进行实体 iOS 设备测试，IPA 保持 unsigned。原生载体、完整 ABC、AOT 方法表、公网地址、准入号替换和旧准入号排除均通过离线检查。

验收报告：`F:/codex/outputs/author-equipment-ios-public-20261001/ios-verification-report.json`

IPA、完整 ABC、密钥配对和编译临时文件不提交 Git，也未部署云服。源码端口入口：`client-patch/author-merge-20261001/ios/prepare_ios.py`。
