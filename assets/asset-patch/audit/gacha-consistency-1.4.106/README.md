# .106 入手方法与 gacha 一致性合并交付

2026-09-12，按用户“修一下咯，如果要生成cdn增量的话，就做到.106的分包内”的要求，本地修复完成。保留原入手方法补全，并替换同一条尚未发布的 `.105 → .106` 版本边。

## 修复内容

- 更新服务端 `assets/gacha.json` 中 95 个池的相关分组，修正此前 14 个池、268 个角色、432 条客户端允许而服务端拒绝的兑换关系。没有取消池范围、积分门槛或刻意禁兑角色的检查。
- 属性池和节日池按当前有效客户端 odds 对齐成员、权重、UP 和限定标记。修正 26 条缺失成员关系、340 条多余成员关系，以及审阅中发现的分布差异；不按角色全集猜测历史池。
- 暗龙阿鲁玛德乌斯 261089 保留原 ID、五星角色数据，在 82 个历史池关系中从四星分组移到五星分组；采用各自池中相同 UP／限定属性的五星条目权重。本次所有目标的该类权重均唯一，不需要猜测或选平均值。原有是否可兑换、UP、限定和试读标记沿用本池配置。
- 各池总体星级概率、十连保底概率、消耗、券种、期限、角色本身及所有装备池不变。深渊 `990001` 与竞速 `990002` 的既有完整配置保持不变。
- 修复 `tools/rebuild_gacha_from_odds.cjs`：默认从校验过的有效资源链读取；本池条目直接生成，不再继承其他池中第一次出现的角色记录，不再用 ID 前缀猜星级，也不在缺失节日 odds 时自行拼池。缺表会明确失败；历史 `--store` 仅允许 `--no-write` 调查。

## 交付文件

1. 服务端：`assets/gacha.json`。最终摘要见 `report.json` 的 `server_after_sha256`。
2. CDN：`assets/asset-patch/active/pinball-1.4.105-1.4.106-1-mech-item-sources.zip`。
3. CDN 清单：`assets/asset-patch/manifest.json`。

**三者需同批交付。** CDN ZIP 不包含服务端卡池 JSON，服务器的兑换判断需要更新第 1 项。以后部署时按正常流程重启服务端以重新载入卡池配置。

- ZIP 大小：**357164 字节，约 357 KB**。
- SHA-256：`f25bccc0027d54b980462d78b792d86d015efabb568a76c207e6ba7debd3d9b2`。
- 共 **86 个 Android/iOS 共用资源**：84 张 gacha odds 表，以及原 .106 的入手搜索表和道具说明表。
- 原有两项资源逐字节保留，152 条入手来源补全不受影响；没有更改 APK、IPA、SWF 或图片。
- `.105` 及以前的 active ZIP、manifest 记录均保持原样，没有写入 `.cdn`。
- 文件名沿用未发布 .106 的机兵包名以完成用户指定合并；旧 221787 字节、摘要 `8b0d3913...` 的仅入手方法版本已备份，不能再用作当前交付包。

## 验证结果

- 7 项资源回归通过：真实旧数据必须失败、82 个升星关系的权重与原标记保留、共享表不能把角色加入无关池、权重有歧义必须拒绝、兑换/成员/权重/星级破坏负例、无关配置保留、ZIP 逐成员回读。
- Node 回归共 15 项通过，包括旧深渊／竞速池完整性、生成器错误记录继承与缺表负例、实际兑换路由结算。
- 原先 432 个 HTTP 400 关系均在隔离数据库中兑换成功，每次准确扣除 250 积分；暗龙在两个暗池及两个既有合法池均成功。249 积分、池外角色、刻意禁兑角色继续拒绝并保持积分及角色状态不变。
- 原生成器断言套件以当前有效链运行通过。未调用生成器主命令覆盖整棵配置。
- 独立复用修复前审阅器，重新导出实际 `getGachaSync` 数据并读取最终有效 CDN 链，覆盖 586 池、110207 个成员关系、5752 个可兑换关系；成员、兑换标记、权重、星级分组、UP、限定及总星级概率均无残余差异。
- 最终 ZIP CRC、86 个成员与 manifest 摘要通过校验；86 个直接下载路径通过实际资源路由的 Fastify inject 检查，HTTP 200 且字节一致。没有启动监听服务。
- 手机兑换、抽卡动画及云服实际请求尚未验收；以上是源码数据、资源读取与隔离接口证据。

复查入口：

```powershell
python -B -X utf8 tools/lens-integration/test_gacha_consistency.py --work F:/codex/work/gacha-fix-20260912
node --test tests/gacha-exchange-consistency.test.cjs tests/gacha-generator-parity.test.cjs tests/abyss-gacha-effective-pool.test.js
node tools/rebuild_gacha_from_odds.test.cjs
```

生成／应用脚本为 `tools/lens-integration/repair_gacha_consistency.py`，锁定本次 221787 字节未发布 .106 的原摘要。完成替换后再次应用会拒绝，不能跳过该保护覆盖后续版本。只读有效链导出器为 `export_effective_gacha.py`。

## 存档、备份与云服状态

本次修改抽取和兑换配置，没有新增或删除角色 ID、角色主表记录、数据库表、字段或已存库存；既有角色、积分和 V1/V2 存档继续使用原有格式。不需要迁移或无关存档导入导出测试；实际兑换测试只使用隔离临时数据库。没有服务端 TypeScript 变更，因此没有新增 out 产物，也不需要服务端构建。

分支 `staging`，HEAD `46bfeeaa3feb1e080ea70dd43cc1dcaecad08876`；与本地记录的 `origin/staging` 无分歧。修改仍未提交、推送或合并 main；没有复制任何文件到 `F:/startpoint-cn-main`，没有重启或部署云服，没有制作云服覆盖整合包。其他用户已有修改保持原样。

被覆盖的源码、manifest、旧 ZIP 和已存在的散资源备份位于 `F:/codex/work/gacha-fix-20260912/backup/`；原文档备份在 `notes-backup/`，生成器原文在同工作目录的 `rebuild_gacha_from_odds.before.cjs`。`backup-files.json` 区分既有文件与本次新增散资源。稀疏输入、输出和独立最终审阅位于该工作目录内。

源仓库直接下载优先读取的 84 个散资源已经更新，仅用于本地资源一致性。下次云服整合包仍按用户规则排除外层 `production/**` 和 `assets/asset-patch/production/**`，纳入完整 active ZIP、manifest 和服务端 JSON，保持内层 ZIP 字节不变。待合并清单 `docs/development/PENDING-CLOUD-OVERLAY.md` 已更新，继续包含用户尚未覆盖云服的四项“空更新响应”修复。
