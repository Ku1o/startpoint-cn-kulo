# 深渊连战 Boss HP 验收报告

> 结论：**静态严格验收通过**。本报告证明本次构建的表结构、HP 回读公式、逐组件目标和解析链均通过门禁；**它不等同于真机实战验证，也不证明已经发布或落库**。

## 一眼结论

- 种子：`46454236`；层数：`30`；难度：`hell`；敌等级：`ramp`
- HP profile：`linear_boss_hp_30e8_150e8`；诅咒前基础总HP：`30亿→150亿`；严格递增：`是`；血量诅咒：`基础目标之后单独应用`
- Boss 关绝对证据：`29/29`
- 最终代理组件：`0`；源代理组件：`0`；未归一豁免：`0`；解析链失败：`0`
- 最大绝对回读误差：`9.03519 HP`
- identity 引用闭包：`3` 个，覆盖 `3` 关
- Boss 封面静态来源闭包：`29/29`
- 客户端内置 HP 曲线基线：`713007008fc91f55555eefe72e913380a29664e23b8e0ac2cfdca95e450f5370`（22 份客户端交叉核对）
- 验证范围：`static_dry_run`；真机实战验证：`否（gameplay_verified=false）`
- 回执 SHA-256：`489794f248b0cecca29e52c7dfd1464cda5228776dacc9f336a18f286018e485`
- 工具 SHA-256：`8707808f4c06a4a6ff29185c858ad82bdd59cecf556c96dde4790d6245438b7e`

## 放行红线

- [x] 每个 Boss 关都有绝对 HP 证据
- [x] 代理证据、target_exempt 与解析链失败均为 0
- [x] 每个组件及整关回读均在回执声明的明确容差内
- [x] Boss 重抽/原生专场政策与当前工具一致
- [ ] 真机进入关卡、阶段切换与胜利结算（本报告无法替代）

## 覆盖分布

| 维度 | 数量 |
|---|---:|
| family `conductor` | 1 |
| family `general` | 16 |
| family `kraken` | 1 |
| family `orochi_ex` | 1 |
| family `standard` | 8 |
| family `touyakiren_ceo` | 1 |
| family `wind_sphere` | 1 |
| channel `boss_level` | 16 |
| channel `special_bundle` | 5 |
| channel `standard_dsl` | 8 |

## 逐关逐阶段明细

第 1 战是无 Boss 小怪房，不进入 Boss HP 绝对证据计数。以下基础 HP 是诅咒前目标，最终 HP 是血量诅咒之后的目标；阶段栏按实际出现次数列出每个胜利条件组件。

| 层 | family / 通道 | Boss | 阶段组件（阶段: 最终目标 / 回读 / 误差） | 基础→最终总HP | 诅咒（HP倍率） |
|---:|---|---|---|---:|---|
| 2 | `general` / `boss_level` | bug1 | bug1 [main]: 3e+09 / 3e+09 / 0.6207 | 3e+09→3e+09 | 「元素滞钝」雷属性伤害减半 (×1) |
| 3 | `general` / `boss_level` | lich_wind_single | lich_wind_single [main]: 3.42857e+09 / 3.42857e+09 / -3.30013 | 3.42857e+09→3.42857e+09 | 「混相禁域」火伤害减半·雷伤害减半·风伤害减半·光伤害减半·暗伤害减半 (×1) |
| 4 | `general` / `boss_level` | hermit_crab_water_single | hermit_crab_water_single [main]: 3.85714e+09 / 3.85714e+09 / 5.1283 | 3.85714e+09→3.85714e+09 | 「元素滞钝」火属性伤害减半 (×1) |
| 5 | `general` / `boss_level` | administrator_light_single | administrator_light_single [main]: 4.28571e+09 / 4.28571e+09 / -1.41207 | 4.28571e+09→4.28571e+09 | 「混相禁域」火伤害减半 (×1) |
| 6 | `standard` / `standard_dsl` | steampunk_fire_single | steampunk_fire_single [form[0]]: 1.41429e+09 / 1.41429e+09 / -0.0857146<br>steampunk_fire_single [form[1]]: 3.3e+09 / 3.3e+09 / -0.2 | 4.71429e+09→4.71429e+09 | 「亡者不屈」减益免疫·能耐50% (×1) |
| 7 | `kraken` / `special_bundle` | kraken_rush | kraken_rush [main]: 4.37143e+09 / 4.37143e+09 / 0.930732 | 5.14286e+09→4.37143e+09 | 「能力抑制」能力耐性40% 「嗜血狂潮」敌攻×1.15·血-15% (×0.85) |
| 8 | `general` / `boss_level` | guardian_golem_fire_single_tower_unique_9th | guardian_golem_fire_single_tower_unique_9th [main]: 5.57143e+09 / 5.57143e+09 / 0.884893 | 5.57143e+09→5.57143e+09 | 「三相封界」火·雷·风属性伤害降至1/10(只留水·光·暗) 「深渊法阵」狂风领域·轻风0.25·8秒·方向2 (×1) |
| 9 | `standard` / `standard_dsl` | halfanv3_boss_expert | halfanv3_boss_expert [form[0]]: 1.5e+10 / 1.5e+10 / 0 | 6e+09→1.5e+10 | 「深渊重甲」韧性×9·弹耐40% 「血肉高墙」敌血×2.5 (×2.5) |
| 10 | `general` / `boss_level` | middle_boss_dragon_smr20_raid3 | middle_boss_dragon_smr20_raid3 [main]: 6.42857e+09 / 6.42857e+09 / -0.571428 | 6.42857e+09→6.42857e+09 | 【风暴】「深渊法阵」狂风领域·轻风0.15·20秒·方向2 「深渊逆鳞」敌攻×1.2·强化弹射易伤40% (×1) |
| 11 | `touyakiren_ceo` / `special_bundle` | touyakiren_ceo_expert_90 | touyakiren_ceo_expert_90 [main]: 3.42857e+09 / 3.42857e+09 / 5.16855 | 6.85714e+09→3.42857e+09 | 【速攻】「玻璃深渊」敌攻×1.4·血-50% 「时之枷锁」限时3分 (×0.5) |
| 12 | `standard` / `standard_dsl` | steampunk_water_hard_multi | steampunk_water_hard_multi [form[0]]: 7.28571e+09 / 7.28571e+09 / -0.714286 | 7.28571e+09→7.28571e+09 | 「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 (×1) |
| 13 | `general` / `boss_level` | maou2 | maou2 [main]: 7.71429e+09 / 7.71429e+09 / -0.285714 | 7.71429e+09→7.71429e+09 | 「元素滞钝」风属性伤害减半 「深渊法阵」重力领域·引力2·10秒·左侧/上方·复合 (×1) |
| 14 | `general` / `boss_level` | yokai_emaki_big_boss_single | yokai_emaki_big_boss_single [main]: 8.14286e+09 / 8.14286e+09 / -5.23771 | 8.14286e+09→8.14286e+09 | 「深渊法阵」攻击领域·攻击+100%/直击+50%/光耐性+100%·复合 「层叠龙鳞」直击抗性×50层（减50%） (×1) |
| 15 | `standard` / `standard_dsl` | steampunk_another_multi、steampunk_another_foom2_multi | steampunk_another_multi [form[0]]: 1.37143e+09 / 1.37143e+09 / -0.0285718<br>steampunk_another_multi [form[1]]: 2.74286e+09 / 2.74286e+09 / -0.0571427<br>steampunk_another_multi [form[2]]: 2.05714e+09 / 2.05714e+09 / -0.0428572<br>steampunk_another_multi [form[3]]: 6.85714e+08 / 6.85714e+08 / -0.0142859<br>steampunk_another_foom2_multi [form[0]]: 1.71429e+09 / 1.71429e+09 / -0.285714 | 8.57143e+09→8.57143e+09 | 「亡者不屈」减益免疫·能耐50% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 16 | `general` / `boss_level` | white_tiger_ghost_thunder_single_tower | white_tiger_ghost_thunder_single_tower [main]: 9e+09 / 9e+09 / 3.47095 | 9e+09→9e+09 | 「三相封界」水·光·暗属性伤害降至1/10(只留火·雷·风) 「深渊法阵」狂风领域·微风0.1·5秒·方向2 「不屈龙心」减益耐性×50层（普通减益几乎无法命中；强制赋予除外） (×1) |
| 17 | `general` / `boss_level` | high_epuration_boss_single | high_epuration_boss_single [main]: 9.42857e+09 / 9.42857e+09 / -0.571428 | 9.42857e+09→9.42857e+09 | 【风暴】「混相禁域」雷伤害降至1/10 「深渊法阵」狂风领域·轻风0.125·15秒·方向2 「深渊逆鳞」敌攻×1.2·能力易伤40% 「魔力枯竭」FEVER需求×3 (×1) |
| 18 | `standard` / `standard_dsl` | guardian_golem_another_water_ex | guardian_golem_another_water_ex [form[0]]: 7.88571e+09 / 7.88571e+09 / -0.114285<br>guardian_golem_another_water_ex [form[1]]: 1.97143e+09 / 1.97143e+09 / -0.0285718 | 9.85714e+09→9.85714e+09 | 「直击偏转」直击耐性40% 「术式扰流」技能耐性40% 「能力抑制」能力耐性40% (×1) |
| 19 | `standard` / `standard_dsl` | steampunk_dark_multi | steampunk_dark_multi [form[0]]: 1.02857e+10 / 1.02857e+10 / -0.714285 | 1.02857e+10→1.02857e+10 | 【偏转阵列】「直击偏转」直击耐性40% 「术式扰流」技能耐性40% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 20 | `general` / `boss_level` | guardian_totem_another | guardian_totem_another [main]: 2.67857e+10 / 2.67857e+10 / -0.659229 | 1.07143e+10→2.67857e+10 | 【风暴】「混相禁域」火伤害减半·风伤害降至1%·光伤害降至1% 「深渊法阵」狂风领域·强风0.5·10秒·方向1 「深渊逆鳞」敌攻×1.3·强化弹射易伤50% 「血肉高墙」敌血×2.5 (×2.5) |
| 21 | `standard` / `standard_dsl` | epuration_boss_highest_single | epuration_boss_highest_single [form[0]]: 5.57143e+09 / 5.57143e+09 / -0.428572<br>epuration_boss_highest_single [form[1]]: 5.57143e+09 / 5.57143e+09 / -0.428572 | 1.11429e+10→1.11429e+10 | 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 22 | `general` / `boss_level` | ghost_fox_single_tower | ghost_fox_single_tower [main]: 5.78571e+09 / 5.78571e+09 / 2.93879 | 1.15714e+10→5.78571e+09 | 「三相封界」火·光·暗属性伤害降至1/10(只留水·雷·风) 「深渊法阵」重力领域·引力1.5·10秒·左侧/上方 「深渊壁垒」全系耐性30% 「玻璃深渊·残响」敌血-50%（攻击增幅已摘） (×0.5) |
| 23 | `general` / `boss_level` | benzaiten | benzaiten [main]: 3e+10 / 3e+10 / 3.20108 | 1.2e+10→3e+10 | 【风暴】「深渊法阵」狂风领域·狂风1·5秒·方向2 「深渊逆鳞」敌攻×1.3·强化弹射易伤50% 「不屈龙心」减益耐性×50层（普通减益几乎无法命中；强制赋予除外） 「血肉高墙」敌血×2.5 (×2.5) |
| 24 | `conductor` / `special_bundle` | boss_conductor_single | boss_conductor_single [main]: 1.05643e+10 / 1.05643e+10 / -7.92654 | 1.24286e+10→1.05643e+10 | 「嗜血狂潮」敌攻×1.15·血-15% 「亡者不屈」减益免疫·能耐50% 「魔力枯竭」FEVER需求×3 (×0.85) |
| 25 | `orochi_ex` / `special_bundle` | orochi_ex | orochi_ex [phase[1]]: 1.34218e+09 / 1.34218e+09 / 0<br>orochi_ex [phase[2]]: 2.93891e+09 / 2.93891e+09 / -0.00598049<br>orochi_ex [phase[3]]: 2.14748e+09 / 2.14748e+09 / 0 | 1.28571e+10→6.42857e+09 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% 「玻璃深渊」敌攻×1.4·血-50% (×0.5) |
| 26 | `general` / `boss_level` | mod_fb_water_s1、mod_fb_sand_s1、mod_fb_eye_s1 | mod_fb_water_s1 [main]: 2.41724e+09 / 2.41724e+09 / 3.09893<br>mod_fb_sand_s1 [main]: 2.67756e+09 / 2.67756e+09 / 4.23736<br>mod_fb_eye_s1 [main]: 6.19806e+09 / 6.19806e+09 / -2.78329 | 1.32857e+10→1.12929e+10 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% 「嗜血狂潮」敌攻×1.1·血-15% (×0.85) |
| 27 | `general` / `boss_level` | alter_sheep_materia_raid1 | alter_sheep_materia_raid1 [main]: 2.91429e+10 / 2.91429e+10 / -4.49807 | 1.37143e+10→2.91429e+10 | 【绞肉机】「血肉高墙」敌血×2.5 「嗜血狂潮」敌攻×1.15·血-15% 「深渊重甲」韧性×9·弹耐40% 「深渊法阵」技能伤害领域·技能伤害 「元素禁壁」光属性伤害降至1% (×2.125) |
| 28 | `wind_sphere` / `special_bundle` | wind_sphere | wind_sphere [main]: 1.41429e+10 / 1.41429e+10 / -0.473566 | 1.41429e+10→1.41429e+10 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% 「能力抑制」能力耐性40% (×1) |
| 29 | `standard` / `standard_dsl` | abyss_cloud、abyss_cloud_p3 | abyss_cloud [form[0]]: 5.46429e+09 / 5.46429e+09 / -0.0857134<br>abyss_cloud [form[1]]: 1.275e+10 / 1.275e+10 / -0.200001<br>abyss_cloud_p3 [form[0]]: 1.82143e+10 / 1.82143e+10 / -0.285713 | 1.45714e+10→3.64286e+10 | 「血肉高墙」敌血×2.5 「术式扰流」技能耐性40% 「能力抑制」能力耐性40% 「亡者不屈」减益免疫·能耐50% (×2.5) |
| 30 | `general` / `boss_level` | runaway_romero | runaway_romero [main]: 1.5e+10 / 1.5e+10 / -5.96173 | 1.5e+10→1.5e+10 | 「深渊法阵」充能领域·充能-30% 「绝对壁垒」技能完全免疫 「三重壁垒」能力·强化弹射·技能三重免疫(只剩直击能打) 「深渊壁垒」全系耐性30% 「层叠龙鳞」强化弹射抗性×90层（减90%） (×1) |

## Boss 封面静态审计

封面按实际 Boss 来源场地解析官方 240×188 quest 大图；混搭层不使用地形 donor 的图片。资源存在性已在构建期回读，但这仍不等于真机 UI 验证。

| 层 | Boss 来源场地 | quest c5 封面 | 证据 |
|---:|---|---|---|
| 2 | `main_5_10_1` | `quest/thumbnail/world_mecha/battle_5_10_1` | ex:exact_field |
| 3 | `lich_wind_single` | `quest/thumbnail/world_tree/battle1_8_2` | ex:exact_boss_identity |
| 4 | `hermit_crab_water_single` | `quest/thumbnail/world_sea/battle_3_11_2` | ex:exact_boss_identity |
| 5 | `administrator_light_single` | `quest/thumbnail/world_mecha/battle_5_13_2` | ex:exact_boss_identity |
| 6 | `steampunk_fire_4` | `quest/thumbnail/advent_event/steam_robot_fire/4` | boss_battle:exact_field |
| 7 | `rush_02_kraken` | `quest/thumbnail/rush_event/combat_diver_02/combat_diver_02_7` | rush:exact_field |
| 8 | `tower_dungeon_area_10_9_2` | `quest/thumbnail/expert_single_event/guardian_golem_100` | practice:exact_boss_visual_identity |
| 9 | `halfanv3_expert` | `quest/thumbnail/world_story_event/challenge_single_battle/anv3half/challenge_boss_anv3half` | world_story:exact_field |
| 10 | `middle_boss_dragon_smr20_raid3` | `quest/thumbnail/raid_event/raid_event_quest_thumbnail_02_003` | raid:exact_field |
| 11 | `cyberpunk01_re01_21_hell` | `quest/thumbnail/expert_single_side_story/cyberpunk01_re01_21` | practice:exact_field |
| 12 | `steampunk_water_hard` | `quest/thumbnail/hard_multi/hard_multi_steam_robot_water/1` | hard_multi:exact_field |
| 13 | `main_7_14_2` | `quest/thumbnail/world_light/battle_7_14_2` | main:exact_field |
| 14 | `yokai_emaki_01_16` | `quest/thumbnail/world_story_event/multi_battle/yokai_emaki_01/multi_big_boss_2` | story_event:exact_field |
| 15 | `steampunk_another` | `quest/thumbnail/advent_event/steam_robot_another/5` | boss_battle:exact_field |
| 16 | `tower_dungeon_area_10_11_2` | `quest/thumbnail/expert_single_event/white_tiger_ghost_100` | practice:exact_boss_visual_identity |
| 17 | `main_11_10_2` | `quest/thumbnail/world_11/battle_11_10_2` | ex:exact_field |
| 18 | `solo_time_attack_blue1` | `quest/thumbnail/solo_time_attack/golem_blue` | solo_time_attack:exact_field |
| 19 | `steampunk_dark_4` | `quest/thumbnail/advent_event/steam_robot_dark/4` | boss_battle:exact_field |
| 20 | `main_8_8_1` | `quest/thumbnail/world_hell/battle_8_8_1` | ex:exact_field |
| 21 | `epuration_boss_highest` | `quest/thumbnail/advent_event/boss_epuration_event/4` | advent:exact_field |
| 22 | `tower_dungeon_area_10_4_2` | `quest/thumbnail/multi_battle/multi1_19_1` | score_attack:exact_field |
| 23 | `main_10_8_1` | `quest/thumbnail/world_10/battle_10_8_1` | score_attack:exact_field |
| 24 | `cyberpunk01_10` | `quest/thumbnail/world_story_event/single_battle/cyberpunk01/single_15` | world_story:exact_field |
| 25 | `multi_normal_1_20_4` | `quest/thumbnail/multi_battle/multi1_20_3` | boss_battle:exact_field |
| 26 | `mod_five_boss_var_s1_direct_a` | `quest/thumbnail/multi_battle/mod_five_boss` | boss_battle:exact_field |
| 27 | `raid_alter_sheep_materia1` | `quest/thumbnail/raid_event/raid_event_quest_thumbnail_05_001` | raid:exact_field |
| 28 | `wind_sphere` | `quest/thumbnail/time_attack_event/green_01` | practice:exact_field |
| 29 | `abyss_cloud` | `quest/thumbnail/raid_event/raid_event_quest_thumbnail_07_001` | raid:exact_field |
| 30 | `advent_z_collabo` | `quest/thumbnail/advent_event/Zcollab/4` | advent:exact_field |

## 最大误差楼层（最多 10 层）

| 层 | family | Boss | 阶段组件 | 目标 HP（基线→实战） | 回读 HP（基线→实战） | 最大绝对误差 HP | 通道 |
|---:|---|---|---:|---:|---:|---:|---|
| 11 | `touyakiren_ceo` | touyakiren_ceo_expert_90 | 1 | 6.85714e+09→3.42857e+09 | 6.85714e+09→3.42857e+09 | 9.03519 | `special_bundle` |
| 7 | `kraken` | kraken_rush | 1 | 5.14286e+09→4.37143e+09 | 5.14286e+09→4.37143e+09 | 8.73701 | `special_bundle` |
| 24 | `conductor` | boss_conductor_single | 1 | 1.24286e+10→1.05643e+10 | 1.24286e+10→1.05643e+10 | 7.92654 | `special_bundle` |
| 30 | `general` | runaway_romero | 1 | 1.5e+10→1.5e+10 | 1.5e+10→1.5e+10 | 5.96173 | `boss_level` |
| 14 | `general` | yokai_emaki_big_boss_single | 1 | 8.14286e+09→8.14286e+09 | 8.14286e+09→8.14286e+09 | 5.23774 | `boss_level` |
| 4 | `general` | hermit_crab_water_single | 1 | 3.85714e+09→3.85714e+09 | 3.85714e+09→3.85714e+09 | 5.1283 | `boss_level` |
| 26 | `general` | mod_fb_water_s1、mod_fb_sand_s1、mod_fb_eye_s1 | 3 | 1.32857e+10→1.12929e+10 | 1.32857e+10→1.12929e+10 | 4.553 | `boss_level` |
| 27 | `general` | alter_sheep_materia_raid1 | 1 | 1.37143e+10→2.91429e+10 | 1.37143e+10→2.91429e+10 | 4.49807 | `boss_level` |
| 16 | `general` | white_tiger_ghost_thunder_single_tower | 1 | 9e+09→9e+09 | 9e+09→9e+09 | 3.47114 | `boss_level` |
| 23 | `general` | benzaiten | 1 | 1.2e+10→3e+10 | 1.2e+10→3e+10 | 3.36245 | `boss_level` |

## 当前保守边界

无法证明身份引用闭包、阶段胜利条件或资源完整性的 Boss 不会被包装成成功；严格模式会重抽或明确失败。继续增加新家族只提升阵容多样性，不是本报告放行的必要条件。

## 建议

此报告适合作为 dry-run、代码审查和金丝雀前置凭据。若要把结论提升为“可正式游玩”，仍应至少真机抽测普通 Hit/Fix、Standard DSL、多阶段专用 Boss 与 Sphere 各一关。
