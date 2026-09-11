# 第十二关本体／核心失联回归输入

`floor12-standard-family.json.zlib` 是 zlib 压缩的 JSON，包含本地测试资源 1.4.105 中第十二关 Boss 的 ESDL、两个原生核心的 ESDL，以及实际可达的 32 份 ActionDSL。Boss 使用塔内已发布 HP，但其原生脚本与核心仍引用 `steampunk_water_hard_multi`；战斗实际 ID 为 `mod_rogue_standard12`。

固定 SHA-256：`d70eb90e2a940d3aa1864c329cb7527e3e0bb878a424647c99e49039eca02a0c`。

来源为 `F:/codex/work/abyss-floor12-reboot-audit-20260910/` 的只读有效资源快照。当前 Android SWF SHA-256 为 `70ae68d0b5ca59650e3a41468b81fd00d6ce1d2861eebb5fb66d90b61b0da653`。其 TypePackerResource2、StandardEnemySource、GeneralEnemy 和 DamageShareCalculator 的窄范围导出证明：`bG` 按真实 Boss master ID 寻找伤害共享目标；`state.e` 是动画，`state.m/T2` 才是 DamageCheck。

测试重现旧核心找不到塔内 Boss，并验证私有完整召唤链可恢复关联；反向重放身份映射必须逐树还原全部输入，HP、10% 试炼及 1800 帧重启周期均保持。静态回归不代表 Android 真机验收。
