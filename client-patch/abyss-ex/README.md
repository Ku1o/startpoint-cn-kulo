# 深渊 EX 客户端配套

在已验收累计 Android/iOS 基线上扩展普通深渊 `700099` 与 EX `700100` 的装备与魂珠生效范围、自动连战队伍复用、关卡详情及逐层纪录入口。事件和关卡的真实编号保持独立，不把 EX 请求伪装成普通深渊。

`prepare.py --out <工作目录>` 先验证两端基线，输出 Android SWF、iOS 完整编译 ABC 和 ARM64 装备范围补丁。Android 只改变四个判断，iOS 准备三个 AOT 方法和一个原生判断；原有方法签名、闭包身份、常量索引及其他方法保持。iOS 编译元数据中的原生方法空壳不能当作功能实现，故从对应累计 Android 方法恢复所需三个函数，并检查 activation ABI。

`prepare.py` 的文件是构建输入。2026-09-17 已基于这些输入完成独立 APK 与 TrollStore unsigned IPA 候选，见 `release.json`。Android 已刷新 AIR UUID 和两个原生缓存常量，并用固定证书签名；iOS 完成三个方法的 AOT 编译、链接及等长 548 字节装备门控替换。未进行设备战斗验收，不变更 accepted registry。

正式发布执行 `release-policy.json`：两端分别写入新的准入校验号，完整服务器名单与密钥从本地受限主记录配对交付。各平台旧号的 `allowUntil` 为该平台正式切换时间加 86,400 秒。准备阶段不提前写入到期时间，不改变现有 enforce。校验号、AIR UUID 和 CDN 资源版本分别管理。

资源包属于 `1.4.109 → 1.4.110` 的第二分包；客户端安装包独立交付。启用 EX 前必须同时满足服务端、CDN 和对应客户端适配依赖。

## 构建与核验

`prepare_release.py` 从当前 accepted registry 的固定输入和已准备 EX 载荷生成本批完整 ABC，首次保留双端独立准入材料；重建复用本批材料。使用新的 `STARPOINT_EX_RELEASE_WORK` 和 `STARPOINT_EX_RELEASE_OUT` 避免覆盖现有成品。

依次运行 `prepare_release.py`、`compile_release.py --attempt compile-final`、`build_android.py`、`build_ios.py`、`verify_ios.py`。编译环境沿用本地 AIR SDK、ARM64 工具库及现有签名进程。四个类初始化方法只恢复为编译上下文，不替换运行时原生初始化函数；101,287 个方法的编号、类及 activation 布局保持。只修改三项有效方法指针，保留原重定位流；追加代码与 ABC 通过扩展已有最后可执行段容纳，不新增超过经典 dyld 索引限制的重定位段。

离线检查包含最终 ZIP 回读、Android v1/v2 签名和对齐、独立 iOS 指令解码、原生累计字节、方法指针、三个 ldid 重签模型及两个历史错误布局负例。准入测试使用实际服务器类和模拟时钟，不作为设备或云端验证。

`activate-admission.cjs <服务器根目录> [both|android|ios]` 在实际发布时开始旧号 24 小时期限；保存各平台首次启用时间，重复运行或重新覆盖配置不延长期限。完整私有配置已包含新旧名单，不需要手动合并。单纯解压配置只允许新旧并存；正式淘汰计时由启用命令开始。
