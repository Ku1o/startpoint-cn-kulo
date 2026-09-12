# 下次云服整合包待合并内容

记录日期：2026-09-12。状态：**待纳入下次整合包，尚未部署云服**。

最新状态：用户已验收昵称版 Android，并恢复提交、公网 APK、云服整合包及之后的 iOS 制作。下文各项保留当时记录；最新 Android 身份以 `client-patch/ACCEPTANCE-RECORD-HOLDER-20260912.md` 为准。打包和本地同步仍不表示云服已覆盖。

用户明确说明：`startpoint-cn-cloud-overlay-empty-update-20260912-140840.zip` 还没有覆盖到云服，要求后续打包时把该包内容与本次 .106 入手方法补全一并加入。这是后续交付范围记录，本次没有要求立即重打整合包或部署。

## 1. 空资源更新响应修复（旧包尚未部署）

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

## 2. 入手方法与 gacha .105 → .106 合并版（本地完成，尚未部署）

- 必需交付路径：`assets/asset-patch/active/pinball-1.4.105-1.4.106-1-mech-item-sources.zip` 和包含该版本边的 `assets/asset-patch/manifest.json`。
- ZIP 大小：357,164 字节。
- ZIP SHA-256：`f25bccc0027d54b980462d78b792d86d015efabb568a76c207e6ba7debd3d9b2`。
- 本次内容：机兵蒸气核及菲诺梅那材料、幻想固定材料、深渊整轮奖励、星空记忆晶 28 个首次 SS 来源；共新增 152 条来源，涉及 55 种道具，保留原有 6,186 条来源。
- 当前 ZIP 另含 84 张暗龙升星卡池表，完整保留原有两项入手方法资源；不要选用历史 47,428 字节的机兵专项版或 221,787 字节的仅入手方法版。
- 记录时源码 HEAD 为 `staging@46bfeeaa`，此修复仍未提交、推送；现已随深渊纪录试用同步本地运行镜像。资源与接口离线验证已通过，手机实际跳转仍待验收。
- 详细证据：`assets/asset-patch/audit/mech-item-sources-1.4.106/README.md`。

## 3. Gacha 兑换与抽取一致性修复（与 .106 同批交付，尚未部署）

- **服务端必需文件：`assets/gacha.json`**，SHA-256：`38fe85ba87359b575e0191d1ba6623e53924e1f5dc22a9bf4c58bbacfb387e32`。该文件和第 2 项的最新 active ZIP、manifest 必须在同一整合包中交付，CDN 分包不包含服务端 JSON。
- 修正 95 个池的相关分组，消除 14 个池、268 个角色的 432 条错误兑换资格；同步属性池与节日池的成员、权重、UP／限定标记。
- 暗龙 261089 保留五星身份和原 ID，在 82 个历史池中转入五星分组，采用本池相同 UP／限定属性的五星权重；总星级概率不变。
- 432 条原失败兑换均已通过隔离数据库中的真实接口验证；586 个池的最终客户端／服务端一致性校验通过。未提交；现已随深渊纪录试用同步本地运行镜像，未部署云服。
- 生成器和回归文件为开发侧防回退内容，默认不进云服包：`tools/rebuild_gacha_from_odds.cjs`、`tools/lens-integration/export_effective_gacha.py` 等。没有服务端 TypeScript 修改，不需要额外 out 产物或数据库迁移。
- 详情：`assets/asset-patch/audit/gacha-consistency-1.4.106/README.md`。下次打包仍须保留第 1 项未部署的四个空更新修复文件。

## 4. 深渊详情全服纪录及换塔计时标记（本地试用，尚未部署）

- 2026-09-12 用户授权本地实现、同步和启动。已在本地运行，但候选未提交、未验收；不把本地试用当作云服授权。
- 服务端路径（每个 TS 均需对应 out JS）：`src/cn-server.ts`、`src/data/index.ts`、`src/data/initializers/abyss-records.ts`、`src/data/domains/abyss-records.ts`、`src/data/snapshots/player-snapshot.ts`、`src/routes/cn/abyssRecords.ts`、`src/routes/api/singleBattleQuest.ts`。
- .106 的 manifest 新增 `quest_time_revisions["rush:700099"] = b7f64b4be9d492d56419293d911d06c3bfef6d2d917275c9d01735fd086340f3`；原 357,164 字节 ZIP 哈希不变。新塔个人最佳下次读取时重置；之前混存的本期成绩也一起重置，通关/奖励状态保留。
- 新表 `abyss_floor_records` 启动时幂等创建，本服公共纪录不进 V1/V2 玩家存档。旧、新版本导入和自动备份已在隔离数据库验证；实际本地服务只读导出通过。
- 原个人最佳保持独立，详情动态纪录需要新客户端。当前只有 Android 内网候选，iOS 未移植；不把 LAN APK 放入云服覆盖包。
- 第 2、3 项已一并同步本地并核对 86 个直读资源，仍全部待部署云服。
- 详细交付、回滚、哈希和验证边界见 `client-patch/abyss-records/README.md`。用户其他未提交修改保持原状。

## 5. 死亡使者魂珠与深渊觉醒核预览（.106 第二分包，本地完成）

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

## 7. 深渊纪录保持者昵称（本地试用，等待验收后恢复发布）

- 用户已验收第 6 项安卓 APK，随后要求先追加纪录保持者昵称并本地试用，再继续提交、公网 APK、云服整合包和 iOS；当前发布流程暂停，云服仍未部署上述待交付内容。
- 第 4 项文件集中的 `src/data/domains/abyss-records.ts`、`src/routes/cn/abyssRecords.ts` 及对应两个 out JS 已更新并同步本地。整合包须选择最终包含 `holder_name` 的版本，不能用此前只返回用时的构建覆盖。
- 读取纪录原有 viewer ID 对应账户的当前公开玩家昵称；没有新增表、列或存档字段，也不改 `.106` 分包和 manifest。现有纪录直接可查询昵称。
- 昵称版安卓 LAN 候选 SHA-256：`e04b9e4f367be0ee447f1cfc8f45ff314fafc4a2df7efcef03db120347278f32`，详情见 `client-patch/abyss-record-holder/README.md`。尚待手机验收，注册表未晋升；iOS 未移植。
- 暂停前生成的 `outputs/item-source-records-public-20260912/` 公网 APK 不包含本次昵称功能；后续须用最终验收的累计版本重新生成。APK 不纳入云服覆盖 ZIP。

## 下次打包时执行

1. 在通常的新增提交范围之外，显式合并上述仍待部署的内容。不要因为空更新包已经生成、其提交早于此次增量范围，或本地镜像已有修复，就把它视为云端已部署。
2. 按打包时已授权的发布提交和已验证构建产物选择文件。四个服务端路径若后续有修改，应使用保留空更新修复的最新发布版本并重新核验，不用旧包字节回退后续改动。发布范围若尚有未提交内容，按用户当次授权处理，不因本记录擅自提交。
3. 将旧包的四个文件按仓库相对路径直接合入新云服包，不把旧云服整合包 ZIP 嵌套进去。CDN 分包则以 `assets/asset-patch/active/*.zip` 原样纳入，并核对最终 manifest、启用链、版本及哈希；需要的历史链依赖按云端基础和发布规则一起覆盖。
4. 云服外层继续排除 `production/**`、`assets/asset-patch/production/**`、`.cdn/**`、`changelog.md` 及其他既定排除项；内层 CDN ZIP 必需的 `production/` 成员完整保留。
5. 在新的文件清单和交付记录中逐项注明本清单的纳入情况、选定提交/摘要及验证结果。单纯完成打包、推送或本地同步后仍保持“云端待部署”；只有用户确认已覆盖，或另获授权后验证云端成功，才记录部署完成及证据。

此清单记录待部署范围；完成本地修复或生成分包不代表云服已部署。上述变更不改变既有角色 ID、存档格式或导入导出规则。
