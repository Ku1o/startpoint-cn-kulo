# iOS 深渊装备 Multi / BothBoss 与 120 级门控

本目录保存 iOS 1.8.4 累计客户端的深渊装备门控补丁方法。它把 Android 已验收的
`BattleCharacterLogic.getAvailableAbilities(...)` 规则移植到 iOS AOT 客户端，同时保留
输入 IPA 中已经存在的 Rush 排行榜 v3 入口和 `MemberView.draw` v6 绘制保护。

2026-09-07，用户已在 iOS 真机验收下述精确目标负载。验收只适用于本页登记的输入、
输出哈希和 Mach-O UUID；重新编译、重新封装或修改任意字节后都必须重新回归。

## 已验收血统

输入是当时最新的 iOS 累计未签名 IPA，已经包含私服与免登录、数据继承、幻想连战、
幻想魂珠异步纹理、`MemberView.draw` v6 和 Rush 排行榜 v3 entry hook：

- 输入文件：`iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-entryhook-test-unsigned.ipa`
- 输入 IPA SHA-256：`A6FCF29F4E0DADA2967D0A50E4DA131473BD1F6CA76E11621BB3F3EB3B8D26B4`
- 输入 Mach-O SHA-256：`9E6B567F2461C29FD5624AE5DEFFDFD3438876DF71C7C203202400B6342FC84D`

本目录是这个累计输入之上的增量构建步骤，不重新生成 Rush 排行榜 v3；输入哈希不匹配时会直接
失败，不能改用较早且不含排行榜的 `MemberView.draw` v6 IPA。

已验收目标：

- 输出文件：`iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-abyss-multibothboss-level120-test-unsigned.ipa`
- 输出 IPA SHA-256：`4D54590D445E6AAD0F189C6BB21AC896D634CDBB2E0E51C7A856317DC3EF694C`
- 输出 Mach-O SHA-256：`7758FD717CB4E38C5EB347677714A03EEC55D92307E2E51838335CD7377E76B3`
- Mach-O UUID：`064F8E49-FDD9-532F-8445-439AB9F71E6C`
- Bundle ID：`com.kulo.wf`
- 版本 / 构建号：`1.8.4` / `1.8.46`
- IPA 成员数：`3568`

输入与输出成员名称及顺序完全一致。唯一变化的 IPA 成员是
`Payload/worldflipper.app/worldflipper`；`Info.plist` 和
`worldflipper_ios_release.swf` 保持逐字节一致。

## 门控规则

补丁只接管能力 ID `8000101..8000115`。非目标能力继续返回官方结果；目标能力允许的任务
条件如下：

| group index | inner index | 允许条件 |
| --- | --- | --- |
| `0` | `8` | `quest_id == 2001` |
| `0` | `10` | `1 <= quest_id <= 97` |
| `0` | `17` | `quest_id / 1000 == 700099` |
| `1` | `4` | `1099001 <= quest_id <= 1099003`（Multi / BothBoss） |

当目标能力由直接装备对象 `EquipmentAbilityLogic` 提供，并且当前任务没有命中上述白名单时，
仅在 `enhancementAbility.index == 0` 且强化对象的 `currentLevel >= 120` 时放行；随后把候选对象
替换为该装备的 `abilitySoulAbility`，与 Android 已验收逻辑保持一致。强化等级 `119` 及以下
不适用这个例外。能力魂珠对象也不会借用装备等级例外。

本补丁不修改 `getAvailableAbilitiesWithCond(...)`，也不增加或改变五重决战 Auto 锁规则。

## 原生实现与保留项

[构建器](./build_ios_abyss_multibothboss_level120.py) 会锁定输入 IPA、Mach-O、UUID、原有门控
跳转和 helper 容量，再替换现有深渊门控 helper。新的 ARM64 helper 位于 Mach-O 文件偏移
`0x3D69660`，大小为 `548` 字节，距容量末端 `0x3D69974` 仍有 `240` 字节；原有
`0x49572FC` 门控 hook 保持不变。

对应的 AOT 方法是 `BattleCharacterLogic.getAvailableAbilities`，method ID 为 `18484`。本步骤不改
该方法的 method table entry，只更新既有 hook 所调用的 helper。

构建器同时验证规则真值表，并要求下列累计功能对应的代码区间逐字节保留：

- Rush 排行榜 v3 entry hook；
- `MemberView.draw` v6 的已验证类型门控；
- 幻想魂珠异步纹理加载；
- 赛瑞斯双形态与湿润目标雷伤逻辑；
- 通用逐角色像素渲染缩放；
- 标题及游戏内数据继承入口。

## 构建与验收边界

使用 Python 3、`capstone` 和 `keystone-engine`，从上述精确输入生成未签名 IPA：

```powershell
python client-patch/ios-abyss-equipment/build_ios_abyss_multibothboss_level120.py `
  --ipa F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-entryhook-test-unsigned.ipa `
  --out F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-abyss-multibothboss-level120-test-unsigned.ipa `
  --report F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-abyss-multibothboss-level120-test-unsigned.json `
  --dependency-path F:\codex\tools\ios-re-libs
```

构建器必须回读 ZIP、成员顺序、Bundle ID、Mach-O 哈希、UUID、变更范围和保留区间，并要求
最终 IPA SHA-256 精确等于本页登记的已验收目标哈希。生成物仍是未签名 IPA，需要使用者按
原有方式合法签名后安装。

仓库只保存构建方法和哈希，不保存源 IPA、目标 IPA、签名证书、描述文件、设备 UDID 或签名
密钥。需要回滚时，重新安装本页登记的输入累计 IPA。
