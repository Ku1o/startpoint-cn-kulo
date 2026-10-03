# 服务端内存后续优化与诊断（2026-09-19）

当前诊断默认值已由 [服务端常驻监测与详细诊断](server-diagnostics-modes.md) 更新：Windows 原生探测默认关闭，内存改为轻量汇总，SQL 采样可独立开关。以下保留当时的实现和验证记录。

本次减少任务结算读出的对象、固定 SQL 的重复编译、种子写盘的临时 Buffer 和正常战斗日志量，并补充 Windows 进程诊断。没有数据库迁移、存档格式变更或奖励规则调整，不需要客户端和 CDN 更新。长期 RSS 增长是否改善须通过部署后的连续数据验证。

## 运行变化

- 任务结算只读取本次参与计算的 category/mission ID 对应的进度和阶段；两个固定 SQL 使用 JSON 参数及已有索引，不再为少数任务加载整个类别。重复范围合并，玩家隔离、阶段状态、事务和奖励防重复行为保持不变。
- 角色、装备、道具、关卡、任务战斗事实及玩家基础读取复用现有 statement LRU。每连接上限仍为 128，不缓存结果；不共享会修改 bind/raw/pluck 等模式或正在迭代的 statement。
- 每次种子文件原子写入复用一个临时 Buffer 完成 UTF-8 编码及主文件、临时文件、备份摘要校验。仍按原时机写完整 JSON 快照，保留 fsync、回读校验、备份、原子替换、失败重试与关闭 flush；没有扩大可能丢失更新的时间窗口。
- 普通 `[MULTI-BARRIER]`、`[MULTI-SETTLEMENT]`、`[RUSH]` 日志按三类分别保留每分钟前三个样例，随后输出 `[GAME-SUMMARY]` 总数和抑制数。被抑制的消息不构造字符串。异常、拒绝和修复日志仍保留。

## 新增诊断字段

仍由现有一分钟一次的 `[MEM]` 记录承载，离线工具 `tools/analyze-memory-log.cjs` 兼容新旧日志。

| 字段 | 含义与限制 |
| --- | --- |
| `runtime` | Node、V8、better-sqlite3 版本，以及平台和架构 |
| `osProcess.memory.privateBytes` | Windows 进程私有提交内存；与 RSS 的定义不同 |
| `osProcess.memory.workingSetBytes` | Windows 工作集；与主样本 RSS 采样时间不同 |
| `osProcess.memory.virtualBytes` | 虚拟地址空间占用，不能当作实际 RAM 用量 |
| `osProcess.memory.handleCount / threadCount` | 句柄和线程数量 |
| `osProcess.memory.regions` | VirtualQueryEx 的 private/mapped/image 已提交区域、保留地址空间、区域数量；不读取内存内容 |
| `osProcess.ageMs / stale / failed / pendingMs` | 异步采样的年龄、有效性和进行状态；无样本、失败或超过 120 秒时标记过期 |
| `counters.sqlite.main` | 主连接公开 prepare 的累计次数、错误数、每 64 次采样一次的耗时，以及启动时的 SQLite 配置 |
| `workers[name=npcPool].diagnostics.sqlite.npc` | NPC 连接的相同统计，使用对应 worker 的样本有效性 |
| `counters.connections.http / tcp` | Node 服务实际连接数及样本年龄 |
| `counters.activeResources` | Node 活跃资源类型计数，最多 64 种类型 |
| `counters.stdio` | stdout/stderr 在 Node 流中的待写字节，不含操作系统或外部日志收集器缓冲 |

区域统计是虚拟内存元数据，**不是按类别拆分的驻留内存**。private 区域同时可能包含 V8 和原生分配；映射页发生写时复制后仍可能显示为 mapped/image。不能把这些字段与 RSS、heapTotal 相加，也不能据此直接认定某个原生模块泄漏。

SQLite 当前依赖未提供所需的 db_status 原生字节统计，明确输出 `nativeBytesAvailable=false`。prepare 计数覆盖公开的 `db.prepare` 调用，包括未经过缓存的调用；不包含驱动内部事务控制语句。累计计数和配置参数不参加离线容器增长排名。配置只在连接建立时读取，不代表动态 PRAGMA 修改后的值。

Windows x64 上每次探测启动一个隐藏 PowerShell，最多保留一个在途请求和一个最近结果，外层超时 5 秒。脚本只查询当前服务 PID 的进程计数和地址区域，不读取进程内存内容、不生成 dump、不强制 GC、不清空工作集。失败不会阻断游戏请求；下一次采样重试。受执行策略或工具缺失影响时，检查 `osProcess.failed/stale`。

## 开关与交付依赖

环境变量在服务启动前设置；常规部署按原流程重启后生效。

| 变量 | 默认 | 回退方式 |
| --- | --- | --- |
| `MISSION_SCOPED_READS` | `true` | `false` 恢复按整个任务类别读取 |
| `SQL_STATEMENT_CACHE` | `true` | `false` 每次重新 prepare |
| `GAME_ROUTINE_LOGS` | `summary` | `full` 恢复逐条普通日志；`off` 关闭这三类普通日志 |
| `PROCESS_MEMORY_DIAGNOSTICS` | `false` | Windows x64 排障时设为 `true`，会启动隐藏 PowerShell 进程诊断 |
| `MEMORY_DIAGNOSTICS` | `true` | `false` 停止内存诊断，包括 SQLite 统计 |
| `SEED_STREAM_WRITES` | `true` | `false` 使用原有 Object/JSON 写入路径 |

`tools/capture-native-memory.ps1` 是**新增运行依赖**，必须与主线程诊断模块一起交付；它不同于只供分析机使用的 `tools/analyze-memory-log.cjs`。没有 npm 依赖变更。

本次运行文件包括下列 19 个 `src/` 模块及逐一对应的 `out/` JavaScript，再加上上述 PowerShell 脚本。不能只交付调用方而遗漏新增辅助模块。

```text
data/domains/character.ts
data/domains/equipment.ts
data/domains/item.ts
data/domains/mission.ts
data/domains/mission_battle_facts.ts
data/domains/player.ts
data/domains/quest.ts
data/index.ts
lib/memory-diagnostics.ts
lib/process-memory-probe.ts
lib/sqlite-diagnostics.ts
lib/routine-game-logging.ts
lib/mission/settlement.ts
lib/seed-stream-file.ts
multi/settlement-snapshot.ts
multi/state/SessionManager.ts
multi/tcp/server.ts
routes/api/rushEvent.ts
workers/quest-npc-party-pool-worker.ts
```

## 本地验证与局限

Windows x64、Node 20.20.2、better-sqlite3 11.3.0 下，隔离目录的 `npm run build` 完成；对应的 19 个生成模块已更新到源码仓库 `out/`。

- 内存诊断、种子持久化、抽卡反馈及日志分析：34 个测试通过。
- V1/V2 存档兼容、实际隔离 HTTP 导入导出、回滚和非法输入：8 个测试通过。没有操作真实玩家存档。
- 深渊查询与常规任务测试已更新过期的内部调用预期：普通塔、EX 塔分别只执行一次修订检查；客户端计数已达目标的称号跳过重复事实计算。深渊测试同时检查修订结果、范围边界、当前版本、其他玩家/类别和重复读取；称号测试检查同次响应发奖、数据库所有权、进度上限、重复上报不重复领奖及旧存档补修。直接运行 `tests/character-awake-query-scope.test.js`、`tools/mission_regular_facts.test.cjs`，12 个测试全部通过，无跳过、无诊断替换加载器。此次测试更新没有修改运行代码、奖励规则或存档协议。
- Active Mission 测试不退出由既有房间清理定时器导致；隔离测试加载器仅对该定时器 unref 后，原测试全部断言通过并正常退出。运行代码没有因此变更，该项验证使用辅助加载器，区别于直接运行原脚本。
- 使用真实 Fastify、Windows 进程查询和 NPC worker 完成两次诊断采样，核对主线程与 NPC 的 SQLite 字段、HTTP 连接和区域统计，并验证离线工具读取。

隔离合成负载对照如下，不代表线上端到端延迟或节省的内存容量：

| 对照 | 原路径 | 优化路径 |
| --- | ---: | ---: |
| 3,000 个任务、9,000 个阶段，当前只涉及 50 个任务/150 个阶段：每次读取平均耗时，3 轮各 200 次 | 8.15 ms | 0.20 ms |
| 六种固定读取各重复 2,000 次：预热后新增 prepare 次数 | 12,000 | 0 |
| 同上：循环总耗时 | 157.8 ms | 42.2 ms |

第一项读取耗时减少约 97.6%，选中结果与原路径过滤后的结果一致；第二项使用独立进程切换缓存开关。没有长时间云服负载验证，不能据此声称 RSS 增长已经消除。

部署后应比较同一服务版本、相近负载的连续 12～24 小时数据，跳过冷启动阶段，结合主线程/worker 堆低值、privateBytes、映射区域、句柄、连接数、prepare 增量和写入量判断。若私有提交内存低值仍持续抬高而 JS 堆、映射和业务容器稳定，下一步仍需针对原生分配做进一步定位；单靠当前统计不能区分所有原生分配来源。
