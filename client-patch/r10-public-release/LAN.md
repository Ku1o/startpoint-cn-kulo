# R10 正式准入 Android 内网派生包

2026-09-15，用户要求“安卓这边做一个带相同校验的内网版本”。使用刚完成的正式公网 APK，沿用 `android-181-r10-20260915` 及其原配对密钥；不使用首次隔离验证号，也不分配新号或轮换密钥。

- 输入：`outputs/r10-public-release-20260915/StarPoint-CN-1.8.1-r10-public-20260915.apk`，SHA-256 `afca9f44d1bea9edea7b573fa96dddd32bc304afd0bbaa4d3df6fb21d41c2a90`。
- 输出：`outputs/r10-admission-lan-20260915/StarPoint-CN-1.8.1-r10-admission-lan-20260915.apk`，SHA-256 `af2699ea9a2e8792b4f84dd72aea0c08cb1da6a5448a572896139150e6d51d4f`。
- SWF SHA-256：`13c2ab8f473622eabd111d5b140af27df3d698994fd8e59f2ddd039a4d57638a`。
- 新 AIR UUID：`f56d1bd9-104f-49fd-b675-4ad209c2930d`；保持 `com.leiting.wf` / `1.8.1` / `1008001` 和固定 wf 签名。
- 连接 `http://<LAN_HOST>`，实际内网主机来自忽略的 `outputs/android-build-local.json`，完整实际地址仅记录在本机成品报告。

`build_lan.py` 锁定这份正式公网输入和已验收累计来源。仅替换三个 ABC 的九个地址字符串（含前置校验、登录及队列里编译器内联的地址）；使用原始字符串池字节切片，避免重序列化改变编译器编码。最终 SWF 回读后反向还原九个字符串，296 个 ABC 均与输入原字节一致，96,631 个方法的指令、分支、异常表、参数和类布局均保持。R8/R9/R10、切队 F1009、商店、觉醒、登录等累计行为及正常偏好存储因此完整保留，未加入日志导出。

原生六个类只更新两处缓存 UUID；manifest 同步新 UUID。最终 APK 全成员回读通过，仅 SWF、DEX、manifest 和签名变化，ZIP 对齐与 v1/v2 签名及固定证书通过。成品 BuildConfig 的真实 ID/KEY 与公网和现有双端私有配对文件一致；构建器不生成或复制密钥，不写生成版 BuildConfig 源码。

本轮只做地址转换和离线校验，未覆盖安装或启动模拟器，未执行手机实战。21:59 核对本地 8001 服务：准入 challenge 路由返回 404，运行镜像尚无准入模块。必须先同步已完成的准入实现、允许配置及原私有配对才能登录此包；没有自动关闭校验或修改正在运行的服务。

配套沿用 `outputs/ios-admission-public-20260915/server-files/` 的七个双端文件及独立 `outputs/ios-admission-release-private-20260915/config/client-admission.keys.json`；此次没有新的配置条目或密钥变化。部署与配置合并要求见原公网交付说明，不能用空模板覆盖已有允许列表，也不能将私有配对文件加入 Git 或普通云服 ZIP。

没有数据库、存档内容 ID、账号归属或 V1/V2 导入导出结构变化，未操作真实账号或存档。未提升 accepted registry，未修改 IPA、公网 APK 或原发布批次记录。分支 `staging` / `origin/staging`，本轮未提交、推送、同步运行镜像或生成云服整合 ZIP；保留原有未提交文件。

复现命令在 PowerShell 中从本机忽略配置取地址：

```powershell
$taskLan = Get-Content -LiteralPath outputs/android-build-local.json -Raw | ConvertFrom-Json
python -B -X utf8 client-patch/r10-public-release/build_lan.py --work F:/codex/work/r10-admission-lan-rebuild --out outputs/r10-admission-lan-rebuild --name StarPoint-CN-1.8.1-r10-admission-lan.apk --origin ('http://' + $taskLan.lan_host) --keys outputs/ios-admission-release-private-20260915/config/client-admission.keys.json
```

复现会分配新的 AIR UUID，因此重签后的 APK 哈希随构建而变；正式准入号与密钥保持不变。
