# release1031 iOS 战斗 F1069 修复基线登记（2026-10-31）

此历史累计 ARM64 公网 IPA 登记为 `accepted_offline`，后续由 [独立编队修复基线](ACCEPTANCE-RELEASE1031-IOS-INDEPENDENT-PARTY-20261031.md) 接替。成品未签名，登记范围为离线成品身份、完整 ABC/AOT 继承链及本批准入材料；未执行新包的 iOS 原生、重签安装、公网登录或手机战斗。

## 成品身份

| 项目 | 登记值 |
| --- | --- |
| IPA | `F:/codex/work/production-release-20261031/client/revision-ios-battle-f1069-fix-20261031/StarPoint-iOS-1.8.4-release1031-battle-f1069-fix-r1-unsigned.ipa` |
| IPA SHA-256 | `67dcd483aa3f7e500b9d2ed494b2106fe8b30da0f1c5f05415828563e7ac5b78` |
| 字节数 | 181504930 |
| 原生程序 SHA-256 | `c5a2072735e3bd62872f4f877d70bcb10e41aa6106e9e9c50ff49896934698b8` |
| 主 SWF SHA-256 | `ebb50ee6867333fd50995169b0dc0068ffac17cebe5092a39f2ee80c743dccf5` |
| 完整 ABC SHA-256 | `ccb1e564a5650b57219cf7f7354ba1da971f5702a0cbc503ce165ca58bfaee8e` |
| 完整 ABC SHA-1 / AOT 摘要 | `9d3b3878cbcc4d40537d6cf9373e924601eab8bb` |
| Bundle / 版本 / Build | `com.kulo.wf` / `1.8.4` / `1.8.46` |
| 架构 / AOT 方法数 | ARM64 / 101873 |
| 公网 origin | `http://124.222.203.221` |
| iOS 准入 ID | `ios-184-r1031-final-public-20261031` |

完整 ABC 使用该修复目录的 `prepared01/full.abc`，不能替换为 stripped runtime ABC。全部实际路径和身份以 [ios-accepted.json](ios-accepted.json) 为准。

准入配对相对本次直接输入 `8e6845291b3b83a41844c241c562961dc097cf2297599f2940cacffec220011c` 保持；与 10-25 旧登记的准入 ID 不同。本次登记使用本批已存在的配对，不生成密钥、不更改允许名单，也不推定云端已部署。

## 实现及累计继承

直接输入为 release1031 主城继承派发修复候选，补入 `BattleAbilityTotalizerImpl.getTotalDashParameter(index:int):Number` 的真实方法及原生 AOT，继续使用已有字段与 `DuringCheckerWithDecimal.sum`。Android 中原本已有且未变化的方法被差分移植遗漏，iOS 导入的调用者仍引用该方法；本次补齐此缺口。

新增一个344字节原生函数和一个 MethodInfo。原六处源码引用对应四处实际原生动态查找，调用者保持原字节。旧359个已编译函数、主城修复、包装链、所有原字段、MethodInfo、方法体、activation、scripts及数值保持。该数量是本批被保护的累计函数集合，不代表整个游戏仅有359个原生函数。

完整旧登记沿 `lineage.previous_ios_baseline_registration` 递归保留；10-25 累计整合及更早原始输入保留用于历史复现。此前构建回执保留生成时状态，其 `accepted_registry_updated=false` 不覆盖后续独立登记。

源码配方见 [F1069修复源码](release1031-ios-battle-f1069-fix-20261031/README.md)，其 `SOURCE-MANIFEST.json` 固定源码与外部依赖；修复目录的 `RECIPE.json` 保存原始阶段参数和回执。它依赖保留的SDK、私有载荷及底层工具，不是自包含原作者工程。

## 验证及限制

- 真实密封接收者负例复现1069；生产 getter及六个真实依赖体通过60条桌面 AIR 断言，覆盖七通道、空数据、条件次数、求和、null Enemy转发及原1034失败路径。条件输入、Enemy类型壳和初始化使用夹具替代。
- 最终实际 IPA 独立读回通过：1个新函数、10处重定位，9930旧类及138812旧继承槽保持，359旧函数与包装链字节保持；实际旧sum调用及参数、返回寄存器已核验。
- 全部825637旧rebase、89122旧展开边界及3566个非目标压缩成员保持，展开页和签名/ldid模型检查通过。前批既有draw wrapper CFI限制保留，未执行实际iOS unwinder。
- 工程证据为修复目录的 `verify-review/final03-battle-summary.json`、`final03-details.json` 与 `fixtures/air01/air-report.json`。早先诊断及检查器假设失败单独保留，未计为通过。
- 登记后通过 `python client-patch/verify_ios_baseline.py` 核对实际 IPA、native、SWF、完整 ABC/AOT、方法数与包身份；本地回执位于修复目录的 `baseline-registration-20261031/identity.log`。

离线验收不证明手机进入战斗已恢复；旧现场反馈也不能唯一确定完整安装包SHA。后续重签安装和手机复测单独记录，不自动将本登记升级为 `user_accepted`。本登记不修改安装包、准入配置、Android、云服或数据库。
