# iOS 公网地址迁移（内网/旧公网 → 新公网 IP）

2026-10-04 起，StarPoint CN 公网客户端统一指向公网 `124.222.203.221`；旧公网
`175.178.160.158` 仅作为历史输入，不再用于新公网包。内网版继续使用 `<LAN_HOST>`。
转换是机械步骤：保留已验收的内容与准入配对，只替换地址、刷新 AOT 摘要并重打包。

## 输入与范围

- 输入 IPA 必须是已验收载体，且登录面板前置构造器 origin 等于 `--old-ip`（默认
  `175.178.160.158`）；同时提供与该 IPA 配对的完整 ABC（AOT 编译输入）用于重算摘要。
- 允许变化：原生可执行文件（地址字符串 + AOT 摘要 20 字节）与主 SWF（仅摘要槽）。
  其余成员必须逐字节一致；准入号、包名、版本、签名布局保持不变。
- 本目录只做离线转换与回读校验：不安装、不签名、不部署、不真机测试。

## 用法

```powershell
python -B client-patch/ios-public-migration/build_public_ipa.py `
  --input-ipa  <已验收 IPA> `
  --input-ipa-sha256 <输入 IPA SHA-256> `
  --input-full-abc <配对完整 ABC> `
  --input-full-abc-sha256 <完整 ABC SHA-256> `
  --out-dir <输出目录> --output-name <输出 IPA 名> --abc-name <输出 ABC 名>

python -B client-patch/ios-public-migration/verify_public_ipa.py `
  --build-report <输出目录>/ios-public-build-report.json `
  --input-ipa <同一输入 IPA> --old-ip 175.178.160.158 --new-ip 124.222.203.221
```

输入地址计数与历史记录不一致时脚本会拒绝运行；默认按历史批次
`native=354`、`full ABC=17` 校验，可用 `--expected-native-hits/--expected-full-abc-hits` 覆盖。

## 校验内容

- IPA 成员顺序与注释一致，仅原生可执行文件与主 SWF 变化；全包不再出现旧地址。
- 原生地址替换点全部落到新地址，除地址与摘要外无其它字节变化；AOT 摘要等于新完整 ABC 的
  SHA-1；加载面板构造器实际 origin 解析为新地址；签名布局与输入一致。
- 运行时 ABC 与完整 ABC 均无旧地址；主 SWF 仅摘要槽变化且长度不变。

## 已执行记录

- 2026-10-04：救援铃铛 C8016 v3 + 10 分钟缓存清理批次，内网基线（`4f62b899…`）转公网
  `124.222.203.221`，仅换地址、AIR `uniqueappversionid` 与重签，见
  `F:/codex/outputs/starpoint-public-migration-20261004/`。
- 2026-10-04：F1009 静态槽修复包（`df4afd7b…`）转公网 `124.222.203.221`，见
  `F:/codex/outputs/orochi-rescue-bell-ios-fix-20261004/public-migration/`。
