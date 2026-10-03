# 云服运行日志复盘与第二轮优化

日期：2026-10-03

数据来源：云服同步的 stdout/stderr 日志，采样窗口约 65 分钟。原始日志不纳入仓库，本文只记录聚合指标和可复现结论。

## 结论

PR #14 的 TCP 竞态修复有效。采样窗口内共新增 8247 次连接关闭，其中：

- `peer_fin=4063`
- `client_bye=4090`
- `socket_error=81`
- `heartbeat_timeout=9`
- `loading_timeout=1`
- `send_backpressure=0`
- `send_queue_limit=0`
- `protocol=0`

服务端 loading/heartbeat 主动超时共 10 次，占关闭增量约 0.12%；没有发送背压或队列上限导致的断线。因此当前主要矛盾已不是 TCP 发送队列，而是主线程 HTTP/结算长尾。

## 图片结论核验

日志目录中的截图结论整体方向正确，但部分措辞需要收紧：

| 图片说法 | 判断 | 更准确的解释 |
|---|---|---|
| ELU 从 35.1% 升至 68.6% | 正确 | 主线程负载明显上升，但 68.6% 还不能称为“占满” |
| loop p99 从 114 ms 升至 486 ms | 正确 | 说明高峰期 HTTP 与 TCP 回调都可能被同步工作延迟 |
| loop max 最高 1367 ms，全部窗口超过 300 ms | 正确 | 66 个采样窗口最低值约 428 ms |
| 事务量从每分钟 1327 增至 2726 | 正确 | 后段同步事务数量明显更高 |
| `db.body` 最大值平均约 520 ms、最高约 699 ms | 正确 | 这是每分钟最大事务体耗时的平均值，不是普通事务的平均耗时 |
| `persistence.transaction` 最大值平均约 648 ms、最高约 2054 ms | 正确 | 包含排队后执行的完整事务区段 |
| `db.commit` 平均约 1.37 ms，因此磁盘不是主因 | 基本正确 | COMMIT 明显小于事务体；不能证明磁盘绝无影响，但它不是当前主要长尾 |
| 每秒约 2700 次 SQL、约 500 次 prepare | 基本正确 | 按首尾累计差值约为 2740 次 execute/秒、515 次 prepare/秒 |
| 问题不在 TCP | 方向正确 | TCP 发送背压为 0，主动租约超时仅 10 次；但 TCP 仍会被共享事件循环停顿间接影响 |
| 问题全是 SQLite CPU | 过度归因 | `db.body` 同时包含同步 SQLite、任务计算、奖励与其他 JavaScript 业务逻辑 |
| 内存完全健康 | 证据不足 | RSS 增长约 87 MiB，而主堆只增长约 1 MiB；暂未发现 JS 堆泄漏，但仍需更长窗口观察 native/cache/mmap |
| 主线程持续恶化 | 当前窗口支持上升趋势 | 三段趋势明显上升，但 65 分钟样本不足以证明长期无界恶化 |

因此最准确的总括是：主线程被高频同步事务体及其中的 SQL/业务计算阻塞，
磁盘提交、SQLite 锁冲突和 TCP 发送队列不是主要瓶颈；需要继续减少主线程同步工作，
但不应把所有事务体耗时都归因于 SQLite 引擎。

事件循环指标仍然偏高：

| 指标 | 数值 |
|---|---:|
| ELU 中位数 | 59.7% |
| loop p99 中位数 | 430.4 ms |
| loop p99 最大值 | 516.9 ms |
| loop max 中位数 | 836.2 ms |
| loop max 最大值 | 1367.3 ms |

按时间均分三段后，负载呈持续上升：

| 区间 | 每分钟请求 | 每分钟 CPU | ELU | loop p99 |
|---|---:|---:|---:|---:|
| 前 1/3 | 1743 | 26.9 s | 48.3% | 323.5 ms |
| 中 1/3 | 1753 | 32.9 s | 59.6% | 435.9 ms |
| 后 1/3 | 1899 | 37.2 s | 65.6% | 458.8 ms |

请求量约增加 9%，CPU/ELU 与 loop p99 的增幅更高，说明流量增长之外还存在高频路径成本随全局流水增长放大的问题。RAID 全量流水扫描符合这一特征。

部署日志还表明以下开关没有按 CPU 优先配置收敛：

- `[DIAGNOSTICS]` 显示 `sqlite=true`，即云服实际仍启用了 `SQLITE_DIAGNOSTICS`；
- 每个 `/load` 都产生 `encode.compressWait`，说明云服仍在本地压缩响应；
- `sqliteWriter.enabled=false`，最新 staging 已实现的 SQLite writer-thread 尚未启用。

这些不是 RAID 390 ms 热点的根因，但会继续占用主线程或总 CPU。下一轮部署应先上线本轮代码修复并保持其他变量不变；确认 RAID 指标下降后，再单独关闭 SQL 诊断和 `/load` 压缩，最后单独开启 writer-thread 做 A/B，避免同时改变多个变量后无法归因。

`multi_battle_quest/finish` 在 66 个采样窗口中累计 4144 次请求，最大响应时间约 8.9 秒。客户端 crash 上报中也大量出现该 URL 的 R2 timeout，但 crash 记录可能包含客户端补传的历史错误，不能直接把上报条数当成本时段新增故障数。

154 条 crash 上报中可安全提取出 66 个 `causeUrl`，其中 53 个指向
`multi_battle_quest/finish`。`startDate` 至少横跨 2026-10-01 至 2026-10-03，
进一步证明这些上报混有历史记录；路由集中度可以作为排查方向，不能作为本窗口故障次数。

## 已定位热点

`SINGLE-SETTLEMENT` 把类别 23，即 RAID_EVENT，定位为绝对异常项：

| 指标 | 类别 23 |
|---|---:|
| 请求数 | 1944 |
| 平均事务体 | 416.6 ms |
| 最大事务体 | 699.5 ms |
| `mode_rewards` 平均 | 390.0 ms |
| `mode_rewards` 最大 | 671.4 ms |

该阶段累计耗时约 758 秒，占 65 分钟采样窗口约 19.4% 的单核时间。仅这一条路径就足以显著推高主线程 ELU，并让本来最多 1.2 秒的多人结算屏障因事件循环排队出现数秒级响应长尾。

其余常见类别平均约 27-39 ms。类别 23 的主要问题在 RAID 结算末尾的两类账本读取：

1. 单局响应只需要当前 `(event_id, quest_id)` 的击杀数，却调用 `getRaidQuestCounts()` 构建整个活动的所有关卡计数。
2. 全量计数缓存用数据库级 `PRAGMA data_version` 判断失效；任意外部连接提交都会使它失效，随后再次扫描整张 RAID 流水。
3. RAID 称号核对按 `(player_id, event_id)` 聚合，但现有索引只有 `(event_id, quest_id)`，高负载时会扫描该活动的全局流水。

## 已实施优化

### 单关卡精准计数

新增 `getRaidQuestCount(db, eventId, questId)`：

```sql
SELECT COUNT(*) AS kill_count
FROM raid_event_global_kill_ledger
WHERE event_id = ? AND quest_id = ?
```

RAID 单局结算改用该查询。活动 summary 仍保留 `getRaidQuestCounts()` 的全量缓存，因为 summary 确实需要全部关卡。

### 玩家维度覆盖索引

新增幂等索引：

```sql
CREATE INDEX IF NOT EXISTS idx_raid_event_global_kill_ledger_player_event_quest
ON raid_event_global_kill_ledger (player_id, event_id, quest_id)
```

它直接服务 RAID 称号的“按玩家、活动、关卡聚合”，不改变表结构、流水主键和存档格式。已有数据库在启动 initializer 时自动创建，无需数据迁移。

### Worker 诊断探针修复

日志中旧 `sqlite-persistence` worker 的 `failed` 每个采样窗口固定增加 1，且与业务命令量无关。原因是：

- `installWorkerMemoryProbe()` 注册了一个 `message` listener 处理 `memory_probe`；
- worker 的业务 `message` listener 同时收到该消息；
- 它把没有 `statements` 的探针当成 PersistenceCommand 执行并记为失败。

worker 现在显式忽略 `memory_probe`。测试连续采样两次后确认 `failed=0`。这项修复只纠正诊断和无效异常处理，不改变业务写入结果。

### RAID 成功日志降载

每次 RAID clear 的普通成功日志改用 `gameVerboseLog()`。`GAME_VERBOSE_LOGS=false` 时不再持续构造和写出成功明细；错误与不一致告警仍保留。

### 热路径语句缓存与阶段指标

RAID 称号聚合和称号幂等写入接入现有有界 `cachedStatement`。预热后连续 100 次称号核对不再新增 prepare。

新增固定指标：

```text
[WORK-PERF].raid.finish
[WORK-PERF].raid.degree
```

下一轮日志可以分别观察全服 RAID 流水更新/单关卡计数，以及玩家称号聚合/发放，不再只能从宽泛的 `mode_rewards` 反推。

## 基准

复现命令：

```bash
npm run typecheck
npx tsc
npm run bench:raid-count
```

100000 条 RAID 流水、300 次查询的本机结果：

| 场景 | CPU |
|---|---:|
| 旧整活动 GROUP BY 后取单关卡 | 511.8 ms |
| 新 `(event_id, quest_id)` 覆盖索引计数 | 10.9 ms |
| 降幅 | 97.9% |
| 旧玩家活动聚合，无索引模拟 | 331.4 ms |
| 新 `(player_id, event_id, quest_id)` 覆盖索引聚合 | 2.7 ms |
| 降幅 | 99.2% |

`EXPLAIN QUERY PLAN` 均显示 `USING COVERING INDEX`。

索引会增加写入维护成本。十万行单事务合成写入中，新增玩家索引使 CPU
从约 81.9 ms 增至 109.9 ms，约增加 34%；折算每条约增加 0.28 微秒。
线上每次 clear 只追加一条流水，而每次结算都会读取当前关卡计数和玩家称号进度，
因此以极小的单行写成本换取每局两次覆盖索引读取，净收益明确。

## 验证

专项验证：

- persistence worker 命令顺序、回滚、PRAGMA 与内存探针：通过；
- SQLite writer-thread 组提交、命令超时、崩溃重启与进程内回退：通过；
- RAID 全量缓存的插入、重复、回滚、更新、删除和外部 writer 一致性：通过；
- RAID 单关卡精准计数：通过；
- RAID 称号索引存在且奖励行为不变：通过；
- RAID 实际清除、奖励领取与幂等流程：通过；
- 十万流水基准与查询计划：通过。

所有临时数据库仍通过项目内隔离运行器创建并清理。

## 尚未解决

RAID 热点修复后仍需重新采集云服日志确认真实收益。特别需要继续观察：

- `loopP99/loopMax` 是否下降；
- 类别 23 的 `mode_rewards` 是否从约 390 ms 回落到其他类别量级；
- `multi_battle_quest/finish` 最大耗时和客户端 R2 是否下降；
- `heartbeat_timeout/loading_timeout` 是否继续减少；
- writer-thread 逐步迁移后，主线程 `persistence.queue/transaction` 长尾是否下降。

建议按以下顺序调整云服配置，每步单独重启并采样：

1. 部署本轮 RAID 索引与精准计数修复；
2. `SQLITE_DIAGNOSTICS=false`；
3. `CN_LOAD_HTTP_COMPRESSION=off`；
4. `CN_WRITER_THREAD=1`，其余 writer 参数先采用 `SQLITE-WRITER-THREAD-20261003.md` 的默认建议。

日志中的 `sqlitePersistence.worker.failed` 每分钟固定增加 1 是旧 persistence worker 将 `memory_probe` 错当业务命令造成的虚假计数。本轮已修复。最新 writer-thread 的 `sqliteWriter.failed` 在日志中为 0，但当时 `enabled=false`，不能据此证明写线程线上效果。

本地 writer-thread 合成 A/B（800 条命令、并发 32、512 字节 payload）结果：

| 模式 | 吞吐 | loop p99 | loop max |
|---|---:|---:|---:|
| writer-thread | 10411-10911/s | 5.7-6.0 ms | 5.7-6.0 ms |
| 进程内 | 4074-4617/s | 148.2-172.9 ms | 148.2-172.9 ms |

该结果证明已迁移命令可以显著隔离事件循环，但不能代表所有结算已经离开主线程。目前 writer-thread 只覆盖已注册命令，仍应显式设置 `CN_WRITER_THREAD=1` 做线上 A/B，不改成无法审计的隐式默认。

多人结算屏障最多等待 1.2 秒，并会在所有真人都提交后提前返回。日志中数秒级 finish 长尾不只来自屏障，仍包含屏障前后的同步业务事务与事件循环排队。不要通过简单移除屏障来掩盖主线程阻塞，否则会破坏多人结算 roster 一致性。

## 复现工具

```bash
node tools/analyze-runtime-log.cjs <stderr.log> [stdout.log]
```

输出包括：

- 日志样本时间窗；
- loop p99/max 和 ELU；
- `tcpDisconnects` 增量；
- persistence worker completed/failed 增量；
- RSS/heap 起止值；
- crash `causeUrl` 路由计数及 start/upload 时间桶；
- 最慢结算类别及阶段分布。

工具只读取日志并输出聚合 JSON，不复制日志、不写玩家或连接标识。
