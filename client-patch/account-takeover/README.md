# Android 账号继承入口补丁

本目录把此前只有不完整操作说明的 V51“数据继承”入口正式固化为可复现的 P-code 方法体。
按用户要求先以已经通过真机验收的局域网通用 Rush 排行榜 APK 为直接基线恢复继承入口；该局域网
成品已于 2026-08-30 通过真机验收。公网候选直接从该验收成品追加地址方法，不能反向从旧公网
候选测试客户端功能。

## 已验收局域网基线

以下继承版已通过用户真机验收，是制作本轮公网版的唯一直接基线：

| 项目 | 值 |
|---|---|
| 直接基线 APK SHA-256 | `07C316413E4E3F99DFF83C52A5000F03ECBD466E76D5BC9F29FCD0884072DE09` |
| 直接基线 SWF SHA-256 | `A354037C593F77773B3A0A18841FE4501CF55C1128BB1F89B0E47AD79DCFBA60` |
| 基线 `uniqueappversionid` | `690fdca8-a0cf-4bf8-9241-733bcc7ed124` |
| 已验收 APK | `outputs/account-takeover-lan-download-slot-test-20260830/StarPoint-CN-LAN-1.8.1-character-carousel-rush-leaderboard-takeover-test-20260830.apk` |
| 已验收 APK SHA-256 | `14F50FB3C08BB3B48A4263AF3D10972FE06856A37957F5828B360E6E6FD0DF4B` |
| 已验收 SWF SHA-256 | `B2C6CDA47882FF4DF6191B24C851C1EB05BCEC16BC650A591853B4E715774C78` |
| 已验收 `uniqueappversionid` | `c96e5f11-5249-4269-a3fb-4b190d663b02` |
| 签名证书 SHA-256 | `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894` |

## 已验收权威公网基线

公网包没有重做继承补丁，而是直接从上述已验收局域网 APK 只移植公网地址构造方法：

| 项目 | 值 |
|---|---|
| 直接基线 APK SHA-256 | `14F50FB3C08BB3B48A4263AF3D10972FE06856A37957F5828B360E6E6FD0DF4B` |
| 直接基线 SWF SHA-256 | `B2C6CDA47882FF4DF6191B24C851C1EB05BCEC16BC650A591853B4E715774C78` |
| 公网地址 | `http://175.178.160.158:8001` |
| 权威公网 APK | `outputs/account-takeover-public-175.178.160.158-from-accepted-lan-test-20260830/StarPoint-CN-1.8.1-character-carousel-rush-leaderboard-takeover-public-175.178.160.158-test-20260830.apk` |
| 权威公网 APK SHA-256 | `0C7BBA3D8E2EF07B8AC9E98B11AAF257008A0B373950FD98332047C727064857` |
| 权威公网 SWF SHA-256 | `7EEA1972F568E31CE5B708E057EB7FEF306E2B25BA5CF7C6A198557914623CA7` |
| 权威公网 `uniqueappversionid` | `71382d72-ac79-46b9-a1ae-495a19c0dd68` |
| 签名证书 SHA-256 | `569D19A3578D4CBA16E3D6E7AD8CCAB4FA667EFC758DEEF6C9BE3ADB99919894` |

该公网 APK 已于 2026-08-30 通过用户真机验收。后续 Android APK 修改必须直接以它为基线，除非
用户明确指定另一份已验收成品；不得回到旧公网 APK、局域网 APK 或诊断包继续叠加。

该血统最早可追溯到同样已验收的 V51 双模式与 MOD 五合一成品：

| 项目 | 值 |
|---|---|
| V51 APK | `F:\codex\幻想连战+深渊连战双模式-v51-赛瑞斯详情缩放终态修复.apk` |
| V51 APK SHA-256 | `30757351160B01E1FFC0E134C4D9F7077EABBD7E02CB70495597353449D84135` |
| V51 SWF SHA-256 | `EB7962184DF5E7D1DA112E4BEF9DED8DB8526E14A6F6F1710E051063A8F1D17C` |

当前权威公网 SWF 相对该 V51 SWF 恰好只变化 19 个后续批准的方法体：轮播 1 个、Rush 排行榜
15 个、继承入口 2 个和公网地址 1 个。其他 96378 个方法体保持一致，因此 V51 中已有的幻想连战和
MOD 五合一实现没有被后续完整类重编译覆盖。

## 权威功能清单

后续构建至少要保留：

- MOD 五合一：免登录、服务器重定向、深渊装备战斗门控、赛瑞斯双形态 P-code、逐角色
  `frame.scale` 渲染；
- 幻想连战：活动路由、战斗门控、结算返回以及队伍/装备图标缓存和生命周期修复；
- 当前编队轮播优化：`PartyCarousel.update`（`284:66481`）；
- 通用 Rush 排行榜的 15 个方法体；
- 标题菜单“下载设定”替换为“数据继承”：`284:37085`；
- 游戏内菜单恢复“继承”：`284:77176`；
- 公网地址 `http://175.178.160.158:8001`：`284:92013`；
- 原版 `TitleMenuDialog.prepare`：`284:37071` 不变；
- 包名、版本身份与现有 StarPoint CN 签名身份不变。

## 客户端变化

只修改两个既有方法体：

1. `pinball.scene.menuTop.MenuTopScene.createMenuListData`（`284:77176`）
   - 在“关注·关注者”和“设置”之间加入 `MenuTopListItemKind.TakeOver`；
   - 使用客户端已有的继承图标和 `title_menu_take_over` 文案；
   - 点击处理仍复用原版已有的 `LoadingTaskKind.TakeOver`。
2. `pinball.dialog.titleMenu.TitleMenuDialogContentView.setupContents`（`284:37085`）
   - 把标题菜单四个实际可见槽位从 `[11,12,4,6]` 改为 `[11,12,4,0]`；
   - 第四格由“下载设定”直接替换为“数据继承”，复用原版已有的标签、图标和 `case 0` 点击逻辑；
   - `TitleMenuDialog.prepare`（`284:37071`）保持原样，不再用调整逻辑按钮顺序冒充显示修改。

载荷分别是：

- `MenuTopScene-createMenuListData.pcode`：SHA-256
  `CB52389CB42B582A532C397EF0CAC66AE24673C7DEA74A8B7473A72419B08125`；
- `TitleMenuDialogContentView-setupContents.pcode`：SHA-256
  `EB24F215E36BB882BAF32347C90D00CC7AFCB1DA74B636C03762EF84CA5D442C`。

两个载荷来自临时完整类 carrier。正式 SWF 由 `build_apk.py` 在干净的局域网 Rush 基线中重新定位方法后，
仅通过 FFDec `-replace` 移植这两个 P-code 方法体；carrier 本体绝不回封发版。

公网地址载荷为
`DevConfig-gf-android-constructor-public-175.178.160.158.pcode`（SHA-256
`71B60ABA2E4001E0617AA5C55B572889B7A9A1D53E60C89EE01087EE33D8025D`）。它只用于替换
`pinball.config.gbits.DevConfig_gf_android.<constructor>`（`284:92013`），并直接应用在已验收继承版
SWF 上；旧的完整类重指向工具不得直接用于发版。

## 血统门禁

最终 SWF 的全方法体比较必须同时满足：

```text
角色轮播基线 -> 最终：changed_count=17
通用 Rush 局域网基线 -> 最终：changed_count=2
```

相对角色轮播基线的 17 项必须恰好是原 15 个 Rush 排行榜方法，以及本补丁
`284:37085`、`284:77176`。当前已验证集合为：

```text
284:37085,284:48482,284:48484,284:71113,284:71115,284:71120,
284:71122,284:71123,284:71132,284:71143,284:71162,284:71163,
284:71167,284:71189,284:71203,284:71207,284:77176
```

因此 `PartyCarousel.update`（`284:66481`）保持在直接基线中，Rush 排行榜 15 个方法保持不变，
`DevConfig_gf_android.<constructor>`（`284:92013`）也保持局域网基线内容，地址仍为
局域网构建所批准基线中的地址（文档不记录个人 LAN IP）。

公网候选还必须满足：

```text
已验收局域网继承版 -> 公网候选：changed_count=1，changed=284:92013
通用 Rush 局域网基线 -> 公网候选：changed_count=3，changed=284:37085,284:77176,284:92013
角色轮播基线 -> 公网候选：changed_count=18
```

公网候选的 18 项是上面的 17 项再加 `284:92013`，不得出现其他方法体变化。

## 构建

签名口令必须按仓库 `AGENTS.md` 从本机 DPAPI 凭据导入到进程级环境变量，不能写入参数、日志或
文件。示例中的环境变量需由调用进程提前安全设置：

```powershell
python -X utf8 client-patch\account-takeover\build_apk.py `
  --target lan `
  --base <已验收通用Rush局域网基线APK> `
  --out <新的测试APK> `
  --report <verification-report.json> `
  --work <全新工作目录> `
  --ffdec F:\codex\tools\ffdec_26.2.1\ffdec.jar `
  --java <java.exe> `
  --javac <javac.exe> `
  --zipalign F:\StartPointCN\wf_full_patch\build-tools\zipalign.exe `
  --apksigner F:\StartPointCN\wf_full_patch\build-tools\lib\apksigner.jar `
  --ks F:\StartPointCN\wf_full_patch\launcher.jks `
  --ks-alias wf `
  --ks-pass-env WF_TAKEOVER_APK_SIGNING_PASSWORD
```

`--target lan` 从精确通用 Rush 基线累计移植两个继承入口；`--target public` 从同一精确基线一次性
累计移植两个继承入口和公网地址方法。公网累计构建必须得到权威 SWF 哈希
`7EEA1972F568E31CE5B708E057EB7FEF306E2B25BA5CF7C6A198557914623CA7`，否则构建直接失败。
公网模式还必须传入
`--legacy-feature-swf F:\codex\mode15-character-migration\apk-three-public-v51\three-public-v51.swf`；
构建器会先核对其 V51 哈希，再要求相对它的变化集合严格等于以下 19 项：

```text
284:37085,284:48482,284:48484,284:66481,284:71113,284:71115,
284:71120,284:71122,284:71123,284:71132,284:71143,284:71162,
284:71163,284:71167,284:71189,284:71203,284:71207,284:77176,
284:92013
```

缺少或多出任一项都会失败，从而同时保护 MOD 五合一、幻想连战、角色轮播、排行榜、继承入口和
公网地址。
该模式用于重建和审计；后续新增 APK 功能仍应直接从上面的权威公网 APK 开始。

构建器会拒绝非精确基线、P-code 哈希变化、方法索引变化、额外方法体变化、旧 UUID 残留、Manifest
除 UUID 外的变化、无关 APK 成员变化、zipalign 失败、v1/v2 签名失败或证书指纹变化。每次构建
自动生成新的 `uniqueappversionid`，且不会安装 APK。

## 真机验收

1. 覆盖安装测试 APK，不卸载原客户端；
2. 在标题页菜单确认右下角“下载设定”已经直接变成“数据继承”，点击后能进入；
3. 登录后打开底部“菜单”，确认“继承”位于“关注·关注者”和“设置”之间并能进入；
4. 在当前账号设置或重置继承密码；
5. 使用另一设备或新的临时账号按“玩家 ID + 继承密码”完成恢复；
6. 回归角色页轮播、队伍切换、Rush 排行榜、排行榜头像、报酬一览、深渊战斗与结算；
7. 用户明确验收后，更新本页和总入口中的权威后继基线并提交。

公网版必须直接从验收后的账号继承 APK 修改 `DevConfig_gf_android.<constructor>`，并要求相对
局域网成品只变化该地址方法体，同时生成另一枚全新 `uniqueappversionid`。不得使用本轮已经判定
错误的旧公网候选，也不得重新制作已经验收通过的局域网包。
