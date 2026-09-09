# Lens 0907 + 0908 安卓累计修改

2026-09-09：本页保留 Lens v3 的历史方法与离线验收，原身份见 [Lens 历史登记](../accepted-history/android-lens-v3-20260909.json) 和 [验收记录](../ACCEPTANCE-20260909.md)。
当前基线已升级为 [深渊续战累计 APK](../android-accepted.json)，新任务必须保留续战与全部 Lens 内容；方法见 [续战目录](../abyss-autostart/README.md)。
以下构建报告保持生成时状态，不改写为真机通过。iOS Lens 方法见 [iOS 目录](../ios-lens0907-0908/README.md)。

## 历史构建与交付记录（以下“当前”“待验收”均指当时）

2026-09-08 整合交付补充：本轮资源 .102～.108 已按用户要求合入 **1.4.102** 单一增量，Android 继续使用既有 v3，不重建或重签 APK。iOS 的 11 组平台贴图已完整纳入；用户明确本次只处理资源增量，IPA 运行补丁留待后续，不能视作双平台客户端均已完成。下文是各历史步骤的身份和验证记录。

2026-09-08 真机反馈修复：当前本地测试成品为 `outputs/lens0907-0908-android-20260908/lan-v3-final/StarPoint-CN-1.8.1-lens0907-0908-lan-v3-20260908.apk`，配套本地资源 1.4.104。公网 v3 位于同级 `public-v3-final/`，云端尚未同步。

.104 仅修复五重决战讨伐/兑换页四种材料的小图标预加载图集，未修改或重签 APK。原有 v3 可直接下载资源更新；两页真机复测尚待完成，不能用资源字节核验替代 UI 验收。

`fix_weapon_steel.py` 从本任务精确 v2 SWF 继续，只在 `284:19690` / `OwnedEquipmentLogic.getUseableAwakingCrystal` 增加 5900101 返回 None 的判断。原有指令、分支、其他方法、常量池前缀及非主 ABC 标签均保留。`CompareExactBodies.java` 独立检查全部 96,404 个方法体，只允许这一处差异；`package_steel_fix.py` 再用 FFDec 回读判断、分配新 AIR UUID、按固定本方证书签名，并检查 APK 其他成员、v1/v2 签名及对齐。未操作用户设备，未更新已验收登记。

以下内容记录最初 v2 移植与其输入来源。

2026-09-08，用户恢复 Android SWF/APK 工作；iOS 运行逻辑继续暂停。两版 APK 已完成本地签名和静态核验，尚未真机验收。后续用户已授权本地服务同步运行，配套 1.4.102 资源链已在本地启用并拦截 iOS；不能将本地联调写成完整双平台上线或更新已验收登记。

## 输入与输出

本步骤当时的直接输入是 2026-09-06 公网/内网标题修复包，原登记已归档至
[历史验收记录](../accepted-history/android-20260906.json)。两版当时均执行基线校验；这不是新任务的起点。

作者 V14 SWF SHA-256：`dee19b6a96d8cece93021c09f937fdf35832ed362dcbf9b9df0b8750a3774572`。作者材料仅作为待审代码/数据输入，未执行其安装、构建或发布入口。

输出位于仓库忽略目录 `outputs/lens0907-0908-android-20260908/`：

| 版本 | 子目录 | APK SHA-256 | 新 AIR UUID |
| --- | --- | --- | --- |
| 公网 | `public-final` | `1dc00bafdf78feb2c66e507842ff201dfd7b31e6dbfb9c747abed9665922cce0` | `a0250e84-ab16-4798-aa91-78c5f8189329` |
| 内网 | `lan-final` | `a767a78e94c808b3c68b4634cf0351179d9e21f5efd5793eb8e559ba6b5de312` | `c112b3a3-da8e-413c-bd73-9ae9e21db32e` |

最终 SWF 哈希：公网 `8e67fdd325b4fb488930cd1febb37fbac7ba1f8a90d31c1ead372d0cbf82079a`，内网 `6bad8317da5e1fc9e528393c1d57bf6f4217a3861ad47d6daa329607ffbecc76`。实际 SWF、独立回读及方法报告在 `F:/codex/work/lens0907-0908-integration-20260908/client/`；仅 `lens-*-v2.swf` 为最终载荷。第一版空字符串常量迁移错误，已废弃，未装入交付 APK。

## 修改范围与保护

- 26 个原有方法按指令核对后迁入新增能力：724 Fever 上限比例增减、422 冲刺参数、相应文案/合并解析、稻穗 PF 与动作注册。校验旧操作、可达分支、异常区间及闭包槽布局；仅容许两边均不可达的旧死跳转采用不同编码。
- BothBossTool 仅迁移 3 个地图方法并新增 6 个辅助方法，保留其余方法。联机随机图带入房号种子，普通 BothBoss 选择规则保持原有分支。
- 在已验收 BattleScene / BattlePauseMenu 中定点插入手动锁：仅联机 1099001–1099003，手动开局后禁止开启自动，暂停菜单也显示锁定。原有自动解锁和教学锁规则保留。
- 新增 BattleAbilityTotalizerImpl 的冲刺参数汇总方法，另追加 3 个实例槽；主 ABC 的既有常量池、类和脚本结构保持前缀不变。
- 共改 32 个旧方法、新增 7 个。独立 FFDec 比对原有 96,397 个方法体，仅指定的 32 个发生变化。主 ABC 之外的 SWF 标签载荷原样保留。
- 保护关注按钮 284:79085 / 79222、本人资料 71120、标题 82510、各版本地址 92013，以及原有 MOD、幻想连战、轮播和导航等累计代码。未移入作者旧 Seris 的 invokeActionSkillIfPossible 差异。

## 复现与核验

`vendor/` 只含经检查的纯 ABC/SWF 解析汇编模块，来源哈希见 `vendor/provenance.json`。本目录脚本还复用 `tools/lens-integration/compare_clients.py` 和 `client-patch/rush-leaderboard/apk_build_common.py`。

1. 本节仅描述当时的精确构建步骤；输入锁定上述 9 月 6 日历史父版本。当前登记已升级为深渊续战 Lens 累计成品，旧构建器会拒绝直接重复套用；新工作必须先验证当前基线并重新审计目标改动，不绕过输入保护。
2. `python build_swf.py --base <accepted.swf> --donor <V14.swf> --out <全新输出.swf>`。输入身份和方法体哈希受 `method-plan.json` 约束；发生基线变化时重新审计，不绕过断言。
3. `python verify_swf.py --base <accepted.swf> --swf <输出.swf> --out <全新核验目录> --ffdec <ffdec.jar>`。独立比对全部方法，回读 5 个关键类；检测 FFDec 返回成功却只导出半个文件的情况。
4. `python package_apk.py --variant public或lan --swf <输出.swf> --validation-report <核验目录/verification.json> --out <全新成品目录> --build-tools <Android build-tools目录>`。
5. `python -m unittest discover -s client-patch/lens0907-0908 -p test_importer.py -v`。5 项回归覆盖真实常量与索引 0 的区分、可达跳转保护和异常处理入口。

打包每次生成新 UUID，除 SWF、AIR UUID、签名外，回读核对 APK 其他文件字节不变。`sign_apk.ps1` 仅在独立签名进程解密本机 DPAPI 凭据，经进程环境传给 apksigner，finally 清除；不记录密码。

两版 v1/v2 签名、ZIP 对齐、内嵌 SWF、AIR UUID 和所有无关 APK 成员校验通过。证书 SHA-256 为 `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894`。Java 子进程均受超时和进程树清理约束，本次没有遗留 Java 进程。

## 验收边界

尚未安装或进行 Android 真机战斗验证。后续本地服务已接入 1.4.102 配套资源，内网 APK 可更新资源后测试新增角色和五重内容。两张地图缺少的召唤落点已经修复，22 个场景的静态依赖检查通过。完整验收仍需实战、两个未映射资源的逻辑名称核验，以及恢复后补齐 iOS。

本地现在可检查新角色、四项改版、五重单人/联机、10 结晶换 1 票、掉落及武器兑换，同时回归覆盖安装、登录、旧角色战斗、关注/取关、本人资料、排行榜和标题等累计行为。未改已验收登记，未提交、推送或部署云端；仅完成用户授权的本地测试同步与启动。
