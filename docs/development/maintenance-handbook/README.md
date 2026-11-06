# 维护与制作交接手册

本手册保存服务端、客户端和 MOD 制作中已经形成的方法，以及仍待验证的设计。各专题中的“已验证”仅指原记录列出的场景；不代表当前所有版本、设备或云服均已通过。历史本机报告没有作为源码附件发布，相关链接已明确标为历史记录。

## 从哪里开始

| 工作 | 入口 |
| --- | --- |
| 运行结构、资源来源、编译与交付 | [运行与入口](topics/runtime-context.md)、[项目架构](../../architecture.md) |
| Android、iOS、ABC、AOT 与 ABI | [客户端方法](topics/clients.md)、[客户端制作流程](client-release-workflow.md) |
| 角色、扭蛋、图集、语音和资源接入 | [MOD 制作方法](topics/mod-production.md)、[可复用制作工具](../../../tools/production-kit/README.md) |
| 工坊原稿、声明与复杂机制 | [工坊方法](topics/mod-studio.md)、[角色工坊仓库](https://github.com/Ku1o/StarPoint-Character-Studio) |
| 角色觉醒 | [觉醒流程](awakening-workflow.md) |
| 原生客户端回包、重试与经济检查 | [测试方法](topics/testing.md)、[AIR 检查工具](../../../tools/client-air-test/README.md) |
| 时间、运营目录和迁移 | [时间与内容](topics/content-time.md) |
| 结算、事务、SQLite 和备份 | [结算与存储](topics/settlement.md) |
| 多人 AI、实时状态与恢复 | [多人 AI](topics/multiplayer-ai.md)、[实时转发](topics/realtime-relay.md) |
| 登录、存档导入、安全与限流 | [安全](topics/security.md)、[代理与限流](topics/proxy.md) |
| 崩溃定位、历史故障与候选机制 | [崩溃日志](topics/crash-logs.md)、[旧校验器故障](topics/client-validator-legacy.md)、[累计伤害设计](topics/mod-damage.md) |
| 大型素材、可编辑工程、私有客户端参考及恢复输入 | [归档索引与校验值](archive-20261103.md) |
| 五池最新工程与手柄适配成品 | [2026-11-06公开资料归档](archive-20261106.md) |
| 语音环境重建 | [固定依赖与模型清单](../../../tools/voice-reproduction/README.md) |

## 路径、状态和输入

- 文中的 `<repo>` 是此仓库的实际根目录；`<workspace>` 是开发者自行选择的仓外工作目录。两者不必在同一个盘符。
- 当前客户端输入从 `client-patch/android-accepted.json`、`client-patch/ios-accepted.json` 及对应说明查询。历史案例文件名、日期、版本号和 SHA 不能替代当前登记。
- 制作模板与大型原稿作为版本化资料附件保存；下载地址、文件摘要和验证方法见[归档索引](archive-20261103.md)。源码、模板和外部依赖必须一起齐备，不能把仅有脚本称为完整可重建工程。
- 原版反编译参考、真实账号数据库、密钥、签名凭据、私人运行配置和聊天记录不在本手册中。
- 静态解析、离线原生方法执行、浏览器预览、真机实战与云服部署是不同证据层级。模板美术采用不等于资源已激活；测试库进度不构成生产数据。

## 隔离测试状态的退出

测试输入应由明确版本的源码、合成夹具、资源清单和必要配置重新生成。一次性整库快照及测试账号进度不应成为制作工具的隐含依赖。删除测试状态前，检查实际写路径、进程占用和文件联接，确保没有落入正在使用的主库、真实玩家数据或唯一输入。

历史主城与卡池测试曾在每轮视觉/身份调整前复制整库，造成大量重复存储。限定运营身份修订可采用范围状态捕获、事务、CAS 和实际启动校验；该方法的适用范围与失败回滚见时间专题，不能直接推广为生产迁移不需要备份。
