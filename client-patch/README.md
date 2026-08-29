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
[iOS 幻想魂珠异步贴图补丁](./ios-fantasy-soul/README.md)。已经完成用户确认真机验收的
`MemberView.draw` v6 绘制保护、精确成品哈希、构建号、UUID 及失败版本演进记录见
[iOS MemberView.draw 稳定保护](./ios-memberview-draw-safe/README.md)。仓库仅保存哈希锁定的
差分构建器，不保存原始或修改后的 IPA，也不保存任何签名材料。

## Android 角色页性能

经过实机验证的当前编队轮播更新裁剪、单方法体 P-code 移植、AIR
`uniqueappversionid` 缓存失效和 APK 回封要求，见
[Android 角色编队轮播优化](./character-carousel/README.md)。该 APK 是排行榜补丁的重建基线；排行榜
验收后，后续 Android SWF 改动应从下节锁定的通用 Rush 成品继续，并为每个不同 SWF 生成新的
`uniqueappversionid`。

## Android Rush 连战排行榜

复用官方 Rush 排行榜界面，通过一套服务端驱动协议读取活动名称、开放状态、排行、本人定位与
奖励字段。深渊连战和后续幻想连战共用客户端实现；新活动只需服务端登记，不再修改 SWF。
客户端按 15 个既有方法体从上述角色轮播成品 APK 移植，详见
[Android Rush 连战排行榜客户端补丁](./rush-leaderboard/README.md)。完整类导入只允许作为临时 carrier，
不得直接回封发版。

当前后续修改基线是该文档锁定的通用 Rush 成品（APK SHA-256
`07C316413E4E3F99DFF83C52A5000F03ECBD466E76D5BC9F29FCD0884072DE09`）。修改流程固定为：本地构建
并产生新 UUID → 静态/方法体/签名校验 → 交给用户覆盖安装和真机测试 → 用户验收后再更新权威基线并
提交。失败候选不得成为下一次基线，也不得进入 Git。
