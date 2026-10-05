# 深渊自动续战逐层队伍变化排查

日期：2026-10-06。

状态：完成源码排查与方案分析，未修改深渊续战逻辑、客户端或玩家存档。
本记录补齐前面讨论的分析，不代表已复现反馈玩家的具体故障，也不表示已经修复。

## 现象与结论

玩家反馈：深渊连战自动续战中设置的每层队伍，有时会自行变化；怀疑受不同设备影响。

目前证据支持的结论是：续战设置读取的是队伍编号和本机历史选择，不是一份独立、
长期云端保存的逐层阵容快照。换设备、修改被引用的 SET、手动挑战某层、重开续战设置，
都可能改变下一次看到的逐层队伍，不能统一归因于数据库自动覆盖。

必须区分两类反馈：

1. 每层选择的 SET/队伍编号变了：优先检查本地选择记录和续战设置初始化。
2. 编号没变，但角色、武器或魂珠变了：优先检查该 SET 的服务端内容是否被编辑。

尚未取得反馈玩家的前后截图、逐层编号、设备本地记录或对应编辑请求，所以不能认定
某个具体玩家一定命中了以下哪一条路径。

## 三层数据

| 数据 | 存储及作用 | 多设备关系 |
|---|---|---|
| SET 的角色、武器、魂珠 | 服务端 `players_parties`，按玩家、分类、组、槽保存 | 同一账号选中同一存档时共用 |
| 某关上次选择的队伍编号 | 客户端 `misc_data.selectedParty.partyForEachQuest` | 本机记录，不是服务端逐层预设 |
| 本轮正在执行的续战计划 | 客户端 `logicStatus.singleQuestAutoStart.lapConfig` | 客户端运行状态，不可视作跨设备长期保存 |

普通深渊活动 `700099` 使用编队分类 `ABYSS_NORMAL=5`，深渊 EX `700100` 使用
`ABYSS_EX=6`，幻想 `700098` 使用 `FANTASY=7`。旧客户端未传活动 ID 时仍可能使用
`RUSH=4`，因此排查多设备差异时也要核对客户端版本及其独立编队支持。

## 逐层列表如何生成

公开 CN 客户端 `PartySelectScene.openSingleQuestAutoStartSettingDialog()`：

1. 从所属关卡组取得后续完整关卡列表。
2. 从编辑子页面返回且已有临时 `partyIds` 时，继续使用这份临时选择。
3. 普通重新打开设置时，当前所在关卡使用准备页当前选中的队伍。
4. 其他关卡通过 `MiscDataLogic.getSelectedPartyIdForQuest()` 查本机上次选择。
5. 某关没有本地记录，则使用准备页当前队伍作为默认值。

`SingleQuestAutoStartSettingDialog.getListSource()` 再按每个 `partyId` 调用
`PartyGroupHolder.getParty()` 读取实际队伍。它不为每层复制一份独立角色装备快照。

点击确认后，`PartySelectScene.startSingleQuestAutoStart()` 调用 `startLap()`，
把关卡、体力成本和 `partyId` 写进运行中的 `lapConfig`。该调用链没有显示把所有
逐层选队一次性写入 `misc_data` 的步骤。`RushEventPartySelectLogic.startBattle()`
则在实际启动某关时调用 `setSelectedPartyIdForQuest()` 更新该关的本地选择记忆。

因此，“配置整塔后尚未打到后面楼层就退出，重新打开后部分选择不一样”有明确的源码
解释，但仍需对当前累计客户端实测；不能把整个运行计划当作已经永久保存。

## 可能触发变化的情况

| 操作或条件 | 可能表现 | 证据边界 |
|---|---|---|
| 换手机、换模拟器实例或重装清除应用数据 | 各层默认队伍不同、未记住的层都使用当前队伍 | 本地 `misc_data` 不随服务端 SET 自动同步 |
| 同一设备切换不同账号 | 原来的每关选队记忆被重置 | 登录补丁在旧、新 viewer 不同时显式重置 misc；不是每次登录都会重置 |
| 修改被多层引用的同一个 SET | 多层阵容一起变化，但队伍编号相同 | 逐层列表引用 SET，不是快照 |
| 另一设备编辑同一账号同一存档的 SET | 原设备下次加载后看到该 SET 内容变化 | 服务端保存以玩家/分类/组/槽定位，没有设备专属副本 |
| 手动用不同队伍启动某一层 | 再开设置时该层默认队伍变为上次实际使用的队伍 | 普通开战写入每关本地选择记忆 |
| 切换当前队伍后重新打开续战设置 | 当前层、以及无历史记录的层跟随当前队伍 | 设置对话框初始化规则 |
| 本轮续战停止或运行状态重建 | 临时计划不再是下一次设置的唯一来源 | `setEnabled(false)` 清除 lapConfig；初始化时 lapConfig 为空 |
| 两设备使用不同代客户端 | 相同编号可能读取不同的编队分类 | 需核对请求 event_id/party_category，不能仅比较编号 |

这不表示两台设备会互相同步、覆盖“每层选队表”。更准确的说法是：
**本地选队记忆可以不同，但它们引用的服务端 SET 内容可能相同。**

如果多个楼层引用同一 SET，在续战设置界面点击角色、武器或魂珠进行编辑，也可能实际
修改该 SET，其他引用它的层随之变化；这与只修改某层的“选队编号”不是同一操作。

## 已核对的服务端行为

- `src/routes/api/rushEvent.ts` 的 `/party` 按活动 ID 读取对应分类的编队。
- `src/lib/special-event-parties.ts` 以现有分类数据优先，合并旧 Rush 与默认编队，
  然后调用补缺操作。
- `src/lib/party-group-persistence.ts` 使用 `INSERT OR IGNORE` 补齐缺失项，
  不在正常读取时覆盖已有 SET。
- `src/data/domains/party.ts` 的 `updatePlayerPartySync()` 按
  `player_id + category + group_id + slot` 保存实际内容，没有按设备型号随机选队。
- `src/routes/api/rushEvent.ts` 的 `/battle/start` 接收客户端发来的 `party_id`，
  没有接收一份完整的“整塔逐层预设保存表”。
- `src/data/domains/abyss-tower-progress.ts` 换塔时清理的是本轮已挑战记录等进度，
  不应把 `players_rush_events_played_parties` 与保存的 `players_parties` SET 混淆。

上述检查没有发现服务端在普通读取时随机替换深渊保存队伍的实现；不等于排除了所有
客户端缓存、旧版本兼容或导入存档路径的问题。

## 与近期改动的关系

- 共斗装备准备拦截、队友 30 秒移出和房主超时解散属于多人大厅逻辑，未实现深渊
  每层队伍预设的读写，也没有批量卸下玩家保存的装备。
- 这些本地未提交改动尚未部署，不能解释现有线上玩家已经出现的反馈。
- Android/iOS 十分钟缓存清理按仓库实现只访问 AIR 缓存目录，不清理 Local Store
  中的 `misc_data`，没有证据表明它会直接重置逐层队伍选择。
- 登录补丁的账号切换重置与 AIR 缓存清理是两件事，不能统称“清缓存”后混为一谈。
- 更早的深渊续战补丁主要解除跨层角色复用限制，独立编队补丁主要区分 5/6/7 分类，
  并没有据此增加云端逐层配置同步。

## 核对依据

本地代码与历史说明：

- [活动编队分类](../../src/lib/rush-party-categories.ts)
- [编队补缺写入](../../src/lib/party-group-persistence.ts)
- [Rush 接口](../../src/routes/api/rushEvent.ts)
- [编队保存](../../src/data/domains/party.ts)
- [账号切换逻辑](../../client-patch/player-login/src/cn/account/PlayerLogin.as)
- [独立编队补丁](../../client-patch/independent-formations/README.md)
- [深渊续战复用补丁](../../client-patch/abyss-autostart/README.md)
- [Android 十分钟缓存清理](../../client-patch/startup-cache/PERIODIC-10M.md)
- [iOS 缓存清理源码](../../client-patch/orochi-rescue-bell-ios/src/cn/mod/CacheCleanupState.as)

只读参考源：[公开 CN 2.1.125 反编译仓库](https://github.com/dennis96292/wf-2.1.125-cn-decompiled)：

- `PartySelectScene.openSingleQuestAutoStartSettingDialog` / `startSingleQuestAutoStart`
- `SingleQuestAutoStartSettingDialog.getListSource`
- `RushEventPartySelectLogic.startBattle`（scripts-priority 中可读版本）
- `MiscDataLogic.getSelectedPartyIdForQuest` / `setSelectedPartyIdForQuest`
- `MiscLocalStore_Impl_.getMiscDataFile` / `save` / `reset`
- `SingleQuestAutoStartLogic.startLap` / `setEnabled` / `getPartyId`
- `GlobalLogic.getSingleQuestAutoStart` / `LogicStatus.singleQuestAutoStart`

公开源码不是当前私服累计 APK/IPA 的实机结果。这里只记录其机制与本地补丁证据，
未修改或重新构建客户端，没有把源码阅读记为真机复现。

## 下一步建议（未实施）

短期使用同一设备和专用 SET，避免把已绑定多层的 SET 临时改作其他用途；每次重新
开启续战时复查逐层列表。不要为排障先清除应用数据或重置编队，以免丢掉证据。

复现时使用测试账号，记录以下信息：

1. 普通深渊还是 EX、客户端版本、设备和账号切换顺序。
2. 变化前后每层的 SET/队伍编号，而不仅是角色截图。
3. 对应服务端 SET 的角色与装备内容，区分编号变化和内容变化。
4. 是否手动重打过某层、是否停止续战或在未打完整塔前重启。
5. 是否在同账号另一设备编辑过同一 SET，以及请求实际使用的编队分类。

长期建议把“逐层续战预设”与“上次挑战选队记忆”分离，明确按账号、活动、
关卡 ID 保存，并设计版本冲突处理。如果需要阵容完全固定，还必须明确选择保存
SET 引用还是完整快照。跨设备同步需要客户端参与读写；仅增加服务端表或在开战时
偷偷改 `party_id`，不能保证界面和实际战斗一致。

本轮没有新增同步接口、预设表、客户端补丁或自动修复脚本，没有读取或修改反馈玩家
的生产存档，没有执行深渊真机复现。该问题仍处于排查结论阶段。
