# iOS Rush 排行榜翻页与玩家资料导航

本目录保存 iOS 1.8.4 累计客户端的 Rush 排行榜 r12b 导航补丁。2026-09-08，
用户已在 iOS 真机确认：排行榜可以正常翻页，点击玩家排行卡片可以进入该玩家资料，
卡片的正常可见区域均可触发跳转。

验收结论只适用于本页登记的输入、输出和 Mach-O UUID。仓库通过
[patch-manifest.json](./patch-manifest.json) 保存可执行的二进制差分，不保存 IPA、SWF、
Mach-O、ABC、AOT object、AIR SDK、FFDec 或签名材料。

## 已验收血统

输入是此前已验收的最新累计未签名 IPA，已经包含私服与免登录、数据继承、幻想连战、
幻想魂珠异步纹理、`MemberView.draw` v6、Rush 排行榜 v3 和深渊装备
Multi / BothBoss、120 级门控：

- 输入文件：`iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-abyss-multibothboss-level120-test-unsigned.ipa`
- 输入 IPA SHA-256：`4D54590D445E6AAD0F189C6BB21AC896D634CDBB2E0E51C7A856317DC3EF694C`
- 输入 Mach-O SHA-256：`7758FD717CB4E38C5EB347677714A03EEC55D92307E2E51838335CD7377E76B3`
- 输入主 SWF SHA-256：`8A6443B2EA8A487D399825FAB7C2AA5150B5CBB79639919BAB268419421F6646`

已验收目标：

- 输出文件：`iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-r12b-navigation-abyss-multibothboss-level120-test-unsigned.ipa`
- 输出 IPA SHA-256：`F44710ABCBB6C657F25A205B8D72CA597BE551F19E2F7B02A9591605339DCC40`
- 输出 Mach-O SHA-256：`530DB20DAA356162B617C5D853335D5C4D2A09965FD89C2151A1DCA03BCCC1E8`
- 输出主 SWF SHA-256：`2B6D7D9C4420872245053BC4150A913A208A589FC282EC0F65A43957618DE6F9`
- Mach-O UUID：`064F8E49-FDD9-532F-8445-439AB9F71E6C`
- Bundle ID：`com.kulo.wf`
- 版本 / 构建号：`1.8.4` / `1.8.46`
- IPA 成员数：`3568`

输入和输出的 ZIP 成员名称、顺序及元数据保持一致。只有以下两个成员变化：

- `Payload/worldflipper.app/worldflipper_ios_release.swf`
- `Payload/worldflipper.app/worldflipper`

`Info.plist` 和 `META-INF/AIR/application.xml` 逐字节不变。目标 IPA 不包含
`embedded.mobileprovision` 或应用目录下的 `_CodeSignature`，仍需按原有方式合法签名后安装。

## 修改范围

本次移植严格对应 Android 已验收 r12b 的三个 P-code 方法体：

| P-code | SHA-256 | iOS body | iOS AOT method | 行为 |
| --- | --- | ---: | ---: | --- |
| `run.pcode` | `6DED16A3113725084486E2D57816F13E14BD92807243401B6E05D1ED49742F76` | `71652` | `78108` | 保留每页 100 人，初始关闭行选择，并在排行榜模式注册玩家行选择处理器。 |
| `copyPlayedParty.pcode` | `F9936F31568C8FB238856CF6C954C01A092A7A24D80B70B16B8612B655AA8133` | `71659` | `78115` | 收到行数据后启用选择并追加分页结果；对有效的 `row.id` 调用 `ProfileGetProfile(row.id)`，通过 `AddCurrent` 返回排行榜。 |
| `content-run.pcode` | `275833E3F2DC2EE4DA284FBDAEE407F46FE9D43A0458D1DB70F7F85786E33D0C` | `71701` | `78158` | 设置 `extraButtonLayer.touchable = false`，让排行卡片的整行点击区接收资料跳转。 |

完整 ABC 只有 AOT method `78108`、`78115`、`78158` 的方法体语义发生变化。
新的 stripped ABC 从 `5,696,079` 增长到 `5,696,101` 字节，因此原有 Rush AOT 代码区被
向后覆盖。构建时在既有 RX 工作区内重新排列下列 15 个 Rush 函数，并同步更新方法表、
入口分支、重定位、Mach-O AOT 哈希和主 SWF AOT 哈希：

`52504, 52506, 78108, 78110, 78115, 78117, 78118, 78127, 78139, 78158, 78159, 78163, 78193, 78207, 78211`

新代码从 Mach-O 文件偏移 `0x5F1D780` 开始，使用到 `0x5F28F40`，没有再次扩展
`__DATA` 或 `__LINKEDIT`。已验收深渊 helper、`MemberView.draw` v6、幻想魂珠、
赛瑞斯双形态、湿润目标雷伤、逐角色缩放和数据继承代码区保持逐字节一致。

本补丁的范围截止于 r12b。Android 后续单独加入的本人资料路由、关注按钮和标题界面逻辑
不属于本次 iOS 验收负载；三个方法体中不含 `get_viewerId` 或 `ProfileGetMyProfile`。

## 构建方法

使用 Python 3 和仓库已有的通用 iOS 差分构建器，从上述精确输入生成已验收的未签名 IPA：

```powershell
python client-patch/ios-five-in-one/build_ios_client.py `
  --source <已验收输入.ipa> `
  --manifest client-patch/ios-rush-leaderboard/patch-manifest.json `
  --output <输出.ipa>
```

也可以只在内存中重建并核对目标哈希：

```powershell
python client-patch/ios-five-in-one/build_ios_client.py `
  --source <已验收输入.ipa> `
  --manifest client-patch/ios-rush-leaderboard/patch-manifest.json `
  --verify-only
```

构建器先检查输入 IPA 及两个被修改成员的大小和 SHA-256，再逐段核对旧字节、应用差分、
复查新成员哈希，并要求最终 IPA SHA-256 精确等于本页登记的已验收目标。任一输入、差分或
ZIP 元数据不一致都会使构建失败。

需要回滚时，重新安装本页登记的输入累计 IPA。
