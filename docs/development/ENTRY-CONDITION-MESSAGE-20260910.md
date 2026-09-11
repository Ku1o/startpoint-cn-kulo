# 幻想装备与魂珠出战提示：解除暂缓并合入 1.4.104

用户在 2026-09-10 明确表示“现在可以提交这个了”，解除此前“先不提交、别混入”的限制。提交前核对本地运行目录，仍显示旧提示，未同步这项文案。

按照同一会话刚确定的单版本方案，继续使用 **1.4.103 → 1.4.104**。这是 `8ae133a09e59a5430f71012aee77a7dda2a45c32` 的文案补充，不另启 1.4.105，不重打 APK，不改变服务端装备或魂珠门禁。

## 最终提示

```text
当前不满足出战条件。
请检查关卡开放状态、入场门票和队伍限制。
幻想连战专属装备及魂珠仅限幻想连战使用，
挑战其他关卡前请先卸下或更换。
```

修改 `master/string/ui_string.orderedmap` 的 `quest_start_out_of_period_error`，总计 3344 行中只有这一行变化，其余行原始压缩字节保持。Android/iOS 共用此资源。这是共用 4050 提示，因此缺门票、其他出战条件失败也会看到装备提醒；没有按拒绝原因拆分弹窗。

## 合并结果

- 当前文件：`assets/asset-patch/active/pinball-1.4.103-1.4.104-1-abyss-lens0910-entry-message-consolidated.zip`。
- SHA-256：`bfdc008bbd59056354466603bba49f63bf4c1663bd2ee84d2c5ddc7d3f139c43`。
- 40,201,420 字节，**601 个成员**。原会话合并包的 600 项逐项不变，增加这一张 UI 文案表。
- 新文案表 SHA-256：`9ca56e9fc89b868d18abaf7b839b8b84354b0c6193b55938f9ffeb57eecac62c`。
- 原文案表 SHA-256：`a901379873ae114774f79b0fb4eada438e6e962c5fbcbe3ab2eb6ba76e85593d`。
- 新旧合并包和原暂缓的单表 ZIP 都保留原字节；旧文件移至 `active/candidates/`，平铺 active 只启用新的合并包。
- 当前清单：`assets/asset-patch/manifest.json`，审计：`assets/asset-patch/audit/entry-condition-message-1.4.104-approved/`。原始构建报告保留生成时状态。

生成器 `tools/lens-integration/merge_entry_condition_message.py` 从明确的原合并清单读取资源，锁定原 600 项载荷和 UI 表前像，验证后仅输出到新的工作目录。历史 `update_entry_condition_message.py` 保留原构建步骤，不能直接在新清单上运行。

## 客户端缓存与交接

APK/SWF 身份不变，更新后的 CDN 哈希见 `client-patch/session-checkpoint-20260910.json`。原 1.4.112 测试链的 600 项内容仍保留，但新提示是本次额外加入的内容。

已缓存 1.4.104 或 1.4.112 的客户端不会因同版本换包自动下载。新安装或资源版本为 1.4.103 的客户端可直接获得新合并包；本地测试新提示需要单独刷新资源缓存。本次不操作玩家存档或缓存，不运行桌面 AIR。

本地暂缓标记已解除，工作区根 manifest 已恢复为与本提交一致的完整合并清单。另一任务的登录、后台、联机改动及历史原始审计仍保持原位。没有制作云服整合包，没有部署云服或合入 main。
