# iOS 幻想魂珠异步贴图补丁

该补丁把 Android 端已有的幻想魂珠异步贴图加载策略移植到 iOS 1.8.4 AOT 客户端，目标是避免资源尚未进入纹理缓存时同步调用 `getTexture`，从而触发 `C8004`，并进一步导致 `G1002`。

补丁只接受仓库当前已校验的五合一未签名 IPA：

- 输入 SHA-256：`EF95265C81ADC0C391BA4AB4DF4F8F8456B0AA9485A572A0AEB822D286ED94F2`
- 输入文件：`iOS-1.8.4-kulo-private-final-unsigned.ipa`

脚本依赖 `capstone` 和 `keystone-engine`：

```powershell
python -m pip install capstone keystone-engine
```

用法：

```powershell
python patch_ios_fantasy_soul.py `
  --ipa F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-unsigned.ipa `
  --out F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-unsigned.ipa `
  --manifest F:\codex\ios-artifacts\iOS-1.8.4-kulo-private-final-fantasy-soul-unsigned.json
```

也可以通过 `--dependency-path <目录>` 使用已安装在独立目录中的两个依赖。脚本会同时锁定
输入、输出 IPA 与 Mach-O 的 SHA-256，避免把补丁误用于其他客户端版本。

实现方式：

- `present(Some)` 保存最新数据，然后通过 `AssetGroupKind.ItemThumbnail` 异步加载贴图。
- 加载完成回调复用该类已有的零参数 `run()` 方法闭包。
- 回调触发后再调用原始同步 `present` 完成 `changeTexture`、对齐和 Y 轴偏移。
- `present(None)` 仍走原始清空逻辑。
- 不修改服务器、资源包、数据库、存档或网络协议。

产物仍是未签名 IPA，需要使用原有方式签名安装。补丁使用一个正常游戏流程不可达的 debug sound-test 方法作为 ARM64 代码存储；该调试动作在补丁版中不受支持。

仓库的最终一体化 manifest 已包含本补丁；本目录保留独立实现，供审查和维护补丁逻辑使用。
