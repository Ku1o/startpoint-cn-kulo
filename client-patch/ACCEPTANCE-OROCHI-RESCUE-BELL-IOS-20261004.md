# 救援铃铛 iOS 缓存清理与超级+ 内置排版验收记录

日期：2026-10-04。平台：iOS unsigned IPA（TrollStore 安装流程）。登记状态：`accepted_offline`。

## 范围

在用户已验收的 iOS 作者装备 F1009 成品（IPA `4ce93ffe…`）上补做 Android 内网救援铃铛批次
（APK `4f62b899…`）对应的 iOS 内容：

1. 超级+ 内置排版：`Payload/worldflipper.app/asset/production/ios_bundle/dc/bcccb129122c0189c8eab004ecc4516a077f3e`
   由 466 字节官方 payload（`bf37fe2f…`）替换为 480 字节紧凑居中 payload（`f9cba755…`），
   与 Android 内置 bundle 使用同一逻辑资源。
2. iOS 等效 AIR 启动缓存清理：`cn.mod::AuthorState` 追加 5 个静态方法（启动、周期回调、清理、
   诊断写入、原生入口桥），周期 600,000 毫秒；仅允许删除 `File.cacheDirectory/app` 与
   `File.cacheDirectory/.AIR`，不触碰 `File.applicationStorageDirectory` 下的下载资源、bundle
   解包目录、账号、存档与设置；删除失败只记录不终止。启动钩子位于
   `pinball.loading.global::GlobalLoading/applyLoad` 原生入口（VA `0x105376DF8`），采用已验收
   F1009 `native_preload_wrapper` 结构：56 字节包装器保存 x0–x7/x29/x30、调用桥、恢复后补执行
   被替换首指令并跳回入口+4；桥体用 `getlex` 载入 `AuthorState` 类对象，不依赖传入接收者。
3. C8016 `InahoAbilityVisuals` 预载：已验收 iOS helper 的 `preload` 无条件加入全部 6 个 Layout
   （4 个稻穗 + 2 个通用），已覆盖嵌套索引 13/14，本批保持原样、不缩小守卫。

本批未改服务端、准入配置、CDN active 链与 manifest；准入号沿用
`ios-184-author-1047-public-20261001` 及原配对，未部署云服。

## 成品身份

- IPA：`F:/codex/outputs/orochi-rescue-bell-ios-20261004/StarPoint-iOS-1.8.4-orochi-rescue-bell-cache-10m-20261004-unsigned.ipa`
- IPA SHA-256：`284f725c71f3582c7eb14f4341a42b26534dcd5907233c688544b1ae1988da47`，167,038,089 字节
- 原生可执行文件 SHA-256：`10fa41a28defeba9c503b4b7bb5e593a469f89c00fe287829ab3cca98c11fd96`
- 主 SWF SHA-256：`c6f2b3c0b997ff7a9cc468e1a972d98d9e2288893fcb6619d0c9ebd9ff8fc010`
- 运行时 ABC SHA-256：`22b092e7aea211208c990872a463247e91b340185d3546136a8a6174f94a0154`
- 完整 ABC：`F:/codex/outputs/orochi-rescue-bell-ios-20261004/ios-full-cache-cleanup.abc`，
  SHA-256 `8b8ff787042e11a2e53fcbd69b17634bcc3996fb0441d20042a516219f56a449`，
  SHA-1 `dc008f7fabbd16bc860f4b4a9261d07af8c06e88`，101,463 个方法
- 来源载体：`F:/codex/outputs/ios-equipment-f1009-fix-20261002/ios/StarPoint-iOS-1.8.4-author-equipment-standalone-20261002-unsigned.ipa`
  （`4ce93ffe967331b088032fa4d3e169c7d58b2c1cef4b10cf727e28906811bf40`，用户已验收）
- 包身份：`com.kulo.wf` / 1.8.4 / 1.8.46；unsigned；公网初始地址 `http://175.178.160.158` 不变

## 静态校验

独立回读记录：`F:/codex/outputs/orochi-rescue-bell-ios-20261004/ios-verification-report.json`
（`status=verified`，无失败项）。

- IPA 成员 3568 个，顺序与 ZIP 元数据与来源载体一致；仅 3 个成员发生字节变化（原生可执行文件、
  主 SWF、内置 payload），其余 3565 个逐字节一致。
- AOT 摘要等于 `sha1(完整 ABC)`；方法表 101,463 项；5 个新方法（101458–101462）表项指向新函数
  且函数哈希匹配；新增 5 个重定位槽与重定位流一致。
- 运行时 ABC：既有 101,458 个方法体与旧运行 ABC 一致，方法/类/实例结构与完整 ABC 一致，
  脚本前缀不变，准入字符串不变。
- `applyLoad` 入口首指令为跳转包装器的分支；包装器 `bl` 目标为 101462 桥函数、尾部跳回
  `入口+4`，被替换首指令与来源二进制一致。
- 主 SWF 仅 20 字节 AOT 摘要变化（解压后逐字节比对），内置 payload SHA-256 等于紧凑 payload。
- 全文件差异均落在声明范围内；LINKEDIT/ldid 签名布局保持（签名区仍在文件末尾）。

## 未验证与边界

- 未真机安装、启动或计时验证，未重签；离线结论不替代 TrollStore 实机验收。
- 未生成公网 Android 版本，未改 CDN active 链或 manifest，未部署云服，未提交或推送。
- 构建入口：`client-patch/orochi-rescue-bell-ios/`（`README.md`、`prepare_port.py`、
  `compile_port.py`、`link_port.py`、`verify_port.py`）；中间工作目录
  `F:/codex/work/orochi-ios-port-20261004/`，交付说明见
  `F:/codex/outputs/orochi-rescue-bell-ios-20261004/README-交付说明.md` 与 `CACHE-10M-IOS.md`。
