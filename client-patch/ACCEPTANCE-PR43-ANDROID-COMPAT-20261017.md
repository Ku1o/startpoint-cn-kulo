# Android PR43 兼容新准入基线登记（2026-10-17）

登记层级为 `accepted_offline`，作为后续 Android 开发的默认输入。当前只登记公网变体；需要内网成品时从该公网基线转换地址并更新缓存身份，保留累计功能和准入配对，不回落历史 LAN 包。

## 成品身份

| 项目 | 登记值 |
| --- | --- |
| APK | `F:/codex/outputs/client-pr-port-20261017/StarPoint-CN-1.8.1-pr43-compat-admission-arm64-x86_64-public-20261017.apk` |
| APK SHA-256 | `a7a2537b7d82d7b8f0beaf6967c38d50a869685cfe2d69e6f776f1f198b2e7ee` |
| 字节数 | 214195900 |
| 游戏 SWF SHA-256 | `1a731486c2256052011226faf17582251a1030965698fa16b6596669e8c9a922` |
| DEX SHA-256 | `2b540b88bda3ddf2b7815326be24b5972e5c84c7e00f5061525903e4144ad42d` |
| AIR uniqueappversionid | `2345e786-ae2c-4984-9b7e-bd9ab55e3d9f` |
| 包名 / 版本 | `com.leiting.wf` / `1.8.1` / `1008001` |
| 架构 | `arm64-v8a`、`x86_64`，各 15 个原生库 |
| 地址 | `http://124.222.203.221:8001` |
| Android 准入 ID | `android-181-pr43-compat-public-20261017` |
| 证书 SHA-256 | `569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894` |

SWF 共 302 个 DoABC；主 `boot_ffc6` 为零基 DoABC ordinal 301、原始 SWF tag index 364。主 ABC 有 92601 个方法体，整个 SWF 共 96734 个方法体，不能将全容器数量写成主 ABC 数量。

## 累计内容与证据

- 接续此前已登记功能，加入已审阅的 PR43 方法差异、Lv120 超限、四个内置配套资源及 x86 原生/ANE 适配；R4 的未采用实现不进入该基线。
- 普通角色继续用旧材料；仅支持扩展且普通突破完成的角色进入新材料分支。缺新材料 master 定义与库存为零分别处理，展示回退不启用错误消耗。
- 兼容修正的 14 个完整生产方法实际 AIR/AVM2 执行记录包含 1918 项断言、184 个窗口场景；这是受控执行范围，不代表完整游戏验收。
- 最终新准入 APK 的独立回读包含 1415 项检查，核对两个准入 DoABC 的实际常量和引用、Manifest/DEX 缓存身份、原证书 V1/V2、对齐、CRC，以及原生/ANE/bundle 保留。
- 对应完整私有配对的真实协议实现离线检查 69 项通过。实际密钥和私有配置不写入本登记。

既有离线回执保持原样：本地 `work/client-pr-port-20261017/compat-public/`、`admission-release/`，最终身份与独立回读分别为后者的 `android-final-package.json`、`validation/android-final-independent-readback.json`。本次登记复用这些未变输入的有效证据，不重签或重新制作 APK。

## 当前入口与历史

```powershell
python -B client-patch/verify_android_baseline.py --variant public
```

登记路径、身份与默认变体以 [android-accepted.json](android-accepted.json) 为准。实现和固定输入复现说明见 [pr43-port/README.md](pr43-port/README.md)，其中历史固定配方不替代未来的基线身份检查。

旧 10-02 LAN、10-04 public 的原日期和验收层级保存在 `lineage.previous_android_baseline_registration`。完整旧登记可由 Git 修订 `a199a139` 的同名文件恢复到任务目录，用 `--record` 明确复现；旧变体不再作为当前默认输入。[R4 回退记录](ANDROID-BASELINE-ROLLBACK-20261017.md)及已有构建回执保留其历史状态。

## 范围

未记录真机验收，未实连公网完成登录或游戏，未核验当前云端允许名单已经应用。`accepted_offline` 表示允许从该包继续开发，不表示设备、游戏或部署已验收。本次仅更新 Android 登记与入口，不更改 iOS、服务端、CDN、运行配置或准入密钥。
