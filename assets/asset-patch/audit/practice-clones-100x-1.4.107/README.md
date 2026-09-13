# 无属性高血量木人：.107 第 1 包修订

2026-09-13，按用户最终要求恢复原版练习木人，在原有两个入口各增加一关；血量为原版 100 倍，时限 10 分钟。用户明确要求 CDN 增量合并进此前生成的包，因此直接修订尚未提交、未同步的 `.107` 第 1 包，资源版本仍为 `1.4.107`。

| 入口 | 新关卡 | Practice ID | 来源 | 本体 HP | 小木人 HP | 时限 |
| --- | --- | --- | --- | ---: | ---: | --- |
| 结实假人（100） | 高血量木人·无 | 1101 | 原 97 | 100,047,977,312 | 无 | 10 分钟 |
| 结实假人们（99） | 高血量木人们·无 | 1102 | 原 87 | 100,047,977,312 | 每个 100,024,515,359，共 4 个 | 10 分钟 |

群体初始总 HP 为 **500,146,038,748**。倍率在客户端最终 `floor` 前应用；小木人的浮点乘积略低于整数，实际 `Number` 运算向下取整比十进制精确乘积少 1 HP。Python IEEE-754 与 Node `Number` 的运算回读一致，所有整数均在安全范围内。

原版 91 条关卡压缩行、原入口表均与 `.106` 逐字节一致；原版 81–87、91–97 的十倍 HP 修改已经撤回，原时限仍为 3 分钟。两个新关保留原场景、无属性、等级、攻击力、4 个小木人的生成、回血动作、解锁条件、缩略图与无奖励规则。新关排序值 8，在各自入口内按客户端降序排列显示在原七关之前，不新增入口。

三把武器的复原完整保留：4010014 木灵大剑为 3 次；2040001 无名之弓为 10 次；5040009 埃俄罗斯之弓第二条回充能力为 10 次。能力表与修订前第 1 包完全相同，目标三条能力行匹配 `.54` 官方基线。

## 交付内容

- 原路径：`assets/asset-patch/active/pinball-1.4.106-1.4.107-1-weapon-caps-practice-hp.zip`
- 修订后：**41,940 字节**、2 个共享 orderedmap 成员；SHA-256 `9527476e7df4f01460f282907a3ec6ecb1beb9b55727b4fc171cd5061b88ff50`。
- 被替代的未发布包 SHA-256：`55f99926afbd3588890505ec52a26f0b67dc13225a2b951509886d91db4f4171`。原包与修改前清单、文件保存在 `F:/codex/work/practice-colorless-100x-20260913/before/`；旧审计 `weapon-caps-practice-hp-1.4.107/` 是已被本修订替代的历史记录。
- `assets/asset-patch/manifest.json` 已更新第 1 包大小、摘要、说明及本审计入口。原 `.107` 第 2 包 SHA-256 `0bdd8b6482f516e4aa5cfc7473cefbb34a3d3ff6cde95306f0007bd9646d17ed` 保持不变，同版本仍为两包。
- **必须同时交付 `assets/practice_quest.json`**：增加 1101/1102，服务端四档评价时间为 600,000 ms；CDN 中评价时间为 600 秒、战斗时限为 36,000 帧。服务端原有 98 条配置保持。
- 无 TypeScript、数据库结构或 APK/IPA 改动。现有 `out/lib/assets.js` 直接加载项目根目录 `assets/practice_quest.json`，无需新建 `out/` 产物；后续部署加载新 JSON 时需按正常流程重启服务。

## 战斗记录与存档

当前 Android 公网基线 SHA-256 `35e0e7c777798594d68c9bcd74c507c6f0b7d065453e0425c301258c6bc38ac6`，内嵌 SWF `e60cc4a82e3b305257040dedc54d180794234e2c2d4d3cef68a105b9f8405927`。按类定点导出记录链路，未修改或启动客户端：

- `HistoryPracticeBattleRealRemote` 请求 `history/practice_battle`，按 `Number` 接收用时、总伤害与角色伤害。
- `PracticeHistoryListScene` 按接口记录的类别和关卡 ID 从关卡表取关卡，逐条生成记录，无官方 ID 白名单；按日期排序后全部加入列表。
- `BattleHistoryListAdapter` 与 `BattleHistoryDialog` 从该关卡读取名称、缩略图，详情展示总伤害、用时和角色数据。因此新编号映射到各自的新名称，不混用原版 97/87。
- 服务端现有练习记录上限仍为客户端最近 100 条，持久历史保留；新关沿用相同规则。

新增的 1101/1102 使用现有 `players_quest_progress` 和 `players_practice_battle_history`，无需新表或字段。原编号不改，V2 schemaFingerprint 不变。隔离数据库验证了原关、新关的独立进度、V2 完整战斗历史迁移，以及旧、新 V1/V2 通过真实 HTTP 下载和 multipart 导入。V1 沿用既有部分存档语义，验证其关卡进度兼容，不将其描述为完整历史存档。四次导入的自动备份均与导入前目标数据完全一致，非法 JSON、错误结构指纹均在不修改目标数据的情况下被拒绝。

## 已执行验证

```text
python -B -X utf8 tools/fantasy-gauntlet-mod-tools/revise_practice_clones_1_4_107.py --verify
node tools/practice_high_hp.test.cjs assets/asset-patch/audit/practice-clones-100x-1.4.107/server-verification.json
python -B tools/fantasy-gauntlet-mod-tools/wf_quest_time_revision.py
```

覆盖 ZIP 回读、全部原关保护、两关入口/100 倍 HP/600 秒评价/36,000 帧时限、武器不变、第 2 包不变、实际有效 CDN 链、服务端真实 accessor、两关 10 分钟结算与 SS 评价、7 分钟退出后的记录、总伤害及角色伤害、独立进度、V1/V2 及导入前备份。深渊计时修订标记保持 `b7f64b4be9d492d56419293d911d06c3bfef6d2d917275c9d01735fd086340f3`，不重置深渊纪录。

本地源码完成；分支 `staging`，开始时 HEAD `0691fef4208bb56263984fcfbc2a4dae846cc188`。未提交、推送、同步 `F:/startpoint-cn-main`、部署云服或生成云服覆盖包；保留其他任务的未提交改动。记录显示属于当前客户端静态链路核查，接口和存档测试使用隔离数据库，不代表真机画面或实战验收。
