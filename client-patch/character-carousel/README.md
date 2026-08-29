# Android 角色编队轮播优化

本目录固化已经过实机验证的 Android AIR 客户端角色页优化。补丁只改变
`pinball.scene.character.partyCarousel.PartyCarousel.update`：

- 每帧只推进当前编队的缩略图 playhead；
- 每帧只初始化、更新和浮动当前编队的 `PartyCharacterCellContainer`；
- 保留所有编队的透明度传播、淡入淡出、页面绘制、切换和编辑逻辑；
- 不提前更新左右相邻编队。实机结果表明预更新相邻编队不会让切换更顺，反而会增加常驻负载。

## 已验证成品

成品 APK 不进入 Git。2026-08-29 的本地验证记录如下：

| 项目 | 值 |
|---|---|
| 成品文件 | `outputs/StarPoint-CN-LAN-1.8.1-character-carousel-optimized-final-20260829.apk` |
| APK SHA-256 | `FA45B7727B638ACCFDEB133E7E47EB3612B54AF614D6C8DA2001FDB60B603CCF` |
| 内嵌 SWF SHA-256 | `E3E6CDC8D9A5D93A297912C571BEF58239EFB50F7B77132CF1768AD5A4260475` |
| `uniqueappversionid` | `808339e8-8e32-42f5-9a1a-d66cc876d4bb` |
| 签名证书 SHA-256 | `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894` |

该 APK 与通过实机验收的 AB08 字节一致。实机确认角色页更流畅，上方编队小人显示正常，
队伍编成、左右切换、编辑和返回均可用。首次切到尚未加载过的相邻编队仍可能出现一次加载停顿，
之后恢复流畅；这是原版已有的按需加载行为，不应通过常驻预更新相邻编队来掩盖。

重建 Rush 排行榜补丁时应直接以上述成品 APK 为基线，先提取它的
`assets/worldflipper_android_release.swf`，从而自然保留本补丁。Rush 排行榜已经验收后，新的客户端
功能应从 `../rush-leaderboard/README.md` 锁定的通用 Rush 成品继续，避免重复移植或丢失排行榜。
无论哪条路径，都不要再从旧 LAN APK、分享包或 AB00–AB07/AB09 诊断包开始。

## 从原始 LAN 基线复现补丁

已验证的原始 LAN 基线：

- APK SHA-256：`30757351160B01E1FFC0E134C4D9F7077EABBD7E02CB70495597353449D84135`
- 内嵌 SWF SHA-256：`EB7962184DF5E7D1DA112E4BEF9DED8DB8526E14A6F6F1710E051063A8F1D17C`
- 原 `uniqueappversionid`：`b51f8a71-5d24-4c90-a6e3-7f1b2d8c4695`
- FFDec：26.2.1

补丁载荷是
[`PartyCarousel-update-current-party-only.pcode`](./PartyCarousel-update-current-party-only.pcode)，
其 SHA-256 为
`EDBBCEF866156BF22F57E3CAFE9F75359CFD69501C66DAC1B3B2AE21D530EB2C`。

先编译本目录的两个只读检查器，再定位目标方法体：

```powershell
javac -cp F:\codex\tools\ffdec_26.2.1\ffdec.jar `
  client-patch\character-carousel\FindMethodBody.java `
  client-patch\character-carousel\CompareMethodBodies.java

java -cp "client-patch\character-carousel;F:\codex\tools\ffdec_26.2.1\ffdec.jar" `
  FindMethodBody <原始SWF> `
  pinball.scene.character.partyCarousel.PartyCarousel update
```

上述已验证基线应返回 `abc=284`、`body=66481`。如果换了 SWF，必须以检查器的实际结果为准，
不能照抄索引。随后只移植该方法体：

```powershell
java -jar F:\codex\tools\ffdec_26.2.1\ffdec.jar -air -onerror abort `
  -replace <原始SWF> <补丁SWF> `
  pinball.scene.character.partyCarousel.PartyCarousel `
  client-patch\character-carousel\PartyCarousel-update-current-party-only.pcode `
  <方法体索引>
```

不要把 FFDec 对完整 ActionScript 类执行 `-importScript` 后得到的 SWF 直接发版。FFDec 会重编译
常量池及大量方法体，即便源码只改了一个方法，也可能产生大范围二进制变化。完整类导入只能用于
制作临时 carrier SWF；应从 carrier 导出目标方法的 P-code，再用上面的 `-replace` 把单一方法体
移植回干净基线。

移植后必须比较所有方法体：

```powershell
java -cp "client-patch\character-carousel;F:\codex\tools\ffdec_26.2.1\ffdec.jar" `
  CompareMethodBodies <原始SWF> <补丁SWF>
```

已验证结果必须是：

```text
changed_count=1
changed=284:66481
```

对于不同基线，索引可以变化，但 `changed_count` 仍必须为 `1`，且该项必须与
`FindMethodBody ... PartyCarousel update` 的结果一致。

## APK 回封和 AIR 缓存失效

`uniqueappversionid` 位于二进制 `AndroidManifest.xml` 的 UTF-16LE 字符串池中。每一个不同的
SWF 载荷都必须生成一个全新的 UUID；只改 `versionCode` 或 `versionName` 不能替代这一缓存失效。
重复使用旧 UUID 可能让设备继续加载旧 SWF，造成“改动无效”或误判测试结论。

本目录的 `repack_apk_with_unique.py` 会同时替换主 SWF 和等长 UUID，并校验基线 APK、基线 SWF、
ZIP 条目及替换结果。示例：

```powershell
$newUnique = [guid]::NewGuid().ToString()
python -X utf8 client-patch\character-carousel\repack_apk_with_unique.py `
  <基线APK> <补丁SWF> <未签名APK> `
  --expected-base-apk-sha256 <基线APK_SHA256> `
  --expected-base-swf-sha256 <基线SWF_SHA256> `
  --old-unique <基线APK中的UUID> `
  --new-unique $newUnique
```

当基线是上面的最终成品时，`--old-unique` 是
`808339e8-8e32-42f5-9a1a-d66cc876d4bb`；新 SWF 绝不能再次使用这个值。
若以上一版通用 Rush 成品继续，旧值改为该成品的
`690fdca8-a0cf-4bf8-9241-733bcc7ed124`，下一版同样必须生成从未使用过的新 UUID。

回封后依次执行 `zipalign -p -f 4`、使用项目持久签名密钥签名，并验证：

1. 实际 APK 中的 SWF SHA-256 等于待注入 SWF；
2. 实际二进制 Manifest 只包含新 UUID，不再包含旧 UUID；
3. `zipalign -c -p 4` 通过；
4. `apksigner verify --verbose --print-certs` 通过，证书 SHA-256 等于上表；
5. 安装前再次记录 APK、SWF、UUID 和签名指纹。

签名口令不得出现在命令行、日志、仓库或临时文件中。按仓库 `AGENTS.md` 使用本机
DPAPI 保护的凭据，仅在签名进程内设置进程级环境变量，并在结束后立即清除。

## 不应合入的诊断改动

- 禁用 `PartyCarousel.initialize`：虽然很流畅，但队伍编成无法打开；
- 禁用 `PartyCarousel.update`：会让上方编队小人消失；
- 禁用 carousel draw：没有可测改善；
- AB09 可见角色表裁剪：没有可测改善；
- 移除大立绘或 fullshot/CDN 资源：没有解决角色页持续掉帧；
- 预更新当前编队左右邻居：常驻负载更高，不采用。
