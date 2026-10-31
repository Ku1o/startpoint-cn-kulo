# release1031 Android 公网基线登记（2026-10-31）

最终累计签名公网 APK 登记为 `accepted_offline`，并将默认 Android 开发输入切换为 `variants.public`。既有 iOS 登记保持不变；旧 R11 LAN 登记完整保留，其功能并不与当前公网包相同。

## 成品身份

| 项目 | 登记值 |
| --- | --- |
| APK | `F:/codex/outputs/release1031-public-clients-20261031/android/StarPoint-CN-1.8.1-release1031-final-public.apk` |
| APK SHA-256 | `ca180d7d6707e2969aef12a88dd623d567affc05cde7bc8c382172225c65abf8` |
| 字节数 | 214236860 |
| SWF SHA-256 | `a4f73ebfef424d724cf4f47eb73396b8361fa41b083f1a29bde2cf1518d9bd43` |
| DEX SHA-256 | `4155d73dc740e4c93e8198f2a3835cbfaa7413bce29eb4b5381a82897474d410` |
| AIR UUID | `95dfe546-7124-4e0f-a728-54960fd72204` |
| 包名 / 版本 / versionCode | `com.leiting.wf` / `1.8.1` / `1008001` |
| ABI | `arm64-v8a`、`x86_64` |
| 公网 origin | `http://124.222.203.221:8001` |
| 准入 ID | `android-181-r1031-final-public-20261031` |
| DoABC数量 / 主ordinal / 原始tag index | 306 / 305 / 368，后两项为零基序号 |
| 主ABC / 全SWF方法体数量 | 92766 / 97013 |

精确入口以 [android-accepted.json](android-accepted.json) 为准。原证书SHA-256为 `569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894`；最终包已有v1/v2签名及ZIP对齐证据。

## 累计范围和继承

保留R11及此前累计内容，并包含release1031已选功能、设置、教程日期守卫、trigger9000和冲刺缺失helper修复。功能载荷来自 `production1031-dash-action-r1`，SHA-256 `ccb18e4a6ea295d14e2ab7a17e478d7b0ea7fc54a6dbc78d06f1375569c67254`；之后的8001直连版只改地址和缓存身份，SHA-256 `885e6b972d7e09440b6603b3825572bf41b74c0855827e88d556c50f67886d19`，它是本次公网版的直接输入。

公网转换修改9处地址、两个准入helper的本批配对及AIR缓存UUID；完整SWF/ABC、Manifest和DEX逆变换与6125个非目标成员保留证明游戏方法和类布局保持。构建和准入发行记录位于 `F:/codex/work/production-release-20261031/client/revision-public-admission-20261031/`，功能修复源码索引为同批 `client/CURRENT-REPAIR-SOURCE-INDEX.json`。

登记采用本批已经存在的准入号和密钥，不再分配新号、不生成密钥、不改允许名单，也不推定云端已应用。旧完整登记保存在 `lineage.previous_android_baseline_registration`；当前 `variants.lan` 仍保留10-24 R11的原路径、哈希、地址、准入及验收状态。后续同功能内网版应从当前公网基线转换，不能退回旧LAN重新拼装。

## 验证及边界

- 复用与此APK身份匹配的最终 `verification.json`：v1/v2固定签名、ZIP对齐、9地址、准入平台/配对、全SWF逆变换、Manifest/DEX UUID逆变换和6125个非目标成员保留通过。
- 本次从实际最终APK读回SWF、DEX、唯一AIR UUID、ABI及各ABC结构/方法体计数。元数据回执为 `F:/codex/work/production-release-20261031/client/registration-android-baseline-20261031/metadata.json`；数量核对不代表执行全部方法。
- 登记后执行 `python -B client-patch/verify_android_baseline.py --variant public`，核对新登记与实际APK、SWF、DEX、大小及AIR UUID。回执位于同一登记目录的 `identity.log`。
- 前批LAN曾有教程、冲刺和部分战斗/返回的有限设备证据；它不自动构成本次最终公网APK的完整设备验收。最终公网包未新增安装、游戏、全玩法、公网登录或云端准入实测，保持 `accepted_offline`。

本记录只推进Android登记和当前入口，不修改或重打包APK、准入配置、云服或数据库。原构建回执保留生成时 `acceptedRegistryChanged=false`，后续登记由本记录单独说明。累计客户端源码见 [release-20261031](release-20261031/README.md)。
