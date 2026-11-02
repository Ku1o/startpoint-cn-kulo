# SP-LOG-001 · 崩溃解析与关键证据保留

适用：StarPoint CN /crash 出现长报告元数据丢失、误标表单 JSON、解析 500 或落盘问题。状态：生产处理器回归与完整入口隔离 HTTP 场景已验证；公网真实客户端上报和历史五王黑屏根因须另验。

原 2000 字符前缀会丢失长调用栈后的玩家、版本和异常；raw JSON 被标 form 时不按 &/= 拆分。优先 JSON，再尝试 legacy base64 MessagePack、标准 URL 表单及文本；畸形 JSON 不得引发 undefined.substring。修复限制在 /crash，不改变普通游戏接口解析。

先提取白名单玩家、版本、设备、异常字段和代码，元数据限制数量/字节并标记；对日志副本脱敏后，将含 [CRASH] 前缀的整条 JSON 限为 48 KiB，超长保留首尾、原脱敏长度/摘要和 truncated。UTF-8 边界切片，嵌套 JSON 脱敏后仍可解析；collector 的 64 KiB 分片不能破坏一行 JSON。只增大前缀截断不足以解决问题。

C3032 seed 反馈使用完整解码报告，不受日志脱敏/截断影响。保留原 256 KiB 请求体和 30/min 限流，不由日志改善推断注册/IP 防护完成。

隔离真实入口前设置 DATA_DIR、seeds、TMP、随机端口、hardcoded .logs 的读写 remap 与 worker 路径 guard，须在加载入口前完成；生产文件身份保持。测试包含真实 HTTP、超过旧截断位置的 seed 持久化和 writer 落盘；Windows SIGTERM 跳过项不计通过。

实现、历史本地加载及可选 relay 启停/回退边界见原结果（历史本地记录）与原条目历史（历史本地记录）。本条不自动启用 PR28、修改 .env 或重启服务。
