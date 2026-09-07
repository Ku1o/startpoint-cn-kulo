# 深渊换塔后的个人最佳用时

深渊连战普通塔使用 `section=24`、`quest_id=700099001..700099098`，当前为 30 层。关卡 ID 在换塔后复用，因此单靠 ID 会继承旧塔同层的最快时间。

## 生效规则

- 已发布的普通塔内容改变时，每个存档的所有普通塔关卡最佳用时变为 `NULL`，客户端显示无最佳用时。
- 首次成功通关建立新纪录，之后按最小通关用时更新。失败不建立纪录。
- 登录、重新启动服务端、普通重置重打以及无关资源更新保留同一座塔的纪录。
- 只改 `best_elapsed_time_ms` 和内部版本标记；通关状态、评价、最高分、奖励领取、角色、物品、爬塔进度均保留。原 Boss 副本、幻想连战、官方 Rush 和深渊无尽纪录不参与此次清理。
- 换塔前开始的战斗不能结算到新塔。活动战斗行持久化开始时的塔版本，登录时丢弃过期的恢复入口，迟到的结算返回更新提示。旧客户端省略 `/start` 时，仍可凭 `res_ver` 确认当前塔后补报；旧版本或缺少版本依据的补报不能写入新纪录。

## 发布与记录版本

`wf_publish.py` 从实际待发布的 `rush_event_quest.orderedmap` 提取 `700099` 普通楼层（1..98），按键排序后生成 SHA-256，并将 `quest_time_revisions["rush:700099"]` 与补丁一起原子登记到 `assets/asset-patch/manifest.json`。`wf_rogue_build.py --write --publish` 和 `wf_rogue_reroll.py --apply` 均走该发布器，无需另行操作数据库。生成失败、仅 dry-run 或尚未发布的 store 不会改变线上纪录版本。

摘要只取普通深渊楼层，排除官方活动、幻想连战和无尽行。完全相同的普通塔重新打包仍使用同一纪录版本；换 Boss、场地、楼层配置或诅咒等改变该表内容时，全塔重新记录。

如果通过其他工具合并或发布包含这张关卡表的补丁，必须用 `wf_quest_time_revision.quest_time_revisions` 对最终 ZIP 的实际成员生成并保留同名 manifest 元数据，不能直接复制旧塔摘要。纯角色或图片更新不填写该字段。运行时选择最高启用版本的塔摘要；停用新塔、回到旧塔时也清除不匹配的纪录。

当前登记的初始摘要来自实际生效的 `1.4.95 → 1.4.96` 累计包，已检查其后的启用补丁均未覆盖这张表。首次安装这项修复时，历史存档缺少版本标记，因此会先清空现有普通深渊最佳用时一次。重新登录即可读取清空后的数据，不需要重建 APK 或重摇当前塔。

## 存档与验证

初始化兼容新增 `players_quest_progress.best_time_revision` 与 `players_active_quests.quest_time_revision` 两个可空列。读取全量、部分或单关进度时修正该玩家的过期时间；不会删除进度行。存档快照沿用已有表的自动列导出机制，旧快照缺少标记时同样按未知版本清空旧时间。

回归命令：

```text
npm run build
node --test tests/abyss-best-time-revision.test.js
python -m unittest discover -s tools/fantasy-gauntlet-mod-tools/tests -p test_quest_time_revision.py -v
python -m unittest discover -s tools/fantasy-gauntlet-mod-tools/tests -p test_publish.py
```

Node 用临时数据库验证迁移、原 Boss 隔离、客户端序列化、换塔/回滚、真实结算端点与普通重打；Python 核对发布摘要及当前实际胜出的 ZIP 成员。均不修改正式数据库或 `.cdn/`。
