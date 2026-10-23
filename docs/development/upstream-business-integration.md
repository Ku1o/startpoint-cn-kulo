# 上游业务能力选择性整合

本批把上游的资源保护与原生入口能力适配到本服持久化、运营控制和存档体系。以下描述的是源码行为；部署、实际客户端入口和设备交互应分别验收。

## 玩家可见行为

| 范围 | 行为 |
| --- | --- |
| EX 洗练 | 材料扣除与待选结果一起持久化；同次抽取重试回放，重启后可以继续确认。确认失败不删除结果。 |
| 角色邮件 | 按附件实际份数走标准角色获得流程，重复角色库存和补偿一致；零份通知不授予角色，数量为零的称号邮件仍正常领取。 |
| 装备分解 | 锁定装备不可分解；单件接口只消耗一份重复库存，保留基础装备。批量及部分分解按真实数量发奖。 |
| 单人复活 | 使用原生统计中的累计复活次数识别重试，同次请求只扣一次星导石；GET 编码与 POST 均可解析。 |
| 剧情推进 | 主线 7014002 的必败剧情可继续推进，战斗任务事实仍记为失败；其他败北不变。 |
| 剧情入队 | 映射剧情首次通关时获得尚未持有的角色；重复完成不增加份数。 |
| 任务领奖 | 本次奖励推动后续任务时继续结算，最多五轮；只处理本次事实及奖励影响的作用域。 |
| 多人兜底队伍 | 缺少上传队伍时使用玩家当前 SET，读取真实觉醒等级；缓存隔离玩家与 SET。显式 NPC 与本局冻结队伍保留。 |
| 排名摘要 | 使用真实队长、榜首与分数，百分比仅作展示转换；既有发奖比例不变。 |
| 商店期号 | 首次选择持久保存，同一选择可重试，不能换期；列表、单买、批买与入手来源遵守同一期号及运营开关。 |
| 绊证装备兑换 | 原生入口支持两件既有装备，与旧普通商店共享限购，不能从两个入口各买一次。 |
| 公共礼包码 | 原生领取入口支持物品、免费星导石、角色、装备、玛纳和经验池；每个本服目标玩家每码只能领取一次。 |

### EX 与单人复活的请求边界

有原生 nonce 的 EX 抽取使用 nonce 与 api_count 组合身份，不把可重用的 api_count 单独作为永久回执键。缺少 nonce 的普通 draw 请求，仅在相同角色和材料仍有待选结果时免费回放；同角色换材料拒绝且保留原结果，换角色沿用放弃旧待选结果的行为。first_draw 在角色已有 EX 状态时免费返回当前值。已完成结果的持久回执可阻止旧存档重新确认。

普通单人复活要求有效的 statistics.zones[].continue_count；缺失、畸形或乱序次数拒绝且不扣费。字符串统计限制为 64 KiB，区域数量限制为 128。五王续战保持独立协议。上述原生字段已做接口回归，当前设备实际报文仍需验收。

### 绊证与商店兼容

装备 5010005、5030005 各消耗 50 绊证、各限一次，对应旧普通商店商品 100001、100002。原生兑换次数、目标持久回执与旧商品购买次数共同决定剩余限购。原生兑换同时更新旧商品次数，旧入口也读取相同限制，入手来源与列表一致。

期号必须有该期自身可兑换的商品，不能借公共商品开放而选择完全关闭的期号。既有活动可见性和日、月、累计限制继续生效，不按上游历史日期自动关闭本服内容。

### 礼包码后台

管理页面位于后台“礼包码”，API 前缀为 /api/server/gifts/。创建和启停要求管理会话，启停使用 revision 防止陈旧覆盖。

- 创建后默认停用，无自动生成或启用的礼包码。
- 码名和奖励创建后不可修改，不能删除后复用同一个码；可停用、另建新码。
- 码名区分大小写，最多 20 字符，无空白或控制字符。
- 每码最多 20 项奖励；角色、装备每项一份，ID 必须存在。
- 奖励、获得历史、觉醒协调与领取回执在同一事务；容量不足时拒绝且保留领取资格。
- /load 与 /tool/check_enable_gift 共用有效礼包码判断。管理页创建失败保留输入，并显示服务端错误。

## 保存、升级与回退

本批增加以下表，由数据库初始化幂等创建，不重置已有玩家进度：

| 表 | 存档策略 |
| --- | --- |
| players_ex_boost_pending_draws | V2 便携玩家状态；保存已付材料的待选结果。 |
| players_shop_campaign_lineups | V2 便携玩家状态；保存商店选择。 |
| players_bond_token_exchanges | V2 便携玩家状态；保存兑换次数。 |
| server_gift_codes | 本服全局配置；不放入玩家存档。 |

礼包领取与绊证兑换防重使用已有 player_operation_receipts，属于目标玩家本服账本，不随来源存档迁移。当前 V2 严格检查表集合、结构指纹及 EX 状态内容，拒绝未知表或非法待选结果。明确识别的旧 V2 缺少本批三个玩家表时保留目标对应状态；V1 替换也保留这些关系，避免父行替换级联清空。后台 V2 导入接口的 V1 拒绝规则不变。

存档导入仍是替换便携进度，不是合并物品。导入旧存档可能恢复较早库存，但不会清除目标已消费的礼包码、支付或兑换回执，也不会为了对账再次发奖。不要删除回执来恢复兑换资格。

升级前按现有运维流程备份数据库与配置。回退时同时评估新状态及领取事实：旧程序不了解新存档结构，不得使用旧程序导出再覆盖新状态；不能删除新增表、礼包码或防重账本来规避结构检查。如需还原升级前数据库，必须处理升级后业务写入，不能把源码回退当作数据无损回退。

## 保留的政策

- Pass 商品入口仍关闭；既有购买权益与历史补领保留，未启用模拟购买。
- 不自动向已经通关的旧存档补发剧情角色。
- 已无法确认旧对局身份的 finish 请求继续拒绝，不伪造成功结算。
- NPC 每场随机、跨服联机不属于本批内容。
- 未修改客户端包、CDN 发布链、资源版本、准入配对或云服部署配置。

## 验证边界

相关 25 个文件共 188 项检查通过，覆盖重复请求、SQL/提交失败回滚、重启恢复、保护装备、旧档覆盖、双入口限购、真实 HTTP 导出与 multipart 导入及安全备份前像。测试使用隔离临时数据库；固定读取源码的套件与使用最终编译产物的套件分别记录，不访问真实玩家库。

服务端及管理端编译通过；运行输入按每次实际暂存集合隔离编译。管理端保留体积提示，未为此改动打包策略。浏览器视觉验收不可用，礼包码页面布局和当前手机实际入口未作验收。隔离回归不等于云端运行或设备游玩验收。

推荐入口：

- tests/economy-business-fixes.test.cjs：EX、邮件和装备的资源保全与事务。
- tests/content-history-native-quest-rules-http.test.cjs、tests/upstream-mission-cascade.test.cjs：复活、剧情和任务级联。
- tests/multi-party-fallback.test.cjs、tests/ranking-summary.test.cjs：多人兜底与排名。
- tests/shop-campaign-lineup.test.cjs、tests/bond-token-shop-compat.test.cjs、tests/upstream-gift-bond-http.test.cjs：入口、限购、礼包、存档及重启。
- tests/admin-save-transfer-integration.test.js、tests/player-save-export-worker.test.js、tests/storage-snapshot-compat.test.cjs、tools/player_snapshot_v2.test.cjs：保存与导入导出。

使用 node tools/run-isolated-check.cjs --test 后接明确文件列表，逐文件隔离；编译模式须先生成当前 out，支持双模式的文件可设置 STARPOINT_TEST_COMPILED=1。不将生成 out 或临时库加入 Git。

## 上游来源

参考 [DontBeAlarmed/startpoint-cn main 固定版本](https://github.com/DontBeAlarmed/startpoint-cn/tree/b2e40c3f1b24b704e5881fbefa12be101ea78134) 与 [dev 固定版本](https://github.com/DontBeAlarmed/startpoint-cn/tree/574a40abdd767abcddbb72d7c6b478d4d3009c0d)。代码按本服持久化、奖励、身份与运营体系适配，未整体合并分支。

元数据来源保留上游署名：

- [剧情角色入队映射](https://github.com/DontBeAlarmed/startpoint-cn/blob/8e6742c25ed66b848db1138dffbbae79990deed8/assets/story_join_character.json)
- [绊证装备兑换表](https://github.com/DontBeAlarmed/startpoint-cn/blob/2e60cdcbe81850688f346f8ba6e0a0e1cfc929ae/assets/bond_token_exchange.json)
- [商店选择映射](https://github.com/DontBeAlarmed/startpoint-cn/blob/dc70930860d398114d4f059c5f1d9f4e08cff866/assets/shop_select_item_campaign.json)
