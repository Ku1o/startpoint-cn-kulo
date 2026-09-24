# 服务端结算与响应性能

## 实现范围

- 普通任务定义按类别和 ID 建索引，缓存不可变定义的开放时间、最终阶段阈值；活动任务按内容快照和条件组合缓存读取计划，最多保留 32 个组合。
- 任务计算只读取角色经验、进化、突破和羁绊字段。请求内共享事实，发奖后的活动核对重新读取，避免使用过期玩家数据。
- 常用 SQL 进入每连接有界语句缓存；一场战斗的队长、主位和辅助角色通关计数合并写入，保留去重与联机计数语义。
- Raid 按关卡累计击杀数使用连接内 TEMP 派生表和 TEMP 触发器。首次查询按流水重建，此后增量维护；回滚、删除和重置与原事务一起生效。检测到其他连接提交时重建。持久数据库结构、存档标识与归档指纹不变。
- MessagePack 整数兼容处理跳过字符串、二进制等不透明区段，仅遇到 uint32 时分配转换缓冲；保留 AIR 的 int32/float64 转换规则，并正确跨过扩展类型字节。
- 大响应的 MessagePack、整数转换、Base64 和可选压缩在工作线程执行。输入是已生成的响应字符串，线程不访问 SQLite、房间、会话或奖励状态。核心结算仍使用原有原子事务，不属于跨线程结算实现。

## 线程与回退

`CN_RESPONSE_WORKERS` 控制线程数，默认 `min(2, availableParallelism - 1)`，限制在 0–4。设为 `0` 可关闭后台编码，仍使用优化后的本地编码器；需要重启生效。

仅至少 524288 个 UTF-16 码元的字符串进入线程池。默认最多 16 个未完成任务，输入及结构化复制按字符串长度乘 4 计入 32 MiB 配额，排队加执行最多 10 秒。超限、超时或线程异常回退到本地编码。线程异常后暂停新建线程 30 秒；关闭时清理任务和计时器。这个配额限制输入积压，不是进程总 RSS 上限，编码中间缓冲和 V8 堆另占内存。

后台化用于释放主线程，不保证单个请求更快，也可能提高进程合计 CPU。大并发超过配额时会有本地回退，因此不承诺主线程永不阻塞。较小响应保留本地路径以节省传输成本。

HTTP 压缩沿用现有 `CN_LOAD_HTTP_COMPRESSION` 配置和 `Accept-Encoding` 协商。默认压缩模式不变；编码优化不依赖启用压缩。

## 指标

- `[PERF] actualInterval`：本次采样实际墙钟间隔，用于解释拥堵时 CPU 毫秒数。
- `[WORK-PERF] encode.pack/fix/base64`：执行编码阶段的墙钟时间；可能来自主线程或工作线程。
- `encode.compressWait`：压缩完成等待，包含异步等待；不是纯 CPU 时间。
- `encode.queue/clone/workerRoundTrip`：线程池排队、发送结构化复制、工作线程往返时间，不能与编码阶段相加当作 CPU。
- `db.single.body/commit`：单人结算事务体、成功返回前的提交阶段。嵌套事务对应保存点释放；异常回滚不计为成功提交。
- `db.begin/body/commit/playerQueue`：写协调器的锁获取、事务体、提交及同玩家队列等待。
- 内存诊断的 `sqlite.main` 增加执行次数、忙错误和每 64 次一次的执行耗时采样，同时报告 `busy_timeout`、`synchronous`、`wal_autocheckpoint`。采样结果不等于精确总执行时间。
- `responseWorkers`：工作线程完成、失败、回退、超时、积压和输入字节计数。

## 验证与回退

构建使用 `npm run build`。专项覆盖 `tests/server-response-workers.test.cjs`、`tests/mission-performance-safety.test.cjs`、`tests/raid-count-cache.test.cjs`；响应链、存档 V1/V2、奖励重复领取和结算生命周期继续使用既有测试。

基准工具为 `tools/server-performance-benchmark.cjs`、`tools/server-encoding-benchmark.cjs`、`tools/server-raid-count-benchmark.cjs`。结算基准强制使用独立临时数据库，支持 `PERF_TARGET_RPS` 和 `PERF_ITERATIONS`，比对响应与持久化结果摘要；摘要排除运行时产生的时间戳。合成数据的吞吐不代表线上玩家容量。

这些变更不需要数据库迁移。关闭线程可单独回退后台执行；全量代码回退需要恢复相匹配的源码与构建输出，TEMP 派生计数在连接关闭时消失，不需要回滚玩家存档。
