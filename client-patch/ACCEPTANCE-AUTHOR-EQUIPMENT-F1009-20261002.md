# 作者装备规则 iOS F1009 修复验收记录

日期：2026-10-02。最终 unsigned IPA 已完成 iOS 实机验收，登记状态为 `user_accepted`。

## 成品身份

- IPA：`F:/codex/outputs/ios-equipment-f1009-fix-20261002/ios/StarPoint-iOS-1.8.4-author-equipment-standalone-20261002-unsigned.ipa`
- IPA SHA-256：`4ce93ffe967331b088032fa4d3e169c7d58b2c1cef4b10cf727e28906811bf40`
- 原生载体 SHA-256：`1a427b648fc62297effb0dbc9982611b7f0e6e9d0e0623d46cebdbe72872b1dc`
- 主 SWF SHA-256：`7e7e3642f19d59b3471bd6b09f344cf83b097924bc7a4bd094780deb7b793e72`
- 完整 ABC SHA-256：`83149cffbef675fb0661a3072725473e4c49817c645bc069516124dc094b1097`
- 包身份：`com.kulo.wf` / `1.8.4` / `1.8.46`
- 准入号：`ios-184-author-1047-public-20261001`
- 签名状态：unsigned，沿用现有设备安装流程

## 修复范围

- 修正进入副本时触发 F1009 的 AVM verifier 失败桩；装备 helper 通过 `AuthorState` 的 `getlex + callproperty` 调用，原角色作为显式首个参数传入。
- 保留进入副本、角色编成、角色点击和装备规则功能；不向原生 `BattleCharacterLogic` 追加实例 trait，原生实例/vtable 布局保持不变。
- AOT 方法表从 `101436` 扩展到 `101458`，新增 22 个入口；13 个既有方法保持 activation 布局，8 个装备 helper 和 1 个描述闭包进入追加区域。
- 未改变存档结构、持久化 ID、服务端资源链或 CDN；不需要存档迁移。

## 验收与边界

- 实机验收：通过；覆盖进入副本、角色编成及点选角色，未再出现 F1009 或闪退，装备功能保留。
- Codex 未直接操作验收设备；设备结果登记来源为最终成品确认。
- 离线验收报告：`F:/codex/outputs/ios-equipment-f1009-fix-20261002/ios/ios-verification-report.json`
- 编译告警复核：新增 helper/hook 方法无 `Verify error`；仅保留基线既有的 101312 告警。
- 云服未部署，本次不制作云服整合包；IPA、完整 ABC、准入密钥及临时构建物不进入 Git。
