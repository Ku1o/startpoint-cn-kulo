# iOS 资料页关注状态与排行榜本人资料路由

2026-09-08 从当天**已验收的 r12b 导航累计 IPA**增量构建，并已获得用户明确真机验收。
当前成品是下列原始无 DEBUG 修复包，已登记到 [ios-accepted.json](../ios-accepted.json)；
后续修改从这个累计输出继续，不回退到 r12b 输入，不采用诊断版。
此前“关注无反应、本人仍进入他人卡”的反馈，用户随后澄清测试时使用了旧版，
再确认先前无 DEBUG 修复包正常。过程与证据边界见 [AUDIT-20260908.md](./AUDIT-20260908.md)。
用户明确要求：**不加入标题页 `CNtips_b` 隐藏**。
本次验收直接采用原无 DEBUG 文件，没有重新编译或打包；历史输入只用于精确复现本步骤。

## 输入与输出

- 输入：`F:/codex/ios-artifacts/iOS-1.8.4-kulo-private-final-fantasy-soul-memberview-v6-rush-leaderboard-v3-r12b-navigation-abyss-multibothboss-level120-test-unsigned.ipa`
- 输入 SHA-256：`f44710abcbb6c657f25a205b8d72ca597be551f19e2f7b02a9591605339dcc40`
- 输出：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-profile-follow-self-20260908-unsigned.ipa`
- 输出 SHA-256：`09eca214d1e73559bbc7af98d642f9056b0eeee4a44f3e09dd25f2a1e9091a43`
- 新 Mach-O SHA-256：`82afb40b01ca016002aca36a31ff921111885065ddfdb5dac7d13e6b75f1d978`
- 新主 SWF SHA-256：`ae7899011bc55c4a988d2773f96f9222a3f881fc55f2c4f7bb04a12a77983b33`
- 包身份保持 `com.kulo.wf`、版本 `1.8.4`、构建 `1.8.46`；服务器地址沿用输入。

## 本次移植的三个方法

| iOS 方法 | body index / AOT method ID | 行为 |
| --- | --- | --- |
| `PlayerProfileView.refreshFollowRelationButtons` | `79682 / 87249` | 保留关系枚举和父容器帧映射，直接设置 `follow_button` 与 `remove_button` 的可见性。状态 0/3 显示关注，1/2 显示取消关注。 |
| `OtherProfileLogic.applyButton` | `79819 / 87420` | 保留真实服务端关注流程。旧取消关注按钮误触时，0/3 走新增关注，1/2 走删除关注。 |
| `RushEventRankingPartyScene.copyPlayedParty` | `71659 / 78115` | 对比 `globalLogic.getPlayer().get_viewerId()` 与排名行 `id`；本人走原生 `ProfileGetMyProfile`，他人仍走 `ProfileGetProfile(id)`，均保留返回栈。 |

P-code 来自 [已验收安卓包记录](../android-accepted.json) 的公网成品，仅移植上述方法。
保存的 [三个方法及编译初始化声明](./pcode/) 与 [方法编号及哈希](./methods.json) 用于继续维护。
不反转关注枚举，不伪造本地关系，不直接读取 `viewerId` 属性，不加入曾引起 F1069 的提前刷新。
本次没有新的服务端修改。

## 保留范围与原生实现

ZIP 的 3568 个成员中只有 `Payload/worldflipper.app/worldflipper` 和主 SWF 改变。
主 SWF 解压后只改变 20 字节 AOT 校验值，标题画面及 `CNtips_b` 原样保留。
Mach-O 的主 stripped ABC、常量池、类/脚本定义、方法参数、activation 信息、段布局、UUID、
dyld 重定位以及此前全部非目标原生代码保持逐字节一致。

只在原有空白 RX 区间 `0x5f28f40..0x5f2bc60` 放入三个函数与常量；只更新方法表中的上述三项。
跳转钩子位于 `0x311f308`、`0x5f207e0`、`0x361f198`、`0x362b81c`。
排行榜方法同时更新原始入口和上次重定位入口，兼容已经绑定的调用地址。
其余排行榜分页、整行触摸、深渊装备限制、MemberView v6、幻想魂珠、角色 MOD、轮播和继承修改均保留。

AIR 编译器需要恢复两处脚本 `newclass` 声明才会生成资料页方法：
`PlayerProfileView` 的 iOS class `8254` / body `79694` / AOT `87260`，
`OtherProfileLogic` 的 class `8261` / body `79821` / AOT `87421`。
这两项仅是编译上下文；**不替换它们在 IPA 中的原生实现或运行时元数据**。
完整编译 ABC SHA-256 为 `b374e739c7da1541182f0608f6f52c2e597efafc5133f2ecad97da819f842c4c`，
AOT SHA-1 为 `d21b4739765e3a0dc58ede7a558cc5507ea58008`。

## 精确重建

使用仓库现有的差分构建器，输入必须与本文哈希一致：

```powershell
python client-patch/ios-five-in-one/build_ios_client.py `
  --source <本文已验收输入.ipa> `
  --manifest client-patch/ios-profile-follow/patch-manifest.json `
  --output <新的输出.ipa>
```

加 `--verify-only` 并省略 `--output` 可以在内存里检查完整输出哈希。
差分清单保存了实际原生补丁，因此复现本次 IPA 不依赖临时编译目录或旧 APK。

继续修改方法时，原生生成与验证脚本保存在 [native-build](./native-build/)。通过
`STARPOINT_IOS_PROFILE_WORK` 指定工作目录；工具依赖仍使用已安装的 FFDec 26.2.1、AIR 51.2.1.5、
`F:/codex/ios-rush-leaderboard-port-20260830` 的 AOT 工具和
`F:/codex/ios-rush-navigation-port-20260907` 的已验证增量构建工具。
当前编译/验证材料位于 `F:/codex/ios-profile-follow-port-20260908`。
这些脚本锁定本次确切输入；后续任务不能为了运行历史脚本而倒退客户端基线。

原生重建入口为 `native-build/build_all.ps1`，先将 `STARPOINT_IOS_PROFILE_WORK` 设置为新的任务目录。
脚本使用本目录固化的 P-code，不再从会继续变化的安卓成品中取代码；完整编译输入也有哈希门禁。

## 验证与用户验收

已检查包内容及元数据、320 处原生重定位、三个方法指针与四处入口钩子、所有非目标字节保留。
对实际 iOS 编译输入重新导出的 P-code 做了 10 个模拟执行场景，覆盖四种关注关系、陈旧按钮防御、
本人/他人 ID（含字符串 ID）和无效 ID。这是模拟 UI/服务的分支测试，不是真机验收。

2026-09-08 用户确认资料页关注功能可用，榜上本人进入带编辑等入口的本人资料卡，
并明确选择前一份无 DEBUG 包验收，原话：

> 确认了，用户用先前的版本反馈正常，那`DEBUG`  可以去掉了，验收前面的那个版本

验收状态单独登记，不改写构建时报告。没有新增逐项真机日志，因此不将用户总体确认扩写成自动化测试结果。
后续回归仍需覆盖四种关系、连续关注/取消、重进页面、菜单搜索、本人/他人资料及排行榜分页。
IPA 与签名材料不提交 Git。
