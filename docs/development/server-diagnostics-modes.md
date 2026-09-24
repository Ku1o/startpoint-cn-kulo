# 服务端常驻监测与详细诊断

服务默认保留每分钟的内存、队列与性能汇总，关闭 Windows 原生内存区域扫描和详细内存统计。内存与 SQL 诊断可分别控制；诊断开关不修改数据库结构、存档格式、奖励、事务或 SQL statement 缓存。

## 默认配置

| 环境变量 | 默认值 | 行为 |
| --- | --- | --- |
| `MEMORY_DIAGNOSTICS` | `true` | 每分钟输出 `[MEM]`，含 RSS、主线程和 worker 堆、连接与业务队列 |
| `MEMORY_DIAGNOSTICS_DETAIL` | `false` | `true` 恢复 V8 附加统计、活跃资源枚举、房间阶段分类、NPC/种子池条目遍历 |
| `PROCESS_MEMORY_DIAGNOSTICS` | `false` | Windows x64 上显式设置 `true` 后才启动 PowerShell 进程内存区域探测，且需要内存采集开启 |
| `SQLITE_DIAGNOSTICS` | `true` | SQL prepare/get/all/run 计数与每 64 次一次的计时采样，用于结算性能定位；稳定后可独立关闭 |
| `ROUTE_PERF_SUMMARY` | `true` | 保留 CPU、事件循环、请求状态/耗时及结算、编码、数据库提交等阶段汇总 |

详细内存和原生内存开关只接受 `1/true/yes/on` 开启；未配置或无效值保持关闭。环境变量须在服务启动前设置，修改后重启生效。现有 `.env` 若显式写了 `PROCESS_MEMORY_DIAGNOSTICS=true`，该值仍会覆盖新的默认值，须改成 `false` 才能停用。仅更新 `.env.example` 不会更改现有 `.env`。

服务启动时输出一次 `[DIAGNOSTICS]`，列出实际 memory 模式、sqlite、nativeMemory 和周期。内存与 SQL 均关闭时不安装这个采集器；基础性能监测仍由 `ROUTE_PERF_SUMMARY` 单独决定。

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
