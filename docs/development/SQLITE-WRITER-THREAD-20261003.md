# SQLite 单写线程实施记录

日期：2026-10-03
分支：`staging`

本文记录把已注册的业务写入迁移到独立 SQLite 写线程的第一阶段实现、边界、配置、验证和回退方式。目标是主线程只保留 HTTP、联机 TCP、业务计算和读取，让数据库写入不再占用同一个事件循环。

## 1. 背景与目标

- 主服务是单进程 Node.js 服务：HTTP、联机 TCP、业务结算和 `better-sqlite3` 同步调用共用主线程。
- 联机 TCP 帧热路径本身几乎不访问数据库，卡顿来自共享事件循环：一次较重的同步事务会同时推迟心跳、广播和房间屏障。
- 本机日志实测：`domain.mission` 事务平均约 30ms、最大约 82ms；`single-quest` 平均约 5.8ms、最大约 29.5ms。
- 目标：把业务写入搬到其他核心，主线程不再支付事务体内的阻塞；同时保留关闭开关，任何部署都能立即回到单进程语义。

## 2. 运行时结构

| 位置 | 职责 |
| --- | --- |
| 主线程 | HTTP、联机 TCP、业务计算、只读数据库访问、命令排队与指标 |
| 写线程 | 唯一业务写入所有者；执行注册命令、组提交、`afterCommit` 副作用 |
| checkpoint 线程 | 既有的 WAL 维护；成功接管后写线程连接切换为 `wal_autocheckpoint = 0` |
| 备用核心 | 保留给后续实时层拆分评估 |

线程启动顺序：主进程先完成数据库初始化与迁移，再启动写线程。写线程使用独立连接，只应用 PRAGMA，不执行 initializer、迁移或版本文件写入，因此写线程重启不会重跑 schema 变更。

## 3. 命令模型

- 命令名与参数形状集中在 `src/lib/persistence/command-names.ts`，注册表在 `src/lib/persistence/command-registry.ts`。
- 命令实现绑定在 `src/lib/persistence/commands.ts`，由主进程与写线程共同加载，因此两条执行路径使用同一份领域代码。
- 一个命令拥有完整的读改写区段：可以在事务外做昂贵的上下文扫描，再通过 `runPersistenceTransactionSync` 写入。写线程会把整条命令放进批次事务，嵌套调用退化为 savepoint（已在测试中确认）。
- 参数与返回值必须是 structured-clone 安全。写线程会在 `COMMIT` 之前先做一次 `structuredClone`：无法跨线程返回的结果会让该命令回滚，而不是提交后只给调用方一个错误。
- `context.afterCommit` 注册的副作用只在批次 `COMMIT` 成功后执行；命令回滚时其副作用被丢弃。

## 4. 组提交

写线程按窗口收集命令，然后执行一次 `BEGIN IMMEDIATE`：

1. 每条命令前 `SAVEPOINT`，命令失败时 `ROLLBACK TO` 自己的 savepoint，其余命令继续。
2. 全部完成后执行一次 `COMMIT`，因此同一批命令只支付一次持久化提交。
3. 单条命令失败不改变其他命令的结果；`COMMIT` 失败则整批命令都未确认，调用方全部收到错误。
4. 只有 `COMMIT` 返回后才会向主线程确认结果。

窗口由 `SQLITE_GROUP_COMMIT_WINDOW_MS` 控制（默认 2ms，0 关闭），单批上限由 `SQLITE_GROUP_COMMIT_MAX` 控制（默认 64）。`synchronous` 仍是 `FULL`，本方案降低的是提交次数，不降低持久性等级。

## 5. 可用性、失败与降级

- 命令在主线程侧有排队上限（`SQLITE_WRITER_QUEUE_MAX`）与同时在途上限（`SQLITE_WRITER_MAX_IN_FLIGHT`）。
- 单条命令可设置超时（`SQLITE_WRITER_COMMAND_TIMEOUT_MS`）。超时后拒绝该命令并强制重启写线程：关闭连接会让未提交事务回滚，避免在未知状态下继续派发。
- 写线程异常退出时，在途与排队命令全部失败，客户端按退避自动重启，最多 `SQLITE_WRITER_MAX_RESTARTS` 次。
- 写线程启动期间，命令最多等待 10 秒就绪，避免重启后的第一个请求失败。
- `SQLITE_WRITER_FALLBACK` 默认关闭：写线程配置了但不可用时，命令直接失败，而不是静默回到进程内写入。关闭 `CN_WRITER_THREAD` 才是官方回退路径。

## 6. 状态所有权

| 状态 | 所有者 | 说明 |
| --- | --- | --- |
| 数据库 schema、版本文件、迁移 | 主进程 | 写线程只开连接，不跑初始化 |
| 业务写事务 | 写线程 | 通过命令注册表执行 |
| master data（`assets/*.json`） | 各自线程内独立副本 | 管理端重载后需要让写线程重新加载，属于后续工作项 |
| 全局虚拟时间偏移 | 主进程 | 写线程在 ready 后及每次偏移变化时通过 `set_time_offset` 同步（协议版本 2）；每玩家偏移写线程自行查库，不需要同步 |
| `active_account.json` 缓存 | 主进程 | 写线程不直接读写该文件 |
| 内存副作用（seed、抽卡 movie 等） | 命令所在线程 | 必须通过 `afterCommit` 注册 |

## 7. 配置

```env
CN_WRITER_THREAD=1
SQLITE_GROUP_COMMIT_WINDOW_MS=2
SQLITE_GROUP_COMMIT_MAX=64
SQLITE_WRITER_BUSY_TIMEOUT_MS=1000
SQLITE_WRITER_QUEUE_MAX=512
SQLITE_WRITER_MAX_IN_FLIGHT=32
SQLITE_WRITER_COMMAND_TIMEOUT_MS=30000
SQLITE_WRITER_MAX_RESTARTS=5
SQLITE_WRITER_FALLBACK=0
```

默认关闭。4 核 8G 的目标配置建议：主线程 + 写线程 + checkpoint 线程，响应编码 worker 保持默认 0。

监控字段位于 `[MEM]` 的 `counters.sqliteWriter`：`submitted/completed/failed/batches/maxBatchSize/lastCommitMs/timeouts/restarts/waiting/inFlight`，以及 `counters.persistence.writer.fallbacks`、`counters.persistence.writer.startupWaits`。写线程自身计数通过 worker 内存探针输出。

## 8. 目前迁移范围

已迁移（5 个命令）：

- `mission.settle_categories`：多人战斗结算使用的任务结算入口（`settleMissionCategoriesAsync`）。
- `single.refresh_quest_progress`：单人副本结算前的关卡进度刷新（兼深渊最好成绩修正）。
- `multi.cleanup_active_quest`：多人结算后清理本场战斗的进行中关卡记录。
- `multi.record_battle_facts`：多人结算的战斗事实写入（任务战斗事实、推荐队伍、蒸气机器人挑战、角色经验）。
- `single.settle_finish`：单人 `/finish` 的完整结算事务体与响应组装（`settleSingleQuestFinishInTransaction`）。

写线程与主线程共用同一虚拟时钟：worker ready 后及每次时间偏移变化时，主线程推送
`set_time_offset`（协议版本 2），worker 收到即调用 `setServerTimeOffset()`；每玩家偏移
仍由写线程自行查库。时间口径规则、数据库时间列归属与写线程迁移前检查清单见
`docs/development/time-base-policy.md`。

待迁移（按已知阻塞时间排序）：多人结算其余事务、抽卡、邮件/排行榜/领取历史维护、登录与会话、管理后台与工具类写入。

## 9. 验证

- `tests/sqlite-writer-thread.test.cjs`：组提交把 4 条命令合并为一次提交、失败命令只回滚自身、嵌套 savepoint、不可克隆结果回滚、`afterCommit` 只对已提交命令生效、超时后拒绝并恢复、不可用时明确失败。
- `tests/sqlite-writer-inprocess.test.cjs`：关闭写线程时同一注册项在进程内执行，未注册命令明确报错。
- `npm run test:multicore`：包含上述两个文件后 65+ 项测试通过、0 失败。
- `npm run test:multiplayer-connectivity`：全部通过，包含使用任务结算入口的多人结算用例。

验证使用仓库内隔离临时数据库，不访问 `.database/`。

## 10. 回退

```env
CN_WRITER_THREAD=0
```

重启后命令回到主进程执行，与改造前一致；没有 schema 变更、没有存档格式变更、没有客户端协议变更，因此不需要数据修复。写线程停机前会先 drain 队列再关闭连接，随后 checkpoint 所有权交回主连接。

## 11. 已知限制与后续工作

- master data 重载尚未广播到写线程；在管理端热重载资源后，需要重启写线程或补充重载命令。
- 时间列存储口径、写线程迁移前检查清单与待定项见 `docs/development/time-base-policy.md`。
- 仍未消除主线程的 CPU 长尾（大对象组装、GC、MessagePack 编码）；是否需要把实时层拆到独立线程/进程，按事件循环长尾与 TCP 断线计数决定。
- 单写线程意味着写吞吐仍受单写者限制；只有多进程 HTTP 落地且指标证明 SQLite 单写者是瓶颈时才评估外部数据库。
