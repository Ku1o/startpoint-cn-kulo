# Android / iOS 深渊续战累计成品验收（2026-09-09）

用户要求：“ios和安卓都验收并提交修改内容至github”。本次回读已交付的 Android 公网、内网 APK 和 iOS IPA，完成离线包体、累计方法和基线保护检查，登记为后续开发基线。
状态为 `accepted_offline`；这条指令授权执行验收与提交，不是用户已完成真机测试的声明。本次没有重新编译、重签或安装客户端。

| 当前成品 | SHA-256 |
| --- | --- |
| Android 深渊续战 Lens 公网 | `c868534b575348dde825fcd4c88c156157174fd4444724f1141fd9aa95e32a2d` |
| Android 深渊续战 Lens 内网 | `3dd568ff64c3c099cf60d99985d706f1704a1c5666f945f8b548d8eaefa3d588` |
| iOS 1.8.4 深渊续战 Lens（unsigned） | `8e6fb8cc4de6fe1c79efaded8e4ab1159c012645bdc3a52a22e19562e0661193` |

路径、载荷哈希和应用身份以 [Android 登记](./android-accepted.json) 和 [iOS 登记](./ios-accepted.json) 为准。
文件名保留原来的 `test` / `unsigned`，避免重打包改变身份；原始构建报告保留生成时的候选状态，本记录单独描述后续离线验收。

## 修改行为与累计内容

服务端已有深渊逐关阵容解锁。双端客户端为活动 `700099` 的续战预设队伍解除跨关角色重复拦截，每关仍返回一个独立空数组。逐关选队、其他活动的原重复检查和开战条件保留；本次不需要服务端改动。

- Android 只改 `RushEventAutoStartQuestGroup.getDuplicatedCharacterIdsForEachQuest`（`284:24599`）。公网、内网分别从原 Lens v3 成品继续，使用不同的新 AIR UUID 与原固定签名证书。
- iOS 移植对应的一个原生方法 `26363`（ABC body `24810`），新段 `__ABYAUTO` 保存运行时 ABC 和函数。只更新主可执行文件与 SWF 的 AOT 身份；原 `__LENS` 段完整保留。
- 保留 Lens 724/422、基诺维冲刺解析、稻穗 PF、五重地图与手动 Auto 锁、5900101 铁钢限制，以及此前 MOD、资料页、关注、排行榜和标题行为。iOS 继续保留其原有 `CNtips_b`，没有套用 Android 标题隐藏。

方法、输入身份与复现要求见 [Android 续战](./abyss-autostart/README.md) 和 [iOS 续战](./ios-abyss-autostart/README.md)。

## 离线验收

- 回读三个最终成品的 SHA-256、嵌入载荷、应用身份；Android 核对 AIR UUID、ZIP CRC、ZIP 对齐、v1/v2 签名和固定证书。
- Android 两版各比较全部 96,404 个方法体，仅 `284:24599` 改变。独立 ABC 解析保护既有常量池、类/脚本/方法元数据、非目标异常表及 activation 和非主 SWF 标签。
- 基诺维 422 解析方法代码哈希保持 `4a035a6b48b89a8a1b3f60eb371c49dfcf8095b1fe129e7bff46730e3a81b065`，避免此前旧基线遗漏解析器导致的 C7050。目标方法回读包含 7 个指令用例：深渊 0/1/30/60 关，以及三类非深渊活动回退。
- iOS 回读全部 3,568 个 IPA 成员，独立检查 73 处重定位、方法表、ASLR rebase、加载段及全部非目标原生字节。完整 Lens 段保持，双端续战方法规范化指令一致，编译专用初始化方法未装入运行时。
- Android 3 项回归覆盖历史 Lens、当前续战与失败版的公网/内网共六份实际 APK；iOS 2 项回归确认从当前 AOT 指针读取 Lens ABC，并拒绝对当前累计成品重复套用续战步骤。

验收回执保存在 `F:/codex/work/abyss-autostart-submit-20260909/`，包含 `android-verification.json`、`ios-verification.json` 及日志。
原构建时 P-code、完整比较和载荷材料保留原工作目录；本次回读与其精确成品身份对应，没有改写原报告。

## 后续基线与历史复现

新任务必须先运行当前基线检查器，不按文件名或日期找替代包：

```powershell
python client-patch/verify_android_baseline.py --variant public
python client-patch/verify_android_baseline.py --variant lan
python client-patch/verify_ios_baseline.py
python -X utf8 -m unittest discover -s client-patch/abyss-autostart -p test_lineage.py -v
python -X utf8 -m unittest discover -s client-patch/ios-abyss-autostart -p test_runtime_pointer.py -v
```

前一阶段的离线验收见 [Lens 验收记录](./ACCEPTANCE-20260909.md)，当时身份已归档至
[Android Lens v3](./accepted-history/android-lens-v3-20260909.json) 和 [iOS Lens](./accepted-history/ios-lens-20260909.json)。
它们只用于本步骤的精确复现：Android 显式传 `--reproduce-lens-v3`，iOS 准备步骤显式传 `--reproduce-lens`；仍须通过全部输入哈希保护。默认入口拒绝对已包含续战修改的当前成品重复打补丁。

两份从旧标题包制作、遗漏 Lens 的错误续战 APK 继续登记在 `excluded_artifacts`，不得交付或作为输入。详见 [失败记录](./abyss-autostart/HISTORY-REJECTED-20260909.md)。

## 提交与验收边界

本次授权提交的是双端修改方法、检查器、回归用例、验收身份及入口文档。Git 不保存 APK/IPA/SWF、编译对象、签名凭据或本机内网配置。
本任务没有服务端运行文件变化，不需要同步运行镜像、创建备份或制作云服整合包；其他任务的资源、卡池和工具改动不属于本次提交。

离线验收不能证明设备上的覆盖安装、启动、角色详情、续战推进和整轮结算已经通过。iOS 登记对象仍是原始 unsigned IPA，需要沿用既有方式重签后安装；没有收集或登记用户重签后的文件。
