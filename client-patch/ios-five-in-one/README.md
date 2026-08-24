# iOS 1.8.4 私服客户端补丁

本目录保存已经通过真机回归的 iOS 客户端最终差分流程。它把哈希完全匹配的原始
`iOS-1.8.4.ipa` 直接转换成最终无签名客户端，不再依赖调查期间产生的多个 stage IPA。

## 包含的功能

- 私服连接与免登录。
- 标题及游戏内菜单的数据继承入口。
- 幻想连战第 5、10、15 阶段多人路由及房主/访客返回流程。
- 深渊装备模式门禁。
- 赛瑞斯双形态、湿润目标雷伤终乘和退场充能。
- 风巨蜥吐息兼容。
- 通用逐角色像素渲染缩放。
- 幻想魂珠异步纹理加载保护。

明确不包含 `OmniElement`、随机楼层和额外商店按钮代码。

## 构建

只需要 Python 3 标准库：

```powershell
python client-patch/ios-five-in-one/build_ios_client.py `
  --source F:\iOS-1.8.4.ipa `
  --output F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-unsigned.ipa
```

构建器会先锁定原始 IPA 的 SHA-256，再逐成员校验原始字节、应用差分，并要求最终
IPA 的 SHA-256 精确等于 manifest 中的目标值。只做内存回读验证、不写出 IPA：

```powershell
python client-patch/ios-five-in-one/build_ios_client.py `
  --source F:\iOS-1.8.4.ipa `
  --verify-only
```

输出仍然是未签名 IPA，需要由使用者自行合法签名。Bundle ID 为 `com.kulo.wf`。

## 维护 manifest

只有新客户端经过完整真机回归后，才允许从两个已审查 IPA 重新生成差分：

```powershell
python client-patch/ios-five-in-one/generate_patch_manifest.py `
  --source F:\iOS-1.8.4.ipa `
  --target F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-unsigned.ipa `
  --output client-patch/ios-five-in-one/patch-manifest.json
```

幻想魂珠补丁的独立实现和设计说明见
[iOS 幻想魂珠异步贴图补丁](../ios-fantasy-soul/README.md)。最终 manifest 已经包含该补丁，
普通构建无需再次运行独立脚本。

仓库只保存原创构建代码、字节差分和哈希，不保存原始/修改后 IPA、证书、描述文件、
设备 UDID 或任何签名密钥。`.gitignore` 已排除 `*.ipa`。
