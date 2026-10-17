# Android PR43 适配与独立封包

本目录保存 Android 方法移植、Lv120 超限、旧服材料兼容、ARM64/x86_64 封包及准入轮换的源码。需要 Python 3.11 及以上，依赖仅为标准库和本目录 `support/`，不依赖尚未合入的补丁档案。来源和许可见 [support/SOURCES.md](support/SOURCES.md)。

这是固定输入的补丁配方，不是完整客户端重编工程。输入身份由 `game-plan.json`、`bundle-plan.json` 和各阶段报告约束；后续换基线需重新审查这些契约，不能删除哈希检查。默认开发基线仍由上一级 `android-accepted.json` 选择，本目录不会修改验收登记。

## 实际变化

- 保留当前累计功能，只移植最终采用的 37 个主方法、ShopFirstOpen 和两个新增加载 helper；保留角色 Cell 生命周期。R4 的 #102–107、#62 离屏更新 guard 和 #52 身份常量不进入本配方。
- 12 个超限方法配合四个内置 bundle 资源，支持专门配置的五星角色扩展至 120 级。普通角色继续使用原材料；支持扩展且普通突破完成后切换新材料。缺少新材料 master 定义时只回退展示，确认保持禁用；库存为零与定义缺失分别处理。
- x86 只补 15 个原生库、13 个 ANE 平台及其资源；既有 ARM64、游戏 SWF、DEX 和 bundle 保留。JNI 导出和资源等价不代表桩库语义完整或设备性能提升。
- 准入轮换同时修改 ClientAdmission 的折叠常量和 BuildConfig；新 ID、HMAC 前缀、key 必须匹配外部完整私有 config。报告不含 key。

## 私有输入和输出

需要合法持有的基线 APK、v33-x86 捐赠 APK、平台签名材料，以及需要轮换时的完整准入配对。二进制、SWF/ABC、私有 config、签名凭据和生成报告都放在仓库外，不随源码提交。

`prepare_inputs.py` 锁定基线 APK SHA-256 `4f62b899a89b0648f79d0dbaf20d8aab9b64ad91959d91706dc71af02cb6c335`、捐赠 APK `572dd17256de6708b9cdcbe752e184a97b44781bce8fd5ffacf7be7413e0c331`。只提取两份 SWF、四个 bundle 资源及 1966 个 x86/ANE 输入，不物化完整客户端资源库。输出目录必须是新的仓库外目录。

以下命令从本目录执行。`$clientWork` 是仓库外任务目录，`$baseApk`、`$donorApk` 为上述 APK，`$lanHost` 是输入包实际使用的裸主机，`$publicOrigin` 为目标 `http://<HOST>:8001`。主机及本机路径通过命令参数传入。每个不同 SWF 必须使用不同的 AIR UUID；选择以数字开头的 UUID 后，仍由 DEX 排序检查决定能否使用。

```powershell
python -B prepare_inputs.py --base-apk $baseApk --donor-apk $donorApk --output-dir "$clientWork/inputs"
python -B port_game.py --source "$clientWork/inputs/source.swf" --donor "$clientWork/inputs/donor.swf" --output "$clientWork/game.swf" --report "$clientWork/game.json"
python -B package_android.py --base $baseApk --base-sha256 $baseSha --final-swf "$clientWork/game.swf" --swf-sha256 $gameSha --bundle-targets "$clientWork/inputs/bundle-targets.json" --old-uuid $baseUuid --new-uuid $gameUuid --output-dir "$clientWork/game" --output-root $clientWork
python -B x86_port.py --base "$clientWork/game/game.unsigned.apk" --base-sha256 $gameApkSha --inputs "$clientWork/inputs/x86-native-ane" --inputs-sha256 4dda31632d1f0294556d21cb24fc243c7abc9d8e4af5caf7ff09df91ae10c8e6 --output "$clientWork/x86/game.unsigned.apk" --output-root "$clientWork/x86"
```

`$baseSha/$baseUuid` 来自匹配输入的基线核验，`$gameSha` 来自 `game.json`，`$gameApkSha` 来自 `game/package-report.json`，不可用未知文件现算出的哈希代替来源核验。兼容阶段可接同 SWF 的已核验双架构载体；两阶段必须使用相同参数，`$carrierSha/$carrierUuid` 来自该载体的报告。

```powershell
python -B build_compat_android.py --stage swf --base-apk $carrierApk --base-sha256 $carrierSha --old-uuid $carrierUuid --work-dir "$clientWork/compat" --lan-host $lanHost --public-origin $publicOrigin
python -B build_compat_android.py --stage package --base-apk $carrierApk --base-sha256 $carrierSha --old-uuid $carrierUuid --work-dir "$clientWork/compat" --lan-host $lanHost --public-origin $publicOrigin
```

兼容阶段固定功能 SWF，只修正两处材料筛选及九个地址字符串，更新 Manifest/DEX 的 AIR 缓存身份，保留其余内容。输出仍未签名。需要准入新配对时，从已核验的当前公网兼容 SWF 继续（轮换工具会拒绝其他输入）。`$pairDir` 是含两个 `config/client-admission*.json` 文件的完整私有配对根，`$buildId` 为其中启用的新 Android 编号；工具不生成或部署配置。

```powershell
python -B rotate_admission.py --input-swf "$clientWork/compat/android-game.swf" --pair-dir $pairDir --build-id $buildId --output-swf "$clientWork/admission.swf" --report "$clientWork/admission.json"
python -B package_android.py --base "$clientWork/compat/android.unsigned.apk" --base-sha256 $compatApkSha --final-swf "$clientWork/admission.swf" --swf-sha256 $admissionSwfSha --swf-only --old-uuid $compatUuid --new-uuid $admissionUuid --output-dir "$clientWork/admission-package" --output-root $clientWork
```

最后在私有环境使用 Android `zipalign`、原平台证书和 `apksigner` 对齐、签名，再核对最终文件的 SWF/准入、新 UUID、包名版本、V1/V2 签名、证书指纹、CRC 和对齐。本目录不会安装设备、改变存档、启动服务、发布 APK 或提升 accepted。更新准入配置需交付完整配对，先 keys 后允许列表；具体部署单独执行。

## 验证入口

```powershell
python -B -m unittest -v test_port_game test_package_android test_x86_port test_prepare_inputs test_build_compat_android
python -B test_overlimit_port.py --apk $baseApk --support-dir ./support --report "$clientWork/overlimit-check.json"
python -B test_old_server_compat.py --swf $functionalSwf --support-dir ./support --report "$clientWork/compat-check.json"
python -B test_rotate_admission.py --input-swf $publicCompatSwf -v
```

前一组不需要私有客户端；后面三组必须提供匹配真实输入。AIR/AVM2 窗口执行、设备运行、GPU、模拟器和公网游戏验收分别记录，不能由受控指令夹具或封包检查推定。
