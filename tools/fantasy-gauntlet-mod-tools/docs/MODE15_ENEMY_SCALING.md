# 幻想连战敌人血量倍率配置

幻想连战构建器从 `mode15_abyss_plan.json` 读取每关的目标 Boss 血量，并在构建时
按当前官方数据自动换算 Boss 与小怪的独立倍率。全局增强开关 `enemy.boss_hp`
应保持官方状态（×1）；幻想连战只修改自己的关卡修正，不改变其他游戏内容。

## 目标血量（推荐入口）

每关的 `target_effective_hp` 是最终希望达到的 Boss 总血量。例如：

```json
"target_effective_hp": 35000000000
```

正式构建会沿 `quest → field_data → zone → Boss` 读取当前实际 Boss 实例，并解析：

- 普通 Boss 的 `boss_level`、等级曲线和多实体合计；
- 标准 Boss 的 ESDL 多形态血条；
- APK `assets/bundle.zip` 内置、CDN 不重复下发的默认 HP 曲线；
- `Fix` 固定 HP 与 `Hit` 公式 HP。

随后用 `目标血量 ÷ 当前原生血量` 生成该关 `hp` 修正。上游更新即使改变了 Boss
原生 HP，下次构建也会重新换算，目标血量不会跟着漂移。任一 Boss 只能得到代理值
或完全不可解析时会拒绝构建，并指出关卡和原因，不会拿猜测值静默发布。

`audited_base_hp` 与 `hp` 保留为上次审计快照，便于代码审查和比较；日常调整难度时
只需要修改 `target_effective_hp`。读取 APK 内置曲线时可显式设置 `WF_APK`，未设置时
工具会自动寻找当前服务端 `弹国服` 目录下最新的 APK。

## 全局小怪倍率

在 `rules` 中设置：

```json
"minion_hp_scale": 0.10
```

该值只作用于 `zako`（场上小怪）与 `funnel`（动态召唤单位），Boss 主体使用构建期
自动换算的关卡 `hp` 值。本项目当前默认值为 `0.10`，即小怪和召唤物使用该关 Boss
倍率的 10%。

## 单关覆盖

如某一关需要不同的小怪倍率，可直接在对应的 `stages` 项目中加入：

```json
"minion_hp_scale": 0.05
```

单关配置优先于 `rules.minion_hp_scale`。未填写时使用全局值。

## Boss 倍率快照

每关的 `hp` 仍只控制 Boss 主体，但现在它是审计快照而不是首选编辑入口。例如：

```json
"stage": 14,
"hp": 1.0
```

表示上次审计时第14关 Boss 使用原始 HP 倍率 1；正式构建仍会按
`target_effective_hp ÷ 当前原生 HP` 重新计算，小怪按最终 `hp × minion_hp_scale` 计算。

若该特殊倍率不符合原先的单人关递增校验，应同时在 `rules` 中明确登记：

```json
"hp_progression_exempt_stages": [14]
```

只有列入该数组的关卡会跳过递增性检查，其余关卡仍受保护。

构建器同时对 Rush 单人表和 Advent 多人表写入正确的列顺序：`zako / funnel / boss`，避免降低小怪时误改 Boss 主体。
