# .109 与双端准入分类交付（2026-09-15）

用户授权“把所有内容分类一下，提交到github，同步到本地，并给我云服整合包”。本记录覆盖统一接收的作者融合、校园技能图、C2265、双端准入及Android累计优化。其他角色工具与历史联机诊断实验保留本地。

## 发布状态

- 分支 staging，运行发布提交 `7e1b2d61129843af034f977a56acce4144171249`；已推送 origin/staging。未合并 main。
- 功能提交 GitHub CI 通过：https://github.com/Ku1o/startpoint-cn-kulo/actions/runs/34980419340 。
- 本地运行目录 `F:/startpoint-cn-main`：64个运行文件全部与提交字节一致，实际更新11个，额外安装受控双端私有配对；新进程28392监听HTTP8001/TCP8003。
- 备份：`F:/startpoint-cn-main/.codex-backups/20260915-221719-integration-109-admission`；精确回执 `sync-receipt.json`。数据库、环境配置、CDN原始基线和其他本地状态保留。
- 校验保持 enforce:false，Android号 android-181-r10-20260915，iOS号 ios-184-admission-20260915，均启用且无截止日期。正式号内网APK可使用同一允许项与密钥。
- 云服覆盖包 `F:/codex/outputs/server-overlays/startpoint-cn-cloud-overlay-109-dual-admission-20260915-221719.zip`，8990786字节，SHA-256 `f7b83478222be641ee723d86727dbc2f894e238c13eca8e84da99943276b55bc`。64个根目录相对成员，已核对CRC、路径、全部成员字节及内层ZIP原字节。
- 云端基础按用户确认的.107；本包包含尚待云服覆盖的.108及本次.109。未把“生成包/提交/本地同步”记作云服已部署。
- 独立受控双端配对目录 `F:/codex/outputs/server-overlays/private-109-dual-admission-20260915-221719/`。不入Git、普通覆盖包或玩家分发；云端已有配置时用完整现有材料与merge-policy.cjs合并，保留管理员设置。

## 分类提交完整说明

```text
2b1262be968a6cae238323edca6499b21d4cdec7
feat(content): 融合作者角色平衡与三项深渊成就

合入作者最终角色平衡、技能与文本，校园希尔媞技能槽增量采用最终设定；追加三款成就称号及资源。
将累计兑换、装备强化与单人练习补领奖励接入服务端，保留既有角色字段和存档结构，通过同版第一分包交付。

0abe310cc64f0c919840d3055b1e9a4754fbcb7d
fix(assets): 调整校园三人技能展示图取景

从完整立绘重新裁切六张进化前后技能图，扩大上半身和动作的可见范围，修正原取景过近的问题。
保留透明画布与主数据几何，配套两端纹理并登记同版第三分包，保持第一分包及普通头像不变。

c0238de8cb3d5955edceb87fe1fa91581801b741
fix(assets): 修正未进化角色主页台词触发条件

将角色149988的首条主页台词设为初始可见，避免未进化时所有台词被过滤而触发C2265。
基于当前资源保留完整台词文字及其他角色行，将有效修正归入同版第二分包并保留作者与技能图分包。

c9bbb99f863a6b7182819849787bd6d84bfb0cc9
feat(server): 接入双端构建准入与会话续期

加入构建号与一次性HMAC挑战，覆盖账号、游戏HTTP和共斗TCP入口，并将临时凭证绑定账号会话。
有效活动延长同一凭证，过期后提供受限续期与重新握手恢复；支持双端独立允许项、撤销及期限，保留兼容过渡模式。

0edf95b393ac2fd03a08fd2e4383ce7c8d67d334
perf(client): 整合安卓队伍缓存与正式公网准入

保留能力计算优化、完整队伍缓存键和分批预计算，补齐加载与离场生命周期，减少重复队伍派生计算。
以累计R10制作正式公网版，移除诊断和日志导出，加入构建准入、后台续期、账号恢复及取消回调保护。

7e1b2d61129843af034f977a56acce4144171249
feat(client): 为已验收iOS累计版加入准入与恢复

从已验收的iOS商店累计版本加入独立平台准入、凭证续期和失效恢复，保留原有功能与TrollStore交付布局。
为同批iOS配置独立正式号，保留Android原号与配对，明确不移植安卓性能和队伍缓存优化。
```

## 核验

- 隔离目录使用原配置完成 npm run typecheck 和 npm run build（TS及CSS）；发布清单所有JS与该构建字节一致。源仓库现有outputs目录未纳入构建，不改用户tsconfig。
- 成就/强化/兑换21项通过；将作者分包数量断言改为按分包回执核验，避免后续同版资源扩展造成误报。
- 准入核心34、生命周期47、TCP36、构建JS生命周期47、账号登录63、配置合并12、双端正式配对37项通过。TCP长时为模拟准入时钟，非真机长时间共斗。
- 实际运行服务完成双端正式号挑战与证明、兼容旧包资源请求、.107到.109六包及当前版本无更新响应；六个实际HTTP下载包摘要匹配。没有为验证创建或改写真实玩家。
- C2265已追溯用户确认的.110成功条件修正，仅恢复149988的home_0初始可见条件，排除历史包误删的一个文字；563个其他角色行逐字节保留。
- .109第1/2/3包共6,016,383字节。第1与第3包原字节不变；第2新包SHA-256 4e0c253a1ba7e461231182e0a729faee06362c13a3877ac1dc9c7973a9c99f9a。源资源链和Android/iOS路由通过。
- 每类暂存卫生检查、已知私有配对值泄露扫描及许可证卫生回归通过。全部源改动按明确路径暂存，没有提交密钥或APK/IPA成品。

## 客户端与部署边界

- Android公网：`outputs/r10-public-release-20260915/StarPoint-CN-1.8.1-r10-public-20260915.apk`，SHA-256 afca9f44d1bea9edea7b573fa96dddd32bc304afd0bbaa4d3df6fb21d41c2a90。保留R8/R9/R10与累计功能，无诊断/日志导出。内网派生见 `client-patch/r10-public-release/LAN.md`。
- iOS：`outputs/ios-admission-public-20260915/StarPoint-iOS-1.8.4-admission-public-20260915-unsigned.ipa`，SHA-256 764a7c5183a8605f58364e786a08a59f65333403bded9918dd3b544a85112f09。来自已验收iOS累计版，只增加准入、续期及恢复，不移植Android优化；TrollStore unsigned，未真机测试。
- 新两端包须先部署配套接口、名单和私有文件；确保iOS公网80与Android8001入口均转发准入路由。未测试实际云服，未提升accepted registry，未切严格模式。
- 已是.109的客户端不会因同版本新增分包自动补拉；保留用户指定版本，不清除账号或存档。五重长时间渐慢根因仍未确认。
- 外层云包排除production散资源、.cdn、changelog.md、密钥、数据库、日志、备份、依赖与开发工具；内层production结构保持。

## 64个运行文件

- `assets/abyss_shop_degree_reward.json`（已一致）
- `assets/asset-patch/active/pinball-1.4.107-1.4.108-1-reborn-character-degrees.zip`（已一致）
- `assets/asset-patch/active/pinball-1.4.107-1.4.108-2-epuration-gacha.zip`（已一致）
- `assets/asset-patch/active/pinball-1.4.107-1.4.108-3-campus-summon-g1008.zip`（已一致）
- `assets/asset-patch/active/pinball-1.4.108-1.4.109-1-author-update-fusion.zip`（已一致）
- `assets/asset-patch/active/pinball-1.4.108-1.4.109-2-c2265-character-speech.zip`（本轮更新）
- `assets/asset-patch/active/pinball-1.4.108-1.4.109-3-campus-skill-cutin.zip`（本轮更新）
- `assets/asset-patch/manifest.json`（本轮更新）
- `assets/cdndata/character_text.json`（已一致）
- `assets/cdndata/character_text_rank_p5b.json`（已一致）
- `assets/character_degree_rewards.json`（已一致）
- `assets/degree_character_mod.json`（已一致）
- `assets/degree_exclusive.json`（已一致）
- `assets/equipment_degree_rewards.json`（已一致）
- `assets/gacha.json`（已一致）
- `assets/gacha_cnmod.json`（已一致）
- `assets/gacha_rank_p5b.json`（已一致）
- `config/client-admission.json`（本轮更新）
- `out/cn-server.js`（本轮更新）
- `out/lib/abyss-shop-degree-reward.js`（已一致）
- `out/lib/character-degree-catalog.js`（已一致）
- `out/lib/character-degree-rewards.js`（已一致）
- `out/lib/character.js`（已一致）
- `out/lib/client-admission.js`（本轮更新）
- `out/lib/content-master.js`（已一致）
- `out/lib/equipment-degree-rewards.js`（已一致）
- `out/lib/mission/battle-dimensions.js`（已一致）
- `out/lib/mission/character-queries.js`（已一致）
- `out/lib/quest/practice-battle-history.js`（已一致）
- `out/lib/route-performance.js`（已一致）
- `out/lib/seed-persistence-worker.js`（已一致）
- `out/lib/seed-persistence.js`（已一致）
- `out/lib/seed-validator.js`（已一致）
- `out/lib/settlement-performance.js`（已一致）
- `out/multi/tcp/server.js`（本轮更新）
- `out/routes/api/character.js`（已一致）
- `out/routes/api/gacha.js`（已一致）
- `out/routes/api/profile.js`（已一致）
- `out/routes/api/shop.js`（已一致）
- `out/routes/api/singleBattleQuest.js`（已一致）
- `out/routes/web_api/seeds.js`（已一致）
- `src/cn-server.ts`（本轮更新）
- `src/lib/abyss-shop-degree-reward.ts`（已一致）
- `src/lib/character-degree-catalog.ts`（已一致）
- `src/lib/character-degree-rewards.ts`（已一致）
- `src/lib/character.ts`（已一致）
- `src/lib/client-admission.ts`（本轮更新）
- `src/lib/content-master.ts`（已一致）
- `src/lib/equipment-degree-rewards.ts`（已一致）
- `src/lib/mission/battle-dimensions.ts`（已一致）
- `src/lib/mission/character-queries.ts`（已一致）
- `src/lib/quest/practice-battle-history.ts`（已一致）
- `src/lib/route-performance.ts`（已一致）
- `src/lib/seed-persistence-worker.ts`（已一致）
- `src/lib/seed-persistence.ts`（已一致）
- `src/lib/seed-validator.ts`（已一致）
- `src/lib/settlement-performance.ts`（已一致）
- `src/multi/tcp/server.ts`（本轮更新）
- `src/routes/api/character.ts`（已一致）
- `src/routes/api/gacha.ts`（已一致）
- `src/routes/api/profile.ts`（已一致）
- `src/routes/api/shop.ts`（本轮更新）
- `src/routes/api/singleBattleQuest.ts`（已一致）
- `src/routes/web_api/seeds.ts`（已一致）

完整哈希表和部署/回退说明在覆盖包同名 sidecar。此次交付无数据库表/列、账号归属、存档ID或V1/V2格式变化，无迁移。
