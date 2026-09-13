# iOS 纪录保持者昵称版验收

2026-09-13 后续说明：本记录为商店累计版的历史来源，精确登记现保存在
`accepted-history/ios-record-holder-20260912.json`；当前基线由 `ios-accepted.json` 指定。
以下保留昵称版验收当时的范围及提交状态。

2026-09-12，用户在此前交付公网 iOS IPA 后明确确认：“ios也验收了”。据此登记该原件为后续 iOS 工作的最新基准，Android 继续使用已经登记的最新昵称版。

- IPA：`F:/codex/ios-artifacts/StarPoint-iOS-1.8.4-record-holder-public-20260912-unsigned.ipa`
- SHA-256：`93695c623782164c243ace5bafd52c8ba170778d2fd9fd73199ef5c8840b2470`
- 身份：`com.kulo.wf`，1.8.4 / 1.8.46，保留交付的 unsigned 原件。
- 完整 AOT ABC：`F:/codex/ios-artifacts/record-holder-public-20260912/record-holder-full.abc`，SHA-256 `99f753dfb209e1070ec47d7d0725c147dfd60db2616a6b704224a7c0028135cc`，101206 方法。
- 制作方法提交：`d35eb315cc2575330f0c4dd3a4ee5a520c45bf4d`。精确身份、旧原生修复和检查范围见 `ios-accepted.json` 与 `ios-record-holder/README.md`。

新增深渊有限层详情全服用时及保持者昵称、常驻活动文件夹入手来源跳转；继续保留 iOS 缓存圆角、登录、HUD 布局、TrollStore 签名边界及此前全部累计功能，不引入 Android 专属切队或标题隐藏行为。配套资源版本为 `.106`。

旧注册表按原字节保存在 `accepted-history/ios-cache-rounded-20260912.json`。该历史包用于复现本次增量，不作为后续新任务默认输入。`ios-record-holder/prepare.py` 对历史输入的哈希约束保留。

用户验收与 Codex 离线检查分别记录：本次只回读 IPA、原生文件、SWF、应用身份和完整 ABC/AOT 摘要及方法数量，没有重新编译、重签、安装或替用户执行逐项真机测试。原构建报告与 candidate.json 保留当时状态。

此次登记不修改服务器、CDN、数据库或存档，不改变云服待部署状态。制作代码此前已提交，本次新增验收登记保留在本地，未新增提交或推送。
