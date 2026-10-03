# 游戏对象响应分流与提交尖峰观测

> 本文保留响应 worker 的实现机制。2026-10-02 的生产默认、三轮基准和完整决策见 [四核服务器 CPU 优化实施记录](MULTICORE-CPU-OPTIMIZATION-20261002.md)。

`/load` 返回 MessagePack 对象，而旧线程池仅把达到字符串长度门槛的字符串派给 worker，导致实际对象响应始终留在主线程。现在 `/load` 的对象响应先在主线程打包并复制为独立字节快照，达到 32 KiB 后，由后台完成 AIR 整数兼容修正、Base64 和已有配置所要求的压缩。对象转 MessagePack 仍在主线程；这不是并行游戏结算。

小响应和普通对象路由继续本地执行。字符串响应保留原来的长度门槛。四核 CPU 优化复测后，默认线程数改为 0；`CN_RESPONSE_WORKERS=1` 可用于吞吐或事件循环隔离对照，2 个以上线程在当前 `/load` workload 下没有稳定降低总 CPU。保持最多 16 个未完成任务和 32 MiB 估算输入预算；配额是输入及复制估算，不是进程堆上限。

最终 30 并发、三轮中位数对照为：本地编码 384 ms CPU；1/2/3 个响应 worker 分别为 505/494/544 ms CPU。worker 没有降低墙钟或主线程 ELU，并增加结构化复制、调度和 worker 往返成本，因此默认关闭是经过测量的 CPU 决策，不代表线程池功能被删除。

快照独立于 msgpackr 的复用缓冲区，排队或故障回退均使用发送时的字节，不会读取之后改变的响应对象。队列满时在生成快照前尽量回退本地，不改变客户端编码、压缩协商或响应次数。线程仅处理响应数据，不访问数据库或发奖。

`[MEM]` 的 `responseWorkers` 增加 `configuredWorkers`、`submitted`、`completedObjects`、`localDisabled`、`localSmall`、`localIneligible`。`workers` 表示实际创建的线程数，不是配置值；对象分流应由 `completedObjects` 的增量确认。`[WORK-PERF] encode.snapshot` 包含主线程打包快照，和 `encode.pack` 有重叠，不应相加为 CPU 时间。

同步数据库提交增加 `[SQLITE-COMMIT]`，每个性能统计窗口输出计数和最多 8 条最慢样本，默认慢阈值 100 ms。样本包含提交墙钟、进程合计 CPU、错误码和 WAL 提交前后帧数/回填进度。只读 `-shm` 的头部元数据，检查两份头部及重复读取是否一致；不可读或存在竞争时记为 null。它不读取玩家内容，也不执行 checkpoint。

- `checkpointProgress=true` 说明该区间观测到回填进度，不能单凭这一项断言是哪个连接执行了 checkpoint。
- `processCpuMs` 包括所有线程，不能当成当前提交独占 CPU。
- `settings` 缓存该连接首次采样时的 journal mode、同步级别、自动整理阈值和 busy timeout。
- `SQLITE_COMMIT_DIAGNOSTICS=false` 可独立关闭；关闭 `SQLITE_DIAGNOSTICS` 或 `ROUTE_PERF_SUMMARY` 也跳过提交探测。
- `SQLITE_SLOW_COMMIT_MS` 可调整慢阈值；0 适合隔离实验，不建议作为长期日志配置。
- 嵌套事务释放 savepoint 不作为真正的 WAL 提交采样。原有事务体、提交、回滚与重试语义保留。

WAL 自动 checkpoint 默认会由达到阈值的提交线程执行，能够造成少数提交明显变慢；机制见 [SQLite WAL 性能说明](https://sqlite.org/wal.html#performance_considerations)。元数据解释依据 [SQLite WAL-index 格式](https://sqlite.org/walformat.html#the_wal_index_header)。当前实现没有调整 synchronous、wal_autocheckpoint 或数据库写入线程，未改变存档格式、表结构、持久化 ID、奖励或导入导出协议。

覆盖检查位于 `tests/cn-load-worker-integration.test.cjs`、`tests/cn-response-object-snapshot.test.cjs` 与 `tests/sqlite-commit-diagnostics.test.cjs`。真实 CN `/load` 测试使用隔离账号、567 个角色与真实 HTTP，比较本地/后台返回字节，涵盖不压缩、gzip、Brotli、禁用线程及延迟钩子。提交检查涵盖自动 checkpoint 进度、写锁等待、回滚、延迟外键约束、嵌套事务及关闭探测。

`tools/server-object-encoding-benchmark.cjs` 只接受隔离生成的响应快照；`tools/sqlite-commit-evidence.cjs` 仅操作临时合成数据库。后者为因果对照在临时库中分离提交和 checkpoint，不代表服务端采用了这种配置。
