# SET 编队 C8601 双端公网客户端离线验收

日期：2026-09-24。状态：`accepted_offline`。设备上的公网包与 iOS 真机行为尚未在本次验收中验证。

## 成品与直接输入

| 平台 | 成品 SHA-256 | 直接输入 SHA-256 | 准入 ID |
| --- | --- | --- | --- |
| Android 1.8.1 公网 | `f24f469c1be0cb3d2d16520a739ace52b58055ce65621f5243404026beba6066` | 已修复 SET 的内网 APK `e531534d9548d6e1cac5cc412d3bf9aad6d5df8330565ce022f54b0fe8180d51` | `android-181-independent-party-20260923` |
| iOS 1.8.4 公网 unsigned | `64edf9ada1c0cb1dd8ebff00978394907b93174b519f0106fd41b55f2949917a` | 独立编队公网 IPA `3eedbcb595856a0a2347058ae4a8fecc9a5a3e80a7f636ab0de35d1ffaa37188` | `ios-184-independent-party-20260923` |

Android 成品位于 `F:/codex/outputs/set-edit-c8601-public-20260924/StarPoint-CN-1.8.1-independent-formations-set-edit-c8601-public-20260924-0fcf027e.apk`；iOS 成品位于 `F:/codex/outputs/set-edit-c8601-ios-public-20260924/StarPoint-iOS-1.8.4-independent-formations-set-edit-c8601-public-20260924-unsigned.ipa`。iOS 完整编译 ABC 位于同一输出目录的 `formal-set-edit-full.abc`，SHA-256 为 `79dcca2a2936e8d0476bf42d701d4e0e6b10b206b18230909a7fec228561a10c`。

## 范围与检查

- SET 编辑标题对空值及范围外编队分类使用现有 Rush 标题；普通深渊、深渊 EX、幻想连战的保存及请求分类不变。Android 主 SWF 的 `refreshPartyCategory` 方法为 `85066`；iOS 原方法 `85605` 指向新编译的 AOT 方法 `101314`。
- Android 从内网包切换到 `http://175.178.160.158:8001`，九个 ABC 字符串位置变化；其他方法体及 APK 非目标成员保持一致。AIR `uniqueappversionid` 改为 `0fcf027e-c219-4d6c-9221-7e10db70b513`。包名、版本号和原签名证书保持一致，v1/v2 签名和 ZIP 对齐通过。
- iOS 沿用独立编队公网 IPA，只修改主可执行文件和主 SWF。完整 ABC 的旧方法前缀及既有类 trait 前缀保留；原生 AOT hook 长度为 1748 字节。原 AOT 方法表长度保持 101,287，新增 hook 通过原方法槽重定向，不扩大旧表。公网启动地址、Mach-O 签名布局及三种 ldid 签名尾部模型通过离线检查。
- 两端准入 ID、签名前缀及匹配密钥沿用现有独立编队配对。本批未修改服务端准入配置，也没有云服覆盖包。
- 本次客户端改动不改变存档结构、服务端持久化表或已保存的编队分类 ID；存档导入导出路径不在本次变更范围内。

离线验收入口为 `client-patch/independent-formations/verify_set_edit_release.py`。原构建报告保留生成时状态；验收身份以两端 accepted registry 为准。iOS IPA 仍为 unsigned，需要目标设备的既有签名安装流程；本次没有 iOS 真机验收结果。
