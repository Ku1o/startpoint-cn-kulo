# 觉醒任务回调即时刷新：本地候选

2026-09-13 后续：该客户端回调已随商店优化 LAN／公网 APK 累计交付，并按用户授权纳入 Android 提交，
见 [商店优化验收记录](../ACCEPTANCE-SHOP-FIRST-OPEN-20260913.md)。LAN 商店效果已有用户反馈，
不据此推断觉醒逐项真机回归已完成。以下保留最初 SWF 候选记录；服务端修改仍单独待交付。

2026-09-12：已完成本地服务端优化、Android SWF 定点修改和离线验证。尚未回封 APK、移植 IPA、安装测试、更新验收注册表或部署服务端。候选不是已验收客户端。

当前已验收 Android 在 `CharacterAwakeScene.preparation()` 缓存角色对象及一板觉醒等级。公共响应先更新玩家保存模型，然后执行任务回调；更新会替换 `mana_board_awake` map，旧 `OwnedCharacterLogic` 仍持有旧引用。原回调只保存任务进度并 reload，所以四项任务可显示完成，而标签继续禁用。退出再进入会重建角色对象，因而恢复。

`patch_swf.py` 只在当前主 ABC 的方法体 `290:67327`（`applyMissionProgress`）插入以下动作：

1. 从 player 重新取得角色，并读取一板权威觉醒等级。
2. 等级大于 0 时移除 `disabledTabButtons` 中的标签 2，并调用 `enableOnlyActiveTab(currentTabKind)` 更新按钮状态。
3. 保留原 reload 和当前页签。任务不满足时仍锁定，无额外网络请求或每帧检查。

角色对象、等级和标签必须一起刷新；仅对旧角色再调用 getter 或仅点亮按钮都不足够，后续觉醒请求还依赖该等级。

输入严格限定为 2026-09-12 纪录保持者昵称版的已验收注册表载荷：公网 SWF `0bbe58fab5f51b16220b11f9ffefece899854749ce3287a9c264ba67d4941eae`，LAN SWF `c5fcc853a10db415fc898d24ac940dc59a2ee1c886e7cff9544fd6a0ba661559`。修改前须运行 `client-patch/verify_android_baseline.py --variant public` 或 `--variant lan`；注册表未来更新后，本目录只作为这个版本的精确复现入口，不可绕过哈希从旧包继续发布。

离线复现入口（从源仓根目录运行；输入应由上述 APK 提取，输出必须是不存在的任务工作区路径）：

```powershell
python client-patch/awake-page-refresh/patch_swf.py <input.swf> <candidate.swf>
python client-patch/awake-page-refresh/test_bytecode.py <input.swf> <candidate.swf>
```

本次公网候选位于 `F:/codex/work/awakening-unlock-fix-20260912/awake-page-public.swf`，SHA-256 为 `28c03d6d22ff6cf4dbb851b3a726b148908b5c50eb111579919602313e8a2cbf`。

验证包括：原始 ABC 可逐字节重序列化；插入可逆；保留常量池、方法签名、类布局及其他标签；检查分支和栈边界；用独立 JPEXS Java 比较器确认 96,535 个方法体中只改 `290:67327`；独立反编译回读新回调。`test_bytecode.py` 执行候选中的实际回调指令，对既有玩家模型做有限指令回放，复现原故障并通过 5 种状态、每种 3 次回调。它不替代 AIR 虚拟机或真机测试。

配套服务端改动位于 `src/lib/mission/`、任务路由和玛纳节点路由：同次请求复用任务快照，重复请求仍发布已持久化资格，未变化进度不重复写入，已满足全部配置资格时跳过事实扫描，节点校验只读取目标角色。`tests/character-awake-query-scope.test.js` 覆盖 8 类回归，包括 45 角色、180 项任务的全量/限定范围计算一致性；已有官方/扩展觉醒、F1009 二板发布时序和存档兼容测试通过。没有新表、列、任务/角色 ID、奖励或资源版本。

完整前后数据、查询计划及验证边界见 `F:/codex/work/awakening-unlock-fix-20260912/修复与负载验证.md`。运行服务和用户设备尚未应用本地改动，不能把服务器字段检查等同于当前页已在真机开放。

后续若获准制作 APK，必须按 Android 工作区规则从当时有效基线构建，更新 AIR `uniqueappversionid` 和原生启动缓存 build identity，核验固定证书、对齐及所有其他成员；此次没有生成可安装 APK。iOS 必须独立移植和验证，不能把 Android SWF 直接当成 IPA 修复。
