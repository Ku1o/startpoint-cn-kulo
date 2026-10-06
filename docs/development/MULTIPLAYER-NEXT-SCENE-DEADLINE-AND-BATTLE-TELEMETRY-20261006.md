# 五重换场无限等待修复与每场联机战斗摘要

日期：2026-10-06

基线：`staging` `3995738e`

## 一、五重换场（LevelNext）可能无限等待

### 现象

五重第二场景开始时，已经加载完的队友停在转换画面一直等，本地战斗计时继续增长，
最终只能退出，表现为“掉线/卡住”。

### 根因

五重连接通过首轮 BattleStart 后，服务端有意取消 25 秒普通心跳租约（五重客户端战斗中
可能长时间静默，见 `FIVE-BOSS-STAGING-LOG-FOLLOWUP-20261004.md`）。之后换场屏障只有
两种收口方式：

- 成员发了 `LevelNext`：它自己的 60 秒 loading 租约会兜底；
- 成员 socket 关闭：8 秒缺席宽限后转 AI。

如果某成员 socket 还开着、却既不发 `LevelNext` 也不发 `SceneReady`（应用卡死或切到
后台、移动网络半开连接、客户端停在其他界面），没有任何计时器会结束等待，其余成员
在换场屏障上无限等待。

### 修复

`SessionManager.beginBattleLevelNext()` 在本轮换场屏障建立时登记一个截止计时器
`BATTLE_LEVEL_NEXT_DEADLINE_MS`（默认 90 秒，最小 10 秒）：

- 到期时仍在线、但本轮既没有 `LevelNext` 也没有 `SceneReady` 的成员被断开，断线原因
  记为新的 `level_next_timeout`；
- 断开后走原有关闭路径：8 秒缺席宽限、转 AI、`Leave` 在 BattleStart 之后发布；
- 已发 `LevelNext` 的成员仍由自己的 loading 租约负责，不受这个计时器影响；
- 屏障已释放、房间换代、结算或解散后计时器失效。

普通共斗、首轮屏障、五重战斗中的静默容忍都不变。

### 复现与验证

`tests/multi-battle-sim.test.cjs` 用真实 TCP 起会话服务器，三名模拟玩家走完五重首轮
屏障、约 30 帧/秒互发战斗帧，然后两人换场、第三人保持连接但静默：

- 截止时间设为 10 分钟（等同修复前）时，18 秒内两名换场玩家仍收不到 BattleStart；
- 默认逻辑下约 11 秒（10 秒截止 + 1 秒宽限）放行，两人收到 BattleStart 和第三人的
  `Leave`，第三人的连接被关闭。

## 二、每场多人战斗一行摘要 `[MULTI-BATTLE]`

为测试服收集联机数据新增 `src/multi/battle-telemetry.ts`。房间进入 `BATTLE` 时开始，
离开 `BATTLE`（结算、返回、解散）时输出一行 JSON：

| 字段 | 含义 |
|---|---|
| `room` / `battle` / `category` / `quest` / `fiveBoss` | 房间与关卡 |
| `end` | 结束方式，例如 `settling:finish_received`、`disbanded:<原因>` |
| `durationMs` | 战斗时长 |
| `realMembers` / `aiMembers` | 开战时真人与 AI 数 |
| `barriers` | 首轮与换场屏障各自等待了多久 |
| `seatsExpired` | 被转 AI 的缺席席位数 |
| `loopLagMaxMs` | 战斗期间服务器主线程最长卡顿 |
| `loopStalledSeconds` | 战斗期间主线程卡顿 ≥200 ms 的秒数 |
| `members[]` | 每名真人：battle 连接次数、入站包数、广播数、SceneReady/LevelNext/Finalize 次数、客户端线路警告（LineSpeedWarning）次数、最长入站静默、转发给他的帧数、发送背压次数与最长时长、按原因统计的断线 |

读法：

- `loopLagMaxMs` 高：服务器本身卡，所有人的转发都会延迟，查同时段 `[PERF]`/`[WORK-PERF]`；
- 单人 `lineSpeedWarnings` 多或 `maxInboundGapMs` 很长，其他人正常：该玩家网络问题；
- `maxBackpressureMs` 高：服务器发给该玩家的下行堵塞（玩家下行或服务器出口）；
- `disconnects` 区分服务器主动断开（`*_timeout`、`send_*`）和客户端/网络断开
  （`peer_fin`、`socket_error`）；
- `barriers` 里 `next_scene` 等待很长：换场慢或有人卡住。

开销：每个入站包和每次转发只更新一个已存在对象的计数器；主线程延迟直方图只在有战斗
时启用；不写数据库、不逐包记日志。`MULTI_BATTLE_TELEMETRY=false` 可关闭。

最近 100 条（`MULTI_BATTLE_TELEMETRY_RECENT`）同时保存在内存，可通过管理接口
`GET /api/server/diagnostics/battles` 读取。

## 改动文件

- `src/multi/state/SessionManager.ts`：换场截止计时器；屏障等待、席位过期、连接计数上报
- `src/multi/tcp/disconnect-diagnostics.ts`：新增断线原因 `level_next_timeout`
- `src/multi/five-boss/connection-diagnostic.ts`：新增诊断事件 `level_next_timeout`
- `src/multi/battle-telemetry.ts`：新增
- `src/multi/coordinator/embedded.ts`：进入/离开 `BATTLE` 时开始/结束摘要
- `src/multi/tcp/battle.ts`、`relay.ts`、`reliable-send.ts`、`server.ts`：计数上报
- `src/routes/web_api/diagnostics.ts`：`GET /battles`
- `.env.example`：新增两个变量说明
- 测试：`tests/multi-battle-sim.test.cjs`、`tests/multi-battle-telemetry.test.cjs`，
  `tests/multi-barrier-recovery.test.js` 新增两项，已加入 `npm run test:multiplayer-connectivity`

## 回退

服务端代码与对应 `out/` 一起回退即可；无数据库变更。只想关闭摘要可设
`MULTI_BATTLE_TELEMETRY=false`；只想放宽换场截止可调大 `BATTLE_LEVEL_NEXT_DEADLINE_MS`。
