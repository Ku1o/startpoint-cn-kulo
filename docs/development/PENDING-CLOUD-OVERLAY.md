# 下次云服整合包待合并内容

## EX 第20关三兄弟与深渊角色兑换（1.4.115）

- 第20关使用普通讨伐三兄弟的私有完整战斗族，修复计分版缺少传伤导致本体不掉血、辅助实体反复复活的问题。保留约298.28亿总血量、属性和伤害限制、奖励与时限；关联实体HP同比缩放，九处破弱点保留原始绝对伤害门槛。
- 盾牌座149988、夏日白149990开放深渊池990001的250点兑换，同步服务器获胜配置、客户端兑换列表与说明；抽取权重及竞速池不变。
- 运行文件为 `assets/gacha.json`、`assets/gacha_cnmod.json`、完整 `assets/asset-patch/manifest.json` 和 `assets/asset-patch/active/pinball-1.4.114-1.4.115-1-abyss-ex20-exchange.zip`。服务器私有交付另带完整准入配对，保持现有平台期限。云服部署仍待完成，具体提交、同步与交付结果见批次回执。
- 仅推进EX计时成绩版本；普通塔成绩、挑战进度、已有角色、奖励领取记录和存档结构保持不变。接口与离线资源验证通过，手机实战验收待完成。详情见 `assets/asset-patch/audit/abyss-ex20-exchange-1.4.115/README.md`。

## 服务端内存诊断与分配优化（2026-09-18）

- 新增按分钟的主线程、NPC/抽卡线程内存与业务容器/队列计数日志；NPC 常规记录改为阵容增量同步，完整重载按关卡确认后原子切换缓存。
- 抽卡种子保留 JSON 主文件、有效备份、原子替换和 flush 契约，改用分块编码与摘要回读；固定任务/计数及 NPC SQL 增加每连接有界 statement 复用。各项均提供独立停用开关。
- 运行范围为 17 个源模块及对应构建产物，精确路径、诊断字段和开关见 [server-memory-diagnostics.md](server-memory-diagnostics.md)。无需客户端/CDN 更新或数据库迁移，不修改存档格式、账号归属、任务奖励与 NPC 阵容筛选规则。
- 隔离构建与种子持久化、NPC 同步/删除/重载、SQL 事务、任务领取、多人连接及旧存档兼容回归通过。本机合成负载显示分配和耗时下降；云服长期收益尚未验证。
- 已备份并同步本地 34 个源文件/构建产物及 1 个离线分析工具，重启后 HTTP 8001、多人 TCP 8003、NPC 阵容池就绪、后台状态与真实服务 V2 只读导出验证通过。手机游玩与长期内存观察待完成；未部署云服、未生成覆盖包。
- 配套 `tools/analyze-memory-log.cjs` 离线汇总线程、容器与队列变化；按进程/线程区分，排除累计计数及过期样本，限制分析状态大小。5 项针对性回归通过；工具不在服务进程中运行，可随运维资料单独交付。

## 角色更新、深渊双模式与幻想兑换（1.4.110～1.4.114）

- 角色、武器、铭牌及卡池内容与普通深渊／EX 同批交付；完整 manifest 的终点为 1.4.114，六个新增 CDN 分包保持原有顺序和字节。最终范围见 [RELEASE-114-CONTENT.md](RELEASE-114-CONTENT.md)。
- 普通深渊 Boss 基础血量 20～100 亿、梦境纹章固定 800；EX 30 关 200～350 亿，末关两只依次登场、各 350 亿，限制 3～4 属性和两类伤害，保留默认时限并取消时限诅咒。独立解锁／进度／计时、共享商店、校园角色兑换与 EX 五档称号奖励已接入。
- 修复 EX 首关前置、结算 H500 旧表约束、C8601 缺失奖励组及普通属性详情；说明修正保留成绩和塔进度。幻想单人／多人商店新增王印 100 币、觉醒核 500 币，各 999 共享库存，并补齐入手来源。
- 服务端与资源已经同步本地测试服。双端下载、隔离存档与结算回归已有通过记录；手机战斗验收仍待完成。双端客户端候选见 client-patch/abyss-ex/release.json，正式旧准入号 24 小时过渡期尚未启动。
- 云端尚未部署，未生成本批服务器整合包。后续包只纳入本批实际运行差异，资源采用 active ZIP 与完整 manifest，外层排除 production 散资源。连击挑战 B 未实现，不属于已完成功能。


## 2026-09-15 最新统一交付（已分类提交、推送并同步本地，云服仍待部署）

作者融合、校园三人技能图、C2265、服务端双端准入、Android累计优化正式版及iOS准入版已按六类提交，运行发布提交 `7e1b2d61129843af034f977a56acce4144171249`。GitHub CI通过；本地64个运行文件与提交字节一致，更新11个并安装独立双端私有配对，已重启核验。后续原“未提交/未同步”段落保留历史时点，以本条为准。

云服覆盖包 `startpoint-cn-cloud-overlay-109-dual-admission-20260915-221719.zip` 已生成，包含仍待覆盖的.108和本次.109；云端前置基础仍按用户确认的.107。没有云服已覆盖确认，保持待部署，不重复打入已部署的.107及更早资源。

.109当前第1作者融合、第2C2265、第3校园技能图，总计6,016,383字节；第1/3原包不变。C2265只改变初始主页台词条件，保留当前完整文字，未恢复无效试验包。已上报.109的客户端需单独安排资源补拉。

准入配置包含独立Android/iOS正式号，保持enforce:false；必须单独安装私有配对，已有云端名单先合并，不能盲目覆盖。iOS公网80和Android8001均须转发准入接口。未部署云服、未开严格模式、未合并main；IPA未真机测试。详见 [RELEASE-109-ADMISSION-20260915.md](RELEASE-109-ADMISSION-20260915.md)。

2026-09-13 最新交付：五类功能已分别提交并推送 `origin/staging`，运行代码基准 `1ec70d4095bca2e348d9677c2ac1439fbfffd327`；GitHub CI 已通过。本地已同步同一提交的 43 个运行文件并重启，另 4 个此前同步的直读资源保持且与已提交内层分包一致。云服覆盖包 `startpoint-cn-cloud-overlay-1.4.108-20260913-182019.zip` 已生成并核验，**仍待用户覆盖云服**。云服部署基础继续按用户确认的 `.107` 记录；`.106/.107` 旧范围不重复打入。完整提交、文件、备份及验证见 [RELEASE-108-20260913.md](RELEASE-108-20260913.md)。

用户本轮提醒 H400 已提交且已有包；已直接核对 GitHub 的 `726d6771` 和 2026-09-13 13:57 原包。本次没有重复创建 H400 提交，木人时间修复后的两个接口文件已累计保留 H400 逻辑，因此本包也覆盖该保护。没有获得 H400 云服已覆盖的确认，不把“已有包”记为“已部署”。

本次五类为：抽卡并发性能、24 角色 48 款称号、歼灭者两池抽取兑换、校园碧安卡／奈芙提姆 G1008、木人历史真实时间。以下早期“未提交／未打包／未同步”描述保留其历史时点，以本条交付状态为准；资源和客户端仍需实际手机验收。

## 2026-09-13 Reborn 24角色48款称号（已提交、已打包，云服待部署）

- 用户确认云服当前为 `.107`，本次仅追加 `.108`；既有三个 `.107` 分包保持原样。24名名单角色满破4次并达100级时同时获得两款称号；旧角色成功完成一次原生单人木桩练习后按整个持有名单补领，无需上场，不额外要求觉醒或玛纳板。
- 服务端沿用 `grantPlayerDegreeSync` 写入 `acquired_at`，不引入作者工程中的 `ensurePlayerDegreesTableSync`；补齐服务端称号主数据并接入当前合并访问器。
- 运行文件共16项：6个 TypeScript 文件及各自的6个 `out/` JavaScript，`assets/degree_character_mod.json`、`assets/character_degree_rewards.json`、最新 `assets/asset-patch/manifest.json` 和 `assets/asset-patch/active/pinball-1.4.107-1.4.108-1-reborn-character-degrees.zip`。完整路径与哈希见 `assets/asset-patch/audit/reborn-character-degrees-1.4.108/delivery.json`，细节见同目录 `README.md`。
- 最终复核期间并行任务追加了 `.108` 净化扭蛋第2分包，已保留并核验共享清单的两平台下载。上述16项为称号组件本身；交付当前共享manifest时须同时合入 `assets/asset-patch/audit/epuration-gacha-1.4.108/` 所记录的并行组件依赖，不能漏掉其第2分包或所需服务端数据。
- `.108` ZIP 含49个 common 资源，48张称号图为Android/iOS共用的原生编码PNG，旧1497条称号压缩行逐字节保留；没有新APK/IPA或数据库迁移。V2继续携带称号持有记录，旧V1导入后可通过木桩补齐；不改变存档schema或账号归属。
- 类型检查、隔离构建、14项新增服务端及存档HTTP验证、28项既有回归、2项双平台资源HTTP验证、7项资源回归通过。后续38项组合回归、实际双平台三包下载及只读存档导出也通过。已提交 `554b4698`，同一提交内容已同步本地并纳入顶部 `.108` 整合包；云服仍待用户覆盖。

## 2026-09-13 抽卡并发性能修复（已提交、已打包，云服待部署）

- 将旧种子全量 JSON 转换和原子保存移到单一后台线程，按变化合并写入；保留动画选种、异常纠错、管理模式和失败重试。
- 角色剧情查询改为静态前缀索引，完整觉醒补修范围不变；增加抽卡分段耗时及实际抽数汇总。
- 后续提交及交付须显式包含以下 TS 与各自对应的 `out` JS，共 18 个运行文件：`src/cn-server.ts`、`src/lib/seed-validator.ts`、`src/lib/seed-persistence.ts`、`src/lib/seed-persistence-worker.ts`、`src/lib/mission/character-queries.ts`、`src/lib/settlement-performance.ts`、`src/lib/route-performance.ts`、`src/routes/api/gacha.ts`、`src/routes/web_api/seeds.ts`。新增的两个工作线程相关 JS 不能遗漏，部分 out 文件受 Git 忽略规则覆盖。
- 沿用云服现有种子文件，不装入测试种子、数据库或本地学习记录；没有卡池概率、角色定义、存档 schema 或 CDN 修改。
- 早期本地试用记录：2026-09-13 14:12 定向同步 18 个文件，备份 14 个旧文件、新增 4 个模块，进程 PID 17460。备份为 `F:/startpoint-cn-main/.codex-backups/20260913-141106-gacha-performance/`，回执为 `F:/codex/work/gacha-concurrency-fix-20260913/local-sync/20260913-141106/receipt.json`。现已提交 `6a58147d`、推送并纳入顶部 `.108` 包，同一提交已重新核验本地运行；云服待覆盖。验证及既有回归失败的修复前回放见 `docs/optimization/gacha-concurrency-fix.md`。

## 当前状态（2026-09-13 用户最新确认：.107 已部署）

用户已确认“空更新修复、`.106` 入手来源和深渊纪录更新已经部署了”，随后在 H400 交付时进一步确认“`.107` 已经覆盖了，别再加进来了”。据此，`.106` 内容和下列 `.107` 整合包的 39 个运行文件均记为**已部署**。依据为用户确认，本次没有另行连接云服核验。下方早期记录中的“尚未部署”“下次必须合入旧包”已失效，不能再次用于扩大打包范围。

此前 `.107` 整合包的以下内容现已由用户确认覆盖：

- 第 8、9 项服务端觉醒、称号及查询优化：对应 TypeScript 和 JavaScript 产物。
- 第 10、11 项武器次数、独立无属性百倍木人、作者选定角色/卡池/美术/语音：10 个服务端 JSON，以及 `.106 → .107` 第 1、2 分包。
- 两池注意事项排版：同一 `.107` 第 3 分包及最终 manifest；不递增版本。
- 运行发布清单为 39 个文件。APK/IPA 独立交付，客户端资源重新获取由用户处理；当前共斗闪退诊断继续排除。

该 `.107` 包以前述 `.106` 内容为基础，不重复装入旧空更新与深渊纪录专属源文件/产物或 `.106` 两个 ZIP。该包中的 `assets/gacha.json`、manifest 及三个 `.107` ZIP 均已随该包覆盖。本次 H400 包只交付退出接口的源码和对应 JS，不重复纳入 `.107` 原有文件。

用户同时明确要求按功能大类拆成多个 commit，已纳入 `branch-workflow.md` 的长期协作约定。分类提交与包的最终清单、摘要及本地同步记录见本次交付报告。

## 历史交付记录（按当时状态保存）

2026-09-13 两池注意事项修复：按用户要求追加到 `.107` 第 3 分包，版本不递增。下次包须纳入 `assets/asset-patch/active/pinball-1.4.106-1.4.107-3-gacha-note-layout.zip`（2,148 字节，SHA-256 `2967f361d5c5b957f40e1613c00031c8534594ee4c3200a2687000c7dd2ffd28`）和最新 manifest。修复段落丢失导致的叠字，正文及概率/兑换规则不变；已备份并同步本地，两平台 HTTP 下载校验通过，客户端获取资源由用户处理。详见 `assets/asset-patch/audit/gacha-note-layout-1.4.107/README.md`。未提交、未制作云服覆盖包、未部署云服。

2026-09-13 三会话整合更新：第 8、9 项服务端觉醒/称号修复与第 10、11 项最终资源已按明确清单同步到 `F:/startpoint-cn-main`，共 38 个文件，实际有效链为 `.107` 两分包。同步阶段完成实际模块及隔离存档/HTTP 路由检查；用户随后授权启动本地测试，已于 11:07 启动 PID 26440，8001/8003 监听、实际两分包下载哈希及真实服务 V2 只读导出通过，游戏测试进行中。本轮没有新增提交、推送、云服覆盖包或云服部署，以下云端待部署范围保持。iOS 商店累计版按用户整合请求登记 `accepted_offline`，当前共斗闪退诊断排除。最新精确文件及分类测试见 `docs/development/INTEGRATION-THREE-SESSIONS-20260913.md`，历史段落中“未同步/待回封”等状态以本条为准。

2026-09-12 后续确认：用户已验收 iOS 纪录昵称版，登记见 `client-patch/ACCEPTANCE-IOS-RECORD-HOLDER-20260912.md`。本次只更新客户端验收状态，未确认云服已覆盖，以下待部署范围保持。

记录日期：2026-09-12。状态：**待纳入下次整合包，尚未部署云服**。

最新状态：用户已验收昵称版 Android，并恢复提交、公网 APK、云服整合包及之后的 iOS 制作。下文各项保留当时记录；最新 Android 身份以 `client-patch/ACCEPTANCE-RECORD-HOLDER-20260912.md` 为准。打包和本地同步仍不表示云服已覆盖。

已完成打包：`F:/codex/outputs/server-overlays/startpoint-cn-cloud-overlay-106-record-holder-20260912-215250.zip`，发布提交 `4d4c326502a1250d5d04773aac182c20f645870a`，22 个文件，SHA-256 `ce480e16e9a5c0d067eddb7db335d11099c851d3b47000bc30647db69fc64246`。包含旧空更新四文件、gacha JSON、深渊纪录源文件/产物及最新 `.106` manifest 和两个原样分包；客户端 APK/IPA 独立交付。已推送 staging 并同步本地，CI 通过；**云端仍待用户覆盖**。iOS 对应候选见 `client-patch/ios-record-holder/README.md`，尚待设备验收。

用户明确说明：`startpoint-cn-cloud-overlay-empty-update-20260912-140840.zip` 还没有覆盖到云服，要求后续打包时把该包内容与本次 .106 入手方法补全一并加入。这是后续交付范围记录，本次没有要求立即重打整合包或部署。

## 1. 空资源更新响应修复（已部署；以下为历史记录）

- 原包：`F:/codex/outputs/server-overlays/startpoint-cn-cloud-overlay-empty-update-20260912-140840.zip`
- 包大小：11,369 字节。
- SHA-256：`7171e7069e9a49697620b22c8f9433f72bebbe31e65ec3765aa824d665ade023`。
- 来源提交：`46bfeeaa3feb1e080ea70dd43cc1dcaecad08876`，已提交到 staging；云服未应用由用户于本次明确确认。
- 修复行为：没有实际资源下载任务时，`/asset/get_path` 返回 `full=null`、`diff=null`、`asset_update=false`，避免弹出 0 MB 空更新。首次下载与真实增量任务继续保留。
- 原部署说明以 `c726e483a5ac2af8ca43ffc91b12646d13776efd` 对应的多人幻想装备拦截提示整合包为前置基础；本记录未检查云端实际提交或资源版本，不能把这个前置说明当成部署证据。

下次包必须覆盖以下四个路径的修复。2026-09-12 已读取原 ZIP，CRC 通过，全部成员与当前源码树字节一致：

| 路径 | SHA-256 |
| --- | --- |
| `out/lib/version.js` | `5d597ebefdfbcfebad19b2efe177c71cd6acf6c778a2a8ff46241dbc666ab8b4` |
| `out/routes/cn/asset.js` | `f98df56ee9a10740220f8d9e03e81d555ab8b97fecca684d42be70224f93b327` |
| `src/lib/version.ts` | `65ed91d34a99c15f08d23980a3f8e05f6d885e25e441c382a5ef29745f6d934d` |
| `src/routes/cn/asset.ts` | `2d8ce867187b99826431d2b73b88bc0d4f330654197e098f0a49fe7b5eebb438` |

同名前缀的 `.files.txt`、`.files.sha256.txt`、`.sha256.txt`、`.部署说明.txt`、`.verification.json` 和 `.交付记录.md` 位于原包旁，保留为历史证据。

## 2. 入手方法与 gacha .105 → .106 合并版（已部署；以下为历史记录）

- 必需交付路径：`assets/asset-patch/active/pinball-1.4.105-1.4.106-1-mech-item-sources.zip` 和包含该版本边的 `assets/asset-patch/manifest.json`。
- ZIP 大小：357,164 字节。
- ZIP SHA-256：`f25bccc0027d54b980462d78b792d86d015efabb568a76c207e6ba7debd3d9b2`。
- 本次内容：机兵蒸气核及菲诺梅那材料、幻想固定材料、深渊整轮奖励、星空记忆晶 28 个首次 SS 来源；共新增 152 条来源，涉及 55 种道具，保留原有 6,186 条来源。
- 当前 ZIP 另含 84 张暗龙升星卡池表，完整保留原有两项入手方法资源；不要选用历史 47,428 字节的机兵专项版或 221,787 字节的仅入手方法版。
- 记录时源码 HEAD 为 `staging@46bfeeaa`，此修复仍未提交、推送；现已随深渊纪录试用同步本地运行镜像。资源与接口离线验证已通过，手机实际跳转仍待验收。
- 详细证据：`assets/asset-patch/audit/mech-item-sources-1.4.106/README.md`。

## 3. Gacha 兑换与抽取一致性修复（随 .106 已部署）

- **服务端必需文件：`assets/gacha.json`**，SHA-256：`38fe85ba87359b575e0191d1ba6623e53924e1f5dc22a9bf4c58bbacfb387e32`。该文件和第 2 项的最新 active ZIP、manifest 必须在同一整合包中交付，CDN 分包不包含服务端 JSON。
- 修正 95 个池的相关分组，消除 14 个池、268 个角色的 432 条错误兑换资格；同步属性池与节日池的成员、权重、UP／限定标记。
- 暗龙 261089 保留五星身份和原 ID，在 82 个历史池中转入五星分组，采用本池相同 UP／限定属性的五星权重；总星级概率不变。
- 432 条原失败兑换均已通过隔离数据库中的真实接口验证；586 个池的最终客户端／服务端一致性校验通过。未提交；现已随深渊纪录试用同步本地运行镜像，未部署云服。
- 生成器和回归文件为开发侧防回退内容，默认不进云服包：`tools/rebuild_gacha_from_odds.cjs`、`tools/lens-integration/export_effective_gacha.py` 等。没有服务端 TypeScript 修改，不需要额外 out 产物或数据库迁移。
- 详情：`assets/asset-patch/audit/gacha-consistency-1.4.106/README.md`。下次打包仍须保留第 1 项未部署的四个空更新修复文件。

## 4. 深渊详情全服纪录及换塔计时标记（已部署；以下为历史记录）

- 2026-09-12 用户授权本地实现、同步和启动。已在本地运行，但候选未提交、未验收；不把本地试用当作云服授权。
- 服务端路径（每个 TS 均需对应 out JS）：`src/cn-server.ts`、`src/data/index.ts`、`src/data/initializers/abyss-records.ts`、`src/data/domains/abyss-records.ts`、`src/data/snapshots/player-snapshot.ts`、`src/routes/cn/abyssRecords.ts`、`src/routes/api/singleBattleQuest.ts`。
- .106 的 manifest 新增 `quest_time_revisions["rush:700099"] = b7f64b4be9d492d56419293d911d06c3bfef6d2d917275c9d01735fd086340f3`；原 357,164 字节 ZIP 哈希不变。新塔个人最佳下次读取时重置；之前混存的本期成绩也一起重置，通关/奖励状态保留。
- 新表 `abyss_floor_records` 启动时幂等创建，本服公共纪录不进 V1/V2 玩家存档。旧、新版本导入和自动备份已在隔离数据库验证；实际本地服务只读导出通过。
- 原个人最佳保持独立，详情动态纪录需要新客户端。当前只有 Android 内网候选，iOS 未移植；不把 LAN APK 放入云服覆盖包。
- 第 2、3 项已一并同步本地并核对 86 个直读资源，仍全部待部署云服。
- 详细交付、回滚、哈希和验证边界见 `client-patch/abyss-records/README.md`。用户其他未提交修改保持原状。

## 5. 死亡使者魂珠与深渊觉醒核预览（随 .106 已部署）

- 用户明确要求继续放在 `.106` 的分包中，新增 `assets/asset-patch/active/pinball-1.4.105-1.4.106-2-deathbringer-core-icons.zip`，同时交付最终 `assets/asset-patch/manifest.json`，保留第 2 项原 `.106-1` 包。
- 第二包 970,506 字节，SHA-256 `eeb310b65106cf8a3a827cd8bc5bc434ff95e91d939e1a01557f610cdae343b4`。三个 common 资源：20×20 新魂珠 PNG、trimmed_image 显示尺寸表、event_item_shop 商品 `9700199` 的图片路径。
- 使用现有魂珠转换工具从已导入的死亡使者新装备图生成；深渊觉醒核预览引用真实道具图。兑换成本、限购、奖励和存档无变化，深渊计时标记保留。
- 已备份并同步本地，实际安卓/iOS 下载接口与第二包下载哈希验证通过，手机显示待验收。已是 `.106` 的客户端不会自动补拉同版本新增分包，需客户端资源重新下载；仍为 `.105` 或更早版本的客户端按正常升级链取得两包。
- 未提交、未推送、未部署云服。详情与精确同步文件见 `assets/asset-patch/audit/deathbringer-core-icons-1.4.106/README.md`、`report.json`；外层云包继续排除所有 production 散资源，新增 ZIP 原样纳入。

## 6. 入手来源文件夹过滤修正（安卓客户端候选，不属于云服覆盖文件）

- 用户重新下载 `.106` 后仍无法查看机兵齿轮/蒸汽核来源。已确认客户端只承认普通/支线活动，漏掉文件夹中的常驻机兵及幻想/深渊；第 2 项索引仍需交付，但单靠它不能完成 UI 修复。
- 安卓候选 `outputs/item-source-folders-lan-test-20260912/StarPoint-CN-1.8.1-item-source-folders-lan-test-20260912.apk`，SHA-256 `e79f6abcde6ce9286023689a876173a8bb9d8ed2583aee06a11a6b128e91674e`。保留深渊纪录候选的累计功能，新增文件夹成员、解锁及开放期 fallback。
- 本次不修改 CDN `.106` 两个分包、manifest 或服务端，不能把 LAN APK 放入云服整合包。用户必须安装修正后的客户端；iOS 尚未移植、手机验收待完成、注册表未晋升。
- 实现与验证边界见 `client-patch/item-source-folders/README.md`。后续不得把第 2 项服务端/CDN 交付等同于所有平台客户端已修复。

## 7. 深渊纪录保持者昵称（已部署；以下为历史记录）

- 用户已验收第 6 项安卓 APK，随后要求先追加纪录保持者昵称并本地试用，再继续提交、公网 APK、云服整合包和 iOS；当前发布流程暂停，云服仍未部署上述待交付内容。
- 第 4 项文件集中的 `src/data/domains/abyss-records.ts`、`src/routes/cn/abyssRecords.ts` 及对应两个 out JS 已更新并同步本地。整合包须选择最终包含 `holder_name` 的版本，不能用此前只返回用时的构建覆盖。
- 读取纪录原有 viewer ID 对应账户的当前公开玩家昵称；没有新增表、列或存档字段，也不改 `.106` 分包和 manifest。现有纪录直接可查询昵称。
- 昵称版安卓 LAN 候选 SHA-256：`e04b9e4f367be0ee447f1cfc8f45ff314fafc4a2df7efcef03db120347278f32`，详情见 `client-patch/abyss-record-holder/README.md`。尚待手机验收，注册表未晋升；iOS 未移植。
- 暂停前生成的 `outputs/item-source-records-public-20260912/` 公网 APK 不包含本次昵称功能；后续须用最终验收的累计版本重新生成。APK 不纳入云服覆盖 ZIP。

## 8. 觉醒页面刷新及查询减负（本地修复，未提交、未同步或部署）

- 2026-09-12：针对“任务已完成但能力觉醒仍锁定，退出重进才开放”完成本地修复和离线回归。当前页面持有旧角色对象、旧等级及禁用页签；服务端补发字段不能独立修正这些客户端缓存。
- 服务端源文件：`src/data/domains/character.ts`、`src/data/domains/mission.ts`、`src/lib/mission/awake-settlement.ts`、`src/lib/mission/awake-unlock-response.ts`、`src/lib/mission/awake-unlock.ts`、`src/lib/mission/computer-awake.ts`、`src/lib/mission/types.ts`、`src/routes/api/character/mana.ts`、`src/routes/api/mission.ts`。TypeScript 构建已通过；除仅类型变化的 `types.ts` 外，上述 8 个运行模块均须带对应 `out/` JS，含被 Git 忽略的构建输出。
- 同次请求复用限定范围的任务快照；已领取且进度未变时跳过数据写语句；重复请求继续补发权威资格；只补查尚缺资格的角色；玛纳节点校验合并为目标角色读取。未新增表、列、存档字段、角色/任务 ID、奖励或资源版本。官方与扩展觉醒、二板 F1009 延迟发布、旧存档修补及快照兼容回归通过。
- 本地大存档隔离样本：重复任务页读取 22→14 次、数据写语句 5→0、返回行数 1187→44；已具备全部配置资格时的通用检查读取 13→1 次、数据写语句 46→0。不代表云端压测或整机 CPU 降幅。
- Android 仅生成 SWF 候选，主 ABC `290:67327` 一个回调改变，其余 96,534 个方法体保持。方法、精确基线和验证边界见 `client-patch/awake-page-refresh/README.md`。尚未回封 APK、移植 IPA 或真机验收，不更新客户端注册表；客户端补丁不能由云服覆盖包代替安装。
- 完整证据：`F:/codex/work/awakening-unlock-fix-20260912/修复与负载验证.md` 与同目录前后查询报告。本条仅登记新增范围，不改变前 7 项或其已有交付记录。本次无提交、推送、运行镜像同步或云服整合包。

## 9. 称号统计与觉醒条件查询第二轮优化（本地完成，未提交或部署）

- 2026-09-13：用户授权继续合理优化。在第 8 项基础上，将称号累计节点/信赖之证统计改为数据库聚合，亲密度仅查经验及已领取标志；二板逐个校验必需节点并返回完成角色 ID，保留空板、缺节点、未拥有角色及二板 F1009 的原有语义。
- 已达到最终目标的称号跳过事实统计，仍处理未领取阶段和旧存档缺失的称号归属；部分完成与未来开放的称号继续正常结算。只缓存预编译查询，不缓存玩家结果。指定关卡及角色通关次数按最多 400 个 ID 批量读取，精确类别与深渊换塔计时修补保持。
- 本轮源文件：`src/data/domains/character.ts`、`src/data/domains/character_clear.ts`、`src/data/domains/quest.ts`、`src/lib/mission/computer-awake.ts`、`src/lib/mission/computer-degree.ts`、`src/lib/mission/settlement.ts`，必须带对应 6 个 `out/` JS。和第 8 项合并后共 25 个服务端文件；共享路径用本轮最新版，不回退第一轮刷新修复。
- 相邻进程对照的大存档中位耗时：觉醒节点 10.225→1.820 ms、学习节点 9.897→1.779 ms，进一步减少约 82%；SQL 返回行数分别 13,361→40、13,360→39，其中统计行包含紧凑角色 ID 数组，不等于仅扫描几十行。小存档约增加 0.03～0.06 ms；不宣称每个场景或整机 CPU 同比例改善。
- 构建、37 项回归及独立称号战斗统计测试通过，验证了执行计划、跨玩家新鲜结果、旧存档补发、精确二板成员及快照兼容。没有数据库迁移、角色/任务/节点 ID 或奖励变更，也没有 APK/IPA、CDN 或客户端注册表修改。
- 报告与累计文件哈希：`F:/codex/work/awakening-query-followup-20260912/称号与觉醒查询优化验证.md`、同目录 `verification-manifest.json`。本轮未提交、推送、同步本地运行镜像或生成云服整合包；第 8 项客户端 SWF 候选仍待独立打包和设备验收。

## 10. 三把武器次数复原与独立无属性木人百倍血量（.107 第 1 包本地修订）

- 2026-09-13 最终要求：撤回原版木人的十倍血量调整，在单体与群体原入口分别新增无属性高血量关，HP 为原版 100 倍、时限 10 分钟；用户明确要求 CDN 增量合并到之前生成的包。全部 91 条原有关卡压缩行已恢复/保留为 `.106` 字节，原版 81–87、91–97 仍为原 HP 和 3 分钟。
- 三把武器复原保留：木灵大剑 4010014 为 3 次，无名之弓 2040001 与埃俄罗斯之弓 5040009 的回充为 10 次；目标能力行匹配 `.54`，整个能力表与此前第 1 包一致。
- 新增 Practice 1101“高血量木人·无”，置于结实假人入口 100；1102“高血量木人们·无”，置于结实假人们入口 99。本体 100,047,977,312 HP，小木人每个 100,024,515,359 HP，群体初始合计 500,146,038,748 HP。两关时限 36,000 帧，客户端评价时间 600 秒，服务端评价时间 600,000 ms；原场景、无属性、回血、攻击力、解锁条件、缩略图及无奖励规则保持。
- 原 `1.4.106 → 1.4.107` 第 1 包直接修订：`assets/asset-patch/active/pinball-1.4.106-1.4.107-1-weapon-caps-practice-hp.zip`，41,940 字节、2 个共享 orderedmap，SHA-256 `9527476e7df4f01460f282907a3ec6ecb1beb9b55727b4fc171cd5061b88ff50`。必须同时带最终 `assets/asset-patch/manifest.json` 及 **`assets/practice_quest.json`**；仅 CDN 包不能注册服务端的新关卡。第 11 项第 2 包与作者内容保持，最终 .107 仍为两包；其历史说明中的第 1 包身份以本条新版为准。
- 战斗记录：新编号通过当前客户端的类别/关卡 ID 映射读取各自新名称；列表与详情无官方编号白名单。隔离测试通过两关 10 分钟结算、SS 评价、7 分钟退出记录、用时、总伤害与角色伤害查询，原关卡进度不变。已核查当前 Android 的记录显示类；未做真机画面或实战验收。
- 存档：新增两个编号使用现有关卡进度及练习历史表，不新增表/字段、不改变原编号或 V2 schemaFingerprint。旧、新 V1/V2 HTTP 下载/multipart 导入兼容，V2 完整记录保留，导入前备份逐项匹配目标原数据；错误 JSON 和结构指纹被拒绝且不改写目标。V1 保持原来的部分存档语义。
- 新生成器 `tools/fantasy-gauntlet-mod-tools/revise_practice_clones_1_4_107.py`；验证 `tools/practice_high_hp.test.cjs`。最终审计见 `assets/asset-patch/audit/practice-clones-100x-1.4.107/README.md`，原十倍方案审计保留为被替代的历史记录。当前 `out/lib/assets.js` 直接加载根目录 JSON，无需本任务的 TypeScript 构建或 APK/IPA 更新；后续部署应按正常流程加载新服务端 JSON。
- 仅源码本地修改，未提交、推送、同步 `F:/startpoint-cn-main`、部署云服或生成云服整合包。修订前包及文件备份在 `F:/codex/work/practice-colorless-100x-20260913/before/`；其余待部署项目状态保持。

## 11. 作者 858 选定内容融合（.107 第 2 分包，本地完成）

- 与第 10 项共用 `1.4.106 → 1.4.107`，新增 `assets/asset-patch/active/pinball-1.4.106-1.4.107-2-author858-selected.zip`。579 个成员、61,440,691 字节，SHA-256 `0bdd8b6482f516e4aa5cfc7473cefbb34a3d3ff6cde95306f0007bd9646d17ed`；第 1 包原字节与武器／木人有效表完整保留。两包、最终 manifest 一起交付。
- 接入四位新角色、十五位小 Boss、已确认的光杰拉德／冰雪罗尔夫／夏日白改动、二板日期、美术与正式语音。两池采用作者 MOD 概率、排序及标红，普通兑换沿用本服，排除 26 个非扭蛋角色，竞速五位零概率角色不可兑换；同步改写注意事项。
- 服务端必需路径共 9 个：`assets/character.json`、`assets/cdndata/character.json`、`assets/cdndata/character_text.json`、`assets/cdndata/character_text_rank_p5b.json`、`assets/mana_board.json`、`assets/mana_node.json`、`assets/gacha.json`、`assets/gacha_cnmod.json`、`assets/gacha_rank_p5b.json`。CDN 分包不包含这些 JSON；打包时必须使用保留既有内容和本次目标行的最终版，尤其三份 gacha 镜像应一致。
- 新增 4 个角色 ID 及 164 个节点 ID，无冲突；既有 ID 和存档格式保留，无数据库迁移。12 组 iOS 立绘资源配对、最终资源回读、技能类型、真实数据 accessor／卡池一致性、两平台同版本两包下载清单均已离线验证。未访问玩家数据库、安装客户端或做真机战斗验收。
- 作者已书面确认校奈芙 `FindAllSubjects` 参数 8 的类型错误，本包仅改该位置为 `DoNothing`。该修正只涉及 CDN。火狮王五条正式技能语音已重排为原生连续编号，不需要改 APK；准备音沿用原生两条路径，保留额外录音资源，但本次不新增 `_alt_1` 轮换。临时 APK 候选已移出交付目录；不将其装入云服包，也不替换已验收注册表。
- 本项仅在源码工作区完成，未提交、推送、同步 `F:/startpoint-cn-main` 或部署云服。详细范围、哈希和验收边界见 `assets/asset-patch/audit/author858-selected-1.4.107/README.md`。不因本记录推断其他任务已经部署。

## 后续打包规则

1. 以本文顶部的最新用户确认和当次授权范围为准；历史段落不覆盖最新状态。
2. `.107` 整合包的 39 个明确路径已由用户确认部署。本次 H400 新增范围仅两个接口文件，使用已提交版本；现有 `.107` 部署作为前置条件。后续有其他新增或用户纠正时重新确定范围。
3. 外层包排除 `production/**`、`assets/asset-patch/production/**`、`.cdn/**`、`changelog.md`、密钥、数据库、日志及本地工具；启用的 CDN 分包按原始 ZIP 字节交付，保留其内层 `production/` 成员。
4. 在包旁记录文件、SHA-256、提交、依赖基础、验证及本地同步结果。只有用户确认覆盖或获授权后的云端核验，才能把本轮新增内容更新为已部署。

四个新角色、164 个节点和两个新练习关使用既有存档结构；旧 ID 及 V1/V2 规则保留，无数据库迁移。隔离测试和真实服务只读导出证据见三会话整合记录。

## 练习关崩溃后放弃恢复 H400（已于13:57交付，本次接口累计保留）

- 重登放弃练习关时客户端可以省略 `statistics`，旧退出接口读取 `statistics.party` 后报错并返回 400，未完成关卡未清除，造成重复登录/放弃均 H400。
- 已让身份匹配的退出在缺少或无效统计时跳过历史记录并完成清理，保留身份校验、正常结算记录及事务回滚，不伪造伤害或进度。
- 发布需包含 `src/routes/api/singleBattleQuest.ts` 与 `out/routes/api/singleBattleQuest.js` 两个文件并重启服务；本次修复没有 APK、IPA 或 CDN 资源变更。
- 源码/构建 JS 的恢复回归、原版/新木人结算及历史、V1/V2 HTTP 存档导入导出与备份验证通过。无表结构、存储 ID 或存档格式变化。详见 `docs/development/PRACTICE-H400-RECOVERY-20260913.md`。
- 用户随后要求“提交，并给我云服整合包”，并明确 `.107` 已经覆盖。本次包仅包含上述两个修复文件，以云端现有 `.107` 为基础。其他任务未提交的抽卡优化保持待交付，不混入本次提交或包。
- 提交、推送、本地同步与打包不代表云服已部署；最终文件和状态见本次 `practice-h400-107` 包旁交付记录。用户要求 G1008 暂缓，待自行本地复现；其未启用候选不属于本项交付范围。

## 木人历史记录改用真实时间（已提交、已打包，云服待部署）

- 本地新记录实际已保存，但日期取自虚拟时钟，客户端再次按日期排序后落到旧记录后面。用户明确要求按真实时间排序。
- 新的练习关结束及退出记录使用真实系统时刻，并按北京时间显示；活动时钟、伤害、战斗用时和 H400 退出保护保持。旧记录缺少历史偏移量，保留原日期，不猜测回填。
- 运行交付须含 `src/routes/api/singleBattleQuest.ts`、`out/routes/api/singleBattleQuest.js`、`src/lib/quest/practice-battle-history.ts`、`out/lib/quest/practice-battle-history.js` 四个文件；最后一个 JS 受忽略规则覆盖，后续提交须显式加入。
- 源码/JS 的真实时间及客户端排序回归、既有练习与 H400 回归、旧/新 V1/V2 HTTP 存档导入导出及备份、独立完整构建均通过。无表结构、存档格式或 CDN/APK/IPA 改动。
- 已提交 `1ec70d40` 并推送，四个运行文件已备份、同步本地并重启，运行镜像真实时间路由隔离回归通过；已纳入顶部 `.108` 包，云服待覆盖。此前 H400 包不含此时间修复，本次接口保留 H400 保护。详见 `docs/development/PRACTICE-HISTORY-REAL-TIME-20260913.md`。

## 歼灭者两池抽取与兑换（.108 第 2 分包，已交付待云服覆盖）

- 用户确认歼灭者 179981 可抽、可兑换：深渊池 0.100%、竞速池 1.000%，两池 250 点兑换。其他 MOD 概率与五星总概率不变，普通五星按原权重比例分摊新增份额；女帝歼灭者 179985 等五个展示 Boss 继续零概率且不可兑换。
- 同批交付 `assets/gacha.json`、`assets/gacha_cnmod.json`、`assets/gacha_rank_p5b.json`、最终 `assets/asset-patch/manifest.json` 与 `assets/asset-patch/active/pinball-1.4.107-1.4.108-2-epuration-gacha.zip`；保留并交付 .108 第一分包依赖。CDN ZIP 不含服务端 JSON，加载新配置需正常重启服务端。
- 第 2 分包 10,190 字节、4 个 Android/iOS 共用资源，SHA-256 `51e148075ca1e166b661f99c7617921f473232eda1cb697e2ff28795059f7b33`。源仓库四个稀疏直读文件已对齐，外层云服包仍排除 loose production，内层 ZIP 保持字节。
- 已核对有效客户端链、三份服务端镜像、普通及保底概率、隔离数据库真实兑换和拒绝路径、两平台 .107→.108 下载清单、直读资源摘要与 ZIP。未改角色 ID 或存档格式，无数据库迁移。详情见 `assets/asset-patch/audit/epuration-gacha-1.4.108/README.md`。
- 已于2026-09-13 17:51并入称号任务同步本地`.108`；现已提交 `4ba885bc` 并推送，纳入顶部 `.108` 包，同一提交内容已重新核验本地运行。云服待覆盖，手机验收待完成；最新回执见 `RELEASE-108-20260913.md`。

## 校园碧安卡与校园奈芙提姆 G1008（.108 第 3 分包，已交付待云服覆盖）

- 用户授权修复两个角色并加入 `.108` 分包；资源包为 `assets/asset-patch/active/pinball-1.4.107-1.4.108-3-campus-summon-g1008.zip`，6 个共用 ActionDSL，5,135 字节，SHA-256 `5737d357d7f9e83ac0702df898ebd6eaf88a5878e24b885177ead42e9ba43911`。
- 校园碧安卡进化前后技能：延迟施加吐息状态前重查本角色小龙；重入仅刷新统一退场计时，保留每次吐息/施法者状态/FEVER；新召唤清理上一代回调，防止旧流程误用新龙。
- 校园奈芙提姆进化前后技能及能力 3、4：仅关闭 6 处召唤物普通增益的强制施加，恢复结算时的原生死亡检查。召唤数量、寿命、伤害与增益数值、出生禁疗、强化弹射脚本及角色表均保留。
- 11 项精确资源/有限生命周期模型回归、完整 DSL 类型与序列化回读、幂等和越界改动拒绝、有效资源链、Android/iOS 进程内 `.107 → .108` 三包清单、深渊计时版本检查通过。无 SWF/APK/IPA、存档 ID 或格式变更；尚未手机战斗复测。
- 同批资源交付需用最终 `assets/asset-patch/manifest.json`，保留 `.108` 第 1 称号包、第 2 歼灭者扭蛋包及其各自交付依赖。用户确认 `.107` 已覆盖，后续云服整合不重新装入 `.107`；外层继续排除 loose production。
- 已于2026-09-13 17:51并入称号任务同步本地`.108`；现已提交 `8f8cd498` 并推送，纳入顶部 `.108` 包，同一提交内容已重新核验双平台下载。云服待覆盖。实现证据见 `tools/campus-summon-g1008/` 与 `assets/asset-patch/audit/campus-summon-g1008-1.4.108/README.md`；最新同步回执见 `RELEASE-108-20260913.md`。

## 校园三人技能展示图（.109 第 3 分包，源仓库本地完成）

- 用户确认技能展示图取景过近，要求从完整立绘重裁并加入同一个版本的分包。保持 `1.4.108 → 1.4.109`，使用第 3 分包，避开 C2265 历史第 2 分包编号。
- 新增 `assets/asset-patch/active/pinball-1.4.108-1.4.109-3-campus-skill-cutin.zip` 和对应 manifest 登记。包大小 4,551,141 字节，SHA-256 `2b89ec0ffae5fac59a36d04c1226493a2f420a4dff3b6fe4d31cbe975a5948f2`；保留既有 .109 作者融合第 1 分包原字节。
- 校碧安卡、校希尔媞、校奈芙提姆进化前后 6 张技能图，含 6 张 medium PNG、6 个 Android ETC1 ATF、6 个 iOS ETC2 ATF。保留原画、1024×512、透明背景及已有主数据几何，不改普通头像、技能数值或存档。
- 严格 PNG 回读、6 组双端纹理及全部 mip 解码、最终 18 成员 ZIP、有效资源链、Android/iOS 实际更新路由处理器均通过。已上报 .109 的客户端不会因同版本追加自动更新；本次按用户要求保留版本。
- 本项未提交、推送、同步本地运行目录或部署云服，未制作云服覆盖整合包；真机战斗效果待复测。后续授权交付时使用最终 manifest 与启用分包原字节，外层继续排除 loose production。详细回执见 `assets/asset-patch/audit/campus-skill-cutin-1.4.109/README.md`。

## APK 轻量接入校验（2026-09-15，本地实现与 MuMu-1 测试）

- 用户要求拦截旧 APK／其他 APK 仅修改公网地址后接入；允许多个构建、配置删减和覆盖更新，无管理面板、无下载链接。实现一次性挑战、构建 HMAC、账号会话绑定的短凭证，HTTP／TCP 均在游戏处理前校验。
- 后续授权交付需含 `src/cn-server.ts`、`out/cn-server.js`、`src/lib/client-admission.ts`、`out/lib/client-admission.js`、`src/multi/tcp/server.ts`、`out/multi/tcp/server.js`，以及运行 `config/client-admission.json`。新增 JS 被 out 忽略规则覆盖，后续提交须显式加入。
- APK 变化时按用户明确要求带配套准入配置，并保留仍允许的旧构建；专用 `config/client-admission.keys.json` 从本地私有打包目录提供，只用于部署该功能，不提交 Git、不发送到玩家群。这是内置 APK 的准入材料，不是 Android 签名私钥/密码。不得将实际签名凭据装入包。没有 APK 变化时避免覆盖管理员已调整的名单。
- 第一批默认 `enforce:false` 保留遗留客户端过渡期；管理员准备完成后切为 `true`。严格模式也会拦住尚未实现该协议的 iOS；没有可信平台豁免。本轮只制作隔离本地测试 APK，后续公网 APK 和配套名单需在获授权发布时生成并校验。
- 配置约 2 秒热加载，停用/删除/到期影响下一条请求；配置不完整保留上一份有效配置。无数据库表、账号归属、存档格式或 CDN 资源变动。
- 本轮未提交、推送、同步正式运行镜像、打云服整合包或部署云服。实现及实际验证范围见 `client-patch/client-admission/README.md` 和 `TEST-20260915.md`，不能将本地可用记为云端已生效。
- 后续用户指定先完成服务端、客户端稍后：已补充 HTTP/TCP 有效活动延长原凭证（每次续到当前时刻后 30 分钟）、仅限已绑定账号的过期 5 分钟续期宽限、恢复动作与相对计时字段，以及 Android/iOS 独立平台条目。撤销/到期优先于续期；iOS 不享受校验豁免。真实 TCP 加速 3 小时、双端 HTTP/真实账号恢复、源码及构建 JS、登录回归通过；本地隔离 8002/8013 服务已加载新源码，正式运行镜像和云服未变。
- 此次服务端补充更新 `src/lib/client-admission.ts`、`out/lib/client-admission.js`、`src/multi/tcp/server.ts`、`out/multi/tcp/server.js`；其余首轮接入文件仍是完整交付依赖。未修改或重打 APK/IPA。后续两端客户端按 `client-patch/client-admission/SERVER-PROTOCOL.md` 完成恢复流程并做设备验证；测试记录见同目录 `SERVER-TEST-20260915.md`。

## R10 非测试公网 Android（2026-09-15，本地成品，云服待配套）

- 用户要求以最终 R10 制作非测试公网 APK，明确移除日志导出。成品保留 R8/R9/R10 与此前全部累计逻辑，移除诊断入口及组件，独立保留首帧缓存清理，并接入完整构建准入、后台续期、恢复与请求取消保护。
- Android 新正式号 `android-181-r10-20260915`；内网验证沿用初始测试号 `android-20260915-admission-01`。正式 APK 在 `outputs/r10-public-release-20260915/`，SHA-256 `afca9f44d1bea9edea7b573fa96dddd32bc304afd0bbaa4d3df6fb21d41c2a90`。未制作 IPA、未提升客户端 accepted registry。
- 本轮实际源配置 `config/client-admission.json` 追加正式 Android 条目，保留 `enforce:false` 过渡。上项 6 个服务器源码/JS 是完整依赖，本轮独立完整构建已证明源码与现有 out 一致；`out/lib/client-admission.js` 仍需显式纳入后续提交。没有新增数据库或存档格式变更。
- 可审查的 7 个服务器文件及哈希在成品目录 `server-files/`、`server-files.json`。独立私有伴随文件在 `outputs/r10-public-release-private-20260915/config/client-admission.keys.json`，目标为云服同相对路径，禁止加入普通整合包或 Git。APK 不放进服务器覆盖 ZIP。
- 实际云服现有名单/私有材料未核查。若已有条目，须依据完整现有配对使用 `merge-policy.cjs` 追加，保留管理员 enforce、提示、旧版本启停/期限；不能用首次接入配置盲目覆盖。先部署配套实现和材料，再分发 APK；本轮未启用严格模式、上传/重启云服、同步运行镜像、提交/推送或制作统一云服 ZIP。
- 实现、验证及未测范围见 `client-patch/r10-public-release/README.md` 与成品目录交接说明。五重共斗逐渐变慢仍未确认根因，不将本轮正式打包等同于已修复该问题。

## 同批 iOS 正式公网准入版（2026-09-15，本地完成，云服待配套）

- 用户要求补做 IPA，明确从 iOS 已验收商店累计版出发，只加入完整准入/续期/失效恢复，不带入 Android R8/R9/R10 性能、队伍缓存或加载优化，不加入诊断/日志导出。成品位于 `outputs/ios-admission-public-20260915/StarPoint-iOS-1.8.4-admission-public-20260915-unsigned.ipa`，SHA-256 `764a7c5183a8605f58364e786a08a59f65333403bded9918dd3b544a85112f09`，沿用 TrollStore unsigned 方式，未真机测试。
- iOS 新正式号 `ios-184-admission-20260915`，平台 `ios`，公网初始/账号/准入/游戏入口沿用端口 80。Android 原号 `android-181-r10-20260915`、APK 及密钥均未改变；两端批次对应关系见 `client-patch/ios-admission-release/release.json`。
- `config/client-admission.json` 已追加 iOS 并完整保留 Android 与 `enforce:false`。最新双端 7 文件候选和哈希在 IPA 成品目录 `server-files/`；六份准入源码/out 与上一 Android 完整构建相同，无服务器接口变更。新完整双端私有材料在 `outputs/ios-admission-release-private-20260915/config/client-admission.keys.json`，禁止放普通覆盖包、Git 或玩家群。后续整合应使用最新双端配置，不用仅 Android 的旧副本覆盖。
- 尚未核查云服已有其他名单和私有材料；按成品说明用完整现有配对合并，保留管理员设置。先部署配套再分发，保证公网端口 80 与 Android 8001 的准入路由可达；不自动切严格模式。
- 3568 成员、9 个既有准入入口、69 个 helper、78 个原生函数、2175 重定位、61 跳转桥接及 3 种 ldid 签名模型通过；56 项 AIR 生命周期、37 项双端正式配对/真实账号 HTTP 协议、5 项历史 iOS 失败回归通过。为离线与隔离模拟时间验证，没有 iOS 真机、云服或长时间实战验收。
- 无存档 ID、表/列、账号归属、V1/V2 格式或 CDN 变更；未操作 MuMu/Android 安装，未提交、推送、同步正式运行镜像、部署/重启云服或制作统一 ZIP，未提升 accepted registry。实现和完整未测边界见 `client-patch/ios-admission-release/README.md`。
