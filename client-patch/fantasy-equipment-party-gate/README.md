# 幻想装备准备页不可出战门禁

幻想连战专属武器及其能力魂 ID `100013..100023` 只允许用于幻想连战。服务端已经在
单人、Rush、Raid、普通多人和 TCP 最终开战边界拒绝非法编队，并以原生 `4050`
显示 `quest_start_out_of_period_error`。本目录补齐更前置的客户端准备页判定。

## 客户端行为

补丁目标是：

```text
pinball.common.data.quest.battle.BattleStartableLogic.isPartyStartable
```

普通单人和 Hard Multi 准备页都通过该方法驱动
`resolveStartButtonEnabled()`。官方队伍条件通过后，补丁再读取 `PartyPeek` 的三个
装备槽和三个能力魂槽：

- 装备使用 `getEquipmentPeek(slot).params[0].id`；
- 能力魂使用 `getAbilitySoulPeek(slot).params[0].get_abilitySoulId()`；
- 任一 ID 位于 `100013..100023`，且当前不是幻想关卡时，返回 `false`；
- 开始按钮进入与机兵队伍条件失败相同的不可出战状态；
- 玩家仍可点击装备或编队编辑，换下受限物后恢复可出战。

机兵的角色属性限制会把具体角色缩略图标成 `CharacterPaticipationState.Restricted`。
装备缩略图 `PartyItemThumbnailView` 没有同等的 `lock/restricted` 接口，因此本补丁不把
角色头像伪装成“属性不符”，也不修改装备图标颜色。反馈使用原生的整队开始按钮禁用状态
和“队伍条件不满足”提示；旧客户端或绕过准备页的请求仍由服务端 `4050` 显示已经下发的
幻想装备说明。

## 允许范围

规则契约位于 `contract.json`：

| QuestIdGroupKind | 内层类型 | ID |
|---|---:|---:|
| Single | RushEvent `17` | `700098001..700098016` |
| Multi | AdventEvent `1` | `300098001..300098003` |

范围包含幻想 1–15 层、练习关及 5/10/15 三个协力节点。相邻 ID、其他 Rush、
普通单人、Hard Multi、Raid、五重和其他多人关卡均不放行。

## 源码补丁

`patch.py` 要求输入为当前累计客户端重新导出的
`BattleStartableLogic.as`。它锁定唯一方法、局部变量形态和终端返回锚点，漂移时拒绝：

```bash
python3 client-patch/fantasy-equipment-party-gate/patch.py \
  --source <BattleStartableLogic.as> \
  --output <BattleStartableLogic.patched.as>

python3 client-patch/fantasy-equipment-party-gate/patch.py \
  --verify <BattleStartableLogic.patched.as>

# FFDec 从实际注入 SWF 重新导出的源码可能没有注释 marker：
python3 client-patch/fantasy-equipment-party-gate/patch.py \
  --verify <BattleStartableLogic.reexported.as> \
  --allow-markerless
```

补丁器已在公开 CN 2.1.125 反编译源码上验证，公开源文件 SHA-256 为
`ce326535d40184e810ebb0e125797cacf795b3172eaf13b121392a1b56fec7f8`，
源级补丁结果 SHA-256 为
`add85082cd61a1dad47d35b259847da8ad29607fa45a5e98466e57c7b2d92aeb`。
这些哈希只证明该公开源码形态可补，不是当前私服累计 APK 的成品身份。

FFDec 重新编译可能去掉 marker 注释。实际 SWF 注入后必须重新导出同一类，并使用
`--allow-markerless` 做语义验证。

## 发布门禁

当前仓库只保存补丁源、契约和测试，不保存 APK、IPA、SWF、签名材料或完整 ABC。
本机没有 `android-accepted.json` / `ios-accepted.json` 登记的累计成品，因此本轮未生成
可安装客户端。

后续构建必须：

1. 从当前登记的最新 Android APK 和 iOS IPA 开始，校验完整文件及 SWF/Mach-O 哈希；
2. Android 只修改目标 `BattleStartableLogic`，回读全部方法差分和目标语义；
3. Android 每个不同 SWF 分配新的 AIR `uniqueappversionid`，重新对齐和签名；
4. iOS 不能只替换 SWF，必须同步完整 ABC 与 AOT 原生方法，并保护现有字段布局；
5. 两端都验证官方机兵属性限制、普通合法编队和幻想关卡行为保持；
6. 安装后真机验证普通单人、普通共斗、房间号、好友房、铃铛、Hard Multi、Raid、
   幻想 1/15/练习及三个协力节点；
7. 未完成上述门禁前，不得把源码验证写成已发布或已真机验收。

## 自动验证

```bash
npm run typecheck
npx tsc
node --test tests/fantasy-equipment-party-gate.test.cjs
```

测试覆盖客户端真值表、六槽检查、边界 ID、官方条件优先、补丁幂等、源码漂移拒绝、
markerless 回读，以及服务端适用范围与客户端契约一致性。
