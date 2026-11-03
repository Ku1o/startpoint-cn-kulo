# 服务端常驻监测与详细诊断

服务默认保留每分钟的内存、队列与性能汇总，关闭 Windows 原生内存区域扫描和详细内存统计。内存与 SQL 诊断可分别控制；诊断开关不修改数据库结构、存档格式、奖励、事务或 SQL statement 缓存。

> 2026-10-02 的 CPU 成本对照和完整实施台账见 [四核服务器 CPU 优化实施记录](MULTICORE-CPU-OPTIMIZATION-20261002.md)。

## 默认配置

| 环境变量 | 默认值 | 行为 |
| --- | --- | --- |
| `MEMORY_DIAGNOSTICS` | `true` | 每分钟输出 `[MEM]`，含 RSS、主线程和 worker 堆、连接与业务队列 |
| `MEMORY_DIAGNOSTICS_DETAIL` | `false` | `true` 恢复 V8 附加统计、活跃资源枚举、房间阶段分类、NPC/种子池条目遍历 |
| `PROCESS_MEMORY_DIAGNOSTICS` | `false` | Windows x64 上显式设置 `true` 后才启动 PowerShell 进程内存区域探测，且需要内存采集开启 |
| `SQLITE_DIAGNOSTICS` | `false` | `true` 临时开启 SQL prepare/get/all/run 计数与每 64 次一次的计时采样 |
| `SQLITE_COMMIT_DIAGNOSTICS` | `false` | 显式 `true` 才开启逐事务 WAL 状态读取和慢提交详情；还需 SQL 诊断及基础性能监测开启 |
| `ROUTE_PERF_SUMMARY` | `true` | 保留 CPU、事件循环、请求状态/耗时及结算、编码、数据库提交等阶段汇总 |
| `ROUTE_PERF_DETAIL` | `false` | `true` 开启 receive/application/serialize 等每请求阶段细分 |
| `SLOW_OPERATION_DIAGNOSTICS` | `true` | 主业务进程保留有界慢阶段样本，随基础性能汇总输出；关闭基础性能监测时也关闭采样 |
| `SLOW_OPERATION_MS` | `250` | 慢阶段阈值，单位毫秒，限制为 1—60000；无效值回到 250 |

详细内存和原生内存开关只接受 `1/true/yes/on` 开启；未配置或无效值保持关闭。环境变量须在服务启动前设置，修改后重启生效。现有 `.env` 若显式写了 `PROCESS_MEMORY_DIAGNOSTICS=true`，该值仍会覆盖新的默认值，须改成 `false` 才能停用。仅更新 `.env.example` 不会更改现有 `.env`。

提交详情诊断默认不执行额外的同步 `-shm` 文件读取。关闭它不改变 SQLite 的正常共享内存访问、事务、同步级别、WAL 维护或 `[WORK-PERF]` 通用提交计时；只停用 `[SQLITE-COMMIT]` 的帧数、代际、回填与慢提交详情。显式启用时，额外读取分别计入 `db.probe.settings/before/after`，避免将诊断自身的等待漏在业务阶段之外。

## 有界慢操作记录

主业务进程启动时输出 `[SLOW-OPERATIONS-CONFIG]`。`[SLOW-OPERATIONS]` 随现有性能汇总输出，每轮最多 16 条：保留首次 4 条以观察故障开始，剩余位置保存最长的 12 条，并报告总数及未保留数。没有新定时扫描、逐请求日志、数据库查询或文件读取。worker 和独立实时 owner 不启用这组主进程样本。

样本仅包含业务域、稳定操作名、阶段、起止 UTC、墙钟耗时、同步阶段的线程 CPU 耗时以及失败标志。操作名去掉冒号后的动态后缀；不记录玩家 ID、SQL、参数、请求载荷、文件路径或异常正文。Node 不支持线程 CPU 时显示 `null`；排队/异步等待始终显示 `null`，因为等待期间其他请求消耗的 CPU 不能归到该等待。

诊断时钟或 CPU 采样自身失败只增加 `observerErrors`，不改变业务返回、原始异常或队列推进；该计数随同一有界摘要报告。业务执行失败仍按原事务逻辑向上传递。

`persistence.order` 是玩家或全局顺序队列等待，`persistence.gate` 是写门等待，`persistence.yield` 是主动让出事件循环后等待恢复；三者属于等待阶段。`db.begin/body/commit`、`db.probe.*` 和同步事务的 `db.sync.body/persistence.sync` 属于同步阶段。现有 `measureServerWork` 的同步业务与编码阶段也可出样本；没有协调器上下文时标签为 `unscoped`。阶段可能嵌套，不能把样本耗时简单相加当作总 CPU。起止 UTC 以开始墙钟加单调计时计算，避免中途系统时钟调整造成负耗时。

这些记录用于定位慢阶段，不能单独证明磁盘、GC 或宿主调度根因，也不取代调用栈和系统侧证据。修改默认诊断负担不等于已经解决某次历史卡顿。

## 登录压缩容量保护

启用 `CN_LOAD_HTTP_COMPRESSION` 后，`/load` 压缩共用主进程预算，默认最多 4 个在途任务、32 MiB 原始输入。可用 `CN_LOAD_HTTP_COMPRESSION_MAX_CONCURRENT`（1—32）和 `CN_LOAD_HTTP_COMPRESSION_MAX_INPUT_BYTES`（1—268435456 字节）调整。编码 worker 只返回原有 Base64，压缩统一在父侧调用异步 zlib；worker、主线程编码及 worker 失败后的本地回退不会各自再建压缩配额。

容量不足或单个输入超预算时不排队，也不先复制一份 Base64 Buffer。允许 identity 的客户端立即收到语义和原字节相同的未压缩回包，代价是传输量变大；明确禁止 identity（含适用的 `*;q=0`）时返回空 HTTP 503，并附 `Retry-After: 1`。没有任何可用编码时返回空 406。小于压缩阈值但禁止 identity 的请求仍尝试可接受的压缩。压缩错误也不能绕过 identity 禁令。协商依据 [RFC 9110 §12.5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.3)。

只有底层压缩成功或报错后才释放配额；HTTP 断连不会把仍执行中的任务记成已完成，也不增加 Promise 超时来伪装取消。既有 `responseWorkers` 内存计数增加压缩在途数、输入字节、拒绝数和失败数，无新增扫描定时器。`Content-Encoding`、`Content-Length` 和 `Vary` 按实际返回内容处理，非 `/load` 回包路径不启用本保护。

这只限制登录回包的压缩阶段，不是所有登录业务/网络发送的总并发或进程 RSS 上限；未压缩内容仍需正常发送。它用于抑制卡顿后的压缩积压放大，不能代替对最初停顿的根因定位，也不能据本地验证承诺线上收益。

## 基础监控行为

服务启动时输出一次 `[DIAGNOSTICS]`，列出实际 memory 模式、sqlite、nativeMemory 和周期。内存与 SQL 均关闭时不安装这个采集器；基础性能监测仍由 `ROUTE_PERF_SUMMARY` 单独决定。默认请求汇总只使用 Fastify 已有的总耗时，在错误/超时/中止和响应结束处计数；`ROUTE_PERF_DETAIL=true` 才安装完整阶段 hook。

紧凑模式仍在根 Fastify 实例为全部请求建立状态，因此通过 plugin 注册的路由不会丢失 outcome 或自定义编码耗时。abort 和 timeout 保留请求真实开始时间，同一个请求即使同时触发 abort、socket close 和迟到的 handler 完成也只计数一次。相关回归覆盖 plugin route、自定义编码、延迟 abort、timeout 和固定基数路由统计。

SQLite PRAGMA 不在连接注册时永久缓存。每次诊断采样都会重新读取 `cache_size`、`mmap_size`、`synchronous` 和 `wal_autocheckpoint`，因此 checkpoint worker 接管或故障回退后的所有权状态可以被正确观察。persistence worker 也报告自身实际 PRAGMA。

## 轻量模式的边界

- 保留进程 RSS、每线程 heapUsed/heapTotal/external/arrayBuffers、线程样本年龄、发送和编码队列、存档持久化队列、连接数及有限业务容器计数。
- 不调用 `getHeapStatistics` 或 `getActiveResourcesInfo`，不为统计房间阶段或 NPC/种子条目数遍历容器。房间只记录总数；种子条目 `entries` 为 `null`，表示未采集而非零。
- 启用 SQL 采样时，主连接和 NPC 连接仍记录原有 SQL 计数、采样时长及错误计数。关闭时不包装 `prepare/get/all/run`；SQL 编译缓存、查询结果和事务回滚保持原行为。
- 仍然每分钟采集，保留原 120 秒过期判断及有界注册表、worker 在途探测限制。不会因隐藏日志而继续运行默认关闭的深度采集。
- 不启动外部 Memory Capture 工具。原生采集是服务自身调用 `tools/capture-native-memory.ps1`；关闭外部工具不等于关闭内置采集。脚本保留用于按需排障。

## 独立开关与日志兼容

`MEMORY_DIAGNOSTICS=true` 时，SQL 数据继续放在 `[MEM].counters.sqlite.*` 及 worker diagnostics 中，保持旧日志分析路径。内存关闭、SQL 开启时，采集器只输出 `[SQLITE-PERF]`；不采集线程堆、内存业务计数或原生进程数据，worker 探测仍可带回 SQL 指标。内存和 SQL 都关闭时，两类采集都停止。

`SQLITE_DIAGNOSTICS=false` 仅关闭详细 SQL 采样；请求错误、失败状态、事务/提交阶段耗时和 SQL 缓存计数仍可由现有独立监测记录。关闭任何诊断不会吞掉数据库异常或改变错误响应。

`tools/analyze-memory-log.cjs` 兼容轻量和旧版 `[MEM]`。SQL 执行总数、采样时间、错误累计值和编码工作线程累计完成/失败次数不再列入容器增长排名；队列数量和 retainedBytes 仍属于可观察的当前状态。

本改动不触及持久化格式、玩家表、账号归属、存档导入导出或客户端资源，不需要数据库迁移或客户端更新。

## 运行时实时房间追踪

基础性能汇总常驻运行，不需要反复修改 `.env` 或重启服务。管理会话可以通过以下接口为单个房间临时开启有界追踪：

```text
GET  /api/server/diagnostics/realtime
POST /api/server/diagnostics/realtime
```

开启请求示例：

```json
{
  "mode": "room-trace",
  "roomNumber": "目标房间号",
  "ttlMs": 600000,
  "maxEvents": 256
}
```

追踪只记录 barrier 和广播的时间、计数、房间号等有限元数据，不记录完整战斗帧；最长保留 30 分钟，事件数量有上限，到期自动回到 `basic`。发送 `{ "mode": "basic" }` 可以立即关闭。接口受管理面板会话保护，游戏客户端不能访问。
