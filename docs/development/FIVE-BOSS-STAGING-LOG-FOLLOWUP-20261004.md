# 五重决战 staging 新日志复查与续战修复

日期：2026-10-04

分析对象：项目外运行日志目录“`五重修复后日志`”。

本轮基线为 `staging` 的 `c08dd5f9`。范围包括五重多人中途掉线、第一轮结束后的
房间续战、Boss 转换阶段等待、合法 abort，以及五重单人连续开战。

## 日志边界

日志包含一次服务重启。`cn-server-20261004-145227.*.log` 对应的新进程约在：

```text
2026-10-04T06:52:29Z
```

短日志中共有 30 条结构化 `FIVE-BOSS-REJECT`：

| 操作与原因 | 数量 |
|---|---:|
| `finish:battle_proof_missing` | 11 |
| `start:active_quest_mismatch` | 6 |
| `abort:request_identity_mismatch` | 4 |
| `start:insufficient_ticket` | 9 |

11 个 `battle_proof_missing` 对应成员的 `started_at` 全部早于本次服务启动时间，
属于重启前已开始且没有 `battle_entered_at` 的旧在途局。重启后新建五重局没有再
产生新的该类拒绝，说明上一轮持久化认证入场凭证的修复对新局生效。

## 根因与修复

### 1. Battle TCP 身份误拒

4 个新局 abort 失败都出现了相同链路：

```text
frozen
-> http_start
-> handshake
-> handshake_denied:frozen_identity_mismatch
-> socket_end/socket_close
-> abort:request_identity_mismatch
```

冻结身份原来同时要求：

- viewer 对应的冻结身份存在；
- `playerId` 相同；
- `connectionId` 相同；
- lobby TCP 与 battle TCP 的 `remoteAddress` 完全相同。

IP 地址不是稳定身份。移动网络、双栈和运营商 NAT 都可能让同一客户端的两条 TCP
连接使用不同出口。battle 握手已经通过同房间 `connectionId` 找回已认证 lobby
连接，并再次校验该 viewer 的 session，因此再要求 IP 相等只会误拒合法玩家。

修复后保留 viewer、player、connection ID 和 superseded 状态校验，移除 IP 等值
要求。错误 player、错误 connection ID 和被替代连接仍然拒绝。

### 2. 25 秒静默租约主动切断五重战斗

结构化 transport 事件中可归因到五重的样本为：

```text
accepted
-> scene_ready
-> 战斗期间无 TCP 包
-> heartbeat_timeout，约 25000 ms
-> socket_close/removed
```

五重客户端在 Boss 战斗期间不保证每 25 秒发送合作通道数据。服务器把“暂时无包”
当成断线并主动销毁 socket 后，客户端无法再通过原连接发送 `LevelNext` 和下一次
`SceneReady`，表现为：

- 与队友通信断开；
- 转换阶段一直等待；
- 客户端本地战斗计时继续增加。

修复只作用于已经通过五重 `BattleStart` 屏障的连接：

- 首轮场景激活后取消普通 25 秒 active heartbeat；
- 同场景重连并补发 `SceneReady` 后也取消临时 lease；
- `LevelNext` 进入下一场景时重新启用固定 loading deadline；
- 缺席席位的重连宽限、AI 缩编和合法 `Leave` 仍保留；
- 房间最终仍由现有 abandoned-battle watchdog 回收；
- 普通共斗的 heartbeat 行为不变。

没有取消 loading deadline，也没有无限保留未完成首轮加载的连接。

### 3. 回房状态只等待新的 Host Enter

成功结算后房间进入：

```text
BATTLE -> SETTLING -> RETURNING
```

原实现只有房主重新执行特定 lobby `Enter` 流程时才完成：

```text
RETURNING -> LOBBY
```

但五重客户端可能继续复用首轮之前已经完成过 `Enter` 的 lobby socket。此时所有人
在画面上已经回房，服务器却仍认为房主没有返回。房间无法从 `RETURNING` 直接进入
`STARTING`，60 秒后被 `settlement_host_return_timeout` 自动解散。

修复后：

- 五重结算进入 `RETURNING` 时，若同房已认证房主 lobby 仍在线且完成过 `Enter`，
  立即完成回房；
- 房主后续 `Ready` 可幂等完成回房；
- 任意成员发送 `StartBattle` 时，若房主已认证在线，先完成回房再按正常流程开局；
- 完成回房时统一更新存活 lobby client 的 generation；
- 普通共斗仍保持原有回房确认语义。

这不是延长 60 秒超时，而是补齐服务器遗漏的“房主原连接仍在线”事实。

### 4. Abort 请求缺少 route 字段

新日志中的合法五重 abort 请求没有携带 `category/quest_id`，原 handler 将空值直接
传给 runtime，因此被判定为“不是准确的五重路由”，旧 active quest 和 run 随之
残留。

修复后先使用 `playerId + play_id` 查询不可变五重账本：

- body 缺少 category/quest 时，从该精确账本绑定恢复五重 canonical 值；
- body 明确携带错误 category/quest 时仍拒绝；
- room number 继续从同一账本恢复；
- 不允许仅凭请求体把普通对局提升为五重对局。

### 5. 单人连续战斗扣费规则不一致

服务端此前在五重单人 `/start` 同时扣：

```text
35 体力 + 1 张深界连战凭证
```

但当前客户端资源把五重单人消耗定义为 35 体力；项目内已恢复的凭证说明明确为：

```text
用于开启五重连战房间的凭证。仅房主在战斗开始时消耗。
```

因此“仍有足够体力但不能继续单人战斗”可能实际是被隐藏的门票检查拦住。短日志里
`single_battle_quest/start` 没有 HTTP 400，不能把全部单人现象归因于 stale active
quest；日志里的 6 个 `active_quest_mismatch` 发生在随后进入多人五重 `/start` 时。

本轮按现有玩法契约调整为：

| 模式 | 体力 | 房主门票 | 队友门票 |
|---|---:|---:|---:|
| 五重单人 | 35 | 0 | 不适用 |
| 五重多人 | 房主 35 | 1 | 准入要求 Rank 130 且持有 1 张，但不消耗 |

单人 active quest 不再记录多人房间门票为 `entryItemId`。单人扣体力、建立 ledger
和 active quest 仍处于同一事务；失败不会留下半扣状态。没有增加“删除任意旧单人
任务”的宽泛恢复逻辑，避免五重入口误删玩家正在进行的普通副本。

### 6. 幻想 5/10/15 层掉线错误重置整轮

幻想连战的当前层数由 `players_rush_events_played_parties` 中本轮已经成功完成的
阶段标记计算。房主在 5、10、15 层共斗中掉线时，客户端可能走失败 `/finish`、
`/abort`，或在房间消失后由下一次 `/cn/load` 清理 stale active quest。原实现会
在这三种路径把通讯中断等价成整轮失败，调用 `resetMode15RunSync()` 删除本轮所有
阶段标记，所以玩家回到第 1 层，并且未成功结算的当前层奖励也不会获得。

服务端无法从 legacy 失败请求可靠区分“主动失败”和“通讯中断”。本轮采用保守的
边界关卡语义：

- 5、10、15 层多人战斗只有成功结算才推进到下一层并发放奖励；
- 失败 finish、abort、房间异常解散后的登录清理，只结束当前 active battle；
- 不写当前层成功标记、不发当前层 token、碎片或其他结算奖励；
- 不删除此前 1-4、1-9 或 1-14 层的 played-party 标记；
- 玩家下一次仍只能创建或进入原来的 5、10、15 层；
- 单人阶段失败仍重置整轮，玩家主动调用幻想整轮重置也仍回到第 1 层；
- 15 层成功完成后的奖励和新一轮重置行为不变。

### 7. AI 自动续战触发 `U_1d93f4`

生产日志中的 `U_1d93f4` 堆栈为：

```text
MaxRectsPacker.allocateRectangle
-> AtlasBuilder.buildTextureAtlas
-> BattleStartProductionViewService.pack
```

并带有 `Failed to allocate packing rectangle: size exceeded`，说明它是客户端在开战时
合并三支队伍的战斗图集超过容量，不是服务端 HTTP 错误。当前 `1.4.130` 资源链已经
包含旧的杰拉德、赛瑞斯图集裁剪和 layer 调整，但日志仍存在同码样本，其中至少一例
紧跟 `MULTI-AI fallback`。

服务端原来在每次回房重建 AI 时重新从玩家队伍池随机选队。首局能成功加载并不代表
第二局的新随机组合仍满足同一图集预算。修复后：

- COM1/COM2 第一次进入房间时，按 COM ID 保存本房间的队伍快照；
- 自动续战和回房重建复用对应 COM 的首次队伍；
- 已有完整 COM 快照时不再查询或随机 AI 队伍池；
- 真人补位只移除对应 COM；该席位之后恢复时仍复用原快照；
- 新房间仍正常从队伍池选择 AI，不跨房间固定；
- 房间解散后快照随房间内存一起释放，不写玩家数据库。

该改动消除了“首局正常、自动续战第二局突然换入高资源 AI 编队”的变量。它不修改
客户端 4096 图集容量，因此仍需通过真机长时间自动续战确认是否存在首局本身就超出
预算的其他角色组合。

## 回归覆盖

新增或更新的回归包括：

- battle TCP 更换 `remoteAddress` 仍可通过冻结身份；
- 错误 player 或 connection ID 仍拒绝；
- 五重 active 场景静默超过普通 heartbeat 时间后 socket 仍存活；
- 下一场景 `LevelNext` 仍建立 loading lease；
- 已完成 Enter 的在线房主可直接完成 `RETURNING -> LOBBY`；
- abort 缺 category/quest 可从精确账本恢复；
- 显式伪造 category/quest 仍返回 400，active run 不被清理；
- 单人零门票、70 体力可连续完成两轮，每轮只扣 35 体力；
- 多人仍只扣房主一张票，队友票不消耗；
- 五重新队友 Rank 129 在铃铛、好友房、房间号、直接选房和 TCP 握手均拒绝，
  Rank 130 后继续执行持票检查；
- 幻想 5、10、15 层失败均保持当前层数，不写成功记录、不发幻想 token；
- 幻想第 10 层真实多人 `/abort` 后 active quest 被清理，但仍只允许重新挑战第 10 层；
- 幻想单人第 6 层失败仍重置到第 1 层；
- AI 候选池第二次返回不同编队时，同一房间自动续战仍复用首局 COM1/COM2；
- 完整 COM 快照存在时，自动续战不再查询随机 AI 队伍池；
- 铃铛真人首战后只断开回房 socket 时，重连席位先保持；房主显式请求 AI 接管后，
  旧真人席位被释放、两名 COM 补齐，并能启动下一战；
- 普通共斗 heartbeat、relay、房间生命周期和协议防护不变。

## 可复现验证

```bash
npm run typecheck
./node_modules/.bin/tsc
node tools/run-isolated-check.cjs --test \
  tools/mode15_persistent_completion.test.cjs \
  tests/five-boss-integration.test.js \
  tests/multi-barrier-recovery.test.js
npm run test:multiplayer-connectivity
npm run test:multicore
npm run check:out -- --worktree
git diff --check
```

本轮结果：

- 类型检查和完整 TypeScript 编译通过；
- 五重及多人专项集成 `51/51` 通过；
- 屏障与重连 `24/24` 通过；
- 完整多人连接回归通过；
- 完整多核、响应 worker、SQLite checkpoint/persistence/writer thread 回归通过；
- `out/` 与源码改动对应检查通过；
- 所有测试仅使用项目内 `tmp/` 隔离目录；
- 每次测试结束均显示 `temporary state removed`；
- 最终 `tmp/` 内容数量为 0，没有残留测试服务或隔离数据库。

## 上线观察

部署后重点观察一个高峰窗口：

1. 新建五重局不应再出现 `handshake_denied:frozen_identity_mismatch` 后紧跟合法 abort。
2. 五重 transport 中 `scene_ready -> heartbeat_timeout` 应降为 0。
3. `settlement_host_return_timeout` 应显著下降；仍出现时确认当时是否真的没有在线房主。
4. 第二场景仍应看到正常 `level_next` 和 `scene_ready`，但不应无限积累 loading lease。
5. 单人零票但体力不少于 35 时 `/start` 应成功；每轮 `total_stamina_used` 增加 35。
6. 多人房主缺票仍拒绝；新队友必须 Rank 130 且持票，准入只检查不扣除。
7. 老进程遗留的无 `battle_entered_at` 在途局可能继续产生旧 H400，不能算作新局回归。

## 剩余边界

- 本轮服务端测试无法替代真实手机上的五 Boss 完整长局验收，特别是移动网络切换、
  后台恢复和所有成员加载速度差异。
- 本轮已让 `active_quest_mismatch` 结构化日志同时输出 active category/quest。
  后续若仍有该错误，应据此判断是五重孤儿状态还是玩家确实仍在普通单人战斗，
  不能直接批量删除。
- 重启前已经开始且缺少认证入场凭证的旧局无法从新日志追溯补证；它们应随旧 run
  结束，不应放宽新局身份和发奖校验。

## 助力成员离房后 AI 补位无法开始下一战

### 现象

首战开始时房间中有房主、铃铛助力玩家和 COM。首战结束回房后，助力玩家离开，
房间可以补入 AI，但房主无法开始下一战。

### 根因

续战大厅使用 `expected_real_viewer_ids` 等待上一战真人回连。旧实现把该集合同时用于
自动准备和最终 `StartBattle` 防线，但离开的真人可能只从实时 client roster 消失，
仍残留在房间成员登记、期待名单或 `room.mates` 中。结果是：

```text
客户端 roster = 房主 + COM1 + COM2
服务端 expected_real_viewer_ids = 房主 + 已离开的铃铛玩家
```

AI 显示和 Ready 都可以成功，最终开战仍因缺少旧 viewer ID 被拒。这与
`U_1d93f4` 的客户端动态图集容量、以及 `C8016` 的 Action timeline 缺失均无关。

### 修复边界

- `removeRoomMember()` 原子删除成员、玩家映射、续战期待名单和 room roster；
- 临时 socket 断开继续保留重连宽限，不立即放弃真人席位；
- 续战大厅中只有房主显式发送 `EnterComs` 才表示“现在由 AI 接管”；
- 接管时只释放当前不在线的非房主成员，在线真人不受影响；
- 铃铛成员同时退出 rescue/reconnect 状态，旧恢复请求不能重新占回席位；
- 旧 rematch 清理定时器被取消，释放和 AI 招募在同一房间命令队列中串行；
- 下一战重新生成五重冻结 runtime，真人名单只包含实际在房成员。

命中修复分支的日志为：

```text
[LOBBY] host AI replacement released absent rematch members: room=... viewers=...
```

### 回归结果

新增测试按真实协议执行：

```text
铃铛真人 socket close
-> 期待名单仍保留，验证重连保护
-> 房主 EnterComs
-> 释放缺席真人
-> COM 补位及 Ready
-> 房主 Ready
-> StartBattle
-> BATTLE
```

结果：

- 五重集成 `51/51`；
- 屏障与重连 `24/24`；
- 完整多人连接回归通过；
- TypeScript 类型检查及完整编译通过。
