# Android 深渊纪录昵称累计版验收（2026-09-12）

用户在昵称版 LAN APK 交付后明确回复：“ok，验收了，继续刚刚暂停的任务，注意一下，apk以最新的这版为准哈，ios制作的时候留意一下”。本记录将该原件登记为最新 Android 功能基准；之前入手来源文件夹版本也已获用户验收。

## 原件和公网派生件

| 项目 | LAN 用户验收原件 | 公网地址转换派生件 |
| --- | --- | --- |
| APK 目录 | `outputs/abyss-record-holder-lan-test-20260912` | `outputs/abyss-record-holder-public-20260912` |
| APK SHA-256 | `e04b9e4f367be0ee447f1cfc8f45ff314fafc4a2df7efcef03db120347278f32` | `69e143bc70a8f03f5c78b89c0262715c41f5a5847f35dde7f482c0443d5dd894` |
| SWF SHA-256 | `c5fcc853a10db415fc898d24ac940dc59a2ee1c886e7cff9544fd6a0ba661559` | `0bbe58fab5f51b16220b11f9ffefece899854749ce3287a9c264ba67d4941eae` |
| AIR UUID | `eeb1d3e6-eb89-47d6-887a-419ad6d063e3` | `dfc8a7fd-86f1-42aa-adb9-8b5541272bce` |

路径、大小、DEX 身份和报告见 `android-accepted.json`。公网派生包只更换 `DevConfig_gf_android` 构造器使用的地址字符串池 92871，以及 AIR/原生缓存身份。独立比对 96,535 个方法体全部相同，六个原生类操作不变，签名、对齐及其他成员回读通过。该公网包未另行真机验收；注册表逐环境区分 `user_accepted` 与 `derived_from_user_accepted_lan`，不能将顶层用户验收解释为所有环境都已实测。

## 必须累计保留

- 历史缓存、圆角、切队 F1009、登录、Lens、属性通道、五重决战、幻想、深渊续战、排行榜、关注和本人资料入口等功能。历史精确注册表为 `accepted-history/android-cache-party-20260912.json`。
- 深渊有限层详情展示本期全服最快用时及当前公开昵称；同分保留旧纪录，缺失身份显示未知玩家，昵称作 HTML 转义；个人最佳独立保留。
- 入手方法允许已解锁、开放期内的常驻活动文件夹；原有活动和关卡解锁条件继续生效。配套 `.106` 两个分包包含补全索引、gacha 表和图标。

主 ABC 290，总方法体 96535。历史 `abyss-records`、`item-source-folders`、`abyss-record-holder` 构建文档是各步骤当时状态，不能当作当前基准。构建报告保持原样，不修改其生成时未验收状态。

## iOS 后续范围

从独立 `ios-accepted.json` 的已验收 IPA 和完整 AOT ABC 开始，移植全服用时、保持者昵称及文件夹入手导航。保留 iOS 的原生布局、TrollStore 签名边界、公开初始地址和累计修复；不移植 Android 专属切队修复或 CNtips_b 隐藏。本次 Android 验收不等于尚未制作的 iOS 已验收。
