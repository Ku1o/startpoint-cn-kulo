# 多人房间 H400 与登录任务恢复循环修复

日期：2026-10-04

实现基线：`staging@c08dd5f9`

交付分支：`fix/multiplayer-stability-h400-recovery`，目标分支为 `staging`；
未合并 `main`

主要实现提交：`890c8874`

交付 PR：`https://github.com/Ku1o/startpoint-cn-kulo/pull/21`（开放、待评审）

## 一、问题现象

玩家在创建或进入共斗房间时，偶发出现：

```text
发生意想不到的错误，回到登录页面
No.H400
```

回到登录页后又立刻出现：

```text
无法读取正在进行的任务信息，退出任务
```

客户端随后再次登录、再次读取同一任务、再次退出，两个错误互相循环。仅关闭游戏并
重新启动，或等待服务端状态发生变化后才可能恢复。

本问题不是单一接口报错，而是两个状态机问题叠加：

1. 创建、进房、开战或结算附近的正常生命周期竞态被服务端表示成 HTTP 400；
2. 登录 `/load` 又把已经无法恢复的多人 active quest 继续发布为未完成任务。

旧客户端把多人接口的 HTTP 400 当作致命协议错误，直接显示 H400 并退回登录页。
登录页收到不可恢复的 unfinished quest 后会自动走恢复或退出流程，从而形成闭环。

## 二、生产日志证据

分析来源：项目外运行日志目录“`五重修复后日志`”。

多人战斗接口中的 HTTP 400 数量：

| 接口 | 数量 |
|---|---:|
| `multi_battle_quest/finish` | 134 |
| `multi_battle_quest/start` | 19 |
| `multi_battle_quest/abort` | 17 |
| `multi_battle_quest/share_room` | 4 |
| `multi_battle_quest/play_continue` | 3 |

五重决战结构化拒绝原因：

| 操作与原因 | 数量 |
|---|---:|
| `finish:battle_proof_missing` | 136 |
| `finish:run_not_active` | 7 |
| `start:insufficient_ticket` | 58 |
| `start:insufficient_stamina` | 1 |
| `start:active_quest_mismatch` | 10 |
| `abort:request_identity_mismatch` | 12 |

这些统计不能全部解释为作弊或畸形请求。大量 finish、abort、continue 会在房间已经
结算、成员已经转 AI、旧局已被新局替换，或客户端重试时到达。它们属于分布式状态机
中的正常延迟与竞态，不应让客户端退出登录态。

## 三、登录循环根因

### 3.1 `/load` 对缺少房号的多人任务判断错误

多人 active quest 没有 `room_number` 时，旧逻辑无法定位真实房间，却仍可能把它加入：

```text
unfinished_multi_quest_list
```

客户端得到 play ID 后尝试恢复或退出，但服务端已经没有可关联的房间身份，退出请求
可能再次失败。下一次 `/load` 又返回同一任务，因此永久循环。

### 3.2 使用了错误的身份域

房间成员保存的是 `viewerId`，旧登录恢复判断曾使用 `accountId` 比较。两者数值域和
生命周期不同，即使是同一账号也不能互换。

正确关系是：

```text
session.viewer_id
-> resolve player
-> room.expected_real_viewer_ids / room.member_viewer_ids
```

不能用 account ID 推断玩家是否仍占有房间中的真人席位。

### 3.3 已转交 AI 的退休席位仍被当成可恢复

多人加载超时或重连宽限到期后，真人席位可能已经退休并由 AI 接管。房间本身仍存在，
关卡也一致，但该 viewer 已经不能重新接管原 battle seat。

若 `/load` 只检查“房间存在”，仍会给玩家发布无法恢复的任务。

### 3.4 旧局延迟清理可能误删新局

active quest 以 `player_id` 唯一保存。旧实现的延迟 finish、abort 或 writer cleanup
若只执行：

```sql
DELETE FROM players_active_quests WHERE player_id = ?
```

可能在玩家已经开始下一局后，把新局的 active quest 删除。下一次登录或新局结算又会
遇到状态不一致，继续产生 H400。

正确的清理条件必须同时包含：

```text
player_id + expected play_id
```

### 3.5 正常生命周期竞态使用 HTTP 400

以下情况都可能由正常网络延迟、重试或房间并发变化产生：

- 铃铛通知到达后房间已满或已开战；
- `select_room` 成功前后房间代次变化；
- prepare、summon、share_room 到达时房间刚被解散；
- start 外层校验后，五重房间在事务开始前消失；
- finish 到达时 active quest 或结算快照已经清理；
- abort、continue 属于上一局，当前玩家已进入下一局；
- 五重 run 已结束，但客户端仍补发 finish；
- 五重客户端真实进入战斗，但认证 proof 没有及时持久化。

旧客户端没有为这些接口实现通用 HTTP 错误恢复。返回 400 会直接触发 H400，而不是
回到房间列表或结束旧请求。

## 四、登录恢复修复

新增：

```text
src/lib/multi-active-quest-recovery.ts
out/lib/multi-active-quest-recovery.js
```

多人 active quest 只有同时满足以下条件，才会进入
`unfinished_multi_quest_list`：

1. `room_number` 是非空字符串；
2. 对应房间仍存在；
3. 房间生命周期仍为 `BATTLE`；
4. active quest 的 category、quest ID 与房间完全一致；
5. 房间已经冻结真人名单时，当前真实 viewer 仍在
   `expected_real_viewer_ids`；
6. 尚未冻结时，当前真实 viewer 仍在 `member_viewer_ids`；
7. 当前 battle seat 没有因超时或 AI 接管被标记为 retired。

任一条件不满足，任务即为不可恢复的多人孤儿任务。`/load` 不再发布它，而是在
持久化事务中按精确 `play_id` 清理：

```sql
DELETE FROM players_active_quests
WHERE player_id = ? AND play_id = ?
```

清理成功后明确返回：

```text
unfinished_quest_list = []
unfinished_multi_quest_list = []
```

连续调用两次 `/load` 时，第二次不会重新看到同一任务，因此登录循环被打断。

如果清理与新开局并发，条件删除会失败。`/load` 会重新读取替换后的 active quest，
只发布当前真实任务，不会把新局误删。

## 五、active quest 并发安全

新增数据层操作：

```text
deletePlayerActiveQuestIfPlayIdSync()
updatePlayerActiveQuestContinueCountIfPlayIdSync()
```

多人 writer command `MULTI_CLEANUP_ACTIVE_QUEST` 新增 `expectedPlayId`。以下操作全部
绑定请求所属的 play ID：

- 普通多人 finish 清理；
- 普通多人 abort 清理；
- 多人 continue count 更新；
- `/load` 孤儿任务清理；
- 五重异常终止清理。

内存中的 `activeQuests[playerId]` 也只有在 `playId` 相同时才删除或更新。

并发结果：

```text
旧 play 的 finish/abort/continue
-> 可以得到幂等终态
-> 不能删除或修改当前新 play
```

## 六、多人接口非致命终态

本轮没有把所有错误都改成成功，而是只将“已认证玩家遇到正常生命周期竞态”改为
协议内 200。

### 6.1 房间创建与选择

| 场景 | 新响应 |
|---|---|
| create_room 对应关卡已经不存在或过期 | HTTP 200，`result_code=4507` |
| select_room 时房间消失、满员、已开战或关卡身份过期 | HTTP 200，拒绝 `raising_state` |
| prepare 时房间消失、关闭或关卡不匹配 | HTTP 200，`raising_state=9` |
| summon 时房间消失或关卡不匹配 | HTTP 200，空队友结果 |
| share_room 时房间刚解散或请求属于旧关卡 | HTTP 200，返回当前分享配置 |

### 6.2 开战

以下 start 竞态统一为 HTTP 200 和业务不可用结果：

- 铃铛 attention key 已过期；
- 关卡已经不存在；
- 房间已经消失；
- 房间状态不再允许开战；
- 房间关卡与旧请求不一致；
- 五重体力或门票不足；
- 五重 run 已被其他请求结束；
- 五重外层房间校验通过后，房间在事务开始前被并发解散。

最后一种竞态在最终审阅中补齐。返回：

```text
HTTP 200
data_headers.result_code = 4050
data = {}
```

并验证不会建立五重 run、不会写 active quest，也不会扣体力或门票。

### 6.3 普通多人 finish

finish 找不到对应 active quest 或冻结结算快照时，不再返回 400，而是返回可解析的
零奖励终态：

- `clear_rank=0`；
- 所有掉落列表为空；
- EXP、Mana 和奖励池增量均为 0；
- 不更新任务进度；
- 不发物品或装备；
- 不删除不同 `play_id` 的当前任务。

结果会进入 finish 幂等缓存，同一旧请求重试仍得到相同响应。

### 6.4 abort 与 continue

延迟 abort 找不到同一 `play_id` 时：

- 返回 HTTP 200；
- 不删除当前新任务；
- 不重置当前新局状态。

延迟 continue 找不到同一 `play_id` 时：

- 返回 HTTP 200；
- `continue_count=0`；
- 不扣星导石；
- 不修改当前新任务的继续次数。

事务开始后若发生 play ID 替换，条件 UPDATE 会失败并返回同样的无副作用终态。

### 6.5 五重 finish

以下已结束或不可恢复状态返回零奖励终态 ACK：

- `run_not_active`；
- `member_not_active`；
- `client_play_not_found`；
- `active_quest_mismatch`；
- `battle_proof_missing`。

`battle_proof_missing` 不会伪造胜利或补发奖励。服务端尝试按精确玩家、play、房间和
五重关卡身份终止该成员任务，然后返回：

```text
clear_rank = 0
无奖励
无进度推进
```

这只解决客户端无法处理 400 的协议问题，不把缺少战斗凭证的请求提升为成功结算。

## 七、五重路由与旧任务隔离

`shouldHandleFiveBossMemberRequest()` 和 `isFiveBossContinueRequest()` 现在要求：

```text
active quest 的 play_id == 当前请求 play_id
```

避免上一局普通多人回调因为玩家当前恰好有一条五重 active quest，而被错误路由到
五重 runtime。

新五重房通过房间身份和准入检查后，可以清理以下旧孤儿任务：

- 已结束的普通单人任务；
- 房间不存在或已无法恢复的普通多人任务；
- 已结束的旧五重任务。

仍处于真实 `BATTLE`、房间和 viewer 席位均有效的多人任务不会被新五重入口抢占。

## 八、幻想边界保护

幻想第 5、10、15 层多人房间若已经不可恢复，`/load` 只清理当前 active battle，
不重置本轮幻想进度：

- 不删除此前成功完成的层数；
- 不发当前失败层奖励；
- 不写当前层成功记录；
- 玩家仍可从原 5、10、15 层重新挑战。

普通单人幻想失败和玩家显式整轮重置仍维持原语义。

## 九、仍保留的硬拒绝

以下请求继续使用 HTTP 400 或 403，因为它们不是房间生命周期竞态：

- 无效 session 或找不到绑定玩家；
- `viewer_id`、party、category 等请求结构畸形；
- 使用五重内部隐藏 scene 作为入口关卡；
- 陌生玩家越权开战或解散他人房间；
- 当前 viewer 被切换绑定到不同 player；
- 房间成员记录与认证 player 明确冲突；
- 明确伪造 category、quest、room 或五重 route；
- 五重 `request_identity_mismatch`；
- 付费 continue 的身份、模式或请求格式伪造。

这保证 H400 修复不会变成跨账号操作、免费领奖或伪造结算的入口。

## 十、测试覆盖

新增或扩展：

```text
tests/multi-active-quest-recovery.test.js
tests/active-quest-conditional-delete.test.cjs
tests/mode15-disconnect-load-recovery.test.cjs
tests/five-boss-integration.test.js
tools/multi_room_identity.test.cjs
```

重点验证：

- 只有精确匹配的实时 BATTLE 才能登录恢复；
- 使用 viewer ID 而不是 account/player ID 判断房间成员；
- 缺房号、房间消失、关卡不匹配、成员退休均清理孤儿任务；
- 连续两次 `/load` 都返回空 unfinished list；
- 幻想多人孤儿任务清理后仍停留在原边界层；
- 条件删除旧 play 不会删除新 play；
- 延迟 finish、abort、continue 均不能修改新局；
- finish 终态不发奖励、不推进进度；
- create/select/prepare/summon/share/start 的房间消失竞态不返回 H400；
- 五重二次房间消失返回 `200/4050`，不扣体力或门票；
- 五重 `battle_proof_missing` 只得到零奖励终态；
- 显式身份和关卡伪造仍被拒绝。

最终可复现命令：

```bash
npm run typecheck
npx tsc
npm run test:multiplayer-connectivity
npm run test:multicore
npm run check:out -- --worktree
git diff --check
```

本轮验证结果：

- TypeScript 类型检查通过；
- 完整 TypeScript 编译通过；
- 多人连接、房间身份、TCP 生命周期和幻想门禁回归通过；
- 五重专项 `53/53` 通过；
- 多人恢复判定 `2/2` 通过；
- active quest 条件删除 `1/1` 通过；
- 连续登录恢复 `2/2` 通过；
- 完整多核、响应 worker、SQLite checkpoint/persistence/writer thread 回归通过；
- `git diff --check` 通过；
- 测试状态仅写入项目 `tmp/`，测试结束后清理；
- 未启动或遗留 `cn-server` 测试进程。

## 十一、上线观察

部署后至少观察一个 30-60 分钟多人高峰窗口。

### 11.1 H400 数量

重点按接口统计：

```text
multi_battle_quest/start
multi_battle_quest/finish
multi_battle_quest/abort
multi_battle_quest/play_continue
multi_battle_quest/share_room
```

正常房间消失、旧请求和重复结算不应再贡献 HTTP 400。

### 11.2 登录恢复

观察：

```text
[CN-LOAD] stale active quest cleared
```

同一 player/play 应只清理一次。下一次 `/load` 不应再发布同一 play ID，也不应继续
出现“无法读取正在进行的任务信息，退出任务”。

### 11.3 安全边界

以下拒绝仍应存在：

- invalid viewer；
- room permission denied；
- room player mismatch；
- five-boss `request_identity_mismatch`。

若这些数量异常升高，应先检查 session/player 映射或客户端请求身份，不能继续把它们
改成无条件 200。

### 11.4 零奖励保证

对 `[FIVE-BOSS-ACK]` 和普通 `stale finish acknowledged` 抽样核对：

- 玩家物品、装备、EXP 不增加；
- 任务进度不推进；
- 当前新 active quest 不被删除；
- 房主费用不重复扣除。

## 十二、部署与回滚

本轮没有数据库 schema migration，不需要迁移 MySQL，也不需要修改玩家存档格式。

部署要求：

1. 源码和对应 `out/` 编译产物一起发布；
2. 重启 Node 进程，使新恢复判定和路由生效；
3. 先用测试账号制造“房间解散后旧 finish”和“登录孤儿任务”；
4. 再观察真实多人高峰日志。

回滚时源码与 `out/` 必须一起回滚。新增逻辑只清理不可恢复的 active battle 记录，
没有新增表或列，因此不需要数据库逆迁移。

## 十三、结论

本轮修复的是一条完整故障链，而不只是把某一个 400 改成 200：

```text
正常房间竞态
-> 协议内业务终态，不再 H400 登出
-> 不可恢复 active quest 按精确 play_id 清理
-> /load 不再重复发布坏任务
-> 登录页退出任务循环终止
```

同时保留了会话、玩家、房间和五重关卡的强身份校验。延迟旧请求只获得零奖励终态，
不能发奖、不能免除合法费用，也不能删除玩家已经开始的新局。
