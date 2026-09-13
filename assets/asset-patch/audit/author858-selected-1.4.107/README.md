# 作者 858 选定内容融合：1.4.107 第 2 分包

2026-09-13 本地融合完成。与武器次数／木人血量任务共用 `1.4.106 → 1.4.107`，本次是第 2 个独立 CDN ZIP，不新增 `.108`。已写入源码工作区；未提交、推送、同步运行镜像或部署云服。

## 交付与同版本关系

- 本包：`assets/asset-patch/active/pinball-1.4.106-1.4.107-2-author858-selected.zip`。
- 大小：61,440,691 字节；579 个资源成员。
- SHA-256：`0bdd8b6482f516e4aa5cfc7473cefbb34a3d3ff6cde95306f0007bd9646d17ed`。
- 第 1 包 `pinball-1.4.106-1.4.107-1-weapon-caps-practice-hp.zip` 原字节及两张有效表完整保留，SHA-256 仍为 `55f99926afbd3588890505ec52a26f0b67dc13225a2b951509886d91db4f4171`。
- 同一个 manifest 版本条目的 `chain` 列出两包，总大小 61,482,339 字节。Android／iOS 实际下载路由在 `.106` 请求下都返回这一版本边的两包。已经报告 `.107` 的客户端按原协议不补拉同版本新增分包；两包应共同发布，提前下载过旧 `.107` 内容的测试客户端需重新下载资源。
- CDN ZIP 只含客户端资源。下列 9 个服务端 JSON 和最终 manifest 也须在后续获授权交付时一起使用：`assets/character.json`、`assets/cdndata/character.json`、`assets/cdndata/character_text.json`、`assets/cdndata/character_text_rank_p5b.json`、`assets/mana_board.json`、`assets/mana_node.json`、`assets/gacha.json`、`assets/gacha_cnmod.json`、`assets/gacha_rank_p5b.json`。精确哈希见 [report.json](report.json)。没有 TypeScript 变动，不需要额外构建 out。
- 没有云服外层整合包。今后打包继续排除外层 `production/**`、`assets/asset-patch/production/**`、`.cdn/**` 和 `changelog.md`；内层 CDN ZIP 原样保留。

## 已确认内容

1. 四位新角色完整接入：校碧安卡 119989、校希尔媞 149989、校奈芙提姆 169989、盾牌座 149988；每位两板共 41 个能力节点，附技能、立绘、语音及依赖。
2. 十五位小 Boss 完整采用作者角色数据、六能力、技能与配套资源：119993、119994、119995、129993、129994、129995、129996、129998、139996、149991、149992、149993、149994、159999、169993。
3. 光杰拉德 149999：两形态强化技最近敌人当前生命 5% 伤害／低于最大生命 5% 时斩杀与对应说明。冰雪罗尔夫 179999：仅三处觉醒立绘位置字段，各增加 128。夏日白 149990：Fever 追加全场攻击 75 倍，并采用作者能力伤害来源及对应说明；不带入未批准的旧平衡差异。
4. 八位二板开放日期修正为 2000-01-01：129998、149994、159999、149993、119970、129970、139970、149970。夏日白／火狮王指定 UI、克劳德肖像、竞速封面／横幅与两张蓝票图标同步更新。
5. 火狮王和基诺维正式语音、台词与准备音配置接入。最终使用原生播放机制，无 APK／IPA 适配交付；具体边界见下节。
6. 卡池采用作者 MOD 入池、精确概率、顺序和标红；普通角色兑换资格沿用本服。保留 215 位普通五星不可兑换与 7 位四星联动可兑换，开放水杰拉尔／秋灯九尾兑换，排除两池原核定的 26 个非扭蛋角色。竞速五位 179982–179986 为零概率且不可兑换；深渊 179981 仍零概率但可兑换。两池注意事项按最终结果重写。

## 供体参数错误：作者已复核确认

校奈芙提姆多球直击增益 DSL 的 `FindAllSubjects` 参数 8 应为 `IfTargetNotFound` 枚举，供体误写 `['Block', []]`。本包仅将该位置修正为 `['DoNothing']`；相邻 `FindMultiballSubjects` 参数 5 的合法空动作块、A4 及其他动作完全保留。

用户提供的[作者回复](author-confirmation.md)确认了同一位置、同一修正和同一原文件哈希 `04d452d5af27ab06f5fce3a034d308a9e32d87d0166364a8f94f6e822dd7f5d8`；实际来自最终包的 `assets/full68-005.zip`，已回读核对。最终资源哈希为 `66a42a466a06f2d56821f320943fa6b35a066c8df138610f7130459f4734f0a8`。

已验证原错误必然被该参数类型检查拒绝，修正候选通过；将唯一修改还原后，整棵动作树与供体相等。此处是 CDN 资源类型修正，无需改 APK。作者要求的进战斗、召唤球及球消失表现仍须设备验证，本次未冒充实测。

另两种供体 null 值经过当前客户端实际读取逻辑核实是合法值：`CreateSummonsMultiball` 参数 13 的 null 使用上下文技能等级；`MultiballNumberVariable` 参数 3 的 null 匹配全部协力球。验证器仅在类型检查副本中采用相应占位，存储脚本中的 null 原样保留。

## 原生多语音与 APK 判断更正

原先把作者特定编号筛选和额外准备音轮换当作必需的 APK 依赖，判断范围过大。现已使用已登记、未改动的本服 SWF 中 `CharacterShortVoiceLogic` 方法核实：原生技能语音连续扫描 `skill_0` 起的编号，遇缺失停止，上限 512 条。

- 作者正式技能录音 `0、1、4、5、6` 在本包中对应原生 `0、1、2、3、4`；音频内容逐字节保留，只调整资源路径。
- 作者试用录音 `2、3` 未进入最终包；基线也没有 `skill_2` 至 `skill_6`，不存在旧尾部编号残留问题。原生方法实际执行验证得到五条正式录音，且断号负例、空列表和 512 上限用例通过。
- 准备音使用现有 `skill_ready` 与 `matched_skill_ready` 两条原生路径。作者的两个 `_alt_1` 文件保留为资源，但当前原生读取器不会选择它们；本次不额外实现分别轮换，也不将“保留资源”描述成“已播放全部准备音”。
- 临时生成的四方法适配源码和 APK 候选已经移至任务工作区的 `history/rejected-apk-*`，不在源码交付目录，不纳入本次发布。已验收注册表、现用 APK 和 IPA 均未被本任务替换或安装。

详细路径映射及未修改客户端的实际方法哈希见 [native-voice-verification.json](native-voice-verification.json) 和 [native-voice-mapping.json](native-voice-mapping.json)。

## 验证与存档影响

- 579 项最终资源回读、170 个存储 PNG 解码、29 份 DSL 类型及 AMF 往返通过；12 组 Android／iOS 立绘配对验证通过，iOS 编码使用 4 个工作进程。
- 658 个完整接入的供体表键逐项比对通过；1,557 个相关媒体／依赖闭合，其中 32 个由当前 APK 内置原字节满足。保留杰拉德优化图集的 37 个完全相同可见帧。
- 两张蓝票在原 505×1770 图集中替换，保留其余 1,520 个图标的像素和全部图集元数据；未覆盖自定义图标。
- 两池 476／500 条最终行通过真实服务端 accessor 和原生卡池构建器的一致性验证；44／68 个 MOD 条目的概率用有理数精确比较，两个池各 432 位普通角色兑换资格与本服前像一致。
- 四个新角色和 164 个新节点没有 ID 冲突；既有角色／节点 ID 保留，服务端真实 accessor 均可解析。没有新增数据库表、列或存档格式，V1／V2 的既有数据表示和 schemaFingerprint 规则不变；不需要存档迁移。未访问玩家数据库，也未声称做过真实存档导入或设备战斗测试。
- 使用实际 `get_path`／`version_info` 路由处理器离线验证两平台下载清单、总大小和已是 `.107` 时的空更新行为，没有监听端口。深渊时间修订标记仍为 `.106` 的原值，未改变塔或重置规则。
- 已改服务端文件的非目标键与写入前像一致；其他任务的工作保留。完整验证见 [static-verification.json](static-verification.json)、[selection-verification.json](selection-verification.json)、[installed-runtime-verification.json](installed-runtime-verification.json)、[release-verification.json](release-verification.json)。

## 输入与回退记录

原输入 `F:/灰-全68角色与配套资源-1.4.858-20260912.zip` SHA-256 为 `a3c5960500c56b8000fb117d4457ea14dceadd7354b70dd66a202036f322fe68`。作者文件仅作为内容和核对证据，没有执行其安装／发布脚本。

本地前像与中间记录位于 `F:/codex/work/author858-merge-20260913/`：`before-server/`、`before-client/`、`manifest-before-apply.json`。需要回退时只移除本任务第 2 包、恢复本任务服务端前像，并从届时的最终 manifest 中撤销本包条目；不能用旧整份 manifest 覆盖其他任务的新分包。此为回退说明，本次没有执行回退或清理运行镜像。

工具在 `tools/author858-integration/`。初始审查产物位于 `F:/codex/work/author858-review-20260912/`，为生成器的 `--review` 输入；最终可复核命令示例：

```text
python -B -X utf8 tools/author858-integration/verify.py --work F:/codex/work/author858-merge-20260913 --review F:/codex/work/author858-review-20260912 --installed
python -B -X utf8 tools/author858-integration/verify-selections.py --work F:/codex/work/author858-merge-20260913 --review F:/codex/work/author858-review-20260912 --installed
node tools/author858-integration/verify-runtime.cjs F:/codex/work/author858-merge-20260913 --installed
node tools/author858-integration/verify-release.cjs F:/codex/work/author858-merge-20260913
```
