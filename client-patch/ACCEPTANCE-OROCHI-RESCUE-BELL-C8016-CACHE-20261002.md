# 救援铃铛 C8016 v3 与 AIR 缓存十分钟清理内网客户端验收

## 范围

- 平台：Android APK，内网环境
- 地址：`http://<LAN_HOST>:8001`
- 组合：超级+内置紧凑排版、C8016 v3 SWF helper、AIR 缓存十分钟清理
- 资源来源：APK 内置 bundle；本批没有 CDN 增量
- 公网 Android 与 iOS：暂不制作

## 成品身份

- APK SHA-256：`4f62b899a89b0648f79d0dbaf20d8aab9b64ad91959d91706dc71af02cb6c335`
- 内嵌 SWF SHA-256：`9418137820c007b52a11ad0d7955c102795d8dd903213670577bf3407ed709f7`
- AIR `uniqueappversionid`：`4728fb03-7242-4fcc-9bc4-e8b4fc073a43`
- 固定签名证书 SHA-256：`569d19a3578d4cba16e3d6e7ad8ccab4fa667efc758deef6c9be3adb99919894`
- 直接输入 APK SHA-256（C8016 v3）：`5505e73fbe770ca3c81e638e6e97b103b9bb997c95b6bc63d2b277323d8e6884`
- 直接输入 AIR UUID：`5a18e114-3549-4e26-bf34-e9616562d08a`

## 静态检查

- 基线沿用已验收的“超级+”内置紧凑排版；排版生成方法仍由 `orochi-rescue-bell-superplus/build_embedded_layout.py` 维护。
- C8016 SWF 只改变 `cn.mod::InahoAbilityVisuals` helper tag `359`；其他 SWF tag 字节一致。
- helper 预载判断保留 `InvokeSkill` 标记，并覆盖 `AllEnemyDamage` / `GeneralEnemyDamage` 的嵌套索引 `13`、`14`。
- DEX 只替换 `StartupCache`、`StartupCache$Periodic`、`BuildIdentity` 及既有 AIR UUID；非目标类回读一致。
- 周期为 600 秒，目标为 `<DATA>/cache/app` 与 `<DATA>/cache/.AIR`；下载资源目录和内置 bundle 未触碰。
- 诊断文件为 `<DATA>/sp-cache-periodic.diag`，记录阶段、实际目录、目标路径和删除结果。
- ZIP、V1/V2 签名、ZIP 对齐和最终 SWF 回读通过；APK 其他非目标成员保留 4173 个。

## 验收状态

用户已在内网实机测试当前组合版本，记录为 `user_accepted`。Codex 当前未连接测试设备，因此不把该状态描述为 Codex 设备实测；云服未部署。构建方法见 [C8016-PRELOAD.md](./orochi-rescue-bell-superplus/C8016-PRELOAD.md) 和 [`startup-cache/PERIODIC-10M.md`](./startup-cache/PERIODIC-10M.md)。
