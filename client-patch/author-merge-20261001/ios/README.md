# iOS 作者装备规则端口（2026-10-01）

本目录记录作者装备规则从已验收 iOS 载体到 iOS ABC 的受控移植入口。`prepare_ios.py` 只生成编译器输入，不处理 IPA 封装、签名或准入密钥。

## 固定输入

- iOS 基线：`StarPoint-iOS-1.8.4-author-1047-startup-download-fix-20260927-r2-unsigned.ipa`
  - SHA-256：`123fdafd38caff60b64bebf4bd2d7dc8f73a48de2e08ba5f99f8d9a79a20d769`
  - 完整 ABC SHA-256：`e100ae2f0d6b77ed278f91fda753df3402d7aa12a1b1867600c61f63e4b07f39`
  - 原始方法数：`101436`
- Android 作者装备 L7 donor SWF：
  - SHA-256：`2eebe2196d5cbe51388efda7ce50bb8eb050da4bcc22eab1a0af85bb680f8845`
  - 路径：`F:/codex/work_author_review_20260930_round2/public1047-rebuild/l7.swf`

运行脚本前必须确认上述文件存在且哈希一致。脚本会保留既有常量池、方法信息、脚本和无关类/实例 trait 前缀。

## 端口范围

- 14 个既有方法：13 个同 activation 布局替换，`resolvePathCollection` 通过 activation-safe hook 重定向。
- 6 个 `BattleCharacterLogic` 作者辅助方法。
- 2 个闭包方法。
- 编译后的 AOT 方法表从 `101436` 扩展到 `101464`，新增 28 个入口。
- 不改变存档结构、签名身份或 iOS 包版本。

## 构建边界

本次编译、原生链接和准入轮换使用任务工作目录 `F:/codex/work/author-equipment-ios-public-20261001/` 中的受控脚本及本机 AIR 工具链完成。IPA、完整 ABC、私有准入配对和构建临时文件不进入 Git；服务端整合使用 `.codex/secrets/starpoint-client-admission/releases/author-1047-public-20261001/config/` 中的完整配对。

最终公网 IPA 的静态验收记录见：
`F:/codex/outputs/author-equipment-ios-public-20261001/ios-verification-report.json`

该记录为离线验收，未进行实体 iOS 设备测试，也未部署云服。
