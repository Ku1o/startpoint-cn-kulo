# 三会话整合与分类测试清单

2026-09-13 分类交付更新：用户确认“可以了”并要求按功能大类分成多个 commit 推送 GitHub、核对本地同步并制作云服整合包。本次运行交付范围为 39 个文件，包含原 38 个文件和两池注意事项第 3 分包；最终 CDN 版本仍为 `.107`。iOS 商店及觉醒刷新已由原任务独立提交 `d97741f7aeb6b561643f25e39df30252649eb252`，并依据原任务用户明确确认登记为 `user_accepted`。本次其余各类独立提交，具体提交及包摘要见最终交付记录。

用户已确认旧空更新修复、`.106` 入手来源及深渊纪录更新部署完成，本次包不重复纳入其专属文件；它们作为已部署基础。当前闪退诊断、客户端重新下载操作及真实玩家存档导入均不在本轮交付操作范围内。下面的未提交、未打包和离线登记说明保留为首次同步时的历史记录，不代表当前状态。

2026-09-13 后续测试修复：已追加 `.107` 第 3 分包，修复深渊池与竞速池“注意事项”多行叠字，版本保持不变，正文及卡池规则保留。第 3 包和最新 manifest 已同步本地，Android/iOS 实际下载校验通过；客户端重新获取资源由用户处理。见[修复记录](../../assets/asset-patch/audit/gacha-note-layout-1.4.107/README.md)。下方 38 文件/两包统计保留首次整合记录。

2026-09-13，已接收“核查武器限制与木人血量”“觉醒修复及性能优化”“审查作者新内容并选择性融合”的已完成内容。当前共斗 93.38% 加载闪退诊断、诊断日志导出、诊断 APK 和相关实验均排除；未实现的长列表按需加载也不算本次功能。

源仓库为 `F:/codex/startpoint-cn-private-clean`，`staging@0691fef4208bb56263984fcfbc2a4dae846cc188`，与 `origin/staging` 一致。本轮依据用户“先同步到本地”的要求，核对现有未提交改动后冻结明确的文件集，不新增提交或推送、不合并 main、不制作云服覆盖包或部署云服。

**38 个运行文件已同步到 `F:/startpoint-cn-main`，36 个原文件已备份，新增两份 CDN ZIP，无删除。有效资源版本为 1.4.107。** 同步阶段本地业务服务未运行；用户随后要求启动测试，已于 2026-09-13 11:07 启动 PID 26440，8001/8003 正常监听。实际 HTTP 接口、两分包下载哈希和真实服务 V2 只读导出均通过，现在可连接本地开始游戏测试。启动证据见工作目录 `local-server-start.json` 与 `live-service-verification.json`；未对真实存档执行导入。

## 测试前置条件

1. 本地运行服务已启动，使用连接本地的客户端。Android 沿用[已登记的商店优化 LAN APK](../../outputs/shop-first-open-lan-test-20260913/StarPoint-CN-1.8.1-shop-first-open-lan-test-20260913.apk)，包含商店优化及觉醒页刷新。
2. 当前 `.106 → .107` 应取得三份分包，总计 **61,484,779 字节，约 61.48 MB**。第 3 包只有 2,148 字节，用于两池注意事项排版修复；原前两包保留。客户端资源获取由用户自行处理。
3. [Android 公网 APK](../../outputs/shop-first-open-public-20260913/StarPoint-CN-1.8.1-shop-first-open-public-20260913.apk) 和 [iOS 公网 IPA](F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-shop-first-open-public-20260913-unsigned.ipa)仍连接公网；本地同步不会更新其公网服务。iOS 可先测独立的商店/觉醒页客户端行为，完整 `.107` 内容需连接提供本次资源的服务后再测。
4. iOS 商店累计版本轮按用户请求登记为 `accepted_offline`，完整 AOT 101214 方法；未宣称真机验收，见[接收记录](../../client-patch/ACCEPTANCE-IOS-SHOP-FIRST-OPEN-20260913.md)。Android 继续使用原已登记累计包，没有安装或选入任何诊断版。

## 分类测试

| 类别 | 本次内容 | 游戏中重点检查 |
| --- | --- | --- |
| 资源更新 | `.106 → .107` 三分包，583 个归档成员（第三包覆盖两份说明）；其中作者包 579 项 | 两池注意事项长段落换行、底部内容及滚动正常；角色图、立绘、技能 cut-in、声音可用，无缺图或资源错误。 |
| 三把武器 | 木灵大剑 4010014 恢复 3 次；无名之弓 2040001 恢复 10 次；埃俄罗斯之弓 5040009 第二段回充恢复 10 次 | 详情描述与战斗触发上限一致；达到上限后相应效果不继续触发。埃俄罗斯之弓原第一段仍为 10 次。 |
| 新练习关与战斗记录 | 在“结实假人”入口增加 1101“高血量木人·无”；在“结实假人们”入口增加 1102“高血量木人们·无” | 两关均为无属性、原版 100 倍 HP、10 分钟；新关位于各自原入口。检查完整结算、约 7 分钟退出、战斗记录中的新名称/用时/总伤害/角色伤害；原关记录独立。 |
| 四名新角色 | 校碧安卡 119989、校希尔媞 149989、校奈芙提姆 169989、盾牌座 149988；每名两板共 41 节点 | 获取后持有列表、详情、技能、两板、进化前后资源均正常；校奈芙重点测进战斗、召唤球、球在场增益与球消失后的状态，确认作者参数修正。 |
| 十五位小 Boss | 完整接入作者角色数据、六能力、技能与配套资源，名单见下方 | 逐角色打开详情、切换形态、学习二板、发动技能，核对能力描述与表现；检查多球/召唤、位移、增益、抗性等对应机制，不能只抽一个代表确认全部。 |
| 既有角色修订 | 光杰拉德强化技最近敌人当前 HP 5% 伤害及低于最大 HP 5% 的斩杀；夏日白 Fever 追加全场攻击 75 倍；冰雪罗尔夫三处觉醒立绘定位 | 两形态强化技的百分比/斩杀条件；Fever 内外技能差异及对应说明；冰雪罗尔夫立绘无错位。本轮保留未批准的其他平衡项原值。 |
| 二板开放 | 水灵幽魂、风暴恶魔拉比、Sec-2600Li、哈宁绿、海茵莱特、维尔努斯、吉布西兹、克拉格的二板开放日期改为 2000-01-01 | 在当前游戏时间下可按原学习资格进入二板，原有等级、角色持有和材料要求正常。 |
| 卡池与兑换 | 作者 MOD 概率、排序、标红；普通角色兑换沿用本服；修正注意事项 | 按下方规则核对两池概率列表和兑换资格，少量正常抽取检查结果与角色显示。概率精确性已通过配置和真实构造器校验。 |
| 语音与美术 | 火狮王、基诺维正式语音；指定角色 UI、克劳德肖像、竞速封面/横幅、两张蓝票图标 | 技能语音无试用音，准备音正常；火狮王五条正式技能录音采用原生连续编号。额外准备音 `_alt_1` 仅保留资源，本轮没有实现额外轮换。检查蓝票和其他既有自定义道具图标。 |
| 觉醒即时刷新 | 任务响应后刷新角色、觉醒等级和能力页签；服务端资格查询减负 | 完成/领取全部任务后，留在同一页面即可开放能力觉醒；重复进入和重复请求不重复扣费或领奖。官方角色与夏日莉莉丝、菲莉亚、暗龙等扩展角色分别回归。 |
| 扩展二板与旧存档 | 保留整板状态、旧进度修复、资格和称号补发机制 | 一板满而二板未满时继续正常学习；扩展二板点满后完整退出并重新登录一次，确认节点、板位与羁绊完成状态不倒退，无 C8601/F1009 或重新可学习。 |
| 查询性能与商店 | 觉醒/称号按需统计和批量查询；客户端活动商品索引、首页存在性短路 | 大存档连续开觉醒页、学习/觉醒及切换账号，观察延迟和状态新鲜度；冷启动首次打开商店、活动兑换、外传兑换，检查商品顺序、价格、库存、限购、过期活动和箱池入口。实际设备耗时需实测，不把历史样本的接口降幅等同整服 CPU 降幅。 |
| 存档兼容 | 四个新角色、164 个节点及两个新练习关使用既有格式，无新表或字段 | 测试存档在本次 `.107` 数据环境中导出、导入后，新角色/两板、练习进度和记录可识别；目标账号身份保持。V2 保存完整历史，V1 沿用既有部分存档语义。破坏性导入只用测试存档。 |

新木人本体为 **100,047,977,312 HP，约 1000 亿**；群体关四个小木人每个 **100,024,515,359 HP**，初始合计 **500,146,038,748 HP，约 5000 亿**。回血机制保持。原版 91 条客户端练习关及服务端原 98 条配置保留；原七属性木人仍是原 HP 和 3 分钟，旧“原版全部乘十”的方案已经撤回。

十五位小 Boss：红蝮蛇 119993、哈宁红Z 119994、炎枪见习兵 119995、冰冻虎鲸 129993、哈宁蓝Z 129994、彷徨铠甲·水 129995、蓝色海妖 129996、水灵幽魂 129998、机枪魔块·雷 139996、疾风狂熊 149991、彷徨铠甲·风 149992、哈宁绿 149993、风暴恶魔拉比 149994、Sec-2600Li 159999、黑之下忍 169993。

卡池核对值：

- 深渊最新五位各 0.25%，排最前且标红、不可兑换；十五位小 Boss 各 0.2%，在巴萨拉卡之后且标红、不可兑换。
- 水杰拉尔、秋灯九尾各 0.1%，开放兑换；深渊歼灭者 179981 仍为 0% 且可兑换。深渊 MOD 总概率 6.55%。
- 竞速 43 位可抽 MOD 各 1%，共 43%，排前并标红；其余 25 位为 0%。其中 179982–179986 五位零概率角色不可兑换。
- 两池继续排除原核定的 26 个非扭蛋角色；保留 215 位普通五星不可兑换、7 位四星联动可兑换。注意事项须与以上最终配置一致。

## 本轮已完成的验证

- `npm run build` 成功；觉醒、称号、二板、任务及存档专项 **37/37** 通过。603 个已有构建文件回读与构建前一致，说明交付的 12 个 JS 均对应已核对的源码。
- 作者包原字节保留；581 个 ZIP 成员 CRC/路径检查通过，两包无成员覆盖。579 项作者资源在最终有效链上的字节全部匹配，Android/iOS 配对证据随原作者审计保留。
- 19 个完整接入角色、164 个新节点及两池 476/500 条最终行通过真实 accessor、原生卡池构造器及兑换资格校验；原权威覆盖文件与运行目录一致。
- 使用源仓与同步后的运行目录各做一轮隔离测试，真实 HTTP 下载与 multipart 导入覆盖旧/新 V1、V2、两关结算/退出/记录、四个新角色和全部 164 节点。每次导入前备份匹配原目标；非法 JSON、错误指纹拒绝且目标不变；外键和数据库完整性通过。没有覆盖真实玩家存档。
- 同步后 38 个文件逐一匹配冻结交付 SHA-256。运行目录实际 `/get_path`、`/version_info` 处理器对 Android/iOS 都返回同一边的两包及正确大小，当前版本保持空更新；未启动业务监听，未做真实在运服务下载或真机测试。
- Android 公网/LAN 身份重新核验；iOS 成品独立检查及新登记通过，旧登记仍通过；缺授权、待验收状态、错误完整 ABC、错误 AOT 方法数四个负例均拒绝。

## 文件、备份及保留状态

完整冻结清单、每个目标前后 SHA-256、脚本和验证结果位于 [本轮工作目录](F:/codex/work/three-session-integration-20260913)。其中 [release-manifest.json](F:/codex/work/three-session-integration-20260913/release-manifest.json) 是本轮精确同步依据；作者早期审计中的第 1 分包旧哈希已被百倍木人修订替代，不能直接沿用旧清单。

回滚备份：`F:/startpoint-cn-main/.codex-backups/20260913-105318-three-session-integration/`。原 36 个目标文件按相对路径保存，两份新 ZIP 在清单中标为新增；本轮无删除。

未改动 `.env`、真实数据库、日志、依赖或其他工作区内容。检测到运行目录另有七个既存 JSON 差异，均保留，详见工作目录 `dependency-closure.json`；未将源仓历史遗留的无依赖 JS 全量镜像过去。`.cdn` 全程只读；发现既存 `archive-ios-diff/pinball-1.4.83-1.4.84-2-bbbc92be.zip`，仅记录于 `cdn-boundary.json`，没有移动、删除或作为本次 `.107` 资源的来源。

其他未提交工具、美术审计、历史客户端资料及正在进行的加载诊断工作继续保留。云端待部署状态不变，见 [PENDING-CLOUD-OVERLAY.md](PENDING-CLOUD-OVERLAY.md)。

## 本轮精确同步路径

以下路径均相对 `F:/startpoint-cn-main/`；SHA-256 见上述冻结清单。

```text
assets/asset-patch/active/pinball-1.4.106-1.4.107-1-weapon-caps-practice-hp.zip
assets/asset-patch/active/pinball-1.4.106-1.4.107-2-author858-selected.zip
assets/asset-patch/manifest.json
assets/cdndata/character.json
assets/cdndata/character_text.json
assets/cdndata/character_text_rank_p5b.json
assets/character.json
assets/gacha.json
assets/gacha_cnmod.json
assets/gacha_rank_p5b.json
assets/mana_board.json
assets/mana_node.json
assets/practice_quest.json
out/data/domains/character.js
out/data/domains/character_clear.js
out/data/domains/mission.js
out/data/domains/quest.js
out/lib/mission/awake-settlement.js
out/lib/mission/awake-unlock-response.js
out/lib/mission/awake-unlock.js
out/lib/mission/computer-awake.js
out/lib/mission/computer-degree.js
out/lib/mission/settlement.js
out/routes/api/character/mana.js
out/routes/api/mission.js
src/data/domains/character.ts
src/data/domains/character_clear.ts
src/data/domains/mission.ts
src/data/domains/quest.ts
src/lib/mission/awake-settlement.ts
src/lib/mission/awake-unlock-response.ts
src/lib/mission/awake-unlock.ts
src/lib/mission/computer-awake.ts
src/lib/mission/computer-degree.ts
src/lib/mission/settlement.ts
src/lib/mission/types.ts
src/routes/api/character/mana.ts
src/routes/api/mission.ts
```
