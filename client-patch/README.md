# 客户端最小补丁(免登录 + 重定向)

让官方 CN 客户端连接本服务,仅需两处改动。补丁作用于 FFDec 反编译出的 AS3 源码。

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

完整的自动化流水线(FFDec 导出 / 导入 / 打包 / 签名)是作者基于 [starview](https://github.com/duosii/starview)(GPL-3.0)的本地扩展,未随本仓库分发。本目录仅提供"最小改动 + 应用脚本",方便手动复现;`apply.sh` 为原创实现,不含 starview 代码。

如需恢复 V51 客户端中已经存在但未加入菜单列表的“数据继承”入口，参见 [V51 客户端恢复游戏内“数据继承”入口](../docs/client-takeover-entry.md)。该修改与本页的免登录、API 重定向相互独立。

## iOS 1.8.4

已经通过真机回归的 iOS 五合一、数据继承、幻想连战及幻想魂珠纹理修复流程见
[iOS 1.8.4 私服客户端补丁](./ios-five-in-one/README.md)。幻想魂珠补丁的独立设计与维护实现见
[iOS 幻想魂珠异步贴图补丁](./ios-fantasy-soul/README.md)。仓库仅保存哈希锁定的差分构建器，
不保存原始或修改后的 IPA，也不保存任何签名材料。

## Android 角色页性能

经过实机验证的当前编队轮播更新裁剪、单方法体 P-code 移植、AIR
`uniqueappversionid` 缓存失效和 APK 回封要求，见
[Android 角色编队轮播优化](./character-carousel/README.md)。后续 Android SWF 改动必须以已验证成品
APK 为基线，并为每个不同 SWF 生成新的 `uniqueappversionid`。
