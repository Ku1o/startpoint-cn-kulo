# iOS 作者装备规则端口（2026-10-02）

本目录记录作者装备规则从已验收 iOS 载体到 iOS ABC 的受控移植入口。`prepare_ios.py` 只生成编译器输入，不处理 IPA 封装、签名或准入密钥。

## 固定输入

- iOS 基线：`StarPoint-iOS-1.8.4-author-1047-startup-download-fix-20260927-r2-unsigned.ipa`
  - SHA-256：`123fdafd38caff60b64bebf4bd2d7dc8f73a48de2e08ba5f99f8d9a79a20d769`
  - 完整 ABC SHA-256：`e100ae2f0d6b77ed278f91fda753df3402d7aa12a1b1867600c61f63e4b07f39`
  - 原始方法数：`101436`
- Android 作者装备 L7 donor SWF：
  - SHA-256：`2eebe2196d5cbe51388efda7ce50bb8eb050da4bcc22eab1a0af85bb680f8845`
  - 路径：`F:/codex/work_author_review_20260930_round2/public1047-rebuild/l7.swf`

运行脚本前必须确认上述文件存在且哈希一致。脚本保留既有常量池、方法信息、脚本、原生类实例特征和无关类/实例 trait 前缀。

## 端口范围

- 13 个既有方法：保持原 activation 布局并通过 `cn.mod::AuthorState` 的 append-only helper hook 替换；其中 `getAvailableAbilities`、`parseAt106`、`parseAt109` 重新启用装备规则和 423 gauge 限制。
- `BattleCharacterLogic/resolvePathCollection` 保留 iOS 原生实现；原方法槽经过兼容桥进入，桥保存 x0–x5，调用静态装备预加载 helper 后恢复寄存器并继续执行原实现，因此不改变 iOS 四槽 activation ABI。
- 装备规则的 8 个辅助方法（诅咒 soul、衰减 tier、计数、tier 构造、规则门、预加载、路径解析和原生桥）全部挂在 `AuthorState` 静态 trait 上。调用使用 `getlex AuthorState` 加 `callproperty`，把原角色作为显式首个参数传入；不向原生 `BattleCharacterLogic` 或其子类追加实例 trait。
- 1 个既有装备描述闭包和 13 个既有方法 hook。
- AOT 方法表从 `101436` 扩展到 `101458`，新增 22 个入口；原生 `BattleCharacterLogic` 实例/vtable 布局保持字节级不变。
- 不改变存档结构、签名身份或 iOS 包版本；Android 规则路径不在本端口内修改。

## 构建边界

本次编译、原生链接和准入轮换使用任务工作目录中的受控脚本及本机 AIR 工具链完成。IPA、完整 ABC、私有准入配对和构建临时文件不进入 Git；服务端整合使用 `.codex/secrets/starpoint-client-admission/releases/author-1047-public-20261001/config/` 中的完整配对。

`compile_native.py` 会读取本批 `port.json` 中的新增 helper/hook 方法号；这些方法出现 `Verify error` 时立即中止，避免编译器把错误方法降级为运行时失败桩。基线中已有的 101312 告警会保留在编译报告中，不会被误认为本批新增错误。

本次 F1009 修复候选的离线验收记录见：
`F:/codex/outputs/ios-equipment-f1009-fix-20261002/ios/ios-verification-report.json`

该记录为离线验收，未进行实体 iOS 设备测试，也未部署云服。
