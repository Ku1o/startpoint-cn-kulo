# Reborn 24角色48款称号：.107 → .108

最新状态：2026-09-13 已按用户要求同步本地 `.108` 并重启，实际双平台下载和存档导出检查通过，详见 [LOCAL-SYNC-20260913.md](LOCAL-SYNC-20260913.md)。尚未提交、推送或部署云服；云服仍按用户最后确认记录为 `1.4.107`，未生成云服覆盖整合包。Android／iOS 实机显示、佩戴及木桩验收待设备测试。

2026-09-13 已按用户要求接收歼灭者抽取兑换、抽卡并发性能、校园碧安卡及校园奈芙提姆G1008修复的交接，范围与当前文件核验见 [HANDOFF-20260913.md](HANDOFF-20260913.md)。交接时 `.108` 已有三个分包；后续使用实际清单，保留第3包及各组件服务端依赖。

称号实现阶段的最终复核期间，并行任务追加了 `.108` 第2分包 `pinball-1.4.107-1.4.108-2-epuration-gacha.zip`，本任务已按当时两分包清单核对两平台下载及总大小。下列16项为称号组件自身的运行文件。`report.json` 的manifest哈希记录本任务首次接入时的状态，`delivery.json` 记录当时两分包验证时点；这些历史快照不能覆盖后来追加的第3包。

## 内容与行为

- 名单内真实持有的五星角色满破4次且经验达到379988（100级）时，同时获得两款称号。
- 角色升级、单次突破及批量突破成功写入后检查资格；旧角色在成功完成一次原生单人木桩练习后补领，扫描当前存档的整个持有名单，无需这些角色上场。
- 两款“觉醒前／后”是外观版本，不分别要求觉醒或玛纳板。失败、未知Practice、非Practice或多人结算不补领；读取称号列表不发奖。
- 复用 `grantPlayerDegreeSync`，保留获取时间、防止重复发放，成对发奖由事务保护。不自动改变正在佩戴的称号。

## 接入与存档

原包只引用作者工程的 `ensurePlayerDegreesTableSync`，没有包含定义；其发奖SQL也没有填写本服必需的 `acquired_at`。本次沿用既有建表与发奖接口，添加24角色固定清单、严格启用配置及48条服务端称号定义，并接入 `content-master.degreeDefinitions`。既有角色、活动、赞助及榜单称号保持原样。

没有新增数据库表、字段或迁移，不改变存档schema及指纹。V2继续携带 `players_degrees` 的全部持有记录和获取时间；V1沿用原有部分存档语义，佩戴称号与角色培养数据保留，名单内满足条件的其余称号可在导入后通过木桩补齐。绑定及未绑定目标、账号归属、导入前自动回滚备份、非法指纹拒绝均已通过实际存档上传下载路由验证。

## 资源与交付

只有 `master/degree/degree.orderedmap` 和48张 common PNG进入新分包，共49个资源。现有1497条称号压缩行逐字节保留，新表1545条；24角色CID和code均与当前服务端合并数据及有效客户端母表相符。图片按原生小写PNG签名编码，解码还原作者原图；共用背景及 `item/etc/degree` 的预加载图集依赖已核验。Android与iOS共用这些common资源，无需生成平台ATF，也没有APK或IPA改动。

文件：`assets/asset-patch/active/pinball-1.4.107-1.4.108-1-reborn-character-degrees.zip`。

大小：1,827,598 字节。SHA-256：`99175068d87d22887b48cce0f06d61a9235c66f2c552bbdacccb6374a8dc0d10`。

源项目配置 `assets/character_degree_rewards.json` 已设为启用。后续交付须让下列16个运行文件属于同一版本，先提供资源ZIP与manifest，再启动包含新逻辑的服务；回退时先关闭该配置，关闭不会删除已经获得的称号。既有三个 `.107` 分包不变。若后续要求云服覆盖包，应原样包含新ZIP，外层不加入 `production/` 散资源。完整文件大小和哈希见 `delivery.json`。

- `src/lib/character-degree-catalog.ts`
- `src/lib/character-degree-rewards.ts`
- `src/lib/character.ts`
- `src/lib/content-master.ts`
- `src/lib/mission/battle-dimensions.ts`
- `src/routes/api/character.ts`
- `out/lib/character-degree-catalog.js`
- `out/lib/character-degree-rewards.js`
- `out/lib/character.js`
- `out/lib/content-master.js`
- `out/lib/mission/battle-dimensions.js`
- `out/routes/api/character.js`
- `assets/degree_character_mod.json`
- `assets/character_degree_rewards.json`
- `assets/asset-patch/manifest.json`
- `assets/asset-patch/active/pinball-1.4.107-1.4.108-1-reborn-character-degrees.zip`

两个新增的 `out/lib/character-degree-*.js` 受仓库现有忽略规则影响，后续提交及交付时须按上面的精确路径显式纳入，不能只依赖普通 `git status` 的未跟踪文件清单。

## 验证记录

- `npm run typecheck` 通过。
- 使用本轮源码副本完成 `npm run build`，仅将六个对应JS写回源码仓库；逐字节匹配隔离构建，未覆盖其他任务的构建产物。
- `tests/character-degree-rewards.test.cjs`：14项，包含漏填获取时间的失败回放、发奖、触发点、重复、事务回滚、佩戴及V1/V2存档上传下载。
- 活动称号、赞助称号、称号统计及空更新既有回归：28项。
- `tests/character-degree-assets.test.cjs`：2项，覆盖Android/iOS各三种资源档位的 `.107 → .108` 响应、实际文件下载及哈希，并验证 `.108` 无更新。
- `tools/character-degrees/test_resources.py`：7项，覆盖全部原有压缩行保留、幂等合并、ID/排序冲突、分类与CSV拒绝、48图严格编码和新分包边界。
- 最后重新读取有效 `.108` 补丁链，全部新增图片及称号母表命中新分包；202个其他任务既有文件哈希不变，待交付文档原有内容保留。

`verification.json` 为检查摘要。历史 `.cdn` 中发现的一份 `.83 → .84` iOS 自定义ZIP已记录在 `report.json`，未采用、移动或修改；基线解析只采用官方段及启用的active链。

## 来源与复现

原始输入为用户提供的 `Reborn-24角色48款铭牌补包-1.4.859-20260913.zip`，包SHA-256为 `9859248a2e71681f377e2bc5aa860a5035aaa4f97bde621efe6b70e144edf733`。作者源补丁提交为 `9e427da26c654b69b84a302371429b5f289e7708`，包中源码按其所附GPL许可交付。只复用审核过的条件、映射与美术，没有执行作者接收器或替换本服工具。作者侧 `.858 → .859` 版本不引入本服资源链。

`tools/character-degrees/build_resources.py` 在 `.107` 前置状态下使用 `--package <原ZIP> --work <独立工作目录>` 构建候选，`--apply` 才写源项目。它拒绝未知包哈希、非 `.107` 前置状态和已有冲突输出。稀疏前后像与构建日志位于本轮工作目录：

`F:\codex\work\reborn-degrees-1.4.108-20260913-153326`。

## 24角色清单

| CID | 角色 | 第一款称号 | 第二款称号 |
| --- | --- | --- | --- |
| 119989 | 碧安卡 | 绯焰召唤学讲师 | 幼龙点名 |
| 119996 | 玛格诺斯 | 灼原的狮王 | 灼原咆哮 |
| 119997 | 夏可缇 | 焚身之誓 | 血祭·爆炎 |
| 129952 | 贝尔赛蒂亚 | 碧海淑女 | 碧潮之爪 |
| 129992 | 杰拉尔 | 纯白誓约的骑士 | 誓约之枪 |
| 129997 | 克劳斯 | 碧牙的狩夜者 | 蚀刃终决 |
| 129999 | 赛瑞斯 | 苍海龙王 | 龙王显现 |
| 139995 | 稻穗 | 秋灯九尾 | 秋灯缭乱 |
| 139997 | 莉莉丝 | 雷雨的夏日公主 | 环刃变生 |
| 139998 | 拉姆斯 | 鸣彻碧海的雷龙 | 碧海雷潮 |
| 139999 | 史黛拉（夏日） | 夏日女神 | 海滩的守望之光 |
| 149988 | 盾牌座 | 庆典星盾 | 青苔的爱 |
| 149989 | 希尔媞 | 定格星风的剑圣 | 十字双空牙 |
| 149990 | 白 | 盛夏白虎兽人 | 盛夏咆哮 |
| 149995 | 希耶提 | 十天众之首 | 十万剑 |
| 149996 | 希尔媞 | 苍蓝疾光 | 疾影·瞬闪 |
| 149997 | 墨斯伊克 | 游历世界的羽龙 | 庇佑之风 |
| 149999 | 杰拉德 | 白狼骑士 | 月耀一闪 |
| 169989 | 奈芙提姆 | 午后珍珠星光 | 甜蜜续杯 |
| 169996 | 西蒙 | 愿望的牧羊人 | 众生之愿 |
| 169997 | 巴萨拉卡 | 不死大镰 | 失落传说 |
| 169998 | 拉芙 | NY★绯樱夜宴 | 绯樱唱诗班 |
| 169999 | 基诺维 | 破契的黑鸦 | 掠影协奏 |
| 179999 | 罗尔夫 | 雪夜里的炉火 | 炉心颂歌 |
