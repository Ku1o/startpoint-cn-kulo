# 深渊连战：属性封锁保底

2026-09-09 用户确认：保留普通 roll 的全部合法诅咒，每关至少封锁两个属性；已封锁更多时保留，最多五个。封锁指战斗伤害近乎失效，不是限制对应角色入场。2026-09-10 用户先授权从已验收 APK 制作客户端测试包，随后授权完成配套塔配置并同步本地供测试。30 层配置、称号与莱特兑换已合入本地测试资源 1.4.104；第二关空脚本引用错误已追加 1.4.105 修复，第十二关苍机兵核心关联问题已追加 1.4.106 修复，等待真机复测。

## 已实现的规则

`tools/fantasy-gauntlet-mod-tools/wf_rogue_build.py` 中的 `guarantee_element_bans` 在完整原始诅咒集合上补足数量，不替换条目、不改变已有条目或消费普通诅咒名额。

| 原有封锁属性数 | 处理 |
| --- | --- |
| 0 | 从六属性中均匀随机选两个补足 |
| 1 | 从其余五属性中随机选一个补足 |
| 2～5 | 完整保留，不补抽、不缩减 |
| 6 | 拒绝原始组合，由调度器重抽冲突组合；不静默删除原有封锁 |

按同一属性合并后的正向耐性计数。客户端普通伤害使用 `damage / (1 + r)`，因此 `r >= 99`（伤害至多 1%）计作封锁，`r=1/9` 不计入保底。新选中的属性补到总 `r=999`（伤害 0.1%），原有弱耐性仍保留。留下的属性可以受到普通减伤，只要合计未达到封锁阈值。

固定伤害、比例伤害存在独立计算路径；上述口径不宣称让所有伤害计算器都绝对归零。直击、技能、能力和 PF 耐性继续沿用四种伤害类型不能全免疫的原有门禁。

`element_ban_rng(seed, round_no)` 使用独立随机序列，同一塔种子和层号可复现，不影响后续 Boss 与普通诅咒的抽签。对已补足的结果再次调用不会重复追加。保底函数只返回计划和回执，`runtime_verified=false`，不会冒充已生效的战斗资源。

普通随机池暂时保留原有“一张普通元素卡”的节奏；这不限制该卡本身封锁三至五种属性，也不限制显式合法多卡及后续独立保底。显式多卡改为按合计封锁数量裁定，不能再被“一律最多一张元素卡”误拒。

## 当前客户端证据与剩余配套

最初只读研究使用历史 Lens v3，APK SHA-256 `8e5999e2689788159362acc81cd4bcd89182966fce9af7800d085ff89dccb41b`，SWF SHA-256 `ff96d39ae9dd30b7341958da0dbb19db38f557f5eb37ec9ed5284fd15f238a71`。它不是本次构建输入。9 月 10 日重新核验登记，APK 构建直接使用深渊续战 Lens 累计包 `c868534b575348dde825fcd4c88c156157174fd4444724f1141fd9aa95e32a2d`、SWF `11c06fd77a0e3811164d196208ecce28cba5ec3a602e3d798f3c67d5d5b17e04`。

只导出并检查了 `EnemyImpl`、`BattleQuestBaseImpl`、`RushEventBattleQuestLogic` 三个相关类。读回目录为 `F:/codex/work/abyss-element-ban-20260909/client-readback/`。

- `EnemyImpl.isConditionPrevented` 对正向属性耐性提前返回 `false`。`resist_element_resistance` 只限制部分非正向属性耐性，不能据 `general_boss.c36=true` 判定本工具的正向耐性卡失效。生成器已修正此误判，继续严格检查实际等级行、列数和布尔编码，不修改 Boss 的 c36 值。
- `EnemyImpl` 初始化时读取 `battle.initialEnemyConditions` 并写入自身条件槽，时间为 9,999,999 帧，设置为不可驱散。这是后续覆盖开场小怪及新出生敌人的统一入口。
- `BattleQuestBaseImpl.getInitialEnemyConditions` 当前只解析关卡的五个既有条件槽；`InitialEnemyCondition` 没有属性耐性构造。纯粹在旧字段中填写新增编号会导致客户端解析错误，不能直接发布。
- 现有 Boss pre-action 通道尚未覆盖全部标准、专用和多阶段 Boss。因此保底算法尚未接入正式 roll，也未把缺失载体的能力矩阵强行标为支持。9 月 10 日 Android 测试包已经加入通用关卡属性入口，仅对 `BattleQuestBaseImpl.getInitialEnemyConditions` 插入调用，保留原五槽。使用 `sub_name` 中的可读属性伤害标记，详细契约、适用范围和构建方式见 [客户端通道](../../client-patch/quest-element-resistance/README.md)。本次不写当前关卡配置；正式 roll 接入、客户端版本门禁、iOS 配套及逐类游戏验证仍未完成。后续必须避免与工具生成的 Boss DSL 同效果重复累计。

## 校验记录与工作区状态

- `test_rogue_element_ban.py`：11 项通过，含 63 种原始属性子集、全部 15 种保底双属性组合、弱耐性合并、重复执行、原条目不变、六封锁拒绝及 DSL 严格签名/序列化回读。
- 相关诅咒、叠层、能力矩阵和 DSL 回归：62 项通过。未执行生成新塔的完整 dry-run 测试。
- 对此前种子 `46454236` 的 30 层记录作内存校验：所有保底计划均为 2～5 个封锁属性，原有条目保持，30 个合并耐性程序内存回读通过。这些结果只是对旧预览的算法验证，不是本轮塔定稿。
- 审计：`F:/codex/work/abyss-element-ban-20260909/policy-check.json`、`regression.log`。
- 9 月 10 日完成 Android 通道测试 APK：`outputs/quest-element-channel-test-20260910/`。351 项桌面 AIR 检查、原 96,404 个方法的独立比较、包体/UUID/签名/对齐检查通过；尚未 Android 真机验证，不代表正式塔已生效。新增五方法模块、原游戏仅一个方法增加调用，保留全部其他累计方法。
- 新塔、IPA、资源 ZIP、云服覆盖包均未生成；本任务没有修改共享资源清单。称号、莱特兑换、暂缓入场文案和其他用户本地修改保留。
- 分支 `staging`，工作开始时 HEAD `2e7ab5a06fbd941fec6d799ebd51e1abd67bf441`，与 `origin/staging` 无提交分歧。本轮未提交、推送或同步运行镜像，没有覆盖运行文件，也没有对应运行备份。
- Android 后续构建开始时 HEAD 为 `8f6252bb31c7f18a8cb61f11fa699282e68ebc4b`，分支仍为 `staging`。APK 构建只作本地未提交修改，未更新验收登记、未同步运行镜像。

## 9 月 10 日配套本地测试交付

- `wf_rogue_element_channel.py` 提供补足、精确百分比编码/回读和旧生成耐性程序迁移。`finalize_abyss_element_tower.py` 从已固定哈希的种子 46454236 稀疏预览生成配套结果，不重抽 Boss/领域或修改 HP。新结果保持全部原有合法卡，仅补缺失属性。
- 原始结果第 20 层已有两种封锁，第 27 层已有一种，其余没有达到 `r>=99` 的封锁。因此本次 30 层补足后恰好都是两种，算法仍保留原有三至五种组合。第 1 层封锁水、风，额外耐性均对应剩余伤害 0.1%。
- 17 条工具生成的 General Boss 载体行仅调整 c109 的旧生成程序引用；元素部分迁到关卡入口，纯元素程序引用移除，混合程序保留非元素部分。原生动作、领域、c110+、其他模式的语义保持。剩余四个生成耐性程序全部经严格签名和序列化回读。
- 新包 `assets/asset-patch/inactive/candidates/pinball-1.4.103-1.4.104-1-abyss-element-sponsor-laite-test.zip`，29 个资源，3,778,769 字节，SHA-256 `d6cee14a122878c3c97f33c910ac8fd1b585de63d1b6e52860f195521dad5fc1`。特别鸣谢 9900012 与莱特 131182 兑换已合入，未发送真实玩家邮件。
- 内网 APK 直接从登记的内网累计基线生成：`outputs/quest-element-channel-lan-test-20260910/StarPoint-CN-1.8.1-quest-element-channel-lan-test-20260910.apk`，SHA-256 `8e21b793091415be13d13ac170a1dc53e89fb92a3d688c135deb86644a71bbcb`；独立 96,404 方法检查与 351 项桌面 AIR 检查通过。
- 资源 ZIP 内真实 30 条副标题已由同一份 APK helper 运行校验；另有五项 Python 通道回归、16 项称号/兑换回归、隔离 `npm run build`、31 条关卡引用链、HP 审计及全表语义范围检查。不能将这些静态/桌面证据称作 Android 实战验证。
- `sync_abyss_element_local_test.py` 按用户本次“同步到本地”授权作未提交测试同步，备份后复制 36 个明确文件，未变化的两个服务端关卡 JSON 跳过。备份：`F:/startpoint-cn-main/.codex-backups/20260910-114620-abyss-element-local-test/`。具体文件清单和前后哈希见 `assets/asset-patch/audit/abyss-element-sponsor-laite-1.4.104-test/local-sync-report.json`。
- 本地服务已启动，HTTP 更新接口只返回本次 `.103 -> .104` 的一个资源包；广告下载地址、ZIP 和全部 29 个直接资源逐字节一致。实际 accessor 读取到莱特可兑换、总计 45 名可兑换及赞助称号定义。
- 源仓库带有暂缓文案的 `.106` 清单保持原样，测试运行目录使用审计目录中的独立 `.104` 清单。暂缓文案没有进入新包或同步列表。构建阶段 `report.json` 与同步阶段 `local-sync-report.json` / `local-test-readiness.json` 分别记录，不将候选构建报告改称真机验收。
- 当前分支 `staging`、HEAD `8f6252bb31c7f18a8cb61f11fa699282e68ebc4b`，未提交或推送；其他用户修改保持。未制作云服整合包、未部署云端、未修改 IPA。测试说明和逐层清单位于内网 APK 同目录。

## 第二关缺资源修复：本地 1.4.105

- 真机日志显示第一关完成，第二关 `battle/start` 返回 200，随后错误 8100：`notify_asset_recovery 未找到素材 (None).action.dsl.amf3.deflate`。当时客户端资源版本为 1.4.104。这不是属性通道抛出的异常。
- 原因是最终生成器在移除纯元素初始化脚本后，把 General Boss c109 写成 `(None)`。`GeneralBossValues` 对该列按字符串数组解析，仅空字符串代表空列表；`GeneralBossSource` 会为数组中每项请求 ActionDSL。已将生成器改为正确的空字符串，并在生成和发布阶段拒绝非法列表成员。
- 从固定哈希的原始种子 46454236 重新生成后比对，唯一资源变化是 General Boss 表的 13 个 c109 字段，对应第 2、3、4、5、8、13、17、20、27 关。其他列、30 层配置、HP 审计及其他资源均保持一致。保留的全部五种初始化脚本引用均能从有效补丁链读取。
- 已增加三个聚焦回归，重现纯元素脚本移除、压缩 CSV 读回及非法占位符导致的资源请求，验证原生/非元素脚本保留。通道八项、属性保底十一项共 19 项通过；真实生成配置复现、30 条 General Boss 行、31 项关卡链检查通过。
- 追加 `assets/asset-patch/inactive/candidates/pinball-1.4.104-1.4.105-1-abyss-pre-action-empty-test.zip`，279,544 字节，仅一个公共表资源，SHA-256 `6d696ccae176bed4ea048b47a9c19cce1d33b818e7b4906f436878756ef15b38`。已发布的 .104 包保持原字节，源仓库暂缓 .106 清单保持不动。
- 本次仅同步新 ZIP、General Boss 直接资源和独立本地测试清单三个路径。备份为 `F:/startpoint-cn-main/.codex-backups/20260910-121107-abyss-pre-action-repair/`；精确文件清单及前后哈希见 `assets/asset-patch/audit/abyss-pre-action-empty-1.4.105-test/local-sync-report.json`。
- HTTP 验证 .103 返回连续两段升级，.104 返回一段修复，.105 无新增差分；实际下载 ZIP、直接资源与源修复字节一致。APK 保持原 SHA-256，无需重装。返回标题更新到 .105 后复测第二关，尚不宣称真机修复验收通过。
- 分支、提交与先前交付一致，保持未提交/未推送；未部署云端或制作云服整合包。生成修复与同步脚本：`tools/fantasy-gauntlet-mod-tools/repair_abyss_pre_action_local_test.py`。审计目录：`assets/asset-patch/audit/abyss-pre-action-empty-1.4.105-test/`。

## 苍机兵核心失联修复：本地 1.4.106

- 用户反馈第十二关反复“系统再启动”，随后授权修正。当前累计 APK 的精确 SWF 经窄范围解析证明，`GeneralEnemy.setupDamageShareTarget` 按真实 Boss master ID 找目标。塔内 Boss 是 `mod_rogue_standard12`，两个核心 `bG` 与主核心六条状态监视仍指向 `steampunk_water_hard_multi`，因此无法分享核心伤害。没有证据表明 HP 数字过大是此次断链原因。
- 本次补齐第 6、12、15、21 关的私有完整召唤链：五份现有 Boss ESDL 更新、25 份私有 Standard Funnel ESDL、237 份私有 ActionDSL，以及新增 25 个条目的 Standard Funnel 表，共 268 个资源。原生表行与原生脚本保持原字节；新编号只供相应塔关使用。
- 每份树反向重放身份映射后与修复前完全相等，所有 HP、试炼、时序、动作数值均不变。第十二关本体仍约 72.86 亿 HP、10% 伤害试炼，重启阶段 1800 帧；原生重启动作仍会正常发生。本次不重新 roll、不重新平衡，也不变更已有 ban 属性。
- 工具新增 Standard Funnel ESDL 反向关联扫描，纳入普通与局部改名门禁，拒绝未经完整关联证明的单独 Boss 克隆。`wf_standard_enemy_links.py` 可在明确输入的完整实体集合上生成独立动作链；常规 roll 尚未自动接入该完整复制路径，不能把门禁修正描述为任意 Boss 自动修复。
- 修正此前错误的试炼判别：Standard `state.e` 是动画编号，`state.m/T2` 才是 DamageCheck；animation 0 也可能有试炼。百分比 `a` 按既有绝对门槛规则缩放；脚本门槛 `h` 缺独立 HP 依赖证明时拒绝 HP 调整。旧 .104 HP 审计中漏记试炼的记录是历史缺陷，本次保留已发布配置并在新回执纠正语义，不追溯改变旧包。
- 23 项不同聚焦回归通过（5 项本次核心关联、9 项 Standard HP、9 项载体与身份门禁）；237 份动作均经过完整签名校验与序列化回读。31 项关卡链检查通过。实际 HTTP 更新链及新包全部 268 个直接资源回读一致，四关本体/核心/召唤引用在实际下载包内闭合。真机击杀复测尚待用户反馈。
- 追加 `assets/asset-patch/inactive/candidates/pinball-1.4.105-1.4.106-1-abyss-standard-links-test.zip`，230,640 字节，SHA-256 `3bcf6c1c032db6d49ae837ba42c67e751e3d9f5c39c94552786db63ea6067ecf`。已发布 .104/.105 包保持原字节；第二关修复继续保留；源仓库暂缓 .106 清单未动。
- 已按此前本地测试授权同步新 archive、268 个直接资源和独立本地测试 manifest，共 270 个明确路径。备份：`F:/startpoint-cn-main/.codex-backups/20260910-125900-abyss-standard-links/`；精确路径及哈希见 `assets/asset-patch/audit/abyss-standard-links-1.4.106-test/local-sync-report.json`。
- 用户继续使用原内网 APK，返回标题更新到资源 1.4.106 后重进第十二关；APK SHA-256 保持 `8e21b793091415be13d13ac170a1dc53e89fb92a3d688c135deb86644a71bbcb`。说明见 `outputs/quest-element-channel-lan-test-20260910/1.4.106修复说明.txt`。
- 分支 `staging`、HEAD `8f6252bb31c7f18a8cb61f11fa699282e68ebc4b`，与跟踪的 `origin/staging` 无提交分歧；修复保持未提交/未推送。未部署云端、未制作云服整合包、未修改 IPA；其他用户既有修改保留。发布复现脚本为 `tools/fantasy-gauntlet-mod-tools/repair_abyss_standard_links_local_test.py`。

## 同日称号宽版：本地测试 1.4.107

当前本地测试资源尾版已追加 1.4.107，仅更新称号 9900012 的透明 PNG 可见宽度；所有 .106 塔配置及修复保持。详情见 [特别鸣谢宽版记录](sponsor-special-thanks-title.md)。
