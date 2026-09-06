# 本会话 Android 资料页、本人资料和标题修复

2026-09-06：用户发现最新公网资料页修复 APK 遗漏了先前的标题提示隐藏。
2026-09-06 用户随后确认最终公网和内网包全部验收。当前直接基线由
[ANDROID-BASELINE.md](../ANDROID-BASELINE.md) 和 [android-accepted.json](../android-accepted.json) 统一登记。
下列后继关系记录每步方法的精确来源；旧步骤输入不能替代最新成品。

## 已完成的后继

- 直接可见性关注修复（用户已验收）：
  `outputs/rush-leaderboard-profile-follow-direct-visibility-lan-20260906/StarPoint-CN-1.8.1-rush-leaderboard-profile-follow-direct-visibility-lan-20260906.apk`。
  APK SHA-256 `2e5101ceaa3e5e8e8ee8bf165f0cb81dd7649ac0cb8b276b2a8738c1e2628927`。
  构建器 `build_profile_follow_lan_rootfix_apk.py`，继承 r12b；改动 `284:79085`、`284:79222`、`284:92013`。
- 本人资料跳转内网 v2（用户已验收）：
  `outputs/rush-leaderboard-self-profile-lan-20260906-v2/StarPoint-CN-1.8.1-self-profile-lan-20260906-v2.apk`。
  APK SHA-256 `972ee319a8e6a9fefeb3360671d5dbd322a5c45b7fa39f4701c3a09b9a9c8049`。
  构建器 `build_self_profile_lan_apk.py`，仅追加修改 `284:71120`。
  必须调用 `globalLogic.getPlayer().get_viewerId()`；它是方法，直接读 `viewerId` 会报错。
  点击本人走原生 `LoadingTaskKind.ProfileGetMyProfile`，其他人走 `ProfileGetProfile(row.id)`。
- 对应公网版（完成本地校验并交付）：
  `outputs/rush-leaderboard-self-profile-public-20260906/StarPoint-CN-1.8.1-self-profile-public-20260906.apk`。
  APK SHA-256 `da49d1b8fa6cb022db4cfcfb62ecb6b4a79c7b4a9efe40cf3fd7c49b6e85f8ce`；
  SWF SHA-256 `b0ae6fbc4adc1de7a87b282b63a905dce8490c65dd1acaaf5bd06cd305f44015`；
  UUID `a69eb356-5730-4709-a5fb-d8b199bba680`。
  构建器 `build_self_profile_public_apk.py`，从已验收内网 v2 仅改 `284:92013`，地址为 `175.178.160.158:8001`。

上述包均遗漏标题隐藏，不能把它们误记成已经包含这项修改。原 r14/r15 报告曾记录标题补丁，
后续改从 r12b 重建时没有移植该方法，是本次回归的原因。失败的关注诊断补丁不能连带复用。

## 本次补回方法

`pinball.scene.title.TitleView.run` 加载
`scene/title_bundled_extend/cntips-assets/CNtips_b` 为 `copyrightImage`，初始设为不可见，
但随后调用 `refreshHealth(true)`；`draw` 也会调用 `refreshHealth(false)`。
原 `refreshHealth` 在 `isHealth=false` 时把 `copyrightImage.visible` 重新置为 `true`。

本次只修改 `TitleView.refreshHealth`（`284:82510`）：把这一次 `pushtrue` 改为 `pushfalse`。
两种健康提示状态均隐藏 `CNtips_b`，`CNtips_a` 的显示逻辑、底部版本信息、资料页和关注方法不变。
只在 `run` 初始化时隐藏不足以修复，因为后续刷新会重新显示。

构建器：`build_title_cntips_apk.py`。输入锁定上面的最新公网包，不重新套用历史排行榜或关注补丁。
构建器校验：输入哈希、目标方法索引、全部 96397 个方法体仅 `284:82510` 改变、
最终 SWF 重新导出的目标方法与预期一致、完整 TitleView 类仅这一条指令变化、
两种状态隐藏及 `CNtips_a` 行为保持、回封 SWF、manifest 仅更新 UUID、其他 APK 成员不变、
zipalign、v1/v2 签名与固定证书。签名凭据遵循根 AGENTS.md 的 DPAPI/进程环境变量规则。

构建参数为 `--base --out --work --java --javac --ffdec --zipalign --apksigner --keystore --password-env`，
均需显式指定；输出与工作目录不得已存在。构建会删除自身的 unsigned/aligned 中间 APK。
本任务不修改服务端、CDN 或 IPA。

## 当前公网交付（用户已验收）

- 公网 APK：`outputs/rush-leaderboard-self-profile-title-public-20260906/StarPoint-CN-1.8.1-self-profile-title-public-20260906.apk`
- APK SHA-256：`7990f9191ecf41bd35a4d886ced4d13248d13559284639c69bee5837bd682f0e`
- SWF SHA-256：`27bdd055f8ca15f0863f564f5b4d57aba7de18d65d5fb9cdec43e87f96740e64`
- `uniqueappversionid`：`10eb0c01-78a1-4a70-8c35-d524208b98b7`
- 同目录 `verification-report.json` 保留构建当时的 `locally_verified_test_candidate` 状态；后续用户明确验收的依据另记于 `../android-accepted.json`。

后续回归需查看首次标题页、进入游戏再回标题页，确认 `CNtips_b` 不再出现。
后续修改需保留 `284:82510` 隐藏逻辑，并以此累计包继续。
以后转换公网/内网只改配置构造器并换新 UUID，必须回读确认标题隐藏、本人资料跳转和关注可见性都在。

## 对应内网交付（2026-09-06，用户已验收）

构建器 `build_title_cntips_lan_apk.py` 从上述标题已修复公网包
`7990f9191ecf41bd35a4d886ced4d13248d13559284639c69bee5837bd682f0e` 继续，
只将配置构造器 `284:92013` 的服务器地址改为 `http://192.168.3.14:8001`。
参数与标题公网构建器相同；严格检查输入哈希和目标方法索引、唯一方法差异，
重新导出最终配置和标题代码确认地址及 `CNtips_b` 隐藏，并校验回封载荷、新 UUID、对齐和签名。

- 内网 APK：`outputs/rush-leaderboard-self-profile-title-lan-20260906/StarPoint-CN-1.8.1-self-profile-title-lan-20260906.apk`
- APK SHA-256：`8e10df1f2b259fdc5cacf30f9a66ed3bc0556d5d253a22f55a931c22a0e6c9c0`
- SWF SHA-256：`e18b627a7735e55d40d65753cc6079ce47e7d969980723aef392513867ec4f30`
- `uniqueappversionid`：`444eb21b-7807-438d-a89c-156c617fcfb6`
- 同目录 `verification-report.json` 记录构建时的本地校验；用户现已明确验收此次标题补回版本，依据见 `../android-accepted.json`。

该内网版保留标题隐藏、本人资料路由及关注修复，不得改用没有标题隐藏的旧内网 v2 代替。

## 最终方法与失败方案

- `PlayerProfileView.refreshFollowRelationButtons`（284:79085）：四态映射本来正确；问题在父层切帧后子按钮仍保留旧可见性。最终显式设置 `follow_button.visible` 与 `remove_button.visible`：0/3 显示关注，1/2 显示取消关注。
- `OtherProfileLogic.applyButton`（284:79222）：旧取消按钮帧遇到状态 0/3 时转入添加关注，状态 1/2 继续删除关注；不伪造服务端关系。
- `RushEventRankingPartyScene.copyPlayedParty`（284:71120）：用 `get_viewerId()` 比较本人，调用原生 `ProfileGetMyProfile`，他人保持 `ProfileGetProfile(row.id)`，两条路径均用 `AddCurrent` 返回排行榜。
- `TitleView.refreshHealth`（284:82510）：隐藏 CNtips_b 的准确位置是每次刷新可能重新显示的分支，不能只在 `run` 初始化隐藏。
- 配置构造器（284:92013）：只在公网/内网转换时切换地址。

失败方案仅记原因，不作为可执行修复提交：反转关注枚举/帧映射、只切按钮文案、在 prepare 提前读取目标资料、在 draw 等位置重复插入刷新（曾触发 F1069），以及直接访问 `PlayerLogic.viewerId`（两种跳转均报错）。

## 已提交方法的依赖与复现范围

| 脚本 | 锁定的直接输入 | 作用 |
| --- | --- | --- |
| `build_profile_follow_lan_rootfix_apk.py` | r12b | 关注按钮直接可见性、动作分派及内网配置 |
| `build_self_profile_lan_apk.py` | 已验收直接可见性内网包 | 本人原生资料路由（v2 正确方法调用） |
| `build_self_profile_public_apk.py` | 已验收本人资料内网 v2 | 公网配置 |
| `build_title_cntips_apk.py` | 上一行公网成品 | 补回标题 CNtips_b 隐藏 |
| `build_title_cntips_lan_apk.py` | 标题已修复公网成品 | 同功能内网配置 |

打包共用逻辑已独立为 `apk_build_common.py`，不再依赖作废的 `build_profile_follow_apk.py`。
本人资料构建器还复用已提交的 `build_navigation_apk.py`；Java 方法工具及 AIR UUID 回封方法位于
`../character-carousel/`。未使用的 draw 诊断函数已从最终关注脚本移除。

每个脚本的 `--help` 列出参数；本人资料两步额外要求 `--report`，其 Java 编译器 `javac` 必须在 PATH。
其他三步显式传入 `--javac`。工作目录必须是任务专用新目录，输出不得覆盖已有成品；签名只传环境变量名称，
密码由本机 DPAPI 凭据在签名进程内加载，退出即清理。

这些脚本保留了产生已验收 SWF 的逐步方法，并通过精确哈希拒绝错误输入。重新回封会生成新 UUID，APK 哈希不会与历史中间产物相同；
不能盲目把新中间 APK 喂给下一个锁定旧哈希的脚本，也不能复用旧 UUID。需要从旧层完整重建时，须显式整理为累计 SWF 方法移植并核对所有层；
普通新增修改直接从当前已验收包继续，无需重跑历史步骤。

验收记录与原始构建报告分开保存，避免把“脚本运行成功”写成“真机已通过”。未来构建器仍应生成候选状态，不能自动继承本次用户验收。
