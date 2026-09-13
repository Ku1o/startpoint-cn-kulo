# Android 商店首次打开优化测试版

2026-09-13 后续：用户反馈 LAN 版起效明显，随后授权制作公网版并验收提交。
公网地址转换及离线验收已完成，最新登记见
[验收记录](../ACCEPTANCE-SHOP-FIRST-OPEN-20260913.md)。下文保留最初 LAN 候选的制作记录。
iOS 另行移植并等待用户验收，其候选不属于本次 Android 提交。

本次只调整客户端查询方式，保留商品、价格、库存、活动时间、排序、兑换规则和画面加载逻辑。
测试包同时包含本任务此前完成的 `awake-page-refresh` 觉醒任务响应回调修复。
不改变存档 ID、进度结构、数据库或导入导出协议，因此无需存档迁移；不涉及 iOS。

## 原因与改动

`ShopProductRepository.getAllProducts` 的活动商店分支以及
`existsEventItemInQuestEvent` 的冷缓存路径，原来都遍历整张活动商品表，
先逐条构造商品对象，再按活动筛选。商店首页判断是否存在兑换活动时，又先构造完整活动结果列表。
活动多时，这些调用会重复分配临时对象、数组，集中占用执行线程。

`cn.shop.ShopFirstOpen` 为主表建立一次“活动类型 + 活动 ID → 商品 ID”索引。
两处商品查询只更换输入 ID 数组，原有商品构造、过滤、时间判断和仓库缓存逻辑全部保留。
索引按主表对象隔离，底层二进制表更换后重建；只保存成员关系，不缓存玩家库存或是否开放的结果。
不同活动类型的同号 ID 不会混在一起，组内顺序沿用原始 `keys()` 顺序。

首页与常驻活动文件夹的存在性判断改为找到首个可用活动就返回。
只有箱池的活动、活动系统解锁条件、兑换期和活动道具收集入口均保留。
实际进入文件夹时仍生成完整活动列表，没有截断列表或修改贴图加载。

原始主 ABC 290 移至 291，前面插入独立辅助类。既有 96,535 个方法体中仅改变：

| 原主 ABC 方法体 | 改动 |
| --- | --- |
| 25379 | 活动商品列表改为对应活动的 ID 数组 |
| 25381 | 活动商品存在性冷缓存改为对应活动的 ID 数组 |
| 81189 | 商店首页存在性短路 |
| 72196 | 常驻活动文件夹存在性短路 |
| 67327 | 任务响应后重新取得拥有角色和觉醒状态，刷新能力页签 |

不增加客户端请求。APK 内只有游戏 SWF、manifest 的 AIR UUID、原生启动缓存的同一 UUID 发生变化，
其余成员逐字节相同；原有登录、Lens、切队、排行榜、昵称等累计补丁保留。

## 性能证据与限制

按资源链 1.4.106 的实际 8,575 件商品、157 个分组验证全部商品顺序一致。
在逐个请求这 157 个分组的查询模型中，成员匹配的整表行访问从 1,346,275 次降为一次 8,575 行索引构建；
随后按分组读取 ID。商品对象仍按需要正常构造。这是调用数量证据，不是手机耗时、CPU 使用率或帧率测量。

索引增加 O(商品数 + 分组数) 的 ID 和数组存储，目的是减少重复扫描及大量临时商品对象的创建。
不能据此断言常驻内存一定更低，也不能认定闪退已修复。首次解析主表、图片解码和列表贴图仍有开销。
如 Android 仍闪退，下一步应根据真机日志区分无响应、内存不足或其他异常，再决定是否调整可见区域加载。

## 本地验证

- 编译后的同一辅助类在桌面 AIR 中通过 698 项断言；覆盖实际分组、顺序、类型隔离、换表、空组、
  256 种开放条件组合、时限边界、重复进入、玩家切换和箱池回退。
- 原始觉醒失败状态通过实际回调指令重放复现，最终 SWF 的 5 组状态各重复 3 次通过。
- Python 精确补丁检查与独立 FFDec 解析器均确认只改变上述 5 个原方法；新增辅助类 8 个方法体。
- 5 个涉及类窄范围反编译通过；另核对实际 `MasterMapBase` 的公开访问器及活动枚举结构。
- APK 全成员回读、全 6 个原生类规范化比较、AIR 新 UUID、固定证书、v1/v2 签名及 ZIP 对齐通过。
- 桌面验证没有启动完整游戏、连接真实账号或执行实际兑换，不等同于 Android 真机验收。

## 构建入口

本目录 LAN 构建入口复现最初候选，输入须通过
`client-patch/verify_android_baseline.py --variant lan --record client-patch/accepted-history/android-record-holder-20260912.json`，
使用历史登记的 2026-09-12 昵称累计 LAN 原件；后续新功能从当前注册表继续，不能把历史输入当作最新基线。
本候选输入 APK SHA-256 为
`e04b9e4f367be0ee447f1cfc8f45ff314fafc4a2df7efcef03db120347278f32`。
地址原样保留；个人内网地址只存在忽略的本机配置和输出报告中。

所有中间文件放在新建任务工作目录，以下步骤均拒绝覆盖已有候选路径：

1. 从已验证 APK 提取 `assets/worldflipper_android_release.swf`。
2. 使用 AIR SDK `compc-cli.jar` 编译 `src/cn/shop/ShopFirstOpen.as`，包含类 `cn.shop.ShopFirstOpen`；
   参数为 `+configname=air -swf-version=44 -target-player=32.0 -debug=false`。
3. `python client-patch/shop-first-open/patch_swf.py INPUT.swf HELPER.swc CANDIDATE.swf`。
4. `python client-patch/shop-first-open/test_runtime.py --work NEW_AIR_WORK --helper HELPER.swc`。
5. `python client-patch/shop-first-open/verify_swf.py INPUT.swf CANDIDATE.swf --work NEW_VERIFY_WORK`。
6. `python client-patch/shop-first-open/build_apk.py --swf CANDIDATE.swf --runtime-checks NEW_AIR_WORK/air-results.json --swf-checks NEW_VERIFY_WORK/verification.json --work NEW_APK_WORK --out NEW_OUTPUT`。

构建器核对被测试辅助 ABC 的哈希与最终 SWF 一致，再分配新 UUID、更新两处原生构建身份、对齐并签名。
签名复用现有 DPAPI 进程内脚本，不复制或记录明文密码。未进行验收登记、提交、推送或服务端同步。
本任务此前的服务端觉醒和称号查询优化仍按原记录单独待交付，不由 APK 安装自动部署。

## 本次候选

本机成品：`outputs/shop-first-open-lan-test-20260913/StarPoint-CN-1.8.1-shop-first-open-lan-test-20260913.apk`。
同目录的 `verification.json`、`SHA256.txt` 和中文测试说明记录本次身份和验证范围。
保留原验收包供覆盖回退；候选须等待用户 Android 测试，不自动晋升基线。

## 公网转换

`build_public_apk.py` 锁定上述已测试 LAN APK 的哈希，从历史昵称注册表取得经过核验的两端地址，
只替换 Android 配置构造器唯一使用的地址常量，再分配全新 AIR UUID 并同步两处原生缓存标识。
它校验 LAN 报告、实际辅助 ABC 和对应源文件哈希；转换后还原地址可逐字节恢复原 ABC。
全部 96,543 个方法体经独立 FFDec 比对保持，6 个原生类除构建身份外保持，APK 其他成员保持。
没有重新运行桌面 AIR；复用与精确辅助 ABC 绑定的 698 项断言及用户已反馈的 LAN 测试证据。

```powershell
python -B -X utf8 client-patch/shop-first-open/build_public_apk.py --work <NEW_WORK> --out <NEW_OUTPUT>
```

本次公网成品为 `outputs/shop-first-open-public-20260913/StarPoint-CN-1.8.1-shop-first-open-public-20260913.apk`。
完整哈希、身份、验证范围与设备验收边界见独立验收记录；原构建报告保留其生成时状态。
