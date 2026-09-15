# R10 队伍派生缓存与分批预计算

本轮落实用户选择的两项优化：修复 R9 在实际加载中的缓存命中，并把角色派生计算分散到多个事件循环。直接输入是 `outputs/party-cache-r9-public-diagnostic-fixed3-20260914/` 内的公网诊断 APK，保留其 R8、R9 F1063 回调修复和全部累计功能。已验收商店包仍由注册表校验，但不能直接替代这个包含后续诊断及优化的输入。

## 变化与边界

- 原缓存使用关卡对象身份；多次构造的等价枚举无法命中。现在比较完整枚举类型、标签及递归参数，并核对队伍数据身份、数据快照、资源容器、调试能力及能力开关。支持游戏实际使用的 `IntMap`、`StringMap` 和标量键 `Dictionary`，包括保留键。
- 同一次加载中，多 Boss 世界和 HUD 需要的同一份队伍派生结果可以复用。缓存不跨局保留；新加载、离开战斗、首个成功战斗更新都会清理。未知对象、复杂度超限、输入变化会走原计算。
- 在资源加载完成后、进入原场景构造前，按原逻辑创建任务队列。每个 16 ms Timer 回调至多计算一个主副角色组合，算完后才调用原 `gotoNextScene`。保留原五参数回调、空槽 Option 布局、队伍顺序及计算函数。取消加载会撤销队列；预计算异常会清除部分结果并回退原路径。
- 恢复/回放共斗状态走原同步路径。图集合成、显式 GC 时机、原生内存采样、原生日志 I/O、窗口焦点处理及战斗中 Gear 更新没有调整。本轮分批不等于整段场景构造都已异步化。
- 不修改服务端、CDN、角色数值、存档 ID 或导入导出结构。测试运行会正常消耗本地测试账号体力并产生战斗结算。

## 精确改动范围

`patch_swf.py` 替换已有 `cn.loading.PartyDerivedCache` ABC；主 ABC 96543 个方法体中只对以下三个方法插入生命周期调用，并验证插入可逆：

| 方法体 | 方法 | 用途 |
| --- | --- | --- |
| 76169 | LoadingSceneBase/gotoNextScene | 预计算完成后再进入原场景构造 |
| 76162 | LoadingSceneBase/startNextSceneAssetLoadWithDetail | 新加载清除旧缓存及任务 |
| 28971 | BattleScene/leaveHandler | 场景退出清理 |

已有 `LoadingTrace` 的 `firstFrame`、`mark` 两个方法分别增加首帧清理和四种缓存阶段的数值指标。其余方法、类字段布局、常量池前缀及 SWF 标签逐项校验保持。R8 的 15140/92540、R9 的 20565、切队修复 66523/66013/66481 保持字节一致。

APK 中仅 SWF、同步 AIR UUID 的 manifest/native DEX 和签名变化。21 个原生类回读规范化后仅 UUID 不同；其他所有成员保持。公网、内网都保留标题“诊断日志”和 ZIP 保存/分享。历史诊断器标识仍是 `CN-LOAD-20260913-r6`；新增统计明确带 `revision: r10`，包身份按 UUID/SWF SHA 判断。

## 2026-09-15 校验

- 45 项 AIR 运行断言通过，包括等价枚举、队伍/装备/玛纳映射变化失效、特殊容器、空槽、五参数回调、部分结果禁止命中、取消及独立 Timer 回调。
- MuMu安卓设备-1 覆盖安装最终内网包，核对固定签名、安装 APK SHA、AIR UUID。普通共斗自动续战至第 7 局；保留的第 1、7 局完整日志均为 9 次角色计算、9 批、12 次缓存命中，零未命中/回退/键绕过。
- 第 8 局由测试脚本主动停止应用以结束连续测试；导出中的该局 `last-unfinished` 和退出记录不能算作闪退。中间各局因日志轮换没有逐局完整留存。
- 五重决战共斗进入战斗，完整加载日志为 9 次计算、9 批、12 次命中；原 R9 手机样本及本轮未交付初稿为 36 次计算。不能把不同关卡、设备和资源冷热状态的总耗时直接当作性能比例。
- 五重单人进入战斗、技能与伤害显示正常后主动放弃。原诊断器只开启共斗加载会话，因此没有单人计算次数记录。
- 左右箭头与滑动切队、进入角色选择再返回正常；标题诊断入口可见，原生导出 ZIP 可读且包含 R10 统计。
- 公网包完成载荷、端点、UUID、累计方法、全部 ZIP 成员、v1/v2 签名和对齐校验，未在公网真机独立实测。手机 ANR/闪退改善仍需用户反馈；切窗口问题不在本轮范围。

最终成品位于 `outputs/loading-r10-{public,lan}-diagnostic-fixed2-20260915/`，各有 `verification.json` 和 `SHA256.txt`。交付及设备证据见 `outputs/loading-r10-review-20260915/`。较早不带 `fixed2` 的 R10 目录为未交付初稿，实际 IntMap 导致缓存绕过，不能使用。

## 复现

使用 AIR SDK 51.2.1.5 的 `compc-cli.jar` 编译 `src/cn/loading/PartyDerivedCache.as`，参数 `+configname=air -swf-version=44 -target-player=32.0 -debug=false -include-classes=cn.loading.PartyDerivedCache`，源码路径为本目录 `src`。另用 `mxmlc-cli.jar` 编译 `tests/RuntimeHarness.as`，同时加入 `src` 和 `tests/fixtures` 源码路径；输出到独立工作目录 `RuntimeHarness.swf`，用 `adl.exe tests/harness-app.xml <工作目录>` 执行，检查生成的 `runtime-tests.json`。测试夹具不会进入 APK。

从固定输入 APK 提取 `assets/worldflipper_android_release.swf` 至工作目录后执行：

```text
python client-patch/loading-preparation-r10/patch_swf.py <R9.swf> <helper.swc> <R10.swf>
python client-patch/loading-preparation-r10/build_apk.py --variant public --swf <R10.swf> --tests <runtime-tests.json> --work <全新构建目录> --out <全新交付目录>
python client-patch/loading-preparation-r10/build_apk.py --variant lan --swf <R10.swf> --tests <runtime-tests.json> --work <另一全新构建目录> --out <另一全新交付目录>
```

构建器锁定 R9 输入 APK/SWF 哈希，并调用当前已验收基线检查器。LAN 地址取已存在的本地忽略配置。每次构建生成新 UUID，同步四处原生身份及 manifest，使用既有 DPAPI 签名流程；不得复用 UUID 或绕过输入校验。签名后回读并校验全部载荷、固定证书、v1/v2 与 ZIP 对齐。

代码未提交、未推送、未登记为已验收。未同步任何文件到运行镜像，未制作云端覆盖包；仅启动既有本地服务以运行模拟器测试。
