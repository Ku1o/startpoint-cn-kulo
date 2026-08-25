# 深渊连战 Boss HP 验收报告

> 结论：**静态严格验收通过**。本报告证明本次构建的表结构、HP 回读公式、逐组件目标和解析链均通过门禁；**它不等同于真机实战验证，也不证明已经发布或落库**。

## 一眼结论

- 种子：`2026082508`；层数：`30`；难度：`hell`；敌等级：`ramp`
- HP profile：`linear_boss_hp_30e8_150e8`；诅咒前基础总HP：`30亿→150亿`；严格递增：`是`；血量诅咒：`基础目标之后单独应用`
- Boss 关绝对证据：`29/29`
- 最终代理组件：`0`；源代理组件：`2`；未归一豁免：`0`；解析链失败：`0`
- 最大绝对回读误差：`26.7047 HP`
- 验证范围：`static_dry_run`；真机实战验证：`否（gameplay_verified=false）`
- 回执 SHA-256：`bedd02d31e7033a67ca4110b6cf9232eb59c3b82088ec3788abe48b91dc5f4a6`
- 工具 SHA-256：`88171ceb884845ab2952e008fdc2fcb3e80ff44d660b726f273222043c991283`

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
| family `general` | 13 |
| family `orochi` | 1 |
| family `orochi_ex` | 1 |
| family `standard` | 9 |
| family `thunder_sphere` | 1 |
| family `touyakiren_ceo` | 1 |
| family `water_sphere` | 1 |
| family `wind_sphere` | 1 |
| channel `boss_level` | 13 |
| channel `special_bundle` | 7 |
| channel `standard_dsl` | 9 |

## 逐关逐阶段明细

第 1 战是无 Boss 小怪房，不进入 Boss HP 绝对证据计数。以下基础 HP 是诅咒前目标，最终 HP 是血量诅咒之后的目标；阶段栏按实际出现次数列出每个胜利条件组件。

| 层 | family / 通道 | Boss | 阶段组件（阶段: 最终目标 / 回读 / 误差） | 基础→最终总HP | 诅咒（HP倍率） |
|---:|---|---|---|---:|---|
| 2 | `general` / `boss_level` | land_dragon | land_dragon [main]: 3e+09 / 3e+09 / 0.05937 | 3e+09→3e+09 | 「混相禁域」雷伤害减半 (×1) |
| 3 | `thunder_sphere` / `special_bundle` | thunder_sphere | thunder_sphere [main]: 3.42857e+09 / 3.42857e+09 / -0.571428 | 3.42857e+09→3.42857e+09 | 「深渊重甲」韧性×9·弹耐40% (×1) |
| 4 | `wind_sphere` / `special_bundle` | wind_sphere | wind_sphere [main]: 3.85714e+09 / 3.85714e+09 / 3.39308 | 3.85714e+09→3.85714e+09 | 「深渊重甲」韧性×9·弹耐40% (×1) |
| 5 | `general` / `boss_level` | discarded_dragon_dark | discarded_dragon_dark [main]: 4.28571e+09 / 4.28571e+09 / 13.5567 | 4.28571e+09→4.28571e+09 | 「绝对壁垒」强化弹射完全免疫 「深渊法阵」深渊之水·全场淹水 (×1) |
| 6 | `standard` / `standard_dsl` | arc_guardian_pcollab_02_single | arc_guardian_pcollab_02_single [form[0]]: 4.71429e+09 / 4.71429e+09 / -0.285714 | 4.71429e+09→4.71429e+09 | 「直击偏转」直击耐性40% (×1) |
| 7 | `water_sphere` / `special_bundle` | water_sphere_single | water_sphere_crystal [phase[1].crystal[1]]: 2.90584e+06 / 2.90584e+06 / 0<br>water_sphere_crystal [phase[1].crystal[2]]: 2.90584e+06 / 2.90584e+06 / 0<br>water_sphere_single [main]: 5.13705e+09 / 5.13705e+09 / -1.93332 | 5.14286e+09→5.14286e+09 | 「深渊重甲」韧性×9·弹耐40% 「魔力枯竭」FEVER需求×3 (×1) |
| 8 | `general` / `boss_level` | guardian_golem_fire_single_tower | guardian_golem_fire_single_tower [main]: 5.57143e+09 / 5.57143e+09 / 3.47824 | 5.57143e+09→5.57143e+09 | 「元素滞钝」火属性伤害减半 「层叠龙鳞」能力抗性×50层（减50%） (×1) |
| 9 | `general` / `boss_level` | yokai_emaki_big_boss_single | yokai_emaki_big_boss_single [main]: 6e+09 / 6e+09 / 0.11874 | 6e+09→6e+09 | 「直击偏转」直击耐性40% 「层叠龙鳞」直击抗性×50层（减50%） (×1) |
| 10 | `general` / `boss_level` | middle_boss_dragon_smr20_raid3 | middle_boss_dragon_smr20_raid3 [main]: 6.42857e+09 / 6.42857e+09 / -0.571428 | 6.42857e+09→6.42857e+09 | 「深渊法阵」重力领域·引力2·10秒·左侧/上方·复合 「层叠龙鳞」技能抗性×50层（减50%） (×1) |
| 11 | `touyakiren_ceo` / `special_bundle` | touyakiren_ceo_single | touyakiren_ceo_single [main]: 3.42857e+09 / 3.42857e+09 / 5.16855 | 6.85714e+09→3.42857e+09 | 【速攻】「玻璃深渊」敌攻×1.4·血-50% 「时之枷锁」限时3分 (×0.5) |
| 12 | `general` / `boss_level` | hungry_dragon | hungry_dragon [main]: 7.28571e+09 / 7.28571e+09 / -5.94909 | 7.28571e+09→7.28571e+09 | 「绝对壁垒」强化弹射完全免疫 「深渊重甲」韧性×9·弹耐40% (×1) |
| 13 | `standard` / `standard_dsl` | halfanv3_boss_hell | halfanv3_boss_hell [form[0]]: 7.71429e+09 / 7.71429e+09 / -0.285713 | 7.71429e+09→7.71429e+09 | 「深渊重甲」韧性×9·弹耐40% 「亡者不屈」减益免疫·能耐50% (×1) |
| 14 | `general` / `boss_level` | guardian_golem_fire_expert_80 | guardian_golem_fire_expert_80 [main]: 8.14286e+09 / 8.14286e+09 / -8.43661 | 8.14286e+09→8.14286e+09 | 「深渊法阵」狂风领域·轻风0.15·20秒·方向2 (×1) |
| 15 | `standard` / `standard_dsl` | steampunk_another_multi、steampunk_another_foom2_multi | steampunk_another_multi [form[0]]: 3.42857e+09 / 3.42857e+09 / -0.171429<br>steampunk_another_multi [form[1]]: 6.85714e+09 / 6.85714e+09 / -0.342857<br>steampunk_another_multi [form[2]]: 5.14286e+09 / 5.14286e+09 / -0.257143<br>steampunk_another_multi [form[3]]: 1.71429e+09 / 1.71429e+09 / -0.0857155<br>steampunk_another_foom2_multi [form[0]]: 4.28571e+09 / 4.28571e+09 / -0.714286 | 8.57143e+09→2.14286e+10 | 「直击偏转」直击耐性40% 「血肉高墙」敌血×2.5 (×2.5) |
| 16 | `standard` / `standard_dsl` | spirit_beast_wind | spirit_beast_wind [form[0]]: 9e+09 / 9e+09 / 0 | 9e+09→9e+09 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×1) |
| 17 | `standard` / `standard_dsl` | epuration_boss_dragon_main | epuration_boss_dragon_main [form[0]]: 2.9011e+09 / 2.9011e+09 / -0.175825<br>epuration_boss_dragon_main [form[1]]: 6.52747e+09 / 6.52747e+09 / -0.395604 | 9.42857e+09→9.42857e+09 | 【偏转阵列】「直击偏转」直击耐性40% 「术式扰流」技能耐性40% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 18 | `standard` / `standard_dsl` | hermit_crab_another_light_ex | hermit_crab_another_light_ex [form[0]]: 9.85714e+09 / 9.85714e+09 / -0.142857 | 9.85714e+09→9.85714e+09 | 【迟滞战线】「直击偏转」直击耐性40% 「魔力枯竭」FEVER需求×3 「亡者不屈」减益免疫·能耐50% (×1) |
| 19 | `general` / `boss_level` | double_owl_lich_ability | double_owl_lich_ability [main]: 8.74286e+09 / 8.74286e+09 / -7.13891 | 1.02857e+10→8.74286e+09 | 「嗜血狂潮·残响」敌血-15%（攻击增幅已摘） 「能力抑制」能力耐性40% 「深渊重甲」韧性×9·弹耐40% (×0.85) |
| 20 | `general` / `boss_level` | hermit_crab_another_light_single_tower | hermit_crab_another_light_single_tower [main]: 1.07143e+10 / 1.07143e+10 / 4.89373 | 1.07143e+10→1.07143e+10 | 「三相封界」水·雷·光属性伤害降至1/10(只留火·风·暗) 「深渊法阵」重力领域·引力1.5·10秒·左侧/上方 「亡者不屈」减益免疫·能耐50% (×1) |
| 21 | `standard` / `standard_dsl` | epuration_boss_highest_single | epuration_boss_highest_single [form[0]]: 5.57143e+09 / 5.57143e+09 / -0.428572<br>epuration_boss_highest_single [form[1]]: 5.57143e+09 / 5.57143e+09 / -0.428572 | 1.11429e+10→1.11429e+10 | 【偏转阵列】「直击偏转」直击耐性40% 「术式扰流」技能耐性40% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 22 | `general` / `boss_level` | lich_wind_single_tower | lich_wind_single_tower [main]: 1.15714e+10 / 1.15714e+10 / -9.19305 | 1.15714e+10→1.15714e+10 | 【风暴】「三相封界」雷·风·暗属性伤害降至1/10(只留火·水·光) 「深渊法阵」重力领域·引力1.1·10秒·左侧/上方 「深渊逆鳞」敌攻×1.2·直击易伤40% 「亡者不屈」减益免疫·能耐50% (×1) |
| 23 | `general` / `boss_level` | hermit_crab_water_single_tower | hermit_crab_water_single_tower [main]: 1.2e+10 / 1.2e+10 / 8.40377 | 1.2e+10→1.2e+10 | 【风暴】「混相禁域」光伤害降至1/10 「深渊法阵」狂风领域·轻风0.2·10秒·方向2 「深渊逆鳞」敌攻×1.1·直击易伤30% 「深渊重甲」韧性×9·弹耐40% (×1) |
| 24 | `orochi_ex` / `special_bundle` | orochi_ex | orochi_ex [phase[1]]: 1.9146e+09 / 1.9146e+09 / -0.385158<br>orochi_ex [phase[2]]: 1.23634e+09 / 1.23634e+09 / 0.000543594<br>orochi_ex [phase[3]]: 3.06335e+09 / 3.06335e+09 / -0.216253 | 1.24286e+10→6.21429e+09 | 「深渊重甲」韧性×9·弹耐40% 「直击偏转」直击耐性40% 「玻璃深渊」敌攻×1.4·血-50% (×0.5) |
| 25 | `orochi` / `special_bundle` | orochi_all_head_multi | orochi_all_head_multi [parent]: 3.21429e+09 / 3.21429e+09 / 6.67616<br>orochi_fire_head_multi [head[1]]: 4.01786e+08 / 4.01786e+08 / 3.47884<br>orochi_recovery_head_multi [head[2]]: 2.67857e+08 / 2.67857e+08 / 9.37074<br>orochi_funnel_head_multi [head[3]]: 4.6875e+08 / 4.6875e+08 / -10.0444<br>orochi_thunder_head_multi [head[4]]: 4.01786e+08 / 4.01786e+08 / 3.47884<br>orochi_gravity_head_multi [head[5]]: 4.6875e+08 / 4.6875e+08 / -10.0444<br>orochi_ice_head_multi [head[6]]: 4.01786e+08 / 4.01786e+08 / 3.47884<br>orochi_wind_head_multi [head[7]]: 4.01786e+08 / 4.01786e+08 / 3.47884<br>orochi_beam_head_multi [head[8]]: 4.01786e+08 / 4.01786e+08 / 3.47884 | 1.28571e+10→6.42857e+09 | 「直击偏转」直击耐性40% 「术式扰流」技能耐性40% 「深渊重甲」韧性×9·弹耐40% 「玻璃深渊·残响」敌血-50%（攻击增幅已摘） (×0.5) |
| 26 | `general` / `boss_level` | security_armour_single_tower | security_armour_single_tower [main]: 1.32857e+10 / 1.32857e+10 / 3.07737 | 1.32857e+10→1.32857e+10 | 「元素禁壁」光属性伤害降至1% 「深渊法阵」狂风领域·微风0.05·5秒·方向2 「深渊法阵」元素结界·元素耐性结界 「深渊壁垒」全系耐性30% 「绝对壁垒」能力完全免疫 「三重壁垒」能力·强化弹射·技能三重免疫(只剩直击能打) (×1) |
| 27 | `general` / `boss_level` | treant_single_tower | treant_single_tower [main]: 1.16571e+10 / 1.16571e+10 / 5.94969 | 1.37143e+10→1.16571e+10 | 「混相禁域」雷伤害降至1/10 「深渊法阵」连击限制领域·连击限制+35 「深渊法阵」攻击领域·攻击+100%/直击+50%/光耐性+100%·复合 「绝对壁垒」能力完全免疫 「深渊重甲」韧性×9·弹耐40% 「嗜血狂潮」敌攻×1.15·血-15% (×0.85) |
| 28 | `conductor` / `special_bundle` | boss_conductor_multi | boss_conductor_multi [main]: 1.20214e+10 / 1.20214e+10 / -12.0259 | 1.41429e+10→1.20214e+10 | 「嗜血狂潮」敌攻×1.15·血-15% 「深渊重甲」韧性×9·弹耐40% 「魔力枯竭」FEVER需求×3 「术式扰流」技能耐性40% (×0.85) |
| 29 | `standard` / `standard_dsl` | abyss_cloud、abyss_cloud_p3 | abyss_cloud [form[0]]: 2.18571e+09 / 2.18571e+09 / -0.214286<br>abyss_cloud [form[1]]: 5.1e+09 / 5.1e+09 / -0.5<br>abyss_cloud_p3 [form[0]]: 7.28571e+09 / 7.28571e+09 / -0.714286 | 1.45714e+10→1.45714e+10 | 【偏转阵列】「直击偏转」直击耐性40% 「术式扰流」技能耐性40% 「深渊重甲」韧性×9·弹耐40% 「亡者不屈」减益免疫·能耐50% (×1) |
| 30 | `standard` / `standard_dsl` | chapter12_boss_story | chapter12_boss_story [form[0]]: 1.5e+10 / 1.5e+10 / 0 | 1.5e+10→1.5e+10 | 【偏转阵列】「直击偏转」直击耐性40% 「术式扰流」技能耐性40% 「深渊重甲」韧性×9·弹耐40% 「魔力枯竭」FEVER需求×3 (×1) |

## 最大误差楼层（最多 10 层）

| 层 | family | Boss | 阶段组件 | 目标 HP（基线→实战） | 回读 HP（基线→实战） | 最大绝对误差 HP | 通道 |
|---:|---|---|---:|---:|---:|---:|---|
| 25 | `orochi` | orochi_all_head_multi | 9 | 1.28571e+10→6.42857e+09 | 1.28571e+10→6.42857e+09 | 26.7047 | `special_bundle` |
| 28 | `conductor` | boss_conductor_multi | 1 | 1.41429e+10→1.20214e+10 | 1.41429e+10→1.20214e+10 | 22.7732 | `special_bundle` |
| 5 | `general` | discarded_dragon_dark | 1 | 4.28571e+09→4.28571e+09 | 4.28571e+09→4.28571e+09 | 13.5567 | `boss_level` |
| 22 | `general` | lich_wind_single_tower | 1 | 1.15714e+10→1.15714e+10 | 1.15714e+10→1.15714e+10 | 9.19305 | `boss_level` |
| 11 | `touyakiren_ceo` | touyakiren_ceo_single | 1 | 6.85714e+09→3.42857e+09 | 6.85714e+09→3.42857e+09 | 9.03519 | `special_bundle` |
| 14 | `general` | guardian_golem_fire_expert_80 | 1 | 8.14286e+09→8.14286e+09 | 8.14286e+09→8.14286e+09 | 8.43665 | `boss_level` |
| 23 | `general` | hermit_crab_water_single_tower | 1 | 1.2e+10→1.2e+10 | 1.2e+10→1.2e+10 | 8.40377 | `boss_level` |
| 19 | `general` | double_owl_lich_ability | 1 | 1.02857e+10→8.74286e+09 | 1.02857e+10→8.74286e+09 | 7.13891 | `boss_level` |
| 27 | `general` | treant_single_tower | 1 | 1.37143e+10→1.16571e+10 | 1.37143e+10→1.16571e+10 | 5.94969 | `boss_level` |
| 12 | `general` | hungry_dragon | 1 | 7.28571e+09→7.28571e+09 | 7.28571e+09→7.28571e+09 | 5.9491 | `boss_level` |

## 当前保守边界

无法证明身份引用闭包、阶段胜利条件或资源完整性的 Boss 不会被包装成成功；严格模式会重抽或明确失败。继续增加新家族只提升阵容多样性，不是本报告放行的必要条件。

## 建议

此报告适合作为 dry-run、代码审查和金丝雀前置凭据。若要把结论提升为“可正式游玩”，仍应至少真机抽测普通 Hit/Fix、Standard DSL、多阶段专用 Boss 与 Sphere 各一关。
