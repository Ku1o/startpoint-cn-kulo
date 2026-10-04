# StarPoint CN 客户端修改方法

## Android 当前入口

**开始 APK/SWF 工作先读 [ANDROID-BASELINE.md](./ANDROID-BASELINE.md)，再运行 [基线检查器](./verify_android_baseline.py)。**
最新已验收公网和内网包的路径、APK/SWF 哈希、UUID 与验收依据统一登记在
[android-accepted.json](./android-accepted.json)。2026-09-09 应用户要求完成离线验收后，当前基线为深渊续战 Lens 公网/内网累计成品；验收范围见 [验收记录](./ACCEPTANCE-ABYSS-AUTOSTART-20260909.md)，不等同于真机测试。

本会话新增的关注按钮、本人资料路由、标题 `CNtips_b` 隐藏及环境切换流程见
[rush-leaderboard/TITLE-CNTIPS.md](./rush-leaderboard/TITLE-CNTIPS.md)。
新增 Lens 724/422 能力、稻穗/基诺维、五重地图及手动 Auto 锁、5900101 铁钢限制见
[Lens 累计方法](./lens0907-0908/README.md)。深渊续战跨关阵容复用见 [续战方法](./abyss-autostart/README.md)。新修改从当前续战累计成品继续；原 Lens v3、9 月 6 日标题包及下文各专题旧包仅描述历史实现，不能覆盖当前登记。

累计保留免登录与私服地址、MOD 五合一、幻想连战路由/战斗/结算/图标修复、角色轮播优化、
通用排行榜和资料导航、标题与游戏内数据继承入口、深渊装备限制，以及最新资料页和标题修复。
Git 保存方法和身份记录，APK 保存在本机 `outputs`；IPA 独立管理。

## 最早的免登录和重定向流程（历史起点）

以下两处改动只说明从官方客户端接入私服的最初流程，不是当前累计 APK 的完整修改内容。

## 前置要求(自备,均不随本目录分发)

- FFDec 24.0.1(SWF 反编译 / 回封)
- 一份官方 CN 客户端 APK(源)
- 一个签名 keystore(重打包后签名)
- Android build-tools(`zipalign` / `apksigner`)

## 两处改动

1. **免登录** — `pinball/config/core/DevConfig.as`
   - `public static var sdkDummy:Boolean = false;`
   - → `public static var sdkDummy:Boolean = true;`
   - 效果:跳过雷霆 SDK 登录,使用假 userId;支付 / 推送 / 实名等真实 SDK 功能变 stub。
2. **重定向到本服** — `pinball/config/gbits/DevConfig_gf_android.as`
   - 域名 `shijtswygamegf.leiting.com` → `<你的服务器 host:port>`(如 `192.168.1.10:8001`)
   - 协议 `"https"` → `"http"`

## 应用步骤(手动)

1. 用 FFDec 把源 APK 内的主 SWF 反编译 / 导出为 AS3 脚本目录(记为 `EXPORT_DIR`)。
2. 运行 `bash apply.sh <EXPORT_DIR> <host:port>`(或按上文手动改两文件)。
3. 用 FFDec 把改后的 AS3 导回 SWF,替换进 APK,`zipalign` + `apksigner` 重签名。
4. 安装到设备。

## 说明

完整的自动化流水线(FFDec 导出 / 导入 / 打包 / 签名)是作者基于 [starview](https://github.com/duosii/starview)(GPL-3.0)的本地扩展,未随本仓库分发。本节仅描述最初的最小补丁；后续累计构建器见各专题目录;`apply.sh` 为原创实现,不含 starview 代码。

V51 客户端的数据继承逻辑仍然存在，只缺少正常可见的入口。原理与人工核对说明见
[V51 客户端恢复游戏内“数据继承”入口](../docs/client-takeover-entry.md)；Android 累计基线、两个
P-code 方法体和带血统门禁的构建器见 [Android 账号继承入口补丁](./account-takeover/README.md)。
完整类导入只能制作临时 carrier，不能直接作为发版 SWF。

## iOS 1.8.4

**当前累计基线见 [ios-accepted.json](./ios-accepted.json)，后续 IPA 修改先运行 [iOS 基线检查器](./verify_ios_baseline.py)。**
2026-09-09 应用户要求，深渊续战 Lens 累计 IPA 已完成离线验收并登记为当前基线，仍为 unsigned；本次没有安装或真机测试。
它保留 Lens 的全部 33 个原生方法、此前资料页修复及 iOS 标题 `CNtips_b` 原有行为，新增一个续战方法。
具体方法见 [iOS 深渊续战](./ios-abyss-autostart/README.md)，范围见 [验收记录](./ACCEPTANCE-ABYSS-AUTOSTART-20260909.md)。
原 [iOS Lens](./ios-lens0907-0908/README.md)、9 月 8 日 [资料页关注与本人路由包](./ios-profile-follow/README.md)
及诊断包都是历史版本，不替代当前登记。

已经通过真机回归的 iOS 五合一、数据继承、幻想连战及幻想魂珠纹理修复流程见
[iOS 1.8.4 私服客户端补丁](./ios-five-in-one/README.md)。幻想魂珠补丁的独立设计与维护实现见
[iOS 幻想魂珠异步贴图补丁](./ios-fantasy-soul/README.md)。已经完成用户确认真机验收的
`MemberView.draw` v6 绘制保护、精确成品哈希、构建号、UUID 及失败版本演进记录见
[iOS MemberView.draw 稳定保护](./ios-memberview-draw-safe/README.md)。仓库仅保存哈希锁定的
差分构建器，不保存原始或修改后的 IPA，也不保存任何签名材料。

2026-09-07 用户真机验收的上一版累计 IPA 在 Rush 排行榜 v3 和 `MemberView.draw` v6 基础上，
补齐了深渊装备的 Multi / BothBoss `1099001..1099003` 与直接装备强化等级 `>=120` 例外。
精确输入/输出哈希、AOT 门控规则及可复现构建方法见
[iOS 深渊装备门控补丁](./ios-abyss-equipment/README.md)。

2026-09-08 用户真机验收的上一阶段累计 IPA 加入 Rush 排行榜 r12b 导航：分页按钮可以正常
加载后续排名，点击玩家卡片会打开对应玩家资料，且整张卡片的正常可见区域都可触发。
精确血统、AOT 方法范围和哈希锁定差分见
[iOS Rush 排行榜翻页与玩家资料导航](./ios-rush-leaderboard/README.md)。

### iOS AOT 体积与累计构建经验

2026-09-27 对多个 1.8.4 iOS 成品的包结构复核表明，IPA 体积增长主要来自累计 AOT 原生代码段，
不是重复嵌入 IPA 或 CDN 文件。IPA 成员数保持 3568 个，非原生程序和主 SWF 的压缩内容基本稳定；
9 月 15 日准入版约 143.6 MiB，9 月 25 日作者版约 153.5 MiB，9 月 27 日八岐大蛇版约 155.4 MiB。
对应的原生程序从约 159.4 MiB 增至 198.7 MiB。`__CNRECIO` 在作者版首次出现约 31.5 MB，
八岐大蛇累计功能又增加约 6.37 MB；这是新增 AOT 方法、常量和关联表的代码容量，不能按未使用资源直接删除。

后续 iOS 修改按影响范围选择方式：

- 小范围条件、常量和跳转修复，优先在已验证的原生入口做原地补丁，避免新增 AOT 段；同时更新完整 ABC 与
  SWF AOT 身份，保留运行时 ABC、方法表、重定位和签名布局。
- 新机制需要新增方法时，先合并同批变更再进行一次增量 AOT 链接，避免每个小功能都扩展一次原生段。
- 经过多个功能批次后，只有在完整 ABC、方法表、入口和重定位都能从规范输入重建时，才做一次完整 AOT
  压缩重建。不能直接截断 `__CNRECIO`，也不能把历史失败候选的空间当成可回收容量。
- 每次构建记录 IPA、原生程序、主 SWF、AOT 方法数和各 `__CN*` 段大小；单独报告包下载体积与设备解包后的
  原生程序体积。IPA 变大首先影响下载、安装临时空间、重签和 dyld 加载处理，不能仅凭文件变大推断战斗性能下降。

本次启动下载修复验证了小补丁路径：原生程序只修改两个 `applyLoad` 条件分支，修复包相对上一验收包仅增加
14 字节。相关补丁的边界和签名布局检查见 [iOS 启动 CDN 下载门控](./ios-startup-download/README.md)。

### iOS 踩坑索引

下面是跨专题构建时必须先检查的失败模式；各专题文档保留了对应的字节证据、构建器和验证命令。

- **SWF、运行时 ABC 和 AOT 不是同一层。** iOS 主要逻辑由 AOT 原生代码执行，不能只改 SWF 或只替换 stripped runtime ABC。完整 ABC、方法表、常量池、activation、AOT 身份和主 SWF 必须保持同一条血统；方法 ID 也不能当作 ABC body 索引。
- **先锁定真实基线，再做增量。** 每次从 `ios-accepted.json` 指向的实际 IPA、原生程序、主 SWF 和完整 ABC 开始并校验哈希。旧版或失败候选不能因为文件名更接近目标功能就当作基线；否则会把已经验收的 Boss、登录或战斗修复覆盖掉。
- **AIR arm64 的字段布局不能凭 AS3 字段顺序猜。** 在已有类中插入 32 位字段会移动后续引用槽，旧 AOT 初始化仍按原偏移取值，最终可能表现为进场 93% 的 F1009。需要保留旧引用偏移，把新状态放在尾部并按整数读取；Android 通过不代表 iOS ABI 也安全。详见 [HUD F1009 R4](./ios-cumulative-login/HUD-F1009-FIX-R4-20260911.md)。
- **既有类的静态槽同样不能追加字段。** 类对象（`static var/const`）槽偏移也会烘焙进已链接的 AOT 代码，新增一个 `Boolean` 静态字段就会把引用槽整体后移。2026-10-04 缓存清理批把 `periodicStarted`/`periodicTimer` 加到 `cn.mod::AuthorState`，`gauge` 偏移 0x30→0x38，进入副本时 `getGauge` 读到未初始化的新字段并抛 F1009；修复改为新增独立类 `cn.mod::CacheCleanupState`，既有类 trait 逐字节不变。新增运行状态一律放进新类；确需给既有类加字段时必须重编译所有绑定该类槽的方法，并保留 `compile_port.py` 的访问器偏移门槛。详见 [类静态槽 F1009](./IOS-STATIC-SLOT-F1009-20261004.md)。
- **TrollStore 重签会重新计算 LINKEDIT 边界。** 新增 rebase/bind/export 数据不能放在符号字符串表之后，也不能把签名块当作普通尾部空间；要让加载元数据位于 `align16(stroff + strsize)` 之前，并把签名放在最后。否则未重签静态检查可能通过，巨魔重签后仍会出现 `unknown rebase opcode 0xF0`。详见 [TrollStore R2](./ios-cumulative-login/TROLLSTORE-FIX-R2-20260911.md)。
- **公网地址要查初始化时序。** 只搜索 IPA 中是否出现公网 IP 不足以证明登录可用；登录面板可能在版本查询完成前缓存原生构造器里的官网地址。必须检查实际构造器、版本查询和缓存 origin 的先后关系。详见 [公网地址修正 R3](./ios-cumulative-login/PUBLIC-ENDPOINT-FIX-R3-20260911.md)。
- **首次启动下载要以本地资源状态为准。** 新安装在服务端仍有教程进度时，不能用教程状态替代本地 CDN 状态。最新验收包曾在全新安装、同一云服和同一存档下跳过“全部下载/部分下载”直接进教程；根因在 `GlobalLoading.applyLoad` 的两个 `needsDownloadAsset()` 条件门控，而不是用户没有下载或稻穗资源缺失。修复只放开 CDN 入口的两个分支，保留 `isDownloaded`、`isAssetComplete`、完整包、分段下载、断点恢复和非 CDN 路径；不能全局重写 `needsDownloadAsset()`，也不能把通用稻穗预加载限制到八岐大蛇。详见 [启动 CDN 下载门控](./ios-startup-download/README.md)。
- **C8102、F2007 和闪退要先按层分类。** 先固定 IPA 哈希、设备签名方式、发生阶段和同一时刻的服务端日志，再区分启动下载门控、AOT/ABI、服务端错误码和 dyld 封装问题。不能因为错误出现在教程或战斗加载界面，就直接归因于 CDN、稻穗预加载或签名工具；也不能把静态验证当作巨魔真机验收。八岐大蛇成品的离线范围和血统见 [Boss 验收记录](./ACCEPTANCE-OROCHI-BOSS-20260926.md)。
- **验收边界要单独记录。** unsigned IPA 的 AOT、Mach-O、ZIP、签名替换模型和方法数量检查，只能证明结构满足预期；全能签/巨魔的干净安装、覆盖安装、首次 CDN 下载、断点恢复、教程和目标副本仍需设备实测。成品、失败候选、准入密钥和工作区临时物不能混入 Git。

## Android 角色页性能

经过实机验证的当前编队轮播更新裁剪、单方法体 P-code 移植、AIR
`uniqueappversionid` 缓存失效和 APK 回封要求，见
[Android 角色编队轮播优化](./character-carousel/README.md)。该 APK 是当时排行榜补丁的历史输入；当前新增修改应从本页顶部登记的成品继续，并为每个不同 SWF 生成新的
`uniqueappversionid`。

## Android Rush 连战排行榜

复用官方 Rush 排行榜界面，通过一套服务端驱动协议读取活动名称、开放状态、排行、本人定位与
奖励字段。深渊连战和后续幻想连战共用客户端实现；新活动只需服务端登记，不再修改 SWF。
客户端按 15 个既有方法体从上述角色轮播成品 APK 移植，详见
[Android Rush 连战排行榜客户端补丁](./rush-leaderboard/README.md)。完整类导入只允许作为临时 carrier，
不得直接回封发版。

当时使用的通用 Rush 历史成品（APK SHA-256
`07C316413E4E3F99DFF83C52A5000F03ECBD466E76D5BC9F29FCD0884072DE09`）。修改流程固定为：本地构建
并产生新 UUID → 静态/方法体/签名校验 → 交给用户覆盖安装和真机测试 → 用户验收后再更新权威基线并
提交。失败候选不得成为下一次基线，也不得进入 Git。

账号继承入口先从本节的已验收局域网 Rush 成品制作和真机验证，详见
[Android 账号继承入口补丁](./account-takeover/README.md)。标题菜单必须修改实际显示列表，把第四格
“下载设定”替换为“数据继承”，不能只调整 `TitleMenuDialog.prepare` 的逻辑顺序。当时已验收的公网 APK
SHA-256 为 `0C7BBA3D8E2EF07B8AC9E98B11AAF257008A0B373950FD98332047C727064857`，内嵌 SWF
SHA-256 为 `7EEA1972F568E31CE5B708E057EB7FEF306E2B25BA5CF7C6A198557914623CA7`；该成品如今仅为后继重建链中的历史输入。累计构建器还会回查 V51
`EB7962184DF5E7D1DA112E4BEF9DED8DB8526E14A6F6F1710E051063A8F1D17C` 血统，保护其中的
MOD 五合一（免登录、重定向、深渊装备门控、赛瑞斯双形态、逐角色缩放）和幻想连战客户端改动，
再检查轮播、排行榜、继承与公网地址，任一层缺失都会失败。
