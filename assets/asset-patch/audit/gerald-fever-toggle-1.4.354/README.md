# 水杰拉德能力3 Fever开关修复与描述修正 1.4.354

在 1.4.353 上追加 1.4.353 → 1.4.354 数据边，保留 1.4.353 及此前资源链原包。
两个 common 主数据资源同时用于 Android/iOS：`master/ability/ability.orderedmap` 与 `master/string/custom_ability_string.orderedmap`。

能力 `1299893`（`white_wolf_gerald_aqua_3`）使用隐藏固有状态 `12998904`（Fever 中激活治疗触发追伤）与 `12998905`（非 Fever 中激活治疗回充 Fever 槽）作为两段分支开关。两个固有状态在 `unique_condition` 中均为 `c4="2"`（可叠加上限 2）、`c9="false"`（不可驱散）。原表第 4 行（0 基索引 4，`c27="184"` Fever 结束清理 `12998904`）与第 6 行（0 基索引 6，`c27="8"` Fever 开始清理 `12998905`）的 `c47` 为 `528`（`DeleteCondition`，仅清除 `cancelable=true` 的状态），导致两处清理均失效，进入一次 Fever 后两个隐藏状态同时常驻。现将这两行的 `c47` 改为 `526`（`ConsumeAllUniqueCondition`，无视 `cancelable` 标志按固有状态 ID 消耗可叠加层数）。

同步修正 `custom_ability_string` 键 `desc_override_white_wolf_gerald_aqua_3` 文案，将「自身攻击力10倍的自适应伤害类型伤害」改为「自身攻击力10倍、伤害类型与队长相同的伤害」，与实际自适应队长伤害类型机制一致（保留 `wfx_adaptive_1299893` 标记及其他角色条目不变）。

两张表仅修改上述两个键，其余键的原始压缩字节与键顺序逐字节保持不变；不引入未上线角色或额外能力改动。无服务端业务代码、存档 ID、奖励来源、数据库、APK/IPA 或准入变化。

## 校验与重建

- 档案：`pinball-1.4.353-1.4.354-1-gerald-fever-toggle.zip`，311871 字节，2 个成员，均在 `production/upload`。
  SHA-256 `815e297ae95510bc854188722fb537abe0f4591e274625870d7fd4f74941c52c`。
- `python -B tools/build-gerald-fever-toggle.py --write`：仅从 1.4.353 有效链生成新包，拒绝覆盖既有归档。
- `python -B tools/build-gerald-fever-toggle.py`：核对归档、完整成员、CRC、manifest、固有状态前置约束与主表回读。
- `python -B tests/gerald-fever-toggle.test.py`：键级范围、非目标键原压缩字节保持、错误前像拒绝、后续版本兼容及双端共用根回归。

这些是离线资源和静态契约验证，未做手机实战或联机同步验收。
云端尚未部署。已下载资源的回退须追加还原边，不能只撤掉 manifest 记录。
