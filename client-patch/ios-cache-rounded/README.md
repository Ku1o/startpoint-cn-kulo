# iOS 公网空更新、安装缓存与深渊详情圆角

2026-09-12 后续登记：用户已明确验收 Android 与 iOS 并授权提交，见 [统一验收记录](../ACCEPTANCE-CACHE-PARTY-20260912.md)。下文保留开发与构建时的状态，不将原报告改写为真机逐项验收。新任务从当前登记成品接续；本目录构建器只用于其锁定历史步骤的精确复现。

2026-09-12 本地候选，接续用户已验收的 iOS R4。仅制作公网 IPA；用户明确要求继续原来的三个任务，不移植 Android 队伍轮播 F1009 修复。没有更新 iOS 验收登记。

## 成品与输入

- 交付：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-cache-rounded-public-20260912-unsigned.ipa`
- SHA-256：`11ccd92b75e00484e57d124b52a02aedc4cecfb9c0012387288fd69e58af42d9`
- 配套完整 ABC、报告和测试说明：`F:/codex/ios-artifacts/cache-rounded-public-20260912/`
- iOS R4 输入 SHA-256：`560d5787411dfa1b603a9c8f0b4fba46f045e02531256e476df5b6474d822fae`，历史来源见 `../accepted-history/ios-login-abyss-hud-r4-20260911.json`。
- Android 行为参考：原三个任务的公网 APK，SHA-256 `32006941eff3a0294e9895aafba4668c8a4691bce1459740cb46afc258492f56`，只提取 EmptyUpdate 和登录继续回调，不提取其他 Android 修改。
- 身份保持 `com.kulo.wf`、1.8.4 / 1.8.46；版本查询前的初始地址仍为 `http://175.178.160.158`，默认端口 80。

## 三项行为

1. **空更新兼容**：收到资源查询响应时，只有在非初始下载、合法资源版本相同、full/diff 全部没有 archive 的情况下，将空任务统一为 null。真实下载、版本不一致、初次安装和格式异常继续走原逻辑，不能仅凭显示“0 MB”跳过一个真实的小更新。登录继续回调仅重置 misc 状态，保留资源版本与下载设置。客户端兼容旧服务器的空任务响应，无须为这三项更新云服。
2. **安装后一次清理**：进入原 main 之前，对比本构建标识、可执行文件路径、创建/修改时间、inode 和大小。首次运行或检测到安装变化时调用 `NSURLCache.sharedURLCache removeAllCachedResponses`，随后写入独立的 UserDefaults 标记；普通重开跳过。读取元数据失败或取不到缓存对象时不写成功标记，下次启动重试。
3. **深渊详情圆角**：原按钮的宽高和颜色参数交给新的 RoundedButton helper，用 Starling Canvas/Polygon 绘制四角曲线。原位置、文字和点击回调保持不变。

清理范围是 iOS 的系统网络响应缓存；不是 Android 的 AIR SWF 解包缓存，不删除游戏文件、下载资源、账号、cookie 或 Keychain。未使用递归目录删除，也没有定时清理脚本。游戏自管的磁盘资源和内存对象不属于本清理范围。API 范围参考 [Apple NSURLCache 文档](https://developer.apple.com/documentation/foundation/urlcache/removeallcachedresponses%28%29?changes=_6)。AIR 的目录规则参见 [AIR 文件对象文档](https://airsdk.dev/docs/development/files-and-data/working-with-the-file-system/using-the-air-file-system-api/working-with-file-objects-in-air)。

同一 IPA 再次覆盖时，依靠安装导致的路径或文件元数据变化识别；若安装器保留了全部这些信息，不能保证再次触发。此项尚未在实际 TrollStore 设备验证，不能把离线模型测试写成真机验收，也不能据此声称解决所有 iOS 缓存问题。

## 原生增量与 ABI

`prepare.py` 先执行登记校验，锁定 R4 的 IPA、原生文件和完整 ABC。新辅助类增加 9 个方法，总数 101191。只链接下列三个旧方法的新实现：

| 方法 ID | 修改 |
| --- | --- |
| 51820 | 空任务归一化，然后继续原 AssetGetPathRealRemote.successHandler |
| 101083 | AbyssDetails.attach 中两个指令，将 Quad 构造改为 RoundedButton.create |
| 101091 | PlayerLogin.title 的继续回调保留资源版本/下载设置 |

保留所有旧类字段、签名、常量池前缀和 activation 布局。圆角不直接导入 Android 的整个 attach：那样可能改变旧点击闭包访问的 activation 字段位置。编译需要的外围方法仅作编译上下文，不替换其运行时实现。R4 的 HUD Number 尾部字段以及 __LENS、__ABYAUTO、__HUDSTATE 原生段保持原字节。

新增 __CNCACHE 和 __CNCTAB，链接所需方法及 AOT 表。main 与资源响应入口的包装代码保存参数和返回信息，执行扩展后恢复并继续原函数。新增 dyld rebase 流置于字符串表之前；字符串表是最后的加载元数据，签名位于文件尾，兼容已有 TrollStore/ldid 裁剪规则。

## 重现与验证

脚本需要本机已有 AIR SDK、FFDec/ABC 工具、iOS 原生辅助库、历史已登记资源与 helper 映射；不下载全量 CDN，不在 .cdn 中生成文件。默认工作区 `F:/codex/work/ios-cache-rounded-r2-20260912`，可通过 `STARPOINT_IOS_CACHE_WORK` 指定新的独立目录。准备和构建脚本拒绝覆盖已有输出。

```powershell
python -X utf8 -B client-patch/ios-cache-rounded/prepare.py
python -X utf8 -B client-patch/ios-cache-rounded/compile.py
python -X utf8 -B client-patch/ios-cache-rounded/build.py
python -X utf8 -B client-patch/ios-cache-rounded/verify.py
python -X utf8 -B client-patch/ios-cache-rounded/test_boot.py
```

最后一项使用隔离安装在工作区 `test-libs` 的 Unicorn 2.1.4，执行成品实际 ARM64 引导与入口包装字节，但 Foundation 调用由模型模拟。

已完成：编译无警告；3568 个 ZIP 成员及 CRC 核对，仅原生文件和主 SWF 改变；101179 个其他旧方法保留；291 个原生重定位；新增 92718 个 rebase；三种 ldid 签名大小模型；实际公网初始地址和 R4 字段布局。10 项执行测试通过，覆盖首次启动、普通重开、同包替换 inode、修改时间/路径/构建变化、异常重试，以及两个入口的参数、保存寄存器、栈参数和原序言。

早先两个入口测试把新栈帧的未初始化空间也要求逐字节相同而失败；已改为比较原 STP 实际写入的保存值及入参空间，寄存器比较保持不变。成品不因此重建或改动。未进行实际 iOS 重签、安装、启动或点击操作；没有用 Android 模拟器冒充 iOS 验证。

本次不修改服务器、存档结构、数据库、玩家归属或导入导出。唯一新持久值是可重建的安装清理标记，不属于游戏进度，未进行无关的玩家存档写入测试。代码留在 staging 本地，未提交推送，未同步运行镜像；保留其他任务的工作。未请求服务端整合包，因此未制作。
