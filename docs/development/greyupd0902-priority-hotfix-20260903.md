# greyupd0902 优先修复：物品小图标与死亡使者获取途径

本次仅处理用户确认的两项问题，不改变既有玩法，不修改 APK。

## CDN：1.4.97 → 1.4.98

沿用当前链：1.4.95 → 1.4.96 整合包 → 1.4.97 资源补缺 → 1.4.98 图标配套修复。
此前 .96/.97 归档未改写；称号、2000 代币强化方案、重 roll 等已接受内容继续保留。

根因是物品表的 `thumbnailId` 和 `smallVectorIconId` 都指向作者独立 PNG 路径，
但兑换页的小图标使用同步缓存读取。资源文件存在不等于已经装入该缓存。

修复将 .97 中以下三张 20×20 原图作为同名帧加入常驻 `item/sprite_sheet`：

- 深渊代币：`item/materials/mod/abyss/abyss_coin`
- 深渊觉醒核：`item/materials/mod/abyss/abyss_core`
- 深渊王印：`item/materials/mod/abyss/abyss_seal`

仅更新 common PNG 与 atlas 两个成员。原 1514 帧的所有 RGBA 像素和 atlas 元数据保留，
图集由 505×1704 / 1514 帧扩展为 505×1726 / 1517 帧；三张新增图不缩放、不重新设计。
无需修改 item、trimmed_image 或其他主表。Android 与 iOS 的 `item/` 路径共同使用这对普通 PNG/atlas，
不走平台专属 ATF 分支。

- 新归档：`assets/asset-patch/active/pinball-1.4.97-1.4.98-1-greyupd0902-abyss-item-icon-closure.zip`
- 大小：756486 字节；2 个成员
- SHA-256：`9d286583480da7c856088a7328d4772d943c23fa9c9598b888c375b51ad0317c`
- 生成器：`tools/fantasy-gauntlet-mod-tools/build_greyupd0902_abyss_icon_closure.py`
- 静态报告：`assets/asset-patch/audit/greyupd0902-abyss-item-icon-closure-1.4.98/report.json`

客户端静态依据：`AssetGroupResolver.getCommonGroups(false)` 加入 Item 公共组，
`AssetResolver` 的 Item 分支加载 `item/sprite_sheet`，atlas 的 `n` 以完整路径注册 subtexture。
因此现有物品表路径可直接命中同步读取，不需要依赖之前访问过某个物品详情页。

## 服务端：休眠的死亡使者兑换来源

原始数据有活动 `2:59001` 的商品 `59001010`，可以用五王材料兑换死亡使者。
但当前客户端明确排除了这一未开放商品。获取途径接口遍历全量服务端商品时仍返回它，
导致客户端查询不存在的商店行（C8601）。

`src/lib/content-master.ts` 在 base + 扩展合并之后，定点过滤休眠商品 `59001010`，
同时从有效 `serverEventShops` 与 `serverEventShopIdMap` 过滤。
因此获取途径、显式活动销售列表和直接购买共用一致的关闭状态，不留下悬空映射。

`assets/event_item_shop.json`、原始 id map、死亡使者装备/强化/产魂、五王材料定义都不删除。
其他商品、称号兑换、深渊卡池及掉落概率均不变。已有死亡使者的强化和使用不受此开关影响。

构建产物：`out/lib/content-master.js`。
新增回归用例：`tests/dormant-event-shop-content.test.js`，检查有效视图只少这一个商品，
原始备用定义及所有其他商品保持原状；按用户要求未执行该用例。

## 验证与交付边界

- 根 `tsconfig.json` TypeScript 编译成功；只生成本地构建产物，没有启动服务。
- `tsconfig.cn.json` 仍引用现有缺失文件 `src/content/startup/bootstrap.ts` 和
  `src/content/sync/entry.ts`，该备用配置构建失败；未扩大范围修改此配置。
- PNG/atlas 编解码与归档字节回读完成；.96/.97 的 SHA-256 前后未变。
- 未运行测试套件、客户端 UI 或设备测试，未启动/重启服务端。
- 未提交、推送、同步运行目录或部署云服；本次没有制作云服覆盖整合包。
- 分支：`staging`；开始修复时 HEAD：`178ee61512ea9f3c58745a60758272325cc0a826`。

后续实际验收只需用户自行打开深渊连战兑换页与死亡使者“获取途径”，确认这两项错误消失。
