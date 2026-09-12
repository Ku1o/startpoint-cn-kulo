# Android / iOS 缓存、圆角与 Android 切队修复验收

2026-09-12，用户明确表示：“安卓和ios的都验收了，提交修改内容到github。然后是其余的服务端更新也提交并给我云服整合包”。据此登记已交付成品为 user_accepted，并归档本任务源码。用户整体验收与下面既有离线、MuMu 验证分开记录；没有逐环境、逐功能的用户测试清单，不补写未观察到的结果。

## 当前成品

| 平台 | 原交付位置 | APK / IPA SHA-256 |
| --- | --- | --- |
| Android 公网 | `outputs/party-carousel-f1009-public-20260912/StarPoint-CN-1.8.1-party-f1009-public-20260912.apk` | `e38ef8256a9fdabd6f834302fbde0c0fdcedf7c8972b3ed5d15b15f66d1038f1` |
| Android 内网 | `outputs/party-carousel-f1009-lan-20260912/StarPoint-CN-1.8.1-party-f1009-lan-20260912.apk` | `0636312d521aa0e075a7c1180cdc6d0e93817e02df63f488cdaf1b8b0f801a1b` |
| iOS 公网 | `F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-cache-rounded-public-20260912-unsigned.ipa` | `11ccd92b75e00484e57d124b52a02aedc4cecfb9c0012387288fd69e58af42d9` |

Android 保持 com.leiting.wf、1.8.1 和固定签名，主 ABC 288、96520 方法体；公网地址为 http://175.178.160.158:8001。iOS 保持 com.kulo.wf、1.8.4 / 1.8.46，公网初始地址 http://175.178.160.158，仍是原 unsigned IPA，使用 TrollStore。iOS 完整 ABC 在 `F:/codex/ios-artifacts/cache-rounded-public-20260912/cache-rounded-full.abc`，SHA-256 为 `d4f9e01de7272d43decfd834e1859c57baf735d8cac4bbe5ddeb5db94d020573`，101191 方法。

`android-accepted.json` / `ios-accepted.json` 保存完整身份和方法来源。上一个登记按原字节归档为 `accepted-history/android-lens0910-20260910.json` 与 `accepted-history/ios-login-abyss-hud-r4-20260911.json`。历史构建器继续锁定精确祖先，不能通过更换最新登记绕过输入哈希。本次未重编译、重签或替换 APK/IPA。

## 功能与方法

- 两平台：兼容旧服务端的空任务响应，只在资源版本相同、非首次下载、没有任何实际归档任务时归一化为空；真实小更新仍照常下载。账号切换只重置账号相关选择，保留设备下载模式和偏好。
- Android：安装变化后在 AIR 加载前清理 cache/app、cache/.AIR，一次成功后记录安装标识；普通重开跳过，保留账号、下载资源和游戏存储。
- iOS：安装变化后、原 main 之前清理一次 NSURLCache 系统响应缓存；不删除游戏文件或账号，不等同 Android 的 SWF 解包缓存。相同包覆盖依靠安装器改变路径或文件元数据识别，用户整体验收不证明所有安装器行为。
- 两平台：深渊连战详情按钮四角曲线，保留点击流程；iOS 保留原点击闭包 activation 布局与 R4 HUD 字段布局。
- 仅 Android：changeIndex 在绑定触摸和更新名称前初始化目标队伍；beginTouch 在无角色格子时安全返回。保留仅更新当前队伍的优化。用户明确不需要把此修复移植到 iOS。

方法见 [启动缓存](startup-cache/README.md)、[Android 切队](party-carousel-f1009/README.md)、[iOS 增量](ios-cache-rounded/README.md)。原始构建报告保持生成时状态；本验收记录不覆盖报告中的当时未登记、未进行设备测试等字段。

## 验证边界

本次回读两份 Android APK 和 iOS IPA，核对包身份、SWF/DEX/原生文件、AIR UUID、完整 ABC 与 AOT 标识；APK CRC、签名和对齐另行检查。新登记检查器还核对 Android DEX 身份，防止只核对 SWF 而丢失原生启动清理。旧登记通过显式 --record 继续可核验。

既有 Android 设备-1 记录包含首次覆盖、普通重开、同包再次覆盖、账号和资源保护、旧服务端空任务兼容、圆角显示与点击，以及旧包切队名称分支的对照复现和新包重复操作。没有独立复现所有 beginTouch 或多指交互分支。

iOS 既有离线记录包含 3568 个 ZIP 成员、101179 个未修改旧方法、291 个原生重定位、92718 个新增 rebase、三种 TrollStore/ldid 签名大小模型和 10 项实际 ARM64/模拟 Foundation 测试。Codex 未在 iPhone 上独立执行；本次新增的是用户明确验收记录。

## 服务端、存档与发布

本任务剩余服务端修改为 `/asset/get_path` 在没有实际任务时返回 full=null、diff=null、asset_update=false，并同步版本流程注释与对应 out 产物。五项接口兼容回归覆盖 Android/iOS、相同或较高缓存版本、首次小包、真实增量、三种下载模式与旧平台配置；npm run build 通过。

客户端和服务端均无存档结构、保存 ID、账号归属、数据库或导入导出协议变更；不要求数据迁移。没有进行真实玩家存档的破坏性测试。

服务端覆盖包从上次用户要求的 `startpoint-cn-cloud-overlay-multi-equipment-dialog-20260911-213809.zip`（c726e483）汇总，只含 src/routes/cn/asset.ts、out/routes/cn/asset.js、src/lib/version.ts、out/lib/version.js。不改资源版本，不交付 production 散资源、.cdn、数据库、私有设置、日志或客户端二进制。提交目标为 origin/staging；main 与云服部署不在本次授权范围。具体提交、CI、本地镜像同步和包哈希记录在交付侧车文档。
