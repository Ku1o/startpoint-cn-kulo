# release1031 iOS 独立编队修复基线登记（2026-10-31）

`independent-party-fix-r1` 作为当前后续 iOS 开发基线，登记层级为 `accepted_offline`。成品未签名；离线成品、原生入口与 ABI 证据不代表已经重签安装、手机进入副本或完成 C2620 真机复测。历史 F1069 登记完整保留在 `lineage.previous_ios_baseline_registration`。

## 成品身份

| 项目 | 登记值 |
| --- | --- |
| IPA | `F:/codex/work/production-release-20261031/client/revision-ios-independent-party-fix-20261031/StarPoint-iOS-1.8.4-release1031-independent-party-fix-r1-unsigned.ipa` |
| IPA SHA-256 | `1990178abd4078beb39e26e5c2f985b6cc1af4900c72868f5b79221fcc21e907` |
| 字节数 | 183619451 |
| 原生程序 SHA-256 | `ab2cf14f9904023c8d3ba00ebf7c943764b8f7c0d033729a04f7e1a7bb2434af` |
| 主 SWF SHA-256 | `ebb50ee6867333fd50995169b0dc0068ffac17cebe5092a39f2ee80c743dccf5` |
| 完整 ABC SHA-256 | `ccb1e564a5650b57219cf7f7354ba1da971f5702a0cbc503ce165ca58bfaee8e` |
| 完整 ABC SHA-1 / AOT 摘要 | `9d3b3878cbcc4d40537d6cf9373e924601eab8bb` |
| Bundle / 版本 / Build | `com.kulo.wf` / `1.8.4` / `1.8.46` |
| 架构 / AOT 方法数 | ARM64 / 101873 |
| 公网 origin | `http://124.222.203.221` |
| iOS 准入 ID | `ios-184-r1031-final-public-20261031` |

精确入口以 [ios-accepted.json](ios-accepted.json) 为准。完整 ABC 继续指向 F1069 目录的 `prepared01/full.abc`，与本次实际链接回执相同；不得另造同名 ABC 或以 stripped runtime ABC 替代。沿用直接输入既有地址和准入配对，不生成新材料、不改允许名单或云服。

## 修复范围与源码

三处原生入口仍执行旧编队逻辑，而完整 ABC 已包含独立编队：`RushEventLoadingTask.summaryRemoteInput`（MID42394）、`EventRushPartyRealRemote` 构造器（MID52468）、`RushEventPartyGroupHolder.getPartyCategory`（MID22164）。本次在真实所属类上下文中编译并绑定两套方法表及原入口分支，不增加字段或 MethodInfo。普通深渊700099对应5、EX700100对应6、幻想700098对应7、其他Rush活动对应4。

累计保留主城派发、战斗 F1069 getter及此前功能；只改变原生程序，完整 ABC、runtime ABC、主 SWF及3567个其他压缩成员保持。独立编队错配与客户端结算角色、服务端专属队伍不一致的 C2620 诊断相符，是否消除玩家现场报错仍需匹配本包的设备复测。

实现和配方见 [独立编队源码](release1031-ios-independent-party-fix-20261031/README.md)、[F1069 源码](release1031-ios-battle-f1069-fix-20261031/README.md) 和 [主城派发源码](release1031-ios-dispatch-fix-20261031/README.md)。外部输入、阶段入口、源文件清单和可迁移范围见 [后续修复说明](release-20261031/ios/FOLLOWUPS.md)。SDK、原始载荷、编译对象及私有回执不进入 Git；源码迁移不等于已从新路径重新制作 IPA。

## 验证与边界

- 复用对应此精确成品的独立读回：3个函数、45处重定位、6处方法表绑定，实际ARM64参数/返回寄存器与原入口分支通过；全部825638旧rebase及89124旧展开边界保留。
- 对应完整ABC的80条桌面AIR断言、category4负例、1项真实服务端编队合同与4项既有编队保护通过；桌面场景仍使用受限替身，不代表执行iOS原生。
- 登记后执行 `python -B client-patch/verify_ios_baseline.py`，核对实际IPA、native、SWF、完整ABC/AOT摘要、方法数和包身份。回执位于 `F:/codex/work/production-release-20261031/client/sync-client-source-20261031/identity-ios.log`。
- 原生/ABI回执位于修复目录 `verify-review/final02.json`、`final02-party-proof.json`、`abi01.json`；原构建报告保持生成时的登记与Git状态，后续登记不改写冻结回执。

IPA比F1069包增加2114521字节，增量全部来自压缩后的原生成员。本批没有实施瘦身；后续封包需复用累计链接和重复runtime ABC检查，避免继续叠加完整载荷。原draw wrapper展开限制保留，未执行真实iOS unwinder或性能测量。

本次登记和源码同步不重打包、不签名、不安装、不改数据库或部署云服。后续设备复测应覆盖普通深渊、EX、幻想的编队保存/切换/进战斗及万圣战斗、主城回归；未完成前保持离线层级。
