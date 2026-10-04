# 幻想装备与魂珠准备页不可出战门禁

## 目标

幻想连战专属武器和能力魂只允许在幻想关卡使用。玩家进入其他关卡的战斗准备页时，
如果当前编队携带这些装备，应在发送开战请求前显示为不可出战，体验接近机兵决战级
属性编队限制；旧客户端或伪造请求仍由服务端最终门禁拒绝。

## 现状复查

服务端此前已经检查 11 个专属 ID `100013..100023`：

- 普通单人 `/single_battle_quest/start`；
- Rush `/event/rush/start`；
- Raid `/raid_event/battle/start`；
- 普通多人 `/multi_battle_quest/start`；
- 多人 TCP `StartBattle` 最终名单预检；
- 推荐编队的写入和读取过滤。

命中限制时返回原生 `4050`，客户端显示已下发的
`quest_start_out_of_period_error`：

```text
当前不满足出战条件。
请检查关卡开放状态、入场门票和队伍限制。
幻想连战专属装备及魂珠仅限幻想连战使用，
挑战其他关卡前请先卸下或更换。
```

这套逻辑能防止实际进入战斗，但只能在点击开始后拦截，不能提前改变准备页按钮状态。

## 原生机制调查

使用公开 CN 2.1.125 反编译源码还原了机兵准备页链路：

```text
HardMultiPartySelectLogic
-> BattleStartableLogic.getCharacterRestrictionSource()
-> CharacterRestrictionSource.Element
-> CharacterRestriction.isRestricted()
-> CharacterPaticipationState.Restricted
```

机兵同时通过 `BattleStartableLogic.isPartyStartable()` 控制开始按钮：

```text
NormalPartySelectLogic.resolveStartButtonEnabled()
HardMultiPartySelectLogic.resolveStartButtonEnabled()
-> BattleQuestLogic.isStartable()
-> BattleStartableLogic.isPartyStartable()
```

`CharacterRestrictionSource` 原生只有 `None` 和 `Element` 两种。强行增加装备枚举会扩大
角色编辑、场景跳转和 iOS AOT ABI 的改动面。装备缩略图 `PartyItemThumbnailView` 也没有
角色缩略图那样的 `Restricted` 叠层。

因此不把角色头像伪装成“属性不符”，而是复用机兵的整队不可出战状态：非法编队的
开始按钮进入原生状态 `4`，准备页显示原生“队伍条件不满足”；玩家仍可进入编队编辑，
卸下装备后立即恢复。旧客户端或绕过准备页的请求继续由服务端 `4050` 显示明确的幻想
装备限制说明。

## 客户端规则

补丁目标：

```text
pinball.common.data.quest.battle.BattleStartableLogic.isPartyStartable
```

处理顺序：

1. 先执行全部官方队伍条件；
2. 官方条件失败时保持失败，不被幻想规则放宽；
3. 幻想关卡直接放行专属装备；
4. 其他关卡读取三个装备槽和三个能力魂槽；
5. 任一 ID 位于 `100013..100023` 即返回不可出战；
6. 普通装备、空槽和边界外 ID 保持原行为。

允许范围固定为：

| 外层 | 内层 | 关卡 |
|---|---|---|
| Single `0` | RushEvent `17` | `700098001..700098016` |
| Multi `1` | AdventEvent `1` | `300098001..300098003` |

范围包含幻想 1–15 层、练习关以及 5/10/15 三个协力节点。相邻 ID、其他 Rush、
普通副本、机兵、Raid、五重和其他多人关卡均不放行。

补丁源和契约：

```text
client-patch/fantasy-equipment-party-gate/patch.py
client-patch/fantasy-equipment-party-gate/contract.json
client-patch/fantasy-equipment-party-gate/README.md
```

补丁器会锁定唯一方法、原生局部变量形态和终端返回锚点；源码漂移时拒绝。它支持
FFDec 回读后的 markerless 语义验证，不能只验证导入前源码。

## 服务端对齐

新增 `isMode15EquipmentAllowedQuest()`，专门表达装备适用范围，不参与幻想层数推进、
奖励和准入。它统一用于：

- 普通单人；
- Rush；
- 普通多人 HTTP；
- 多人 TCP 最终预检；
- 推荐编队过滤。

同时将 optional runtime 的旧练习关默认值从 `700098013` 修正为当前真实 ID
`700098016`。正式层数判定 `isMode15Quest()` 保持不变，练习关不会因此推进进度。

## 验证

新增：

```text
tests/fantasy-equipment-party-gate.test.cjs
```

覆盖：

- 11 个专属 ID 与服务端常量完全一致；
- 六个装备/魂珠槽位；
- 幻想单人首尾、练习关和三个协力节点；
- 四个相邻非法 ID；
- 普通装备和边界外 ID；
- 官方队伍条件优先；
- 补丁重复运行字节一致；
- 方法形态漂移时 fail closed；
- markerless 回读；
- runtime 与 optional wrapper 范围一致。

验证结果：

- TypeScript 类型检查通过；
- TypeScript 完整编译通过；
- 客户端门禁契约 `3/3`；
- 多人最终装备门禁 `8/8`；
- 推荐编队 `6/6`；
- 幻想持久化 `5/5`；
- 五重集成 `51/51`；
- 屏障与重连 `24/24`；
- 完整 `npm run test:multiplayer-connectivity` 通过。

测试使用项目 `tmp/` 隔离目录，不读取或修改生产玩家数据。

## 交付边界

当前 Mac 工作区没有 `client-patch/android-accepted.json` 和
`client-patch/ios-accepted.json` 登记的累计 APK/IPA、完整 SWF/ABC 或 iOS AOT 二进制，
所以本轮没有生成可安装客户端，也没有更新客户端准入号。

当前完成状态：

- 服务端最终防绕过：已实现并编译；
- 客户端准备页判定源码：已实现并通过真实公开 CN 源码形态验证；
- Android APK：未构建、未签名、未真机；
- iOS IPA/AOT：未构建、未真机；
- CDN：无需新增表或资源增量；
- 数据库：无需迁移；
- 玩家存档：无结构变化。

仅部署本轮服务端代码，旧客户端仍会在点击开始后收到 `4050`，不会提前禁用按钮。
要获得准备页不可出战效果，必须从当前登记的最新累计客户端构建并安装新版本。

## 后续客户端构建门禁

1. 获取并校验当前登记的最新 Android APK 与 iOS IPA；
2. Android 导出、补丁、重新导入 `BattleStartableLogic`；
3. 回读实际 SWF，确认只有目标语义变化并完成 markerless 验证；
4. 为 Android 分配新的 AIR UUID，重新对齐和签名；
5. iOS 同步完整 ABC 与 AOT 原生方法，不能只替换 SWF；
6. 轮换或登记匹配的双端准入身份；
7. 真机验证普通单人、普通共斗、好友房、房间号、铃铛、机兵、Raid、幻想
   1/15/练习及三个协力节点；
8. 真机验收前不得将源码验证写成“客户端已上线”。
