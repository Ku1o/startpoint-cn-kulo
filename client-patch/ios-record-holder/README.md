# iOS 深渊纪录昵称及入手来源文件夹

2026-09-12：用户验收最新 Android 昵称版后，要求先完成公网 APK、云服整合包和提交，再按此版功能制作 iOS。本目录是随后完成的 iOS 公网候选，尚未进行设备验收；不晋升 `ios-accepted.json`。

## 输入和产物

- iOS 输入：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-cache-rounded-public-20260912-unsigned.ipa`，SHA-256 `11ccd92b75e00484e57d124b52a02aedc4cecfb9c0012387288fd69e58af42d9`。
- Android 行为参考为用户最新验收原件，SHA-256 `e04b9e4f367be0ee447f1cfc8f45ff314fafc4a2df7efcef03db120347278f32`；不是旧入手方法包或暂停期间生成的不含昵称公网包。
- 最终 IPA：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-record-holder-public-20260912-unsigned.ipa`，SHA-256 `93695c623782164c243ace5bafd52c8ba170778d2fd9fd73199ef5c8840b2470`。
- 完整 AOT ABC、身份与核验报告：`F:/codex/ios-artifacts/record-holder-public-20260912/`。工作区 `F:/codex/work/ios-record-holder-20260912`，可用 `STARPOINT_IOS_RECORD_WORK` 指定新的独立工作目录。
- 保持 `com.kulo.wf`、1.8.4 / 1.8.46。保留 iOS 初始公网地址 `http://175.178.160.158`（端口 80），不照搬 Android 的端口配置。

## 累计行为和原生边界

深渊有限层详情增加本期全服最快用时及纪录保持者昵称，昵称转义、未知玩家、10 秒缓存、1.8 秒超时、换场景丢弃晚到结果等逻辑与已验收 APK 相同。原个人最佳及无尽层详情保持独立。入手方法支持已解锁且开放的活动文件夹，并保留原有活动/关卡解锁条件。

只替换旧方法 `101085 AbyssDetails.openDetails` 和 `83560 ItemHowToGetQuestSearcher.getAvailableQuestLogic`，追加 `AbyssRecordDetails` 与 `ItemSourceFolderGate` 共 15 个方法，AOT 方法总数 101206。保持旧实例字段、方法签名、类/脚本和常量池前缀；详情入口虽然转为委托，仍保留原有五个 activation 字段，避免改变旧回调的布局描述。

新增 `__CNRECORD` 与 `__CNRCTAB`，不更改既有启动清理入口。保留 iOS 缓存/圆角、登录、公网初始配置、HUD Number 尾部字段和此前全部原生修复。没有移植 Android 专属切队或 CNtips_b 隐藏。新增 dyld 重定位流位于符号字符串表之前，保留 TrollStore/ldid 的签名裁剪边界。

## 验证

```powershell
python -B -X utf8 client-patch/ios-record-holder/prepare.py
python -B -X utf8 client-patch/ios-record-holder/compile.py
python -B -X utf8 client-patch/ios-record-holder/build.py
python -B -X utf8 client-patch/ios-record-holder/verify.py
python -B -X utf8 client-patch/ios-record-holder/test_regressions.py
```

编译无警告。独立回读 3568 个 ZIP 成员，仅原生可执行文件和 SWF AOT 摘要变化；101189 个其他旧方法保持，两个替换方法和全部新 helper 与验收 APK 的规范化指令相同。核对 407 个原生重定位、92733 个新增 rebase、三种 ldid 重签大小模型、旧 HUD 布局和启动清理段原字节。五项历史负例回归通过，包含旧包签名后元数据被覆盖、未知 rebase opcode 0xF0、旧初始地址和 R3 HUD 字段偏移错误。

以上是离线身份、代码和布局核验，未进行 iOS 真机重签、安装或启动，不声称设备验收。最初回归脚本误把 `runtime_abc` 返回的三元组整体当作 ABC，修正取第三项后全部通过；候选载荷没有因测试脚本修正而改变。

## 资源和服务端

使用同批 `.106` 两个分包，公共 PNG/索引/卡池表已同时覆盖 Android 与 iOS，本次不另造 CDN 分包。服务端需部署包含昵称接口的 `4d4c3265` 整合包；未部署时新客户端会保留失败提示。

没有改变游戏存档、表结构、玩家身份或资源 ID。无客户端新增持久值；原有安装缓存标记保持。设备验收时检查深渊详情的用时和昵称、机兵齿轮/蒸汽核来源跳转、等级不足仍受限制，以及原有登录和进场。
