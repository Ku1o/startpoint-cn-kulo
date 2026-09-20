# iOS 幻想连战结算后返回修复

状态：2026-09-16 登记为 `user_accepted`，见 [验收记录](../ACCEPTANCE-IOS-FANTASY-RETURN-20260916.md)。基于公网本地账号记录恢复版，保留校验号 `ios-184-admission-20260915`。离线验证通过，未登记逐功能设备测试明细；Codex 未进行真机测试。后续 iOS 修改从注册表指定的本修复版继续。

## 原因及行为

战斗退出会清空场景返回记录。幻想连战三个多人节点（300098001、300098002、300098003）的既有结算/房间返回包装器调用专用 `routeToFantasyRush`，而该入口调用 `LogicScene.changeSceneSimply`，其 `NotChange` 行为不会重新建立返回记录。之后点击返回时，`LogicScene.backChangeScene` 因返回目标不存在抛出 C2120；同次异常后触摸派发又报告 G1002。

修复保留既有 `RushEventQuestSelect(700098, 1)` 目标及黑屏切换动画，将该专用入口改为：

```actionscript
changeSceneWithDetail(
    ChangeSceneNextKind.Transition(transition),
    ChangeSceneBackKind.FromHome([SceneKind.EventTop, SceneKind.RushEventTop(700098)])
);
```

返回记录因此重建为 Title、Home、EventTop、RushEventTop(700098)。现有结果页包装器和退出房间包装器共用这个修复；其他关卡保留原调用路径。房间解散与网络回调未改。

## 二进制范围

- 精确输入 IPA SHA-256：`90d6757bc45c8562926f7ea53b0455c219b9867bf91cbab4314237cab4ffb3f6`。
- 使用已有方法 31064 的签名和常量池编译一个私有辅助函数，只提取其 468 字节 ARM64 代码。编译专用 ABC 和脚本初始化代码不写入成品。
- 新函数放入 `__CNCACHE` 既有零填充区；只修改一处专用 BL、该区节长度和新函数区域。全局方法表入口不变。
- IPA 的 3568 个成员中只改变主可执行文件。SWF、运行时 ABC、101287 个方法表项、类布局、资源、登录准入协议及公网地址保持原样。
- 不改变存档结构、持久化标识、数据库或存档导入导出，不需要服务器更新。

## 构建与验证

脚本使用本机现有 AIR SDK、ABC 工具链、LIEF、ARM64 汇编工具及 Unicorn；具体位置由 `common.py` 和 `test_native.py` 列明。历史复现输入固定在 `source-artifact.json`，并以精确哈希限制构建版本，避免基线登记推进后重复应用补丁。后续新修改仍从 `client-patch/ios-accepted.json` 选择已验收成品。

从仓库根目录执行；重建时通过 `STARPOINT_IOS_FANTASY_RETURN_WORK` 与 `STARPOINT_IOS_FANTASY_RETURN_OUT` 指定两个新的任务目录，脚本拒绝覆盖既有构建目录和交付目录。

```powershell
python -B -X utf8 client-patch/ios-fantasy-return/prepare.py
python -B -X utf8 client-patch/ios-fantasy-return/compile.py
python -B -X utf8 client-patch/ios-fantasy-return/build.py
python -B -X utf8 client-patch/ios-fantasy-return/verify.py
python -B -X utf8 client-patch/ios-fantasy-return/test_native.py
```

验证结果：ZIP CRC、全部成员差异范围、六处链接重定位、Mach-O 签名布局和三个 ldid 签名替换模型均通过。ARM64 回归执行成品中的包装器和新增函数，覆盖 25 个场景：三个节点的结算/重试与冷/热定义缓存、旧包空返回记录负对照、八个普通关卡对照、三个房间退出及普通房间回退。测试同时检查栈、保留寄存器与 AIR MethodFrame 恢复。

ARM64 测试中的 AIR 运行时调用由模型提供；这不是 iPhone 完整客户端执行。实际安装、联网结算和页面触摸仍需真机复测。成品为 unsigned IPA，沿用既有 TrollStore 安装方式。

## 交付身份

输出目录：`outputs/ios-fantasy-return-fix-20260916-r2/`。

文件：`StarPoint-iOS-1.8.4-fantasy-return-fix-20260916-unsigned.ipa`。

SHA-256：`f1d9f41f0b9c16ec79efa5664833fe5dea13038bc844a25f22dbafda367316dc`。

配套 `build-report.json` 记录构建时状态；`verification-report.json`、`native-tests.json` 记录完成的验证。验收重点是第 5、10、15 层多人节点结算后返回列表、退出房间，再返回活动入口及主城，确认没有 C2120/G1002。保留旧包便于回退。
