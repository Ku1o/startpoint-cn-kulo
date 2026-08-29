# 深渊连战 Boss HP 验收报告

> 结论：**静态严格验收通过**。本报告证明本次构建的表结构、HP 回读公式、逐组件目标和解析链均通过门禁；**它不等同于真机实战验证，也不证明已经发布或落库**。

## 一眼结论

- 种子：`2026082902`；层数：`30`；难度：`hell`；敌等级：`ramp`
- HP profile：`linear_boss_hp_30e8_150e8`；诅咒前基础总HP：`30亿→150亿`；严格递增：`是`；血量诅咒：`基础目标之后单独应用`
- Boss 关绝对证据：`29/29`
- 最终代理组件：`0`；源代理组件：`0`；未归一豁免：`0`；解析链失败：`0`
- 最大绝对回读误差：`12.5822 HP`
- identity 引用闭包：`1` 个，覆盖 `1` 关
- Boss 封面静态来源闭包：`29/29`
- 客户端内置 HP 曲线基线：`713007008fc91f55555eefe72e913380a29664e23b8e0ac2cfdca95e450f5370`（22 份客户端交叉核对）
- 验证范围：`static_dry_run`；真机实战验证：`否（gameplay_verified=false）`
- 回执 SHA-256：`fa75716ccc3cb0cc15d1c6e52967c92b25a058b7bfe3beb942380873afcc05a2`
- 工具 SHA-256：`796fa6f820b93ea0fa439ecb19e2284a206f932666dc9f6a92cdfbeb588b6623`

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
| family `holy_sphere` | 1 |
| family `kraken` | 1 |
| family `orochi_ex` | 1 |
| family `standard` | 8 |
| family `touyakiren_ceo` | 1 |
| channel `boss_level` | 16 |
| channel `special_bundle` | 5 |
| channel `standard_dsl` | 8 |

## 逐关逐阶段明细

第 1 战是无 Boss 小怪房，不进入 Boss HP 绝对证据计数。以下基础 HP 是诅咒前目标，最终 HP 是血量诅咒之后的目标；阶段栏按实际出现次数列出每个胜利条件组件。

| 层 | family / 通道 | Boss | 阶段组件（阶段: 最终目标 / 回读 / 误差） | 基础→最终总HP | 诅咒（HP倍率） |
|---:|---|---|---|---:|---|
| 2 | `general` / `boss_level` | cobra | cobra [main]: 3e+09 / 3e+09 / 0.6207 | 3e+09→3e+09 | 「元素滞钝」暗属性伤害减半 (×1) |
| 3 | `general` / `boss_level` | treant_single | treant_single [main]: 3.42857e+09 / 3.42857e+09 / -0.0568876 | 3.42857e+09→3.42857e+09 | 「混相禁域」火伤害减半·水伤害减半 (×1) |
| 4 | `general` / `boss_level` | hermit_crab_another_light_single | hermit_crab_another_light_single [main]: 3.85714e+09 / 3.85714e+09 / -0.734477 | 3.85714e+09→3.85714e+09 | 「混相禁域」火伤害减半·水伤害减半·雷伤害减半·光伤害减半 (×1) |
| 5 | `general` / `boss_level` | owl_single_tower | owl_single_tower [main]: 4.28571e+09 / 4.28571e+09 / -1.41207 | 4.28571e+09→4.28571e+09 | 「绝对壁垒」能力完全免疫 「深渊法阵」深渊之水·全场淹水 (×1) |
| 6 | `standard` / `standard_dsl` | variant_empress_wind_form1_single、variant_empress_wind_form2_single | variant_empress_wind_form1_single [form[0]]: 2.35714e+09 / 2.35714e+09 / -0.142857<br>variant_empress_wind_form2_single [form[0]]: 2.35714e+09 / 2.35714e+09 / -0.142857 | 4.71429e+09→4.71429e+09 | 「深渊重甲」韧性×9·弹耐40% (×1) |
| 7 | `kraken` / `special_bundle` | kraken_multi_80 | kraken_multi_80 [main]: 2.57143e+09 / 2.57143e+09 / -4.3685 | 5.14286e+09→2.57143e+09 | 【速攻】「玻璃深渊」敌攻×1.2·血-50% 「时之枷锁」限时3分 (×0.5) |
| 8 | `general` / `boss_level` | hermit_crab_water_single_tower | hermit_crab_water_single_tower [main]: 5.57143e+09 / 5.57143e+09 / 3.47824 | 5.57143e+09→5.57143e+09 | 「三相封界」雷·风·暗属性伤害降至1/10(只留火·水·光) 「深渊法阵」攻击领域·攻击+100%/哨兵254耐性+30%·复合 (×1) |
| 9 | `standard` / `standard_dsl` | halfanv25_big_boss_expert | halfanv25_big_boss_expert [form[0]]: 6e+09 / 6e+09 / 0 | 6e+09→6e+09 | 「术式扰流」技能耐性40% 「能力抑制」能力耐性40% (×1) |
| 10 | `general` / `boss_level` | middle_boss_dragon_anv1_raid3 | middle_boss_dragon_anv1_raid3 [main]: 6.42857e+09 / 6.42857e+09 / -0.571428 | 6.42857e+09→6.42857e+09 | 「深渊法阵」攻击领域·攻击-100% 「深渊壁垒」全系耐性30% (×1) |
| 11 | `touyakiren_ceo` / `special_bundle` | touyakiren_ceo_single | touyakiren_ceo_single [main]: 5.82857e+09 / 5.82857e+09 / 2.97484 | 6.85714e+09→5.82857e+09 | 「直击偏转」直击耐性40% 「嗜血狂潮」敌攻×1.15·血-15% (×0.85) |
| 12 | `general` / `boss_level` | dark_matter_single | dark_matter_single [main]: 1.82143e+10 / 1.82143e+10 / -1.92555 | 7.28571e+09→1.82143e+10 | 「绝对壁垒」技能完全免疫 「血肉高墙」敌血×2.5 (×2.5) |
| 13 | `general` / `boss_level` | white_tiger_ghost_thunder_expert_80 | white_tiger_ghost_thunder_expert_80 [main]: 3.85714e+09 / 3.85714e+09 / 0.802071 | 7.71429e+09→3.85714e+09 | 「玻璃深渊·残响」敌血-50%（攻击增幅已摘） 「亡者不屈」减益免疫·能耐50% (×0.5) |
| 14 | `general` / `boss_level` | guardian_golem_fire_expert_80 | guardian_golem_fire_expert_80 [main]: 8.14286e+09 / 8.14286e+09 / -8.43661 | 8.14286e+09→8.14286e+09 | 「深渊法阵」重力领域·引力1.7·5秒·左侧/上方·复合 (×1) |
| 15 | `standard` / `standard_dsl` | steampunk_another_multi、steampunk_another_foom2_multi | steampunk_another_multi [form[0]]: 1.37143e+09 / 1.37143e+09 / -0.0285718<br>steampunk_another_multi [form[1]]: 2.74286e+09 / 2.74286e+09 / -0.0571427<br>steampunk_another_multi [form[2]]: 2.05714e+09 / 2.05714e+09 / -0.0428572<br>steampunk_another_multi [form[3]]: 6.85714e+08 / 6.85714e+08 / -0.0142859<br>steampunk_another_foom2_multi [form[0]]: 1.71429e+09 / 1.71429e+09 / -0.285714 | 8.57143e+09→8.57143e+09 | 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×1) |
| 16 | `standard` / `standard_dsl` | variant_empress_light_form1_single、variant_empress_light_form2_single | variant_empress_light_form1_single [form[0]]: 2.7e+09 / 2.7e+09 / 0<br>variant_empress_light_form2_single [form[0]]: 6.3e+09 / 6.3e+09 / 0 | 9e+09→9e+09 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×1) |
| 17 | `general` / `boss_level` | maou2 | maou2 [main]: 2.35714e+10 / 2.35714e+10 / -0.42857 | 9.42857e+09→2.35714e+10 | 「深渊法阵」重力领域·引力1·33秒·中心·复合 「不屈龙心」减益耐性×50层（普通减益几乎无法命中；强制赋予除外） 「层叠龙鳞」强化弹射抗性×50层（减50%） 「血肉高墙」敌血×2.5 (×2.5) |
| 18 | `standard` / `standard_dsl` | grizzly_ex | grizzly_ex [form[0]]: 9.85714e+09 / 9.85714e+09 / -0.142857 | 9.85714e+09→9.85714e+09 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×1) |
| 19 | `standard` / `standard_dsl` | steampunk_light_multi | steampunk_light_multi [form[0]]: 1.02857e+10 / 1.02857e+10 / -0.714285 | 1.02857e+10→1.02857e+10 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×1) |
| 20 | `general` / `boss_level` | guardian_golem_fire_single | guardian_golem_fire_single [main]: 1.07143e+10 / 1.07143e+10 / 4.89373 | 1.07143e+10→1.07143e+10 | 「深渊法阵」重力领域·引力1.25·67秒·中心·复合 「深渊重甲」韧性×9·弹耐40% 「不屈龙心」减益耐性×50层（普通减益几乎无法命中；强制赋予除外） (×1) |
| 21 | `standard` / `standard_dsl` | epuration_boss_highest_single | epuration_boss_highest_single [form[0]]: 5.57143e+09 / 5.57143e+09 / -0.428572<br>epuration_boss_highest_single [form[1]]: 5.57143e+09 / 5.57143e+09 / -0.428572 | 1.11429e+10→1.11429e+10 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×1) |
| 22 | `general` / `boss_level` | discarded_dragon_dark_tower | discarded_dragon_dark_tower [main]: 1.15714e+10 / 1.15714e+10 / 0.493095 | 1.15714e+10→1.15714e+10 | 【风暴】「混相禁域」火伤害减半·水伤害减半·雷伤害降至1/10·风伤害降至1% 「深渊法阵」狂风领域·微风0.1·5秒·方向2 「深渊逆鳞」敌攻×1.3·直击易伤50% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 23 | `general` / `boss_level` | lich_wind_single_tower | lich_wind_single_tower [main]: 1.2e+10 / 1.2e+10 / 8.40377 | 1.2e+10→1.2e+10 | 【风暴】「三相封界」火·光·暗属性伤害降至1/10(只留水·雷·风) 「深渊法阵」重力领域·引力2·10秒·左侧/上方·复合 「深渊逆鳞」敌攻×1.1·能力易伤30% 「层叠龙鳞」直击抗性×50层（减50%） (×1) |
| 24 | `holy_sphere` / `special_bundle` | holy_sphere_single | holy_sphere_crystal [phase[1].crystal[1]]: 2.90584e+06 / 2.90584e+06 / 0<br>holy_sphere_crystal [phase[1].crystal[2]]: 2.90584e+06 / 2.90584e+06 / 0<br>holy_sphere_single [main]: 1.24228e+10 / 1.24228e+10 / 6.62831 | 1.24286e+10→1.24286e+10 | 「术式扰流」技能耐性40% 「能力抑制」能力耐性40% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 25 | `conductor` / `special_bundle` | boss_conductor_multi | boss_conductor_multi [main]: 2.73214e+10 / 2.73214e+10 / 5.95352 | 1.28571e+10→2.73214e+10 | 「嗜血狂潮」敌攻×1.15·血-15% 「血肉高墙」敌血×2.5 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×2.125) |
| 26 | `general` / `boss_level` | double_owl_lich_skill | double_owl_lich_skill [main]: 6.64286e+09 / 6.64286e+09 / 6.12551 | 1.32857e+10→6.64286e+09 | 「能力抑制」能力耐性40% 「术式扰流」技能耐性40% 「玻璃深渊·残响」敌血-50%（攻击增幅已摘） 「直击偏转」直击耐性40% (×0.5) |
| 27 | `general` / `boss_level` | psychic_shouta_sequel | psychic_shouta_sequel [main]: 1.37143e+10 / 1.37143e+10 / -1.63191 | 1.37143e+10→1.37143e+10 | 【枯竭】「元素禁壁」暗属性伤害降至1% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% 「深渊法阵」攻击领域·攻击-50% 「三重壁垒」直击·强化弹射·技能三重免疫(只剩能力能打) (×1) |
| 28 | `orochi_ex` / `special_bundle` | orochi_ex | orochi_ex [phase[1]]: 1.34218e+09 / 1.34218e+09 / 0<br>orochi_ex [phase[2]]: 2.65639e+10 / 2.65639e+10 / -0.0292053<br>orochi_ex [phase[3]]: 2.14748e+09 / 2.14748e+09 / 0 | 1.41429e+10→3.00536e+10 | 「嗜血狂潮」敌攻×1.15·血-15% 「血肉高墙」敌血×2.5 「术式扰流」技能耐性40% 「能力抑制」能力耐性40% (×2.125) |
| 29 | `standard` / `standard_dsl` | abyss_cloud、abyss_cloud_p3 | abyss_cloud [form[0]]: 2.18571e+09 / 2.18571e+09 / -0.214286<br>abyss_cloud [form[1]]: 5.1e+09 / 5.1e+09 / -0.5<br>abyss_cloud_p3 [form[0]]: 7.28571e+09 / 7.28571e+09 / -0.714286 | 1.45714e+10→1.45714e+10 | 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% 「能力抑制」能力耐性40% 「术式扰流」技能耐性40% (×1) |
| 30 | `general` / `boss_level` | yokai_emaki_big_boss_multi | yokai_emaki_big_boss_multi [main]: 1.5e+10 / 1.5e+10 / -5.96173 | 1.5e+10→1.5e+10 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% 「深渊法阵」二段伤害领域·二段伤害+11·复合 「深渊壁垒」全系耐性30% (×1) |

## Boss 封面静态审计

封面按实际 Boss 来源场地解析官方 240×188 quest 大图；混搭层不使用地形 donor 的图片。资源存在性已在构建期回读，但这仍不等于真机 UI 验证。

| 层 | Boss 来源场地 | quest c5 封面 | 证据 |
|---:|---|---|---|
| 2 | `main_2_1_2` | `quest/thumbnail/world_sand/battle_2_1_2` | ex:exact_field |
| 3 | `treant_single` | `quest/thumbnail/challenge_dungeon_event/challenge_dungeon_wind_2` | challenge_dungeon:floor_host_quest |
| 4 | `hermit_crab_another_light_single` | `quest/thumbnail/challenge_dungeon_event/challenge_dungeon_light_3` | challenge_dungeon:floor_host_quest |
| 5 | `tower_dungeon_area_10_4_1` | `quest/thumbnail/tower_dungeon/202010/area_10` | tower:floor_host_quest |
| 6 | `multi_variant_empress_wind_5` | `quest/thumbnail/multi_battle/multi_pick_34_5` | boss_battle:exact_field |
| 7 | `multi_normal_1_9_4` | `quest/thumbnail/multi_battle/multi1_9_4` | boss_battle:exact_field |
| 8 | `tower_dungeon_area_10_10_2` | `quest/thumbnail/tower_dungeon/202105/area_10` | tower:floor_host_quest |
| 9 | `halfanv25_big_boss_expert` | `quest/thumbnail/world_story_event/challenge_single_battle/2halfanv/challenge_boss_2halfanv` | world_story:exact_field |
| 10 | `middle_boss_anv1_raid3` | `quest/thumbnail/raid_event/raid_event_quest_thumbnail_04_003` | raid:exact_field |
| 11 | `cyberpunk01_21` | `quest/thumbnail/world_story_event/single_battle/cyberpunk01/single_31` | world_story:exact_field |
| 12 | `dark_matter_80` | `quest/thumbnail/challenge_dungeon_event/challenge_dungeon_level_end1` | score_attack:exact_field |
| 13 | `expert_white_tiger_80` | `quest/thumbnail/multi_battle/multi1_14_4` | practice:exact_field |
| 14 | `expert_golem_80` | `quest/thumbnail/multi_battle/multi1_6_4` | practice:exact_field |
| 15 | `steampunk_another` | `quest/thumbnail/advent_event/steam_robot_another/5` | boss_battle:exact_field |
| 16 | `multi_variant_empress_light_5` | `quest/thumbnail/advent_event/variant_empress_light/5` | boss_battle:exact_field |
| 17 | `main_7_14_2` | `quest/thumbnail/world_light/battle_7_14_2` | main:exact_field |
| 18 | `solo_time_attack_red1` | `quest/thumbnail/solo_time_attack/grizzly_red` | solo_time_attack:exact_field |
| 19 | `steampunk_light` | `quest/thumbnail/advent_event/steam_robot_light/4` | boss_battle:exact_field |
| 20 | `guardian_golem_fire_single` | `quest/thumbnail/challenge_dungeon_event/challenge_dungeon_fire_3` | challenge_dungeon:floor_host_quest |
| 21 | `epuration_boss_highest` | `quest/thumbnail/advent_event/boss_epuration_event/4` | advent:exact_field |
| 22 | `tower_dungeon_area_10_7_3` | `quest/thumbnail/advent_event/dragon_dark/1` | score_attack:exact_field |
| 23 | `tower_dungeon_area_10_12_2` | `quest/thumbnail/tower_dungeon/202107/area_10` | tower:floor_host_quest |
| 24 | `holy_sphere` | `quest/thumbnail/time_attack_event/white_01` | practice:exact_field |
| 25 | `conductor_multi` | `quest/thumbnail/world_story_event/multi_battle/cyberpunk01/multi_conductor_strong` | world_story_boss:exact_field |
| 26 | `double_owl_lich_skill` | `quest/thumbnail/multi_battle/multi1_1_1` | boss_battle:exact_field |
| 27 | `main_10_12_2` | `quest/thumbnail/world_10/battle_10_12_2` | ex:exact_field |
| 28 | `multi_normal_1_20_4` | `quest/thumbnail/multi_battle/multi1_20_3` | boss_battle:exact_field |
| 29 | `abyss_cloud` | `quest/thumbnail/raid_event/raid_event_quest_thumbnail_07_001` | raid:exact_field |
| 30 | `yokai_emaki_01_big_boss_multi` | `quest/thumbnail/world_story_event/multi_battle/yokai_emaki_01/multi_big_boss_2` | world_story_boss:exact_field |

## 最大误差楼层（最多 10 层）

| 层 | family | Boss | 阶段组件 | 目标 HP（基线→实战） | 回读 HP（基线→实战） | 最大绝对误差 HP | 通道 |
|---:|---|---|---:|---:|---:|---:|---|
| 25 | `conductor` | boss_conductor_multi | 1 | 1.28571e+10→2.73214e+10 | 1.28571e+10→2.73214e+10 | 12.5822 | `special_bundle` |
| 11 | `touyakiren_ceo` | touyakiren_ceo_single | 1 | 6.85714e+09→5.82857e+09 | 6.85714e+09→5.82857e+09 | 9.03519 | `special_bundle` |
| 7 | `kraken` | kraken_multi_80 | 1 | 5.14286e+09→2.57143e+09 | 5.14286e+09→2.57143e+09 | 8.73701 | `special_bundle` |
| 26 | `general` | double_owl_lich_skill | 1 | 1.32857e+10→6.64286e+09 | 1.32857e+10→6.64286e+09 | 8.64195 | `boss_level` |
| 14 | `general` | guardian_golem_fire_expert_80 | 1 | 8.14286e+09→8.14286e+09 | 8.14286e+09→8.14286e+09 | 8.43665 | `boss_level` |
| 23 | `general` | lich_wind_single_tower | 1 | 1.2e+10→1.2e+10 | 1.2e+10→1.2e+10 | 8.40377 | `boss_level` |
| 24 | `holy_sphere` | holy_sphere_single | 3 | 1.24286e+10→1.24286e+10 | 1.24286e+10→1.24286e+10 | 6.62831 | `special_bundle` |
| 30 | `general` | yokai_emaki_big_boss_multi | 1 | 1.5e+10→1.5e+10 | 1.5e+10→1.5e+10 | 5.9618 | `boss_level` |
| 20 | `general` | guardian_golem_fire_single | 1 | 1.07143e+10→1.07143e+10 | 1.07143e+10→1.07143e+10 | 4.89392 | `boss_level` |
| 12 | `general` | dark_matter_single | 1 | 7.28571e+09→1.82143e+10 | 7.28571e+09→1.82143e+10 | 3.66162 | `boss_level` |

## 当前保守边界

无法证明身份引用闭包、阶段胜利条件或资源完整性的 Boss 不会被包装成成功；严格模式会重抽或明确失败。继续增加新家族只提升阵容多样性，不是本报告放行的必要条件。

## 建议

此报告适合作为 dry-run、代码审查和金丝雀前置凭据。若要把结论提升为“可正式游玩”，仍应至少真机抽测普通 Hit/Fix、Standard DSL、多阶段专用 Boss 与 Sphere 各一关。
