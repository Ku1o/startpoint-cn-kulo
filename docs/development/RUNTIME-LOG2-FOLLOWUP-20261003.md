# PR #15 上线后六小时日志复盘

日期：2026-10-03

数据来源：`Documents/日志2` 中 PR #15 部署后的 stdout/stderr。采样窗口约 366 分钟。原始日志包含客户端上报信息，不纳入仓库；本文只保留聚合指标。

## 总结

PR #15 已显著改善原有热点：

| 指标 | 日志 1 | 日志 2 | 变化 |
|---|---:|---:|---:|
| 每分钟请求 | 1798 | 2172 | +20.8% |
| 每分钟 CPU | 32.3 s | 27.4 s | -15.2% |
| 单位请求 CPU | 18.0 ms | 12.6 ms | -29.8% |
| ELU 平均 | 57.8% | 50.4% | -7.4 个百分点 |
| loop p99 平均 | 406 ms | 95 ms | -76.5% |
| loop max 平均 | 797 ms | 414 ms | -48.0% |
| loop p99 中位数 | 430 ms | 90 ms | -79.1% |

流量增加约 21% 的同时 CPU 和事件循环延迟下降，证明此前的 TCP 竞态与 RAID 热路径优化方向正确。

RAID 类别 23 的改善尤其明显：

| 指标 | 日志 1 | 日志 2 | 变化 |
|---|---:|---:|---:|
| 平均事务体 | 416.6 ms | 56.9 ms | -86.3% |
| `mode_rewards` 平均 | 390.0 ms | 33.2 ms | -91.5% |
| `mode_rewards` 最大 | 671.4 ms | 376.1 ms | -44.0% |

日志 2 中新增的细分指标：

- `raid.finish`：14088 次，平均 32.5 ms，最大 375.3 ms；
- `raid.degree`：14088 次，平均 0.28 ms，最大 212.9 ms。

`raid.finish` 按时间三等分后平均约为 33.2 / 32.4 / 31.9 ms，没有随六小时运行继续恶化。RAID 已不是增长型泄漏，但其全服流水写入仍是稳定 CPU 成本。

## 本轮已实施的调整

本轮没有直接修改结算业务语义，而是先补齐日志分析和下一轮生产采样所需的低成本观测边界。这样可以避免根据一个总耗时极值继续盲改事务或超时参数。

### 日志分析工具

`tools/analyze-runtime-log.cjs` 在原有事件循环、内存、断线和结算阶段分析之外，新增：

- 总请求数、每分钟请求数、每分钟 CPU 和单位请求 CPU；
- 汇总每分钟 `REQUEST-PERF top` 中的路由次数、加权平均耗时、最大耗时和状态码；
- 按“次数 × 平均耗时”输出前 20 个主要路由，便于定位累计墙钟成本；
- 保留 stdout crash 路由与发生日期分析，避免把历史补传当成本窗口故障。

路由汇总来自每分钟日志中的 `top` 集合，不是全量逐请求账本。它适合识别主要热点和比较同一路由的前后变化，不适合推导未进入 `top` 的低占比路由总量。

### compact 请求阶段边界

`src/lib/request-diagnostics.ts` 为生产默认使用的 compact 模式增加一个 `preValidation` 时间点。慢请求样本新增：

```text
stages.receiveParse
stages.application
```

- `receiveParse`：从 Fastify 接收请求到请求体完成解析；
- `application`：解析完成后到请求完成的剩余墙钟时间，扣除已单独记录的自定义编码时间。

该边界用于回答日志 2 暂时无法回答的问题：数分钟的 `/finish` 极值究竟主要发生在客户端缓慢上传，还是请求体解析后的服务端路径。它不记录 URL 查询参数、请求体、IP 或玩家标识，路由数和慢样本数仍保持固定上限。

compact 模式没有安装 `preSerialization`/`onSend` 细分 hook，因此 `application` 仍可能包含序列化和响应发送。它只能用于区分“慢收包”和“解析后长尾”，不能直接当作纯业务 CPU。若解析后长尾仍显著，再只对对应路由临时启用 detailed 模式。

### 测试与开销验证

新增真实 TCP 慢请求体回归：客户端先发送不完整 JSON，等待约 120 ms 后补完，服务端 handler 再等待约 20 ms。测试验证：

- `receiveParse >= 100 ms`；
- `application >= 10 ms`；
- 请求仍返回 200，阶段拆分不改变业务结果。

`tools/runtime-overhead-benchmark.cjs` 新增 `compact-legacy` 对照。5000 个内存注入请求、5 轮中位数：

| 模式 | CPU |
|---|---:|
| 旧 compact | 154.2 ms |
| 新 compact 接收边界 | 155.9 ms |
| 增量 | 1.7 ms，约 0.34 微秒/请求 |
| detailed | 161.2 ms |

验收结果：

- `npm run test:multicore`：通过，只有原有条件性跳过；
- `npm run test:multiplayer-connectivity`：94/94 通过；
- `node --test tests/request-diagnostics.test.cjs`：8/8 通过；
- `npm run check:out -- --worktree`：通过；
- Markdown 本地链接和 `git diff --check`：通过；
- 测试临时目录已清理。

## TCP 与断线

六小时内连接关闭增量：

- `peer_fin=31172`
- `client_bye=31163`
- `socket_error=360`
- `heartbeat_timeout=63`
- `loading_timeout=1`
- `send_backpressure=0`
- `send_queue_limit=0`
- `protocol=0`

折算每分钟：

- heartbeat timeout：约 0.17 次；
- loading timeout：约 0.003 次；
- socket error：约 0.98 次。

服务端主动 loading/heartbeat 超时仍然很少，发送背压仍为 0。当前主要问题继续是共享事件循环和 HTTP 结算长尾，而不是 TCP 发送队列。

## 剩余问题

### Writer thread 未启用

日志从第一条到最后一条都显示：

```text
sqliteWriter.enabled=false
sqliteWriter.submitted=0
sqliteWriter.completed=0
```

当前 staging 已注册以下 writer 命令：

- 单人关卡进度刷新；
- 单人 `/finish` 完整结算；
- 多人任务结算；
- 多人战斗事实与角色经验；
- 多人 active quest 清理。

但由于 `CN_WRITER_THREAD` 未开启，这些命令仍回退到主线程执行。

日志 2 的相关阶段累计量：

| 阶段 | 次数 | 平均耗时 | 最大值 |
|---|---:|---:|---:|
| `single.transaction` | 139691 | 46.0 ms | 1549.9 ms |
| `single.progress_refresh` | 139691 | 6.8 ms | 1448.4 ms |
| `multi.mission` | 29669 | 24.2 ms | 1521.8 ms |
| `multi.facts_transaction` | 24151 | 12.0 ms | 1104.7 ms |
| `multi.active_quest_cleanup` | 27399 | 13.1 ms | 1525.4 ms |

这些是墙钟阶段数据，包含排队与执行，不能直接相加作为纯 CPU，但足以说明 writer-thread 有较大的可迁移覆盖面。

本地 writer A/B：

| 模式 | 吞吐 | loop p99 |
|---|---:|---:|
| writer-thread | 10411-10911/s | 5.7-6.0 ms |
| 进程内 | 4074-4617/s | 148-173 ms |

因此下一轮最高优先级不是继续修改 TCP，而是显式启用：

```env
CN_WRITER_THREAD=1
```

保持 `SQLITE_WRITER_FALLBACK=0`，出现错误时明确失败，不静默退回主线程。

### 单人/多人 finish 仍有极端长尾

日志 2 聚合：

| 路由 | 次数 | 平均 | 最大值 |
|---|---:|---:|---:|
| `single_battle_quest/finish` | 139840 | 251 ms | 4672 s |
| `multi_battle_quest/finish` | 31139 | 284 ms | 329 s |

极端最大值可能包含客户端断连、请求迟到、事件循环长暂停或监控期间的异常窗口，不能解释成单次事务持续数分钟。内部事务阶段最大值通常在 1-2 秒以内。

日志 2 使用 compact request diagnostics，旧版本只有请求总时长，无法区分“客户端缓慢上传较大的 finish 请求体”和“服务端应用执行慢”。本轮为 compact 模式增加一个 `preValidation` 时间点，慢请求样本将新增：

```text
stages.receiveParse
stages.application
```

5000 个内存注入请求、5 轮中位数：

| 模式 | CPU |
|---|---:|
| 旧 compact | 154.2 ms |
| 新 compact 接收边界 | 155.9 ms |
| 增量 | 1.7 ms，约 0.34 微秒/请求 |

该开销远低于 detailed 模式，同时能判断数分钟 finish 极值究竟发生在收包还是业务处理。

需要注意：compact 模式中的 `application` 是“请求体解析完成后的剩余墙钟时间”，由于没有安装
`preSerialization`/`onSend` 细分 hook，它还包含序列化和响应发送时间（已单独记录的自定义编码时间除外）。
因此它适合区分“慢收包”和“解析后长尾”，不能直接当作纯业务 CPU；若解析后长尾仍然显著，再针对对应路由
临时启用 detailed 模式继续拆分。

多人分段的稳定平均值：

- `multi.reward_transaction`：13.6 ms；
- `multi.facts_transaction`：12.0 ms；
- `multi.mission`：24.2 ms；
- `multi.active_quest_cleanup`：13.1 ms；
- `multi.barrier`：63.5 ms。

一小部分拥塞窗口中多个阶段同时升高，说明主要是全局主线程/写队列排队，不是某个多人函数永久卡死。

不能通过删除 1.2 秒 settlement barrier 来规避长尾；该 barrier 维护真人结算 roster 一致性，并会在真人全部提交后提前结束。

### SQL 诊断仍开启

启动日志仍显示：

```text
[DIAGNOSTICS] {"memory":"basic","sqlite":true,...}
```

应在生产配置设置：

```env
SQLITE_DIAGNOSTICS=false
```

它不是当前最大热点，但在每秒数千次 SQL 的负载下会持续增加包装和采样成本。

### `/load` 本地压缩仍开启

日志 2：

- `/load` 约 2822 次；
- `encode.compressWait` 也是 2822 次；
- 平均约 70 ms；
- 累计约 198 秒；
- 最大约 4.3 秒。

带宽不是瓶颈时应设置：

```env
CN_LOAD_HTTP_COMPRESSION=off
```

### Statement cache 暂不扩容

日志 2 的 statement cache：

- hit 增量约 6109 万；
- miss/eviction 增量约 70 万；
- 命中率约 98.9%；
- miss 约 31.9 次/秒。

虽然 128 条连接内缓存持续淘汰，但命中率已经较高，且 176 个缓存调用中约 22 个 SQL 形状会随字段或参数数量变化。缺少 A/B 证据时不应直接扩大缓存，避免用内存保存一次性动态 SQL。

## 内存

| 指标 | 起点 | 终点 | 变化 |
|---|---:|---:|---:|
| RSS | 728 MiB | 965 MiB | +237 MiB |
| 主线程 heapUsed | 333 MiB | 297 MiB | -36 MiB |

RSS 上升但 JS heap 下降，不符合普通 JavaScript 堆泄漏形态。可能来源包括 SQLite page cache/mmap、native buffer、WAL、worker 堆和操作系统提交策略。需要更长窗口和 native memory 证据，暂不做泄漏结论。

有界容器表现正常：

- `finishCache` 达到固定上限 512；
- `multiPlayerContext` 上限 1000；
- `npcPool.cachedParties` 达到固定上限 5000；
- settlement/room 数量随在线对局波动，没有单调无界证据。

## Crash 上报说明

日志 2 有 1001 条 crash 行，其中可提取出的路由以 `multi_battle_quest/finish` 最多。但 `startDate` 跨越多天，说明客户端会补传历史错误，不能用 crash 行数直接计算本窗口故障率。

可信用法：

- 用路由集中度定位排查方向；
- 用服务端 `REQUEST-PERF`、阶段计时和 `tcpDisconnects` 计算本窗口指标；
- 不把 crash 上传时间等同于错误发生时间。

## 四核多核适配改进方案

### 当前线程模型与缺口

项目并非完全以单线程运行，当前已经存在多个专用 worker：

| 执行单元 | 当前职责 | 是否分担主要请求 CPU |
|---|---|---|
| Node 主线程 | HTTP、TCP、房间状态、业务计算、同步读库和未迁移写事务 | 是，仍是主要瓶颈 |
| SQLite writer thread | 已注册的完整业务写命令和组提交 | 可以，但日志 2 中未启用 |
| SQLite persistence worker | 少量已命令化的纯 SQL 写入 | 覆盖有限 |
| SQLite checkpoint worker | WAL checkpoint 和截断维护 | 不是主要业务 CPU |
| NPC/seed 等 worker | NPC 队伍池、随机种子持久化等后台工作 | 少量 |
| response worker | MessagePack 后处理、Base64 和可选压缩 | 默认关闭；现有 A/B 中总 CPU 增加 |

`CN_MULTICORE` 当前自动选择四核 SQLite 参数并开启 checkpoint worker，但不会自动开启
`CN_WRITER_THREAD`。这是有意保留的部署审计开关，却也意味着“多核模式已开启”不代表主要业务事务已经离开主线程。
日志 2 的实际状态正是 checkpoint worker 在运行，而 `sqliteWriter.enabled=false`。

多核改造的目标不是让四个核心都持续满载，而是：

1. 主线程尽量只持有网络连接、房间顺序和请求调度；
2. 完整的同步 SQLite 读改写事务交给唯一 writer；
3. 只有跨线程复制成本显著低于计算成本的完整任务才进入计算 worker；
4. 以主线程 ELU、事件循环 p99、断线和单位请求 CPU共同判断收益。

### 阶段 A：先启用现有 writer 能力

建议生产环境先设置：

```env
CN_MULTICORE=1
CN_WRITER_THREAD=1
SQLITE_WRITER_FALLBACK=0
SQLITE_CHECKPOINT_WORKER=1

CN_RESPONSE_WORKERS=0
SQLITE_DIAGNOSTICS=false
CN_LOAD_HTTP_COMPRESSION=off
```

writer 参数先使用已验证的默认值：

```env
SQLITE_GROUP_COMMIT_WINDOW_MS=2
SQLITE_GROUP_COMMIT_MAX=64
SQLITE_WRITER_BUSY_TIMEOUT_MS=1000
SQLITE_WRITER_QUEUE_MAX=512
SQLITE_WRITER_MAX_IN_FLIGHT=32
SQLITE_WRITER_COMMAND_TIMEOUT_MS=30000
SQLITE_WRITER_MAX_RESTARTS=5
```

目标线程预算：

| 资源 | 建议用途 |
|---|---|
| 核心 1 | Node 主线程：HTTP、TCP、房间状态 |
| 核心 2 | SQLite writer：已注册业务写事务 |
| 核心 3 | checkpoint、NPC、seed 等低频后台任务 |
| 核心 4 | 操作系统、GC 以及后续经 A/B 通过的完整任务 worker |

不建议手工设置 CPU affinity。Node worker thread 会由操作系统调度到其他核心；固定亲和性可能让 GC、系统中断和短时突发缺少调度余量。

启用后首先确认：

```text
sqliteWriter.enabled=true
sqliteWriter.started=true
sqliteWriter.ready=true
sqliteWriter.submitted > 0
sqliteWriter.completed 接近 submitted
sqliteWriter.failed=0
sqliteWriter.timeouts=0
sqliteWriter.restarts=0
```

同时比较：

- 单位请求 CPU；
- 主线程 ELU、`loopP99`、`loopMax`；
- `heartbeat_timeout`、`loading_timeout`、`socket_error`；
- writer 的 `waiting/inFlight/maxWaiting/maxInFlight`；
- `lastBatchSize/maxBatchSize/lastCommitMs`；
- 单人和多人结算各阶段的 p95/p99。

writer 会把同步事务从主事件循环迁到其他核心，但跨线程调度仍可能使进程总 CPU略微增加。只要单位请求 CPU 没有明显回退，而主线程长暂停、TCP 超时和请求长尾稳定下降，就属于有效的多核隔离收益。

回退方式：

```env
CN_WRITER_THREAD=0
```

重启后同一注册命令回到进程内执行，不涉及 schema、存档格式或客户端协议回滚。`SQLITE_WRITER_FALLBACK` 继续保持
`0`，避免 worker 故障时静默把重事务重新压回主线程。

### 阶段 B：扩大完整业务命令覆盖

当前 writer 已覆盖：

- 单人关卡进度刷新；
- 单人完整 finish；
- 多人战斗事实与角色经验；
- 多人 mission 结算；
- 多人 active quest 清理。

日志 2 显示多人结算仍有以下主线程工作：

- `multi.progress_refresh`；
- `multi.reward_transaction`，平均约 13.6 ms；
- 多人 awake mission 和 active mission 的同步计算/读改写；
- 响应前的数据库读取与对象组装。

下一项代码改造优先级：

1. 多人 `reward_transaction`；
2. 多人 `progress_refresh`；
3. 多人 awake/active mission 结算；
4. `gacha.transaction`；
5. 高频 mail/shop/equipment 写事务；
6. 登录和 session 写入。

迁移规则：

- 一个 writer 命令必须拥有完整的读取、校验、计算、写入和可克隆返回值；
- 不把一个读改写事务拆成“主线程读、worker 写”，避免陈旧读和竞态；
- 参数和返回值保持 structured-clone 安全；
- seed、movie、缓存等非数据库副作用通过 `afterCommit` 执行；
- 每玩家顺序继续由现有 player write queue 保证；
- 每次只迁移一个完整事务，并保留同一实现的进程内回退路径。

### 阶段 C：合并多人 finish 的 worker 往返

多人 finish 不能把整条 HTTP handler 一次性搬进 writer，因为 settlement barrier、房间生命周期、socket 和
`SessionManager` 必须继续由实时主线程单一持有。适合按 barrier 分成两个完整持久化命令。

barrier 前命令：

```text
multi.settle_pre_barrier
  - progress_refresh
  - reward_transaction
  - battle facts
  - character EXP
  - 返回奖励、任务事实和响应所需快照
```

主线程：

```text
  - 房间 lifecycle 迁移
  - settlement barrier
  - mate roster 合并
  - MVP/贡献等需要 barrier 结果的派生值
```

barrier 后命令：

```text
multi.settle_post_barrier
  - mission settlement
  - awake mission
  - active mission reconciliation
  - active quest cleanup
  - 返回最终任务与玩家响应字段
```

这比为每个小步骤单独发送一个 worker 消息更合适，可以减少：

- structured clone 次数；
- 主线程与 worker 的往返；
- SQLite transaction/COMMIT 次数；
- 同一玩家命令在队列中的重复排队。

必须保持的正确性边界：

- finish cache 和 `acquireFinishExecution` 继续保证同一 finish 幂等；
- battle instance、play ID 和 room generation 继续防止旧请求清理新一局；
- settlement barrier 保留 1.2 秒兼容上限，并在真人全部提交后提前返回；
- 房间 Map、socket、`SessionManager` 和 coordinator queue 不进入 writer；
- 命令失败时不得留下部分奖励、部分任务或已删除 active quest；
- 响应缓存只能在数据库 COMMIT 成功并完成最终组装后写入。

### 阶段 D：统一 SQLite 写入所有者

项目当前同时存在：

- `sqlite-writer-worker`：执行完整领域命令和组提交；
- `sqlite-persistence-worker`：执行少量纯 SQL statement 命令。

SQLite 同一时刻仍只有一个写者。长期保留两条业务写连接不会带来真正的写并行，反而会增加锁竞争、busy 重试和 checkpoint 所有权复杂度。

建议逐步把 `runPersistenceSqlCommand` 的 player/news 等命令迁入 writer registry，最终形成：

```text
所有业务写入 -> 唯一 SQLite writer
主线程       -> 主只读/兼容读取连接
checkpoint   -> 只负责 WAL 维护
```

合并前需要统计两套 worker 的提交次数、busy 和队列等待；合并后必须验证 player/news 的顺序、失败语义和关机 drain。不要通过再增加 SQLite 写线程数量来追求四核利用率。

### 阶段 E：只评估端到端 `/load` worker

此前 `/load` 读取 worker 原型使总 CPU 增加约 60%，主要原因是大对象在线程间多次传输：

```text
worker 读取/组装 -> 大对象复制回主线程 -> 主线程 MessagePack
-> 可选 response worker -> 再次复制
```

如果 writer 扩面后 `/load` 重新成为主要热点，只评估端到端命令：

```text
只读事务 -> 玩家快照组装 -> MessagePack -> AIR uint32 修正 -> Base64
-> 仅返回最终 Buffer/字符串
```

要求：

- 使用同一只读事务获得一致快照；
- 中间大对象不返回主线程；
- 设置并发、排队字节数、超时和 worker 故障本地回退上限；
- 用真实大存档比较总 CPU、主线程 ELU、墙钟和 RSS；
- 只有多轮中位数稳定获益才启用。

日志 2 中 `/load` 频率远低于 finish，因此该项低于 writer 扩面。当前 `CN_RESPONSE_WORKERS` 保持 `0`；已有测试中
1/2/3 个响应 worker 均增加总 CPU，不能仅为“使用更多核心”而开启。

### 阶段 F：实时 Hub 独占核心

只有在 writer 完整启用、主要 finish 持久化已经迁移之后，主线程事件循环仍持续成为瓶颈，才进入多进程实时层改造。

长期目标：

```text
HTTP/API 进程
    |
    | IPC 命令和事件
    v
Realtime Hub
    - TCP sockets
    - rooms
    - SessionManager
    - admission
    - barrier
    - recruitment
```

现有 `EmbeddedMultiCoordinator` 已按房间串行执行命令，并且接口值可以序列化，可作为未来 IPC coordinator 的演进起点。迁移顺序：

1. 定义不暴露 `net.Socket` 和可变 room 对象的 coordinator 接口；
2. 把 HTTP 路由对 `getRoom()`、`SessionManager` 和全局 Map 的直接读取改为查询/命令；
3. 为每条命令增加 request ID、room instance ID、generation 和幂等语义；
4. 先实现同进程 adapter 回归，再实现 IPC adapter；
5. Hub 独占 TCP 监听端口和全部房间状态；
6. API 进程只通过 IPC 查询或提交房间命令；
7. 加入 Hub 重启时的房间终止、客户端重连和 readiness 策略。

在这些边界完成前，不要直接使用 Node cluster 或 PM2 启动四份完整 CN 服务。直接复制会导致每个进程拥有不同的
rooms、SessionManager、finish cache 和 barrier，同一房间玩家还可能被分配到不同进程，同时争写同一个 SQLite。

### 数据库与多进程边界

worker-thread 阶段不需要迁移 MySQL。SQLite 进程内调用和单写线程的开销更低，当前主要目标是把同步事务从网络事件循环移走。

只有同时满足以下条件才重新评估 MySQL/PostgreSQL：

- HTTP 层确实需要多个独立进程或多台服务器；
- 多个 API 进程必须共享可写数据库状态；
- 实时房间状态已由独立 Hub 单一持有；
- writer 指标证明 SQLite 单写吞吐，而不是主线程事件循环，已经成为容量上限；
- 已准备把大量同步领域 API 改造成异步连接池事务。

数据库如果仍与 Node 部署在同一台 4 核服务器上，也会竞争相同 CPU；换库本身不会降低 MessagePack、任务计算或房间协议的 CPU。

### 分阶段验收门槛

每个阶段只改变一个主要变量，至少覆盖一个高峰 30-60 分钟窗口，并与相邻同类窗口比较。

| 指标 | 通过标准 |
|---|---|
| 正确性 | 现有多核、多人连接、finish 幂等、任务和抽卡回归全部通过 |
| writer 健康 | failed/timeouts/restarts/queueFull 为 0，submitted 与 completed 差值可解释 |
| 主线程 | ELU、loop p99/max 长尾或 heartbeat timeout 至少一项稳定改善 |
| CPU | 单位请求 CPU 不出现不可解释的明显回退 |
| 延迟 | 目标事务 p95/p99 改善，不能只看平均值 |
| 数据一致性 | 奖励、任务、active quest 和缓存不存在部分提交 |
| 内存 | RSS/worker heap 有界，队列和 retained bytes 不持续增长 |
| 可回退 | 关闭单一环境变量并重启即可回到上一阶段 |

代码阶段的可复现验证至少包括：

```bash
npm run test:multicore
npm run test:multiplayer-connectivity
PERF_ROUNDS=5 node tools/runtime-overhead-benchmark.cjs
node tools/sqlite-writer-latency-benchmark.cjs --commands=800 --concurrency=32 --payload=512
```

新测试继续通过 `tools/run-isolated-check.cjs` 使用项目内 `tmp/` 隔离数据库，并在成功、失败和信号退出时清理。生产 A/B 只保留聚合日志，不把含客户端上报内容的原始日志提交到仓库。

### 明确不做项

当前阶段不建议：

- 为了显示四核占用而盲目增加 response worker；
- 恢复已经验证总 CPU 更高的 `/load` 中间对象 worker；
- 增加多个 SQLite 业务写线程；
- 删除 settlement barrier 或放宽全部超时；
- 直接用 cluster/PM2 复制完整 CN 进程；
- 在没有 SQLite 单写瓶颈证据时迁移 MySQL；
- 同时启用多个生产开关，导致无法归因。

## 建议顺序

每项单独重启、单独采样，避免多变量同时变化：

1. `SQLITE_DIAGNOSTICS=false`
2. `CN_LOAD_HTTP_COMPRESSION=off`
3. `CN_WRITER_THREAD=1`
4. 保持其他 writer 参数为 `SQLITE-WRITER-THREAD-20261003.md` 的建议值
5. 高峰运行 30-60 分钟后比较：
   - `loopP99/loopMax`
   - 单位请求 CPU
   - `sqliteWriter.submitted/completed/failed/timeouts/restarts`
   - `single.transaction`
   - `multi.mission/facts_transaction/active_quest_cleanup`
   - `multi_battle_quest/finish` p95/p99
   - `heartbeat_timeout/loading_timeout`

## 后续代码优先级

若启用 writer-thread 后多人 finish 仍有明显长尾，再按顺序迁移：

1. `multi.reward_transaction`
2. 多人结算剩余读改写事务
3. `gacha.transaction`
4. 高频 player/mail 事务

每次只迁移一个完整事务，保持同一份命令实现同时支持 writer 与进程内回退，并补充结果一致性、崩溃、超时和 `afterCommit` 回归。

当前不建议：

- 删除 settlement barrier；
- 直接拆 TCP 子进程；
- 迁移 MySQL；
- 盲目扩大 statement cache；
- 同时修改所有超时阈值。

## 复现

```bash
node tools/analyze-runtime-log.cjs <stderr.log> [stdout.log]
npm run test:multicore
npm run test:multiplayer-connectivity
PERF_ROUNDS=5 node tools/runtime-overhead-benchmark.cjs
node tools/sqlite-writer-latency-benchmark.cjs --commands=800 --concurrency=32 --payload=512
```

所有基准临时目录位于仓库 `tmp/` 并自动清理。
